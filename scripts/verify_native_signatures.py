#!/usr/bin/env python3
"""Fail release packaging unless native signatures satisfy the launch policy."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from distribution import ROOT, TARGET_BY_NAME


def verify_macos(bundle: Path, executable: str) -> None:
    codesign = shutil.which("codesign")
    file_command = shutil.which("file")
    if not codesign:
        raise RuntimeError("codesign is required to verify a macOS release bundle")
    if not file_command:
        raise RuntimeError("file is required to inspect a macOS release bundle")
    binary = bundle / executable
    mach_o_files: list[Path] = []
    for candidate in sorted(path for path in bundle.rglob("*") if path.is_file()):
        kind = subprocess.run(
            [file_command, "--brief", str(candidate)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        if "Mach-O" in kind:
            mach_o_files.append(candidate)
    if binary not in mach_o_files:
        raise RuntimeError("macOS native executable is missing or is not Mach-O")
    expected_team_identifier: str | None = None
    for candidate in mach_o_files:
        subprocess.run(
            [codesign, "--verify", "--strict", "--verbose=2", str(candidate)],
            check=True,
        )
        details = subprocess.run(
            [codesign, "-dv", "--verbose=4", str(candidate)],
            check=True,
            capture_output=True,
            text=True,
        )
        output = details.stdout + details.stderr
        if "Authority=Developer ID Application:" not in output:
            raise RuntimeError(
                f"macOS file is not signed with a Developer ID Application identity: {candidate}"
            )
        team_identifier = next(
            (
                line.partition("=")[2].strip()
                for line in output.splitlines()
                if line.startswith("TeamIdentifier=")
            ),
            "",
        )
        if not team_identifier or team_identifier == "not set":
            raise RuntimeError(f"macOS file has no valid Developer ID team identifier: {candidate}")
        if expected_team_identifier is None:
            expected_team_identifier = team_identifier
        elif team_identifier != expected_team_identifier:
            raise RuntimeError(
                "macOS bundle mixes Developer ID team identifiers: "
                f"expected {expected_team_identifier}, got {team_identifier} for {candidate}"
            )


def verify_windows(bundle: Path) -> None:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if not powershell:
        raise RuntimeError("PowerShell is required to verify a Windows release bundle")
    subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(ROOT / "scripts" / "verify_windows_signatures.ps1"),
            "-Bundle",
            str(bundle),
        ],
        check=True,
    )


def verify(target_name: str, bundle: Path) -> None:
    target = TARGET_BY_NAME[target_name]
    if target.os == "darwin":
        verify_macos(bundle, target.executable)
    elif target.os == "win32":
        verify_windows(bundle)
    else:
        print(f"native signature policy uses release integrity/provenance for {target.target}")
        return
    print(f"verified native release signatures: {target.target}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=sorted(TARGET_BY_NAME))
    parser.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    if not bundle.is_dir():
        raise RuntimeError(f"native bundle is missing: {bundle}")
    verify(args.target, bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
