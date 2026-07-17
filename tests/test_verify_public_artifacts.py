from __future__ import annotations

import importlib.util
import sys
import tarfile
import zipfile
from pathlib import Path
from types import ModuleType

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_public_artifacts.py"


def _load_verifier() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_public_artifacts", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_wheel_verifier_rejects_private_runtime_reference(tmp_path: Path) -> None:
    module = _load_verifier()
    wheel = tmp_path / "museoncli-test.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("museoncli/main.py", "source = 'apps/" + "agents/private'\n")

    entries = module._wheel_entries(wheel)
    with pytest.raises(RuntimeError, match="private reference"):
        module._assert_public_wheel_content(entries, artifact=wheel)


def test_sdist_verifier_rejects_links(tmp_path: Path) -> None:
    module = _load_verifier()
    sdist = tmp_path / "museoncli-test.tar.gz"
    target = tmp_path / "target.txt"
    target.write_text("safe", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    with tarfile.open(sdist, "w:gz") as archive:
        archive.add(link, arcname="museoncli-test/link.txt", recursive=False)

    with pytest.raises(RuntimeError, match="contains a link"):
        module._sdist_entries(sdist)


def test_sdist_content_verifier_rejects_private_reference(tmp_path: Path) -> None:
    module = _load_verifier()
    artifact = tmp_path / "museoncli-test.tar.gz"
    entries = [module.ArchiveEntry("docs/internal.md", b"implementation: apps/" + b"api")]

    with pytest.raises(RuntimeError, match="private reference"):
        module._assert_no_private_content(entries, artifact=artifact)


def test_content_verifier_rejects_embedded_secret(tmp_path: Path) -> None:
    module = _load_verifier()
    artifact = tmp_path / "museoncli-test.whl"
    fake_token = b"gh" + b"p_0123456789abcdefghijklmnopqrstuvwxyz"
    entries = [module.ArchiveEntry("museoncli/config.py", fake_token)]

    with pytest.raises(RuntimeError, match="possible GitHub token"):
        module._assert_no_private_content(entries, artifact=artifact)


def test_license_verifier_requires_license_in_sdist(tmp_path: Path) -> None:
    module = _load_verifier()

    with pytest.raises(RuntimeError, match="sdist.*missing license files"):
        module._assert_license_files_packaged(
            source_license_files=["LICENSE"],
            wheel_entries=[
                module.ArchiveEntry("museoncli-1.0.dist-info/licenses/LICENSE", b"license")
            ],
            sdist_entries=[],
            wheel=tmp_path / "wheel.whl",
            sdist=tmp_path / "sdist.tar.gz",
        )


def test_license_verifier_requires_license_in_wheel_metadata(tmp_path: Path) -> None:
    module = _load_verifier()

    with pytest.raises(RuntimeError, match="wheel.*missing packaged license"):
        module._assert_license_files_packaged(
            source_license_files=["LICENSE"],
            wheel_entries=[],
            sdist_entries=[module.ArchiveEntry("LICENSE", b"license")],
            wheel=tmp_path / "wheel.whl",
            sdist=tmp_path / "sdist.tar.gz",
        )
