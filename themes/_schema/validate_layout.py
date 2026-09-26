#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kiểm tra gói kiểu giao diện MewBook (layout.json) và mọi tổ hợp kiểu × theme.

Cách dùng:
    python validate_layout.py <thư mục gói | file .zip | layout.json> --themes <thư mục themes>

Với mỗi theme dùng được ở kiểu này (liệt kê trong layout.json hoặc tự khai báo
layouts.<id> trong theme.json): gộp màu gốc ← màu chỉnh của gói kiểu ← màu chỉnh
của chính theme, rồi chạy đủ bộ kiểm tra của validate_theme.py trên nền nội dung
`content_surface` của kiểu. Mã thoát: 0 đạt, 1 có lỗi, 2 không đọc được.
"""
import copy, json, os, re, sys, tempfile, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate_theme import check, TOKENS, OPTIONAL_TOKENS, HEX, RGBA, RGBA_KEYS

ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

def load(path):
    if os.path.isfile(path) and path.lower().endswith(".zip"):
        tmp = tempfile.mkdtemp(prefix="mewlayout_")
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if n.startswith("/") or ".." in n.split("/"): raise ValueError(f"Đường dẫn không an toàn: {n}")
            z.extractall(tmp)
        c = [os.path.join(d, "layout.json") for d, _, fs in os.walk(tmp) if "layout.json" in fs]
        if len(c) != 1: raise ValueError("Gói phải có đúng một layout.json")
        return json.load(open(c[0], encoding="utf-8")), os.path.dirname(c[0])
    if os.path.isdir(path):
        return json.load(open(os.path.join(path, "layout.json"), encoding="utf-8")), path
    return json.load(open(path, encoding="utf-8")), os.path.dirname(os.path.abspath(path))

def main(argv):
    if not argv: print(__doc__); return 2
    themes_dir = "themes"
    if "--themes" in argv:
        i = argv.index("--themes"); themes_dir = argv[i+1]; argv = argv[:i] + argv[i+2:]
    try: L, root = load(argv[0])
    except Exception as ex: print("KHÔNG ĐỌC ĐƯỢC GÓI:", ex); return 2
    E, W = [], []
    for k in ["schema_version","id","name","description","version","content_surface","metrics","ornaments","default_theme","themes"]:
        if k not in L: E.append(f"Thiếu trường bắt buộc: {k}")
    if E:
        for e in E: print("  LỖI:", e)
        return 1
    if not ID.match(L["id"]): E.append("id sai định dạng")
    if L["content_surface"] not in ("bg", "panel"): E.append("content_surface phải là bg hoặc panel")
    if L["default_theme"] not in L["themes"]: E.append("default_theme phải nằm trong danh sách themes")
    for tid, tv in L["themes"].items():
        for k, v in (tv.get("tokens") or {}).items():
            if k not in TOKENS + OPTIONAL_TOKENS: E.append(f"themes.{tid}: token lạ {k}")
            elif not (RGBA if k in RGBA_KEYS else HEX).match(v): E.append(f"themes.{tid}.{k} = '{v}' sai định dạng")
    for p in L.get("preview", []):
        if not os.path.isfile(os.path.join(root, p)): W.append(f"Thiếu ảnh xem trước {p}")

    # gom theme dùng được
    installed = {}
    if os.path.isdir(themes_dir):
        for d in os.listdir(themes_dir):
            f = os.path.join(themes_dir, d, "theme.json")
            if os.path.isfile(f): installed[d] = (json.load(open(f, encoding="utf-8")), os.path.dirname(f))
    else:
        W.append(f"Không thấy thư mục themes '{themes_dir}' — chỉ kiểm tra được layout.json")
    ids = set(L["themes"]) | {tid for tid, (t, _) in installed.items() if L["id"] in (t.get("layouts") or {}) and t["layouts"][L["id"]].get("supported", True)}
    print(f"Kiểu giao diện: {L['name']} ({L['id']}) — nền nội dung: {L['content_surface']}")
    for tid in sorted(ids):
        if tid not in installed:
            W.append(f"Theme '{tid}' có trong danh sách nhưng chưa cài — sẽ tự bật khi theme được nhập"); continue
        t, troot = installed[tid]
        m = copy.deepcopy(t)
        m["tokens"].update((L["themes"].get(tid) or {}).get("tokens") or {})
        m["tokens"].update(((t.get("layouts") or {}).get(L["id"]) or {}).get("tokens") or {})
        te, tw = check(m, troot, content_bg=L["content_surface"])
        tag = "ĐẠT" if not te else f"KHÔNG ĐẠT ({len(te)} lỗi)"
        print(f"  • {t['name']} × {L['name']}: {tag}")
        E += [f"{t['name']}: {x}" for x in te]; W += [f"{t['name']}: {x}" for x in tw if "ảnh xem trước" not in x]
    for w in W: print("  CẢNH BÁO:", w)
    for e in E: print("  LỖI:", e)
    print("KẾT QUẢ:", "ĐẠT" if not E else f"KHÔNG ĐẠT — {len(E)} lỗi")
    return 0 if not E else 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
