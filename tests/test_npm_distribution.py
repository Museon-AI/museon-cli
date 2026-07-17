from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from distribution import ROOT_PACKAGE, TARGETS, project_version  # noqa: E402
from generate_npm_packages import generate_platform, generate_root  # noqa: E402
from verify_native_signatures import verify_macos  # noqa: E402


def _load_verifier() -> ModuleType:
    script = SCRIPTS / "verify_npm_packages.py"
    spec = importlib.util.spec_from_file_location("verify_npm_packages", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fake_native(native_root: Path, target) -> None:
    bundle = native_root / target.target / "museoncli"
    bundle.mkdir(parents=True)
    executable = bundle / target.executable
    executable.write_bytes(b"native")
    executable.chmod(0o755)
    notices = b"# Third-Party Notices\n\n## fake-runtime 1.0\n"
    (bundle / "THIRD_PARTY_NOTICES.md").write_bytes(notices)
    (bundle / "museon-build.json").write_text(
        json.dumps(
            {
                "target": target.target,
                "version": project_version(),
                "wheel": {"sha256": "a" * 64},
                "third_party_notices": {
                    "filename": "THIRD_PARTY_NOTICES.md",
                    "sha256": hashlib.sha256(notices).hexdigest(),
                    "package_count": 1,
                },
            }
        ),
        encoding="utf-8",
    )


def test_frozen_npm_matrix() -> None:
    assert ROOT_PACKAGE == "@museon/cli"
    assert [(item.package, item.runner) for item in TARGETS] == [
        ("@museon/cli-darwin-arm64", "macos-15"),
        ("@museon/cli-darwin-x64", "macos-15-intel"),
        ("@museon/cli-linux-arm64-gnu", "ubuntu-22.04-arm"),
        ("@museon/cli-linux-x64-gnu", "ubuntu-22.04"),
        ("@museon/cli-win32-x64", "windows-2025"),
        ("@museon/cli-win32-arm64", "windows-11-arm"),
    ]
    assert [item.libc for item in TARGETS if item.os == "linux"] == ["glibc", "glibc"]


def test_workflows_cover_frozen_native_matrix_and_current_scope() -> None:
    workflows = [
        (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        for name in ("ci.yml", "release.yml")
    ]
    for workflow in workflows:
        for target in TARGETS:
            assert f"target: {target.target}" in workflow
            assert f"runner: {target.runner}" in workflow
        assert "@museon-ai" not in workflow
        assert "museon-ai-cli" not in workflow


def test_generator_and_verifier_enforce_exact_versions_and_no_scripts(tmp_path: Path) -> None:
    native = tmp_path / "native"
    packages = tmp_path / "packages"
    for target in TARGETS:
        _fake_native(native, target)
    generate_root(packages)
    for target in TARGETS:
        generate_platform(packages, native, target.target)

    verifier = _load_verifier()
    archives = [verifier._directory_archive(path) for path in packages.iterdir()]
    verifier.verify(archives, require_all=True)

    root = json.loads((packages / "cli" / "package.json").read_text(encoding="utf-8"))
    assert "dependencies" not in root
    assert "scripts" not in root
    assert set(root["optionalDependencies"]) == {target.package for target in TARGETS}
    assert set(root["optionalDependencies"].values()) == {project_version()}
    assert "THIRD_PARTY_NOTICES.md" in root["files"]


def test_verifier_rejects_lifecycle_script(tmp_path: Path) -> None:
    package = generate_root(tmp_path)
    manifest_path = package / "package.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["scripts"] = {"postinstall": "node download.js"}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    verifier = _load_verifier()

    with pytest.raises(RuntimeError, match="forbidden lifecycle"):
        verifier.verify([verifier._directory_archive(package)], require_all=False)


def test_verifier_rejects_mutable_launcher_documentation_url(tmp_path: Path) -> None:
    package = generate_root(tmp_path)
    launcher = package / "lib" / "launcher.cjs"
    launcher.write_text(
        launcher.read_text(encoding="utf-8")
        + "\n// https://github.com/Museon-AI/museon-cli/blob/main/docs/install.md\n",
        encoding="utf-8",
    )
    verifier = _load_verifier()

    with pytest.raises(RuntimeError, match="mutable GitHub branch"):
        verifier.verify([verifier._directory_archive(package)], require_all=False)


def test_release_prerequisites_accept_apache_license() -> None:
    from verify_release_prerequisites import verify

    verify(ROOT)


def test_release_prerequisites_fail_closed_without_license(tmp_path: Path) -> None:
    from verify_release_prerequisites import verify

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "1.0.0"\nlicense = "Apache-2.0"\n',
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="unresolved external decision"):
        verify(tmp_path)


def test_macos_signature_verifier_requires_developer_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    binary = tmp_path / "museoncli"
    binary.write_bytes(b"native")
    monkeypatch.setattr(
        "verify_native_signatures.shutil.which", lambda name: f"/usr/bin/{name}"
    )

    class Result:
        def __init__(self, stdout: str = "", stderr: str = "") -> None:
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(command, **_kwargs):
        if command[0].endswith("/file"):
            return Result(stdout="Mach-O 64-bit executable arm64\n")
        return Result(stderr="Authority=Developer ID Application: Museon\nTeamIdentifier=TEAM123\n")

    monkeypatch.setattr("verify_native_signatures.subprocess.run", fake_run)

    verify_macos(tmp_path, "museoncli")


def test_macos_signature_verifier_rejects_ad_hoc_signature(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    binary = tmp_path / "museoncli"
    binary.write_bytes(b"native")
    monkeypatch.setattr(
        "verify_native_signatures.shutil.which", lambda name: f"/usr/bin/{name}"
    )

    class Result:
        def __init__(self, stdout: str = "", stderr: str = "") -> None:
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(command, **_kwargs):
        if command[0].endswith("/file"):
            return Result(stdout="Mach-O 64-bit executable arm64\n")
        return Result(stderr="Signature=adhoc\nTeamIdentifier=not set\n")

    monkeypatch.setattr("verify_native_signatures.subprocess.run", fake_run)

    with pytest.raises(RuntimeError, match="Developer ID Application"):
        verify_macos(tmp_path, "museoncli")


def test_macos_signature_verifier_checks_every_mach_o_and_rejects_mixed_teams(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    binary = tmp_path / "museoncli"
    library = tmp_path / "_internal" / "libpython.dylib"
    binary.write_bytes(b"native")
    library.parent.mkdir()
    library.write_bytes(b"native")
    monkeypatch.setattr(
        "verify_native_signatures.shutil.which", lambda name: f"/usr/bin/{name}"
    )

    class Result:
        def __init__(self, stdout: str = "", stderr: str = "") -> None:
            self.stdout = stdout
            self.stderr = stderr

    verified: list[Path] = []

    def fake_run(command, **_kwargs):
        candidate = Path(command[-1])
        if command[0].endswith("/file"):
            return Result(stdout="Mach-O 64-bit executable arm64\n")
        if "--verify" in command:
            verified.append(candidate)
            return Result()
        team = "TEAM999" if candidate == library else "TEAM123"
        return Result(
            stderr=f"Authority=Developer ID Application: Museon\nTeamIdentifier={team}\n"
        )

    monkeypatch.setattr("verify_native_signatures.subprocess.run", fake_run)

    with pytest.raises(RuntimeError, match="mixes Developer ID team identifiers"):
        verify_macos(tmp_path, "museoncli")
    assert verified == [library, binary]


def test_release_workflow_signs_before_npm_packaging() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    apple = workflow.index("name: Sign and notarize macOS bundle")
    windows = workflow.index("name: Authenticode-sign and timestamp Windows bundle")
    verify = workflow.index("name: Verify native release signature policy")
    smoke = workflow.index("name: Smoke exact signed target")
    package = workflow.index("name: Prepack signed target")
    assert apple < verify < smoke < package
    assert windows < verify < smoke < package
    assert "xcrun notarytool submit" in workflow
    assert "verify_windows_signatures.ps1" in (
        ROOT / "scripts" / "verify_native_signatures.py"
    ).read_text(encoding="utf-8")
