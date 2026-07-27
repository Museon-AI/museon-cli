#!/usr/bin/env python3
"""Build the deterministic skills.tar.gz release asset."""

from __future__ import annotations

import argparse
import gzip
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "skills"
DEFAULT_OUTPUT = ROOT / "release" / "skills.tar.gz"


def _normalized(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = 0
    info.mode = 0o755 if info.isdir() else 0o644
    return info


def build_archive(source: Path, output: Path) -> None:
    source = source.resolve()
    output = output.resolve()
    if not source.is_dir():
        raise ValueError(f"skills source directory does not exist: {source}")
    output.parent.mkdir(parents=True, exist_ok=True)

    paths = [source, *sorted(source.rglob("*"), key=lambda path: path.relative_to(source).as_posix())]
    with output.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.GNU_FORMAT) as archive:
                for path in paths:
                    archive_name = Path(source.name, path.relative_to(source)).as_posix()
                    info = _normalized(archive.gettarinfo(str(path), arcname=archive_name))
                    if info.isfile():
                        with path.open("rb") as fileobj:
                            archive.addfile(info, fileobj)
                    else:
                        archive.addfile(info)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    build_archive(args.source, args.output)
    print(f"skills archive generated: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
