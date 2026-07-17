"""Install the bundled Museon Agent Skill into supported Agent homes."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from importlib.resources import files
from pathlib import Path
from typing import Any

from museoncli import __version__


SUPPORTED_AGENTS = ("codex", "claude-code", "cursor")


def install_agent_skill(agent: str, *, force: bool = False) -> dict[str, Any]:
    targets = _resolve_agents(agent)
    source = _skill_source()
    results = [_install_one(source, target, force=force) for target in targets]
    return {
        "cli_version": __version__,
        "skill": "museon-cli",
        "agents": results,
        "next_steps": [
            "Restart the host Agent so it reloads installed Skills.",
            "Run `museoncli auth start`, approve access in the browser, then run "
            "`museoncli auth finish --wait` (waits up to five minutes by default).",
        ],
    }


def _resolve_agents(agent: str) -> list[str]:
    if agent in SUPPORTED_AGENTS:
        return [agent]
    if agent == "all":
        return list(SUPPORTED_AGENTS)
    if agent != "auto":
        raise ValueError(f"Unsupported Agent: {agent}")

    active_hosts = [
        name
        for name, marker in (
            ("codex", "CODEX_THREAD_ID"),
            ("claude-code", "CLAUDECODE"),
            ("cursor", "CURSOR_TRACE_ID"),
        )
        if os.environ.get(marker)
    ]
    if len(active_hosts) == 1:
        return active_hosts
    if len(active_hosts) > 1:
        raise RuntimeError(
            "Multiple host Agent environments were detected. Pass --agent codex, "
            "--agent claude-code, --agent cursor, or --agent all explicitly."
        )

    existing_homes = [name for name in SUPPORTED_AGENTS if _agent_home(name).is_dir()]
    if len(existing_homes) == 1:
        return existing_homes
    if not existing_homes:
        raise RuntimeError(
            "Could not detect the host Agent. Pass --agent codex, --agent claude-code, "
            "or --agent cursor."
        )
    detected_names = ", ".join(existing_homes)
    raise RuntimeError(
        f"Multiple Agent homes were detected ({detected_names}). "
        "Pass --agent codex, --agent claude-code, --agent cursor, or --agent all explicitly."
    )


def _agent_home(agent: str) -> Path:
    if agent == "codex":
        return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()
    if agent == "claude-code":
        return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser()
    if agent == "cursor":
        return Path(os.environ.get("CURSOR_HOME") or Path.home() / ".cursor").expanduser()
    raise ValueError(f"Unsupported Agent: {agent}")


def _skill_source():
    bundled = files("museoncli").joinpath("bundled_skills", "museon-cli")
    if bundled.joinpath("SKILL.md").is_file():
        return bundled
    development_source = Path(__file__).resolve().parents[1] / "skills" / "museon-cli"
    if development_source.joinpath("SKILL.md").is_file():
        return development_source
    raise RuntimeError("The Museon CLI package does not contain its bundled Agent Skill.")


def _install_one(source, agent: str, *, force: bool) -> dict[str, str]:
    destination = _agent_home(agent) / "skills" / "museon-cli"
    source_digest = _tree_digest(source)
    if destination.is_dir() and _tree_digest(destination) == source_digest:
        return {
            "agent": agent,
            "status": "current",
            "path": str(destination),
            "digest": source_digest,
        }
    if destination.exists() and not force and not _is_museon_skill(destination):
        raise RuntimeError(
            f"Refusing to replace an unmanaged path: {destination}. "
            "Move it aside or rerun with --force."
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".museon-cli-skill-", dir=destination.parent))
    backup = destination.with_name(f".{destination.name}.backup")
    try:
        _copy_tree(source, temporary)
        if _tree_digest(temporary) != source_digest:
            raise RuntimeError("Agent Skill verification failed after copying files.")
        if backup.exists():
            _remove_path(backup)
        if destination.exists():
            destination.replace(backup)
        temporary.replace(destination)
        _remove_path(backup)
    except Exception:
        _remove_path(temporary)
        if backup.exists() and not destination.exists():
            backup.replace(destination)
        raise

    return {
        "agent": agent,
        "status": "installed",
        "path": str(destination),
        "digest": source_digest,
    }


def _copy_tree(source, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        target = destination / child.name
        if child.is_dir():
            _copy_tree(child, target)
        elif child.is_file():
            target.write_bytes(child.read_bytes())


def _tree_digest(root) -> str:
    digest = hashlib.sha256()
    entries = sorted(_walk_files(root), key=lambda item: item[0])
    for relative, item in entries:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _walk_files(root, prefix: str = ""):
    for child in root.iterdir():
        relative = f"{prefix}/{child.name}" if prefix else child.name
        if child.is_dir():
            yield from _walk_files(child, relative)
        elif child.is_file():
            yield relative, child


def _is_museon_skill(path: Path) -> bool:
    skill_file = path / "SKILL.md"
    if not skill_file.is_file():
        return False
    try:
        return "name: museon-cli" in skill_file.read_text(encoding="utf-8")[:500]
    except OSError:
        return False


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
