from smartdoc.presentation.file_actions import FileActionEngine


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
