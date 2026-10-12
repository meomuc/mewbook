from smartdoc.presentation.file_actions import FileActionEngine


def test_send_to_ereader_copies_files_into_target_folder(tmp_path, app_context):
    source_a = tmp_path / "source" / "book_a.pdf"
    source_a.parent.mkdir()
    source_a.write_bytes(b"content a")
    source_b = tmp_path / "source" / "book_b.epub"
    source_b.write_bytes(b"content b")
    target_dir = tmp_path / "ereader"
    target_dir.mkdir()
    engine = FileActionEngine(app_context)

    succeeded, failed = engine.send_to_ereader([str(source_a), str(source_b)], str(target_dir))

    assert succeeded == [str(source_a), str(source_b)]
    assert failed == []
    assert (target_dir / "book_a.pdf").read_bytes() == b"content a"
    assert (target_dir / "book_b.epub").read_bytes() == b"content b"
    # Source files are untouched -- this is a copy, not a move.
    assert source_a.exists()
    assert source_b.exists()


def test_send_to_ereader_reports_failures_without_raising(tmp_path, app_context):
    missing_source = tmp_path / "does_not_exist.pdf"
    target_dir = tmp_path / "ereader"
    target_dir.mkdir()
    engine = FileActionEngine(app_context)

    succeeded, failed = engine.send_to_ereader([str(missing_source)], str(target_dir))

    assert succeeded == []
    assert failed == [str(missing_source)]


def test_copy_to_ereader_as_uses_the_given_name(tmp_path, app_context):
    source = tmp_path / "book.pdf"
    source.write_bytes(b"content")
    target_dir = tmp_path / "ereader"
    target_dir.mkdir()
    engine = FileActionEngine(app_context)

    reason = engine.copy_to_ereader_as(str(source), str(target_dir), "Author - Title.pdf")

    assert reason == ""
    assert (target_dir / "Author - Title.pdf").read_bytes() == b"content"


def test_copy_to_ereader_as_never_overwrites_an_existing_file(tmp_path, app_context):
    source = tmp_path / "book.pdf"
    source.write_bytes(b"new content")
    target_dir = tmp_path / "ereader"
    target_dir.mkdir()
    existing = target_dir / "Author - Title.pdf"
    existing.write_bytes(b"original content, must survive")
    engine = FileActionEngine(app_context)

    reason = engine.copy_to_ereader_as(str(source), str(target_dir), "Author - Title.pdf")

    assert reason != ""
    assert existing.read_bytes() == b"original content, must survive"


def test_copy_to_ereader_as_reports_a_missing_device_folder_distinctly(tmp_path, app_context):
    source = tmp_path / "book.pdf"
    source.write_bytes(b"content")
    engine = FileActionEngine(app_context)

    reason = engine.copy_to_ereader_as(str(source), str(tmp_path / "not-plugged-in"), "Author - Title.pdf")

    assert "rút ra" in reason


def test_open_file_never_uses_shell_true(monkeypatch, app_context, tmp_path):
    import sys

    calls = []
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        "subprocess.run", lambda args, **kwargs: calls.append((args, kwargs)) or type("R", (), {"returncode": 0})()
    )

    engine = FileActionEngine(app_context)
    weird_path = str(tmp_path / "a.pdf; rm -rf ~")
    engine.open_file(weird_path)

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert isinstance(args, list)  # argument *list*, not a shell string
    assert weird_path in args
    assert kwargs.get("shell") is not True
