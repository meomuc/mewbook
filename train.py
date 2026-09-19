"""Huấn luyện mô hình phân loại thông minh của Mèo Mực (MewBook).

Chạy file này định kỳ, mỗi khi bạn có thêm sách đã gắn nhãn, để nâng độ chính
xác của mô hình. Ứng dụng chính KHÔNG bao giờ chạy huấn luyện và cũng không nạp
mã huấn luyện lúc khởi động -- nó chỉ đọc file mô hình mà script này tạo ra.

    uv run python train.py                      # học từ thư viện của bạn
    uv run python train.py --self-train 1       # thêm 1 vòng tự học từ sách chưa gắn nhãn
    uv run python train.py --dataset D:\\mau     # thêm bộ mẫu: mỗi thể loại một thư mục
    uv run python train.py --output builtin     # ghi làm mô hình đi kèm ứng dụng

Nhãn học được lấy từ đâu (theo thứ tự ưu tiên):
  1. Hashtag đã gắn trên sách khớp một thể loại (hoặc bí danh của nó).
  2. Nhãn "subject" có sẵn trong chính file (EPUB dc:subject, PDF keywords).
  3. Thư mục chứa sách, với --dataset DIR (DIR/<thể loại>/...).
Nhãn do chính bộ phân loại tự gắn không được coi là đáp án thật.

Thêm thể loại mới: sửa/tạo taxonomy.json trong thư mục dữ liệu ứng dụng
(%APPDATA%\\SmartDocLibrary), rồi chạy lại script này.

Mô hình mặc định được ghi vào %APPDATA%\\SmartDocLibrary\\models\\ và ứng dụng
tự dùng nó thay cho mô hình đi kèm.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import sqlite3
import sys
import time
from pathlib import Path

try:
    import smartdoc  # noqa: F401  (installed, e.g. `uv run`)
except ImportError:  # run straight from a checkout: `python train.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from smartdoc.application import classification_trainer as trainer  # noqa: E402
from smartdoc.core.config import default_app_data_dir  # noqa: E402
from smartdoc.domain.taxonomy import Taxonomy  # noqa: E402
from smartdoc.domain.text_classifier import BUILTIN_MODEL_PATH, DEFAULT_FEATURE_WEIGHTS, USER_MODEL_RELATIVE_PATH  # noqa: E402
from smartdoc.infrastructure.text_sampler import DEFAULT_MAX_WORDS, clamp_word_budget  # noqa: E402
from smartdoc.infrastructure.vi_tokenizer import TextProcessor  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Huấn luyện mô hình phân loại thông minh.", formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog="Xem đầu file train.py để biết cách nhãn được lấy và cách thêm thể loại.")
    p.add_argument("--library-db", type=Path, help="đường dẫn library.db (mặc định: thư viện của ứng dụng)")
    p.add_argument("--no-library", action="store_true", help="không học từ thư viện, chỉ dùng --dataset")
    p.add_argument("--dataset", type=Path, action="append", default=[], metavar="DIR", help="thư mục mẫu: DIR/<thể loại>/*.epub|pdf|mobi (có thể lặp lại)")
    p.add_argument("--app-data", type=Path, default=None, help="thư mục dữ liệu ứng dụng (mặc định %%APPDATA%%\\SmartDocLibrary)")
    p.add_argument("--output", default=None, help="file mô hình xuất ra; 'builtin' = ghi đè mô hình đi kèm ứng dụng")
    p.add_argument("--workers", type=int, default=max(1, min(8, (os.cpu_count() or 2) - 2)), help="số tiến trình đọc sách song song")
    p.add_argument("--max-words", type=int, default=DEFAULT_MAX_WORDS, help="số từ đầu mỗi sách được đọc (2000-5000)")
    p.add_argument("--limit", type=int, default=0, help="chỉ dùng tối đa N sách của thư viện (thử nhanh)")
    p.add_argument("--holdout", type=float, default=0.2, help="tỉ lệ sách giữ lại để đánh giá (mặc định 0.2)")
    p.add_argument("--target-precision", type=float, default=0.85, help="độ chính xác mục tiêu khi mô hình quyết định gắn nhãn")
    p.add_argument("--top-features", type=int, default=2500, help="số đặc trưng giữ lại cho mỗi thể loại")
    p.add_argument("--seed-strength", type=float, default=2.0, help="sức nặng của từ khóa khởi tạo trong taxonomy.json")
    p.add_argument("--max-per-class", type=int, default=2000, help="tối đa số sách dùng cho mỗi thể loại")
    p.add_argument("--self-train", type=int, default=0, metavar="N", help="số vòng tự học từ sách chưa có nhãn")
    p.add_argument("--report", type=Path, default=None, help="file ghi báo cáo (mặc định cạnh file mô hình)")
    p.add_argument("--dry-run", action="store_true", help="huấn luyện và báo cáo nhưng không ghi mô hình")
    return p.parse_args(argv)


def default_library_db(app_data: Path) -> Path:
    settings = app_data / "settings.json"
    if settings.is_file():
        try:
            configured = json.loads(settings.read_text(encoding="utf-8")).get("db_path")
            if configured:
                return Path(configured)
        except (OSError, ValueError):
            pass
    return app_data / "library.db"


def library_jobs(db_path: Path, taxonomy: Taxonomy, limit: int) -> tuple[list[dict], dict]:
    """One extraction job per library book whose file still exists."""
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        # Books the classifier tagged itself: their tag is not ground truth.
        auto_tagged: set[str] = set()
        try:
            auto_tagged = {r[0] for r in connection.execute("SELECT doc_id FROM smart_classification WHERE applied_tag IS NOT NULL")}
        except sqlite3.OperationalError:
            pass  # table not created yet: the smart classifier has never run
        rows = connection.execute("SELECT id, title, author, tags, file_path, extension FROM documents ORDER BY id").fetchall()
    finally:
        connection.close()

    jobs: list[dict] = []
    missing = 0
    for row in rows:
        path = row["file_path"]
        if not path or not os.path.exists(path):
            missing += 1
            continue
        raw_tags = row["tags"] or ""
        job = {
            "id": row["id"], "title": row["title"] or "", "author": row["author"] or "",
            "tags": trainer.non_category_tags(taxonomy, raw_tags), "raw_tags": "" if row["id"] in auto_tagged else raw_tags,
            "path": path, "extension": (row["extension"] or Path(path).suffix.lstrip(".")).lower(),
        }
        jobs.append(job)
    if limit and len(jobs) > limit:
        import random

        random.Random(5).shuffle(jobs)
        jobs = jobs[:limit]
    return jobs, {"library_books": len(rows), "missing_files": missing, "auto_tagged_ignored": len(auto_tagged)}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    app_data = args.app_data or default_app_data_dir()
    max_words = clamp_word_budget(args.max_words)
    taxonomy = Taxonomy.load(app_data)
    print(f"Thể loại: {len(taxonomy)} thể loại trong {len(taxonomy.groups())} nhóm (taxonomy {taxonomy.fingerprint()})")

    jobs: list[dict] = []
    if not args.no_library:
        db_path = args.library_db or default_library_db(app_data)
        if not db_path.is_file():
            print(f"Không tìm thấy thư viện: {db_path}", file=sys.stderr)
            return 2
        library, info = library_jobs(db_path, taxonomy, args.limit)
        print(f"Thư viện {db_path.name}: {info['library_books']} sách, {len(library)} file còn tồn tại, "
              f"{info['auto_tagged_ignored']} sách do máy tự gắn nhãn (không dùng làm đáp án)")
        jobs.extend(library)
    for root in args.dataset:
        dataset_jobs, warnings = trainer.collect_dataset_folder(root, taxonomy)
        for warning in warnings:
            print("  !", warning)
        print(f"Bộ mẫu {root}: {len(dataset_jobs)} sách")
        jobs.extend(dataset_jobs)
    if not jobs:
        print("Không có sách nào để học.", file=sys.stderr)
        return 2

    processor = TextProcessor()
    interner = trainer.Interner()
    started = time.perf_counter()

    def progress(done: int, total: int) -> None:
        rate = done / max(time.perf_counter() - started, 1e-6)
        print(f"\r  đọc sách {done}/{total}  ({rate:.0f} sách/giây)", end="", flush=True)

    print(f"Đang đọc {len(jobs)} sách bằng {args.workers} tiến trình (mỗi sách {max_words} từ đầu)...")
    extracted = trainer.extract_jobs(jobs, workers=args.workers, max_words=max_words, weights=DEFAULT_FEATURE_WEIGHTS, progress=progress)
    labelled, unlabelled, stats = trainer.docs_from_extraction(extracted, taxonomy, interner)
    print(f"\r  xong trong {time.perf_counter() - started:.0f} giây" + " " * 30)
    print(f"Nhãn: {dict(stats)}")
    if not labelled:
        print("Chưa có sách nào có nhãn khớp thể loại -- mô hình sẽ chỉ dựa vào từ khóa trong taxonomy.json.")

    options = trainer.TrainOptions(
        seed_strength=args.seed_strength, top_features=args.top_features, holdout_fraction=args.holdout,
        target_precision=args.target_precision, max_per_class=args.max_per_class, self_train_rounds=args.self_train,
        max_words=max_words,
    )
    result = trainer.train(labelled, taxonomy, interner, processor, options, unlabelled=unlabelled, log=print)
    report = result.to_text(taxonomy)
    print()
    print(report)

    if args.dry_run:
        print("\n(--dry-run: không ghi mô hình)")
        return 0
    if args.output == "builtin":
        output = BUILTIN_MODEL_PATH
    else:
        output = Path(args.output) if args.output else app_data / USER_MODEL_RELATIVE_PATH
    result.model.save(output)
    report_path = args.report or output.with_name("classifier_report.txt")
    report_path.write_text(report + "\n", encoding="utf-8")
    print(f"\nĐã ghi mô hình: {output} ({output.stat().st_size / 1024:.0f} KB)\nBáo cáo: {report_path}")
    print("Khởi động lại ứng dụng nếu đang mở để dùng mô hình mới.")
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()  # needed for the worker pool on Windows
    sys.exit(main())
