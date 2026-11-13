"""Exercise real uv self-replacement using synthetic release bytes, never a live update."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile


def smoke_auto_update(wheel: Path, current: str) -> None:
    parts = current.split(".")
    latest = ".".join([*parts[:2], str(int(parts[2]) + 1)])
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("uv is required for the self-update smoke test")
    with tempfile.TemporaryDirectory(prefix="museoncli-update-smoke-") as temporary:
        root = Path(temporary)
        target = root / f"museoncli-{latest}-py3-none-any.whl"
        # Change only wheel metadata: this is a private fixture, never a release.
        with zipfile.ZipFile(wheel) as archive:
            files = {
                name.replace(
                    f"museoncli-{current}.dist-info", f"museoncli-{latest}.dist-info"
                ): archive.read(name)
                for name in archive.namelist()
                if not name.endswith("/RECORD")
            }
        metadata = f"museoncli-{latest}.dist-info/METADATA"
        files[metadata] = files[metadata].replace(
            f"Version: {current}".encode(), f"Version: {latest}".encode()
        )
        records = io.StringIO()
        writer = csv.writer(records, lineterminator="\n")
        for name, data in files.items():
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
            writer.writerow([name, f"sha256={digest}", len(data)])
        record = f"museoncli-{latest}.dist-info/RECORD"
        writer.writerow([record, "", ""])
        files[record] = records.getvalue().encode()
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in files.items():
                archive.writestr(name, data)

        env = {
            **os.environ,
            "UV_TOOL_DIR": str(root / "tools"),
            "UV_TOOL_BIN_DIR": str(root / "bin"),
            "MUSEONCLI_CONFIG": str(root / "config.json"),
            "MUSEONCLI_CREDENTIAL_BACKEND": "file",
            "MUSEONCLI_UPDATE_CHECK": "1",
        }
        env.pop("_MUSEONCLI_UPDATED_TO", None)
        subprocess.run(
            [uv, "tool", "install", str(wheel), "--python", sys.executable],
            env=env,
            check=True,
            capture_output=True,
        )
        hooks = root / "hooks"
        hooks.mkdir()
        counter = root / "installs.txt"
        # Intercept only remote discovery/download. Installation, checksum, lock,
        # version verification, re-exec and both console entry points are real.
        (hooks / "sitecustomize.py").write_text(
            f"""import importlib.util
if importlib.util.find_spec("museoncli"):
    import httpx, os, subprocess
    from pathlib import Path
    from museoncli import updates
    wheel = Path({str(target)!r})
    updates._release = lambda: {{"tag_name": "v{latest}", "assets": [{{
        "name": wheel.name,
        "browser_download_url": updates.DOWNLOAD_ROOT + "/v{latest}/" + wheel.name,
        "digest": "sha256:{hashlib.sha256(target.read_bytes()).hexdigest()}"
    }}]}}
    client = httpx.Client
    updates.httpx.Client = lambda **kw: client(**kw, transport=httpx.MockTransport(
        lambda _: httpx.Response(200, content=wheel.read_bytes())))
    original_install = updates._install
    def install(*args, **kwargs):
        try:
            result = original_install(*args, **kwargs)
            os.environ.pop("PYTHONPATH", None)
            return result
        except Exception as exc:
            raise AssertionError("synthetic update cause: " + repr(exc.__cause__ or exc)) from exc
    updates._install = install
    original = subprocess.run
    def run(command, **kwargs):
        if len(command) > 3 and command[1:3] == ["pip", "install"]:
            assert Path(command[3]).read_bytes() == wheel.read_bytes()
            with open({str(counter)!r}, "a") as output:
                output.write("install\\n")
        if "-c" in command:
            # Do not let our test hook pre-import and hide cwd module shadowing.
            kwargs["env"] = {{**os.environ, "PYTHONPATH": ""}}
        try:
            return original(command, **kwargs)
        except subprocess.CalledProcessError as exc:
            # Only synthetic local inputs are used by this smoke test.
            raise AssertionError("synthetic installer failed: " + str(exc.stderr)) from exc
    subprocess.run = run
""",
            encoding="utf-8",
        )
        env["PYTHONPATH"] = str(hooks)
        untrusted = root / "untrusted-cwd"
        untrusted.mkdir()
        (untrusted / "museoncli").mkdir()
        for name in ("museoncli/__init__.py", "json.py", "httpx.py", "pathlib.py"):
            (untrusted / name).write_text("raise RuntimeError('untrusted cwd module executed')\n")
        for alias, expected in (("museon", "updated"), ("museoncli", "current")):
            executable = root / "bin" / (f"{alias}.exe" if os.name == "nt" else alias)
            result = subprocess.run(
                [str(executable), "version", "--json"],
                env=env,
                cwd=untrusted,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=180,
            )
            if result.returncode:
                raise RuntimeError(f"self-update failed: {result.stdout}\n{result.stderr}")
            payload = json.loads(result.stdout)
            assert payload["data"]["cli_version"] == latest, payload
            assert payload["data"]["update"]["status"] == expected, payload
            # The completed upgrade is announced once, by the first command after it.
            announced = payload.get("_notice", {}).get("updated")
            if expected == "updated":
                assert announced and announced["from"] == current, payload
                assert announced["to"] == latest, payload
            else:
                assert announced is None, payload
        assert counter.read_text() == "install\n", "more than one installer ran"
        print(
            f"self-update smoke passed: {current} -> synthetic {latest}; both aliases; one install"
        )
