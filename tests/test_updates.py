"""Updates must precede business effects, preserve argv and target only this tool."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import httpx
import pytest

import museoncli.main as cli
from museoncli import updates


CURRENT = "0.22.3"
LATEST = "0.23.0"
WHEEL_BYTES = b"synthetic wheel bytes"


class Restarted(BaseException):
    pass


def release(version=LATEST):
    wheel = f"museoncli-{version}-py3-none-any.whl"
    return {
        "tag_name": f"v{version}",
        "draft": False,
        "prerelease": False,
        "assets": [
            {
                "name": wheel,
                "digest": "sha256:" + hashlib.sha256(WHEEL_BYTES).hexdigest(),
                "browser_download_url": f"{updates.DOWNLOAD_ROOT}/v{version}/{wheel}",
            }
        ],
    }


@pytest.fixture
def tool(monkeypatch, tmp_path):
    prefix = tmp_path / "tools" / "museoncli"
    prefix.mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    monkeypatch.setattr(updates.sys, "prefix", str(prefix))
    monkeypatch.setattr(updates, "__version__", CURRENT)
    monkeypatch.setattr(updates, "version", lambda _: CURRENT)
    monkeypatch.setattr(updates, "_tool_bin", lambda _: bin_dir)
    monkeypatch.setattr(updates, "_release", release)
    monkeypatch.delenv("MUSEONCLI_UPDATE_CHECK", raising=False)
    monkeypatch.setenv(updates._REEXEC_VERSION, "")
    monkeypatch.setattr(updates.shutil, "which", lambda _: "/test/uv")
    real = httpx.Client
    monkeypatch.setattr(
        updates.httpx,
        "Client",
        lambda **kw: real(
            **kw, transport=httpx.MockTransport(lambda _: httpx.Response(200, content=WHEEL_BYTES))
        ),
    )
    return prefix, bin_dir


def test_default_upgrade_verifies_wheel_then_restarts_original_argv(tool, monkeypatch, capsys):
    calls = []
    argv = ["hireaicreator", "video", "+create", "--args-json", '{"caption":"a b"}']

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout=LATEST + "\n")

    def restart(executable, arguments):
        assert len(calls) == 2  # Installation and a fresh-interpreter version check.
        assert arguments[3:] == argv
        assert executable == sys.executable
        assert updates.os.environ[updates._REEXEC_VERSION] == LATEST
        raise Restarted

    monkeypatch.setattr(updates.subprocess, "run", run)
    monkeypatch.setattr(updates.os, "execv", restart)
    with pytest.raises(Restarted):
        updates.ensure_latest(argv)
    command, kwargs = calls[0]
    assert command[:3] == ["/test/uv", "tool", "install"]
    assert command[3] == str(
        tool[0].parent / ".museoncli-wheels" / f"museoncli-{LATEST}-py3-none-any.whl"
    )
    assert Path(command[3]).read_bytes() == WHEEL_BYTES
    assert kwargs["env"]["UV_TOOL_DIR"] == str(tool[0].parent)
    assert kwargs["env"]["UV_TOOL_BIN_DIR"] == str(tool[1])
    assert kwargs["capture_output"] is True
    captured = capsys.readouterr()
    assert not captured.out
    assert f"{CURRENT} → {LATEST}" in captured.err


@pytest.mark.parametrize("failure", ["install", "timeout", "wrong_version"])
def test_failed_upgrade_stops_before_business_dispatch(tool, monkeypatch, capsys, failure):
    def run(command, **kwargs):
        if command[0] == "/test/uv":
            if failure == "install":
                raise subprocess.CalledProcessError(1, command, stderr="private-proxy-secret")
            if failure == "timeout":
                raise subprocess.TimeoutExpired(command, 120, stderr="private-proxy-secret")
        return subprocess.CompletedProcess(command, 0, stdout=CURRENT)

    monkeypatch.setattr(updates.subprocess, "run", run)
    monkeypatch.setattr(cli.sys, "argv", ["museon", "health"])
    monkeypatch.setattr(cli, "dispatch", lambda _: pytest.fail("business command ran"))
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code != 0
    output = capsys.readouterr()
    assert json.loads(output.out)["ok"] is False
    assert "cli_update_failed" in output.out
    assert "private-proxy-secret" not in output.out + output.err


def test_current_release_is_cached_but_version_forces_a_check(tool, monkeypatch):
    calls = []
    monkeypatch.setattr(updates, "_release", lambda: calls.append(1) or release(CURRENT))
    monkeypatch.setattr(updates.subprocess, "run", lambda *a, **k: pytest.fail("unneeded install"))
    assert updates.ensure_latest(["health"])["status"] == "current"
    assert updates.ensure_latest(["health"])["status"] == "cached"
    assert updates.ensure_latest(["version"])["status"] == "current"
    assert len(calls) == 2
    cache = tool[0].parent / ".museoncli-update.json"
    cache.write_text(json.dumps({"version": CURRENT, "checked_at": time.time() - 901}))
    assert updates.ensure_latest(["health"])["status"] == "current"
    assert len(calls) == 3


def test_network_failure_is_explicit_and_does_not_claim_current(tool, monkeypatch, capsys):
    def offline():
        raise httpx.ConnectError("private-proxy-secret")

    monkeypatch.setattr(updates, "_release", offline)
    assert updates.ensure_latest(["version"]) == {"status": "check_failed"}
    assert not (tool[0].parent / ".museoncli-update.json").exists()
    captured = capsys.readouterr()
    assert not captured.out
    assert "could not check" in captured.err
    assert "private-proxy-secret" not in captured.err


@pytest.mark.parametrize(
    "field,value",
    [
        ("browser_download_url", "https://example.test/rogue.whl"),
        ("digest", "sha256:invalid"),
    ],
)
def test_untrusted_or_unverified_wheel_never_runs_installer(tool, monkeypatch, field, value):
    manifest = release()
    manifest["assets"][0][field] = value
    monkeypatch.setattr(updates, "_release", lambda: manifest)
    monkeypatch.setattr(updates.subprocess, "run", lambda *a, **k: pytest.fail("unsafe install"))
    with pytest.raises(RuntimeError, match="official release wheel or SHA-256"):
        updates.ensure_latest(["health"])


def test_latest_discovery_uses_official_stable_release_without_auth(monkeypatch):
    real = httpx.Client
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=release())

    monkeypatch.setenv("MUSEONCLI_UPDATE_MANIFEST_URL", "https://example.test/untrusted")
    monkeypatch.setattr(
        updates.httpx, "Client", lambda **kw: real(**kw, transport=httpx.MockTransport(handler))
    )
    assert updates._release()["tag_name"] == f"v{LATEST}"
    assert str(requests[0].url) == updates.RELEASE_URL
    assert "authorization" not in requests[0].headers


@pytest.mark.parametrize(
    "manifest",
    [release("0.24.0-rc1"), {**release(), "prerelease": True}, {**release(), "draft": True}],
)
def test_prereleases_are_not_install_candidates(monkeypatch, manifest):
    real = httpx.Client
    monkeypatch.setattr(
        updates.httpx,
        "Client",
        lambda **kw: real(
            **kw, transport=httpx.MockTransport(lambda _: httpx.Response(200, json=manifest))
        ),
    )
    with pytest.raises(ValueError):
        updates._release()


def test_waiting_process_restarts_after_another_process_upgrades(tool, monkeypatch):
    monkeypatch.setattr(updates, "version", lambda _: LATEST)
    monkeypatch.setattr(updates, "_release", lambda: pytest.fail("redundant release request"))
    monkeypatch.setattr(updates.subprocess, "run", lambda *a, **k: pytest.fail("second installer"))

    def restart(*args):
        raise Restarted

    monkeypatch.setattr(updates.os, "execv", restart)
    with pytest.raises(Restarted):
        updates.ensure_latest(["health"])


def test_restarted_process_does_not_check_again(tool, monkeypatch):
    monkeypatch.setattr(updates, "__version__", LATEST)
    monkeypatch.setenv(updates._REEXEC_VERSION, LATEST)
    monkeypatch.setattr(updates, "_release", lambda: pytest.fail("update loop"))
    assert updates.ensure_latest(["version"]) == {"status": "updated", "latest_version": LATEST}
    assert updates._REEXEC_VERSION not in updates.os.environ


def test_opt_out_and_help_stay_offline(tool, monkeypatch):
    monkeypatch.setattr(updates, "_release", lambda: pytest.fail("unexpected network"))
    assert updates.ensure_latest(["--help"])["status"] == "not_checked"
    monkeypatch.setenv("MUSEONCLI_UPDATE_CHECK", "0")
    assert updates.ensure_latest(["health"])["status"] == "disabled"


def test_source_and_host_managed_installs_are_not_modified(tmp_path, monkeypatch):
    monkeypatch.delenv("MUSEONCLI_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(updates.sys, "prefix", str(tmp_path))
    monkeypatch.setattr(updates, "_release", lambda: pytest.fail("host runtime must own upgrades"))
    assert updates.ensure_latest(["version"])["status"] == "managed_externally"


def test_lock_is_released_when_holder_process_dies(tmp_path):
    lock = tmp_path / "lock"
    code = (
        "from pathlib import Path; from museoncli.updates import _update_lock; import time; "
        f"handle = _update_lock(Path({str(lock)!r})); handle.__enter__(); "
        "print('locked', flush=True); time.sleep(60)"
    )
    holder = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "locked"
        waiter = subprocess.Popen(
            [
                sys.executable,
                "-c",
                code.replace("time.sleep(60)", "handle.__exit__(None,None,None)"),
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            time.sleep(0.2)
            assert waiter.poll() is None
            holder.kill()
            holder.wait(timeout=5)
            stdout, _ = waiter.communicate(timeout=5)
            assert waiter.returncode == 0
            assert stdout.strip() == "locked"
        finally:
            if waiter.poll() is None:
                waiter.kill()
                waiter.wait(timeout=5)
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.wait(timeout=5)


def test_corrupt_download_cannot_replace_installed_tool(tool, monkeypatch):
    manifest = release()
    manifest["assets"][0]["digest"] = "sha256:" + "0" * 64
    monkeypatch.setattr(updates, "_release", lambda: manifest)
    monkeypatch.setattr(
        updates.subprocess, "run", lambda *a, **k: pytest.fail("corrupt wheel installed")
    )
    with pytest.raises(RuntimeError, match="SHA-256 did not match"):
        updates.ensure_latest(["health"])
    assert not list((tool[0].parent / ".museoncli-wheels").glob("*.whl"))
