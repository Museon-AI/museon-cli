"""Updates must precede business effects, preserve argv and target only this tool."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import httpx
import pytest

import museoncli.main as cli
import museoncli.bootstrap as bootstrap
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
    monkeypatch.delenv(updates._REEXEC_FROM, raising=False)
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
        assert arguments[4:] == argv
        assert executable == sys.executable
        assert updates.os.environ[updates._REEXEC_VERSION] == LATEST
        raise Restarted

    monkeypatch.setattr(updates.subprocess, "run", run)
    monkeypatch.setattr(updates.os, "execv", restart)
    with pytest.raises(Restarted):
        updates.ensure_latest(argv)
    command, kwargs = calls[0]
    assert command[:3] == ["/test/uv", "pip", "install"]
    assert command[3] == str(
        tool[0].parent / ".museoncli-wheels" / f"museoncli-{LATEST}-py3-none-any.whl"
    )
    assert Path(command[3]).read_bytes() == WHEEL_BYTES
    assert command[-2:] == ["--python", sys.executable]
    assert kwargs["capture_output"] is True
    captured = capsys.readouterr()
    assert not captured.out
    assert f"{CURRENT} -> {LATEST}" in captured.err


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
        bootstrap.main()
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
    assert updates.ensure_latest(["version"]) == {
        "status": "check_failed",
        "install_method": updates.UV_TOOL,
    }
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
    monkeypatch.setenv(updates._REEXEC_FROM, CURRENT)
    assert updates.ensure_latest(["version"]) == {
        "status": "updated",
        "install_method": updates.UV_TOOL,
        "latest_version": LATEST,
        "previous_version": CURRENT,
    }
    assert updates._REEXEC_VERSION not in updates.os.environ
    assert updates._REEXEC_FROM not in updates.os.environ


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


def test_host_wrapper_entrypoint_reports_managed_version(monkeypatch, capsys):
    from museoncli.config import Config

    monkeypatch.setattr(cli, "load_config", Config)
    monkeypatch.setattr(cli.sys, "argv", ["museon", "version"])
    cli.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["cli_version"] == cli.__version__
    assert payload["data"]["update"] == {"status": "managed_externally"}
    # Mel's sandbox imports main directly: the host owns upgrades, so no notice.
    assert payload["data"]["install_method"] == "managed"
    assert payload["data"]["upgrade_command"] is None
    assert "_notice" not in payload


@pytest.mark.parametrize("fresh_cache", [False, True])
def test_read_only_tools_directory_does_not_block_commands(tool, monkeypatch, capsys, fresh_cache):
    directory = tool[0].parent
    if fresh_cache:
        updates._cache_current(directory / ".museoncli-update.json", CURRENT)

    async def dispatch(_):
        return {"data": {"executed": True}}

    monkeypatch.setattr(cli, "dispatch", dispatch)
    monkeypatch.setattr(cli.sys, "argv", ["museon", "health"])
    monkeypatch.setattr(updates, "_release", lambda: pytest.fail("unlocked update check"))
    mode = directory.stat().st_mode
    try:
        directory.chmod(0o555)
        if os.access(directory, os.W_OK):
            pytest.skip("current user can bypass directory permissions")
        bootstrap.main()
    finally:
        directory.chmod(mode)
    output = capsys.readouterr()
    assert json.loads(output.out) == {"ok": True, "data": {"executed": True}}
    assert "using the installed version" in output.err


# --- Version and update notices (1.0.1) ------------------------------------------------


def run_cli(monkeypatch, capsys, *argv):
    monkeypatch.setattr(cli.sys, "argv", ["museoncli", *argv])
    code = 0
    try:
        bootstrap.main()
    except SystemExit as exc:
        code = exc.code
    output = capsys.readouterr()
    return json.loads(output.out), output.err, code


@pytest.fixture
def installed(monkeypatch, tmp_path):
    """A copy installed by an installer that owns its files (pip by default)."""
    monkeypatch.setenv("MUSEONCLI_CONFIG", str(tmp_path / "home" / "config.json"))
    monkeypatch.delenv("MUSEONCLI_UPDATE_CHECK", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv(updates._REEXEC_VERSION, "")
    monkeypatch.delenv(updates._REEXEC_FROM, raising=False)
    monkeypatch.setattr(updates, "__version__", CURRENT)
    monkeypatch.setattr(updates, "install_method", lambda: updates.PIP)
    checks = []
    monkeypatch.setattr(updates, "_release", lambda: checks.append(1) or release())
    # The detached refresh process, run inline: it finishes before the next command.
    monkeypatch.setattr(updates, "_refresh_in_background", updates.refresh_release_cache)
    monkeypatch.setattr(updates.subprocess, "run", lambda *a, **k: pytest.fail("installer ran"))
    monkeypatch.setattr(updates.os, "execv", lambda *a: pytest.fail("restarted"))

    async def dispatch(args):
        if args.command in {"version", "upgrade"}:
            return await real_dispatch(args)
        return {"data": {"executed": True}}

    real_dispatch = cli.dispatch
    monkeypatch.setattr(cli, "dispatch", dispatch)
    return checks


@pytest.mark.parametrize(
    "method,command",
    [
        ("pip", f'{sys.executable} -m pip install --upgrade "{{url}}"'),
        ("uv_pip", f'uv pip install --python {sys.executable} "{{url}}"'),
        ("pipx", 'pipx install --force "{url}"'),
        ("other", f'{sys.executable} -m pip install --upgrade "{{url}}"'),
    ],
)
def test_outdated_install_tells_the_agent_how_to_upgrade_on_every_command(
    installed, monkeypatch, capsys, method, command
):
    if " " in sys.executable:
        pytest.skip("interpreter path needs quoting")
    monkeypatch.setattr(updates, "install_method", lambda: method)
    command = command.format(url=updates.wheel_url(LATEST))
    payload, _, _ = run_cli(monkeypatch, capsys, "health")
    assert "_notice" not in payload  # The first command only starts the release check.
    for _ in range(2):
        payload, err, code = run_cli(monkeypatch, capsys, "health")
        assert code == 0 and payload["data"] == {"executed": True}
        assert payload["_notice"]["update"] == {
            "current": CURRENT,
            "latest": LATEST,
            "install_method": method,
            "upgrade_command": command,
            "changelog_url": (
                f"https://github.com/Museon-AI/museon-cli/blob/v{LATEST}/CHANGELOG.md#0230"
            ),
            "message": f"Museon CLI {CURRENT} is outdated (latest {LATEST}). "
            f"Tell the user to run: {command}",
        }
        assert err == ""  # Not a terminal: the Agent reads the JSON notice instead.
    assert len(installed) == 1  # The release check stays cached between commands.


@pytest.mark.parametrize("method", ["source", "managed"])
def test_source_and_host_runtime_get_no_notice_and_no_network(
    installed, monkeypatch, capsys, method
):
    monkeypatch.setattr(updates, "install_method", lambda: method)
    payload, err, _ = run_cli(monkeypatch, capsys, "health")
    assert "_notice" not in payload and err == ""
    assert installed == []


def test_current_or_disabled_install_has_no_update_notice(installed, monkeypatch, capsys):
    monkeypatch.setattr(updates, "_release", lambda: installed.append(1) or release(CURRENT))
    payload, _, _ = run_cli(monkeypatch, capsys, "health")
    assert "_notice" not in payload
    monkeypatch.setenv("MUSEONCLI_UPDATE_CHECK", "0")
    monkeypatch.setattr(updates, "_release", lambda: pytest.fail("checked while disabled"))
    payload, _, _ = run_cli(monkeypatch, capsys, "health")
    assert "_notice" not in payload


def test_stderr_line_is_for_terminals_and_at_most_once_a_day(
    installed, monkeypatch, capsys, tmp_path
):
    monkeypatch.setattr(updates, "_interactive", lambda: True)
    line = (
        f"Museon CLI {CURRENT} \u2192 {LATEST} available. Upgrade: "
        f"{updates.upgrade_command('pip', LATEST)}  Changes: {updates.changelog_url(LATEST)}\n"
    )
    run_cli(monkeypatch, capsys, "health")
    capsys.readouterr()
    first, err, _ = run_cli(monkeypatch, capsys, "health")
    assert err == line
    second, err, _ = run_cli(monkeypatch, capsys, "health")
    assert err == ""
    assert first["_notice"] == second["_notice"]  # The JSON notice is not rate-limited.
    state_path = tmp_path / "home" / "update-notices.json"
    state = json.loads(state_path.read_text())
    state["update_line_at"] -= updates.NOTICE_INTERVAL + 1
    state_path.write_text(json.dumps(state))
    _, err, _ = run_cli(monkeypatch, capsys, "health")
    assert err == line


def test_human_lines_need_a_terminal_outside_ci(monkeypatch):
    class Terminal:
        def isatty(self):
            return True

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(updates.sys, "stderr", Terminal())
    assert updates._interactive() is True
    monkeypatch.setenv("CI", "true")
    assert updates._interactive() is False


def test_ordinary_commands_never_wait_for_the_release_check(installed, monkeypatch, capsys):
    refreshes = []
    monkeypatch.setattr(updates, "_refresh_in_background", refreshes.append)
    monkeypatch.setattr(updates, "_release", lambda: pytest.fail("checked in the foreground"))
    for _ in range(3):
        payload, err, code = run_cli(monkeypatch, capsys, "health")
        assert code == 0 and payload == {"ok": True, "data": {"executed": True}}
    assert refreshes == ["pip"]  # One background refresh per interval.


def test_unreachable_release_server_never_blocks_or_fails_commands(
    installed, monkeypatch, capsys
):
    def offline():
        installed.append(1)
        raise httpx.ConnectTimeout("private-proxy-secret")

    monkeypatch.setattr(updates, "_release", offline)
    for _ in range(2):
        payload, err, code = run_cli(monkeypatch, capsys, "health")
        assert code == 0 and payload == {"ok": True, "data": {"executed": True}}
        assert err == ""
    assert len(installed) == 1  # The failure is cached: no wait on every command.


def test_self_upgrade_is_announced_once_with_its_highlights(tool, monkeypatch, capsys):
    manifest = release()
    manifest["body"] = (
        "## What's Changed\n"
        "* feat: tell users which version they run by @dev in "
        "https://github.com/Museon-AI/museon-cli/pull/204\n"
        "* @new made their first contribution in https://github.com/x/pull/1\n"
        "**Full Changelog**: https://github.com/x/compare/v1...v2"
    )
    monkeypatch.setattr(updates, "_release", lambda: manifest)
    monkeypatch.setattr(
        updates.subprocess,
        "run",
        lambda command, **_: subprocess.CompletedProcess(command, 0, stdout=LATEST + "\n"),
    )

    def restart(*_):
        raise Restarted

    monkeypatch.setattr(updates.os, "execv", restart)
    with pytest.raises(Restarted):
        updates.ensure_latest(["health"])
    assert updates.os.environ[updates._REEXEC_FROM] == CURRENT

    # The restarted interpreter is the new version.
    monkeypatch.setattr(updates, "__version__", LATEST)
    monkeypatch.setattr(updates, "version", lambda _: LATEST)
    monkeypatch.setattr(updates, "_interactive", lambda: True)

    async def dispatch(_):
        return {"data": {"executed": True}}

    monkeypatch.setattr(cli, "dispatch", dispatch)
    capsys.readouterr()
    payload, err, _ = run_cli(monkeypatch, capsys, "health")
    url = updates.changelog_url(LATEST)
    assert payload["_notice"]["updated"] == {
        "from": CURRENT,
        "to": LATEST,
        "changelog_url": url,
        "highlights": ["feat: tell users which version they run"],
        "message": f"Museon CLI was upgraded from {CURRENT} to {LATEST}. "
        f"Mention it to the user when relevant; changes: {url}",
    }
    assert err == f"Museon CLI upgraded {CURRENT} \u2192 {LATEST}. Changes: {url}\n"
    payload, err, _ = run_cli(monkeypatch, capsys, "health")
    assert "_notice" not in payload and err == ""


def test_version_reports_install_method_and_upgrade_command(installed, monkeypatch, capsys):
    payload, _, _ = run_cli(monkeypatch, capsys, "version")
    data = payload["data"]
    assert data["current"] == CURRENT  # updates.__version__, patched for the test
    assert {key: data[key] for key in ("latest", "install_method", "update_status")} == {
        "latest": LATEST,
        "install_method": "pip",
        "update_status": "outdated",
    }
    assert data["upgrade_command"] == updates.upgrade_command("pip", LATEST)
    assert data["changelog_url"] == updates.changelog_url(LATEST)
    run_cli(monkeypatch, capsys, "version")
    assert len(installed) == 2  # `version` always asks for the latest release.


def test_upgrade_prints_the_command_an_external_installer_must_run(
    installed, monkeypatch, capsys
):
    payload, _, code = run_cli(monkeypatch, capsys, "upgrade")
    assert code == 0
    assert payload["data"]["status"] == "manual"
    assert payload["data"]["upgrade_command"] == updates.upgrade_command("pip", LATEST)
    assert payload["data"]["upgrade_command"] in payload["data"]["message"]


def test_upgrade_reports_source_checkouts_and_unreachable_releases(
    installed, monkeypatch, capsys
):
    monkeypatch.setattr(updates, "install_method", lambda: updates.SOURCE)
    payload, _, _ = run_cli(monkeypatch, capsys, "upgrade")
    assert payload["data"]["status"] == "managed_externally"
    assert payload["data"]["upgrade_command"] is None

    monkeypatch.setattr(updates, "install_method", lambda: updates.PIP)

    def offline():
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(updates, "_release", offline)
    payload, _, code = run_cli(monkeypatch, capsys, "upgrade")
    assert code == 1
    assert payload["ok"] is False and payload["error"]["code"] == "network_error"
    assert payload["error"]["retryable"] is True


def test_upgrade_installs_a_pinned_uv_tool_and_reports_it(tool, monkeypatch, capsys):
    monkeypatch.setenv("MUSEONCLI_UPDATE_CHECK", "0")  # An explicit upgrade still runs.
    installs = []

    def run(command, **_):
        installs.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=LATEST + "\n")

    def restart(*_):
        raise Restarted

    monkeypatch.setattr(updates.subprocess, "run", run)
    monkeypatch.setattr(updates.os, "execv", restart)
    with pytest.raises(Restarted):
        updates.ensure_latest(["upgrade"])
    assert installs and installs[0][:3] == ["/test/uv", "pip", "install"]

    monkeypatch.setattr(updates, "__version__", LATEST)
    payload, _, code = run_cli(monkeypatch, capsys, "upgrade")
    assert code == 0
    assert payload["data"]["status"] == "upgraded"
    assert payload["data"]["previous_version"] == CURRENT
    assert payload["data"]["current"] == LATEST


@pytest.mark.parametrize(
    "receipt,installer,editable,expected",
    [
        (False, "pip", False, "pip"),
        (False, "uv", False, "uv_pip"),
        (True, "pip", False, "pipx"),
        (False, "poetry", False, "other"),
        (False, "pip", True, "source"),
    ],
)
def test_install_method_names_the_owner(monkeypatch, tmp_path, receipt, installer, editable, expected):
    if receipt:
        (tmp_path / "pipx_metadata.json").write_text("{}")
    package = Path(updates.__file__).resolve().with_name("__init__.py")

    class Dist:
        def locate_file(self, _):
            return package

        def read_text(self, name):
            if name == "INSTALLER":
                return installer + "\n"
            if name == "direct_url.json":
                return json.dumps({"dir_info": {"editable": editable}})
            return None

    monkeypatch.setattr(updates.sys, "prefix", str(tmp_path))
    monkeypatch.setattr(updates, "distribution", lambda _: Dist())
    assert updates.install_method() == expected
    monkeypatch.setattr(Dist, "locate_file", lambda *_: tmp_path / "museoncli" / "__init__.py")
    assert updates.install_method() == "source"  # Running code is not this distribution.


def test_version_and_upgrade_outputs_match_their_contract(installed, monkeypatch, capsys):
    import jsonschema

    from museoncli.domains import schema_payload

    assert [entry["name"] for entry in schema_payload()["cli"]] == ["version", "upgrade"]
    for command in ("version", "upgrade"):
        contract = schema_payload(command)
        assert schema_payload(f"museoncli {command}") == contract
        payload, _, _ = run_cli(monkeypatch, capsys, command)
        assert payload["_notice"]["update"]["latest"] == LATEST
        jsonschema.validate(payload, contract["output_schema"])
