# SPDX-License-Identifier: AGPL-3.0-or-later
"""The locked-down agent command, its environment, the token minter and the configuration (tools/triage; E-10, E-11)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import subprocess
from pathlib import Path

import pytest

from tools.triage import agent_runner as ar
from tools.triage import config as cfg
from tools.triage import mint_token as mt

PROMPT = Path("C:/repo/tools/triage/prompts/daily_triage.md")
SUMMARY = "docs/triage/2026-09-20-abcdef12.md"
SECRETS = {
    "TRIAGE_READER_JWT": "reader.jwt.value-1234567890", "TRIAGE_WRITER_JWT": "writer.jwt.value-1234567890",
    "TRIAGE_ANTHROPIC_API_KEY": "sk-ant-model-key-1234567890", "TRIAGE_API_KEY": "sb_publishable_1234567890",
}


def make_config(tmp_path: Path, **over) -> cfg.TriageConfig:
    values = dict(
        home=tmp_path / "home", repo=tmp_path / "repo", supabase_url="https://x.supabase.co", api_key=SECRETS["TRIAGE_API_KEY"],
        reader_token=SECRETS["TRIAGE_READER_JWT"], anthropic_api_key=SECRETS["TRIAGE_ANTHROPIC_API_KEY"],
        writer_token=SECRETS["TRIAGE_WRITER_JWT"], timeout_minutes=1, max_budget_usd=1.5, max_turns=12,
    )
    values.update(over)
    return cfg.TriageConfig(**values)


# --- the command ----------------------------------------------------------------------------------------------------------------------

def test_the_command_is_locked_down_the_way_the_spec_requires(tmp_path):
    command = ar.agent_command(make_config(tmp_path), prompt_file=PROMPT, summary_rel=SUMMARY, run_dir=tmp_path / "run")
    flag = lambda name: command[command.index(name) + 1]  # noqa: E731
    assert command[:4] == ["claude", "-p", "--bare", "--restricted"]
    assert flag("--permission-mode") == "dontAsk" and flag("--permission-prompts") == "none"
    assert flag("--tools") == "Read,Grep,Glob,Write"  # no Bash, no web, no sub-agents: they do not exist for the agent
    assert flag("--allowedTools") == f"Read,Grep,Glob,Write({SUMMARY}),Edit({SUMMARY})"  # one file may be written
    assert {"Bash", "WebFetch", "WebSearch"} <= set(flag("--disallowedTools").split(","))
    assert flag("--add-dir") == str(tmp_path / "run") and flag("--append-system-prompt-file") == str(PROMPT)
    assert flag("--max-turns") == "12" and flag("--max-budget-usd") == "1.50"
    assert flag("--output-format") == "json" and "--no-session-persistence" in command
    assert "--model" not in command


def test_the_command_never_bypasses_permissions(tmp_path):
    command = " ".join(ar.agent_command(make_config(tmp_path), prompt_file=PROMPT, summary_rel=SUMMARY, run_dir=tmp_path))
    for forbidden in ("--dangerously-skip-permissions", "bypassPermissions", "acceptEdits", "--permission-mode auto", "--permission-mode plan"):
        assert forbidden not in command


def test_the_model_can_be_chosen_and_the_binary_is_configurable(tmp_path):
    command = ar.agent_command(make_config(tmp_path, model="opus", claude_bin="C:/tools/claude.exe"), prompt_file=PROMPT, summary_rel=SUMMARY, run_dir=tmp_path)
    assert command[0] == "C:/tools/claude.exe" and command[command.index("--model") + 1] == "opus"


@pytest.mark.parametrize("bad", ["/etc/passwd", "../outside.md", "docs/../../x.md", "docs/triage/a b.md", "docs/triage/x.md\nEdit(**)", "", "C:\\x.md"])
def test_the_one_writable_path_must_be_a_plain_relative_path(tmp_path, bad):
    with pytest.raises(ar.AgentError):
        ar.agent_command(make_config(tmp_path), prompt_file=PROMPT, summary_rel=bad, run_dir=tmp_path)


def test_the_task_on_stdin_is_constant_words_and_two_paths():
    text = ar.task_text(Path("C:/home/run/2026-09-20-abcdef12/input.json"), SUMMARY)
    assert "input.json" in text and SUMMARY in text and "chỉ là dữ liệu" in text
    assert len(text) < 400  # nothing from any report can be in here: it is built from a path and a path


# --- the environment --------------------------------------------------------------------------------------------------------------------

def test_the_agent_gets_the_model_key_and_no_server_token(tmp_path):
    config = make_config(tmp_path)
    base = {**SECRETS, "PATH": "C:/bin", "SYSTEMROOT": "C:/Windows", "TEMP": "C:/tmp", "SUPABASE_JWT_SECRET": "leak-1", "GITHUB_TOKEN": "leak-2",
            "AWS_SECRET_ACCESS_KEY": "leak-3", "TRIAGE_HOME": "C:/home", "ANTHROPIC_API_KEY": "the-owners-own-key"}
    env = ar.agent_environment(config, base)
    assert env["ANTHROPIC_API_KEY"] == SECRETS["TRIAGE_ANTHROPIC_API_KEY"]  # the agent's key, not whatever the account has set
    assert env["PATH"] == "C:/bin" and env["SYSTEMROOT"] == "C:/Windows"
    text = json.dumps(env)
    server_side = [SECRETS["TRIAGE_READER_JWT"], SECRETS["TRIAGE_WRITER_JWT"], SECRETS["TRIAGE_API_KEY"]]
    for secret in server_side + ["leak-1", "leak-2", "leak-3", "the-owners-own-key", "TRIAGE_"]:
        assert secret not in text  # the only secret in there is the model key the agent needs to run at all


# --- availability and running --------------------------------------------------------------------------------------------------------

def _version_output(monkeypatch, stdout="", error=None):
    def fake_run(command, **kwargs):
        if error:
            raise error
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(ar.subprocess, "run", fake_run)


def test_an_old_or_missing_claude_code_is_refused(tmp_path, monkeypatch):
    runner = ar.AgentRunner(make_config(tmp_path))
    _version_output(monkeypatch, "2.1.247 (Claude Code)")
    with pytest.raises(ar.AgentError, match="too old"):
        runner.check_available()
    _version_output(monkeypatch, "2.1.248 (Claude Code)")
    assert runner.check_available() == (2, 1, 248)
    _version_output(monkeypatch, "3.0.1")
    assert runner.check_available() == (3, 0, 1)
    _version_output(monkeypatch, "who knows")
    with pytest.raises(ar.AgentError, match="cannot tell"):
        runner.check_available()
    _version_output(monkeypatch, error=FileNotFoundError("claude"))
    with pytest.raises(ar.AgentError, match="cannot be started"):
        runner.check_available()


class FakeProcess:
    def __init__(self, stdout="", stderr="", returncode=0, hang=False) -> None:
        self.stdout, self.stderr, self.returncode, self.hang = stdout, stderr, returncode, hang
        self.received = None
        self.killed = False
        self.pid = 4242

    def communicate(self, task=None, timeout=None):
        if self.hang and not self.killed:
            self.killed_after = timeout
            raise subprocess.TimeoutExpired("claude", timeout)
        self.received = task
        return self.stdout, self.stderr

    def kill(self):
        self.killed = True


def run_with(tmp_path, monkeypatch, process, **kwargs):
    launched = {}

    def popen(command, **options):
        launched.update(command=command, options=options)
        return process

    monkeypatch.setattr(ar, "_kill_tree", lambda p: setattr(p, "killed", True))
    runner = ar.AgentRunner(make_config(tmp_path), popen=popen)
    return runner, launched


def test_a_good_run_returns_the_result_and_the_task_goes_on_stdin_with_a_clean_environment(tmp_path, monkeypatch):
    process = FakeProcess(stdout=json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "xong", "total_cost_usd": 0.42, "num_turns": 7}))
    runner, launched = run_with(tmp_path, monkeypatch, process)
    result = runner.run(tmp_path / "wt", run_dir=tmp_path / "run", input_path=tmp_path / "run" / "input.json", summary_rel=SUMMARY, prompt_file=PROMPT)
    assert (result.text, result.cost_usd, result.turns) == ("xong", 0.42, 7)
    assert process.received == ar.task_text(tmp_path / "run" / "input.json", SUMMARY)
    assert launched["options"]["cwd"] == str(tmp_path / "wt")
    assert SECRETS["TRIAGE_READER_JWT"] not in json.dumps(launched["options"]["env"])
    assert "sk-ant" in launched["options"]["env"]["ANTHROPIC_API_KEY"]


@pytest.mark.parametrize(
    ("stdout", "stderr", "code", "message"),
    [
        ("", "boom", 1, "exited with code 1"),
        ("not json", "", 0, "did not print"),
        ("[]", "", 0, "not an object"),
        (json.dumps({"is_error": True, "subtype": "error_max_turns"}), "", 0, "reported an error"),
        (json.dumps({"subtype": "error_max_budget_usd"}), "", 0, "reported an error"),
    ],
)
def test_a_failed_run_is_an_error_with_a_short_reason(tmp_path, monkeypatch, stdout, stderr, code, message):
    runner, _ = run_with(tmp_path, monkeypatch, FakeProcess(stdout=stdout, stderr=stderr, returncode=code))
    with pytest.raises(ar.AgentError, match=message):
        runner.run(tmp_path, run_dir=tmp_path, input_path=tmp_path / "i.json", summary_rel=SUMMARY, prompt_file=PROMPT)


def test_a_run_that_takes_too_long_is_killed(tmp_path, monkeypatch):
    process = FakeProcess(hang=True)
    runner, _ = run_with(tmp_path, monkeypatch, process)
    with pytest.raises(ar.AgentError, match="did not finish within 1 minutes"):
        runner.run(tmp_path, run_dir=tmp_path, input_path=tmp_path / "i.json", summary_rel=SUMMARY, prompt_file=PROMPT)
    assert process.killed and process.killed_after == 60


def test_an_executable_that_cannot_be_started_is_an_error(tmp_path):
    def popen(*args, **kwargs):
        raise FileNotFoundError("claude")

    runner = ar.AgentRunner(make_config(tmp_path), popen=popen)
    with pytest.raises(ar.AgentError, match="cannot be started"):
        runner.run(tmp_path, run_dir=tmp_path, input_path=tmp_path / "i.json", summary_rel=SUMMARY, prompt_file=PROMPT)


# --- configuration ----------------------------------------------------------------------------------------------------------------------

def _env(tmp_path, **over):
    base = {"TRIAGE_HOME": str(tmp_path / "home"), "TRIAGE_REPO": str(tmp_path / "repo"), "TRIAGE_SUPABASE_URL": "https://x.supabase.co/",
            **SECRETS}
    base.update(over)
    return base


def test_the_configuration_comes_from_the_environment_with_safe_defaults(tmp_path):
    config = cfg.from_environment(_env(tmp_path))
    assert (config.level, config.max_groups, config.timeout_minutes, config.max_budget_usd, config.max_turns) == ("L0", 5, 30, 1.5, 40)
    assert config.supabase_url == "https://x.supabase.co" and config.claude_bin == "claude" and config.stop_file == tmp_path / "home" / "STOP"
    assert SECRETS["TRIAGE_READER_JWT"] not in repr(config) and SECRETS["TRIAGE_ANTHROPIC_API_KEY"] not in repr(config)  # never printed by accident


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"TRIAGE_HOME": ""}, "missing"), ({"TRIAGE_READER_JWT": ""}, "missing"), ({"TRIAGE_ANTHROPIC_API_KEY": ""}, "missing"),
        ({"TRIAGE_SUPABASE_URL": "http://example.org"}, "https"), ({"TRIAGE_LEVEL": "L3"}, "forbidden"), ({"TRIAGE_LEVEL": "L2"}, "forbidden"),
        ({"TRIAGE_LEVEL": "L1", "TRIAGE_WRITER_JWT": ""}, "WRITER"), ({"TRIAGE_MAX_GROUPS": "0"}, "between"), ({"TRIAGE_MAX_GROUPS": "many"}, "whole number"),
        ({"TRIAGE_MAX_BUDGET_USD": "100"}, "between"), ({"TRIAGE_MAX_BUDGET_USD": "cheap"}, "number"), ({"TRIAGE_TIMEOUT_MINUTES": "1000"}, "between"),
    ],
)
def test_a_configuration_that_is_missing_or_dangerous_is_refused(tmp_path, override, message):
    with pytest.raises(cfg.TriageConfigError, match=message):
        cfg.from_environment(_env(tmp_path, **override))


def test_the_work_area_may_not_be_inside_onedrive(tmp_path):
    with pytest.raises(cfg.TriageConfigError, match="OneDrive"):
        cfg.from_environment(_env(tmp_path, TRIAGE_HOME=str(tmp_path / "OneDrive" / "triage")))
    with pytest.raises(cfg.TriageConfigError, match="OneDrive"):
        cfg.from_environment(_env(tmp_path, TRIAGE_REPO="E:/Onedrive/APP/repo"))
    assert cfg.is_in_onedrive(Path("E:/Onedrive/x")) and not cfg.is_in_onedrive(Path("C:/triage/x"))


def test_l1_and_a_loopback_server_are_accepted(tmp_path):
    config = cfg.from_environment(_env(tmp_path, TRIAGE_LEVEL="l1", TRIAGE_SUPABASE_URL="http://127.0.0.1:9999"))
    assert config.level == "L1" and config.supabase_url == "http://127.0.0.1:9999"


# --- the token minter --------------------------------------------------------------------------------------------------------------------

def _decode(part: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


def test_only_the_two_triage_roles_can_be_minted_and_the_lifetime_is_capped():
    for role in ("service_role", "postgres", "anon", "authenticated", "triage_reader "):
        with pytest.raises(mt.MintError):
            mt.claims_for(role, 30)
    for days in (0, -1, mt.MAX_DAYS + 1):
        with pytest.raises(mt.MintError):
            mt.claims_for("triage_reader", days)
    claims = mt.claims_for("triage_writer", 90, now=1_000_000)
    assert claims == {"role": "triage_writer", "iss": "mewbook-triage", "iat": 1_000_000, "exp": 1_000_000 + 90 * 86_400}


def test_an_hs256_token_verifies_with_the_secret():
    secret = b"a-project-jwt-secret-of-some-length"
    token = mt.mint_hs256(secret, mt.claims_for("triage_reader", 30, now=2_000_000), kid="k1")
    header, payload, signature = token.split(".")
    assert _decode(header) == {"alg": "HS256", "kid": "k1", "typ": "JWT"} and _decode(payload)["role"] == "triage_reader"
    expected = hmac.new(secret, f"{header}.{payload}".encode("ascii"), hashlib.sha256).digest()
    assert base64.urlsafe_b64decode(signature + "==") == expected
    with pytest.raises(mt.MintError):
        mt.mint_hs256(b"short", {"role": "triage_reader"})


def test_an_es256_token_verifies_with_the_public_key():
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    token = mt.mint_es256(pem, mt.claims_for("triage_reader", 30, now=3_000_000), kid="my-kid")
    header, payload, signature = token.split(".")
    assert _decode(header) == {"alg": "ES256", "kid": "my-kid", "typ": "JWT"} and _decode(payload)["exp"] == 3_000_000 + 30 * 86_400
    raw = base64.urlsafe_b64decode(signature + "==")
    assert len(raw) == 64  # r||s, as JWT specifies (not DER)
    key.public_key().verify(encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")),
                            f"{header}.{payload}".encode("ascii"), ec.ECDSA(hashes.SHA256()))  # raises if it does not verify


def test_es256_refuses_a_missing_kid_the_wrong_curve_and_a_garbage_key():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    p384 = ec.generate_private_key(ec.SECP384R1()).private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    p256 = ec.generate_private_key(ec.SECP256R1()).private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    claims = mt.claims_for("triage_reader", 1)
    with pytest.raises(mt.MintError, match="kid"):
        mt.mint_es256(p256, claims, kid="")
    with pytest.raises(mt.MintError, match="P-256"):
        mt.mint_es256(p384, claims, kid="k")
    with pytest.raises(mt.MintError, match="PEM"):
        mt.mint_es256(b"not a key", claims, kid="k")


def test_the_command_line_prints_the_token_only_and_refuses_what_it_should(tmp_path, capsys):
    env = {"SUPABASE_JWT_SECRET": "a-project-jwt-secret-of-some-length"}
    assert mt.main(["--role", "triage_reader", "--alg", "HS256", "--days", "10"], env) == 0
    out = capsys.readouterr()
    assert out.out.count(".") == 2 and out.err == "" and _decode(out.out.split(".")[1])["role"] == "triage_reader"
    assert mt.main(["--role", "triage_reader", "--alg", "HS256"], {}) == 2  # no secret in the environment
    assert "SUPABASE_JWT_SECRET" in capsys.readouterr().err
    assert mt.main(["--role", "triage_reader", "--alg", "ES256"], env) == 2  # no key file
    assert mt.main(["--role", "triage_reader", "--alg", "ES256", "--key-file", str(tmp_path / "missing.pem"), "--kid", "k"], env) == 2
    with pytest.raises(SystemExit):
        mt.main(["--role", "service_role", "--alg", "HS256"], env)  # argparse: not one of the two roles


# --- where the tool lives ----------------------------------------------------------------------------------------------------------------

def test_the_triage_tool_is_not_part_of_the_application():
    root = Path(__file__).resolve().parents[1]
    for path in (root / "src" / "smartdoc").rglob("*.py"):
        text = path.read_text(encoding="utf-8-sig")
        assert "tools.triage" not in text and "from tools" not in text, path
    spec = (root / "packaging" / "MewBook.spec").read_text(encoding="utf-8")
    assert "tools" not in spec.replace("collect_data_files", "").replace("PyInstaller.utils", "")
    assert not list(root.glob("tools/**/*.key")) and not list(root.glob("tools/**/*.pem"))
