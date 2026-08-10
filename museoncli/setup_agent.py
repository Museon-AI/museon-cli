"""Install the bundled Museon Agent Skills into supported Agent homes."""

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
MANAGED_SKILLS = ("museon-cli", "social-media-hook-analyze")


def install_agent_skill(agent: str, *, force: bool = False) -> dict[str, Any]:
    targets = _resolve_agents(agent)
    sources = _skill_sources()
    for target in targets:
        for skill_name in sources:
            _validate_destination(target, skill_name=skill_name, force=force)
    results = []
    for target in targets:
        installed = [
            _install_one(source, target, skill_name=skill_name, force=force)
            for skill_name, source in sources.items()
        ]
        primary = installed[0]
        results.append(
            {
                "agent": target,
                "status": (
                    "current" if all(item["status"] == "current" for item in installed) else "installed"
                ),
                "path": primary["path"],
                "digest": primary["digest"],
                "skills": installed,
            }
        )
    return {
        "cli_version": __version__,
        "skill": "museon-cli",
        "skills": list(MANAGED_SKILLS),
        "agents": results,
        "next_steps": [
            "Restart the host Agent so it reloads installed Skills.",
            "Install and complete onboarding for ego lite when Instagram browsing is needed; "
            "the social-media-hook-analyze Skill checks the ego-browser command before use.",
            "Run `museoncli auth start`, approve access in the browser, then run "
            "`museoncli auth finish --wait` (waits up to five minutes by default).",
            "After authentication, run `museoncli skills +list` to discover the "
            "Business Skills available in the current workspace.",
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


def _skill_sources() -> dict[str, Any]:
    bundled_root = files("museoncli").joinpath("bundled_skills")
    development_root = Path(__file__).resolve().parents[1] / "skills"
    sources: dict[str, Any] = {}
    for skill_name in MANAGED_SKILLS:
        bundled = bundled_root.joinpath(skill_name)
        if bundled.joinpath("SKILL.md").is_file():
            sources[skill_name] = bundled
            continue
        development_source = development_root / skill_name
        if development_source.joinpath("SKILL.md").is_file():
            sources[skill_name] = development_source
            continue
        raise RuntimeError(
            f"The Museon CLI package does not contain its bundled {skill_name} Agent Skill."
        )
    return sources


def _install_one(
    source, agent: str, *, skill_name: str, force: bool
) -> dict[str, str]:
    destination = _agent_home(agent) / "skills" / skill_name
    source_digest = _tree_digest(source)
    if destination.is_dir() and _tree_digest(destination) == source_digest:
        return {
            "name": skill_name,
            "status": "current",
            "path": str(destination),
            "digest": source_digest,
        }
    if destination.exists() and not force and not _is_managed_skill(destination, skill_name):
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
        "name": skill_name,
        "status": "installed",
        "path": str(destination),
        "digest": source_digest,
    }


def _validate_destination(agent: str, *, skill_name: str, force: bool) -> None:
    destination = _agent_home(agent) / "skills" / skill_name
    if destination.exists() and not force and not _is_managed_skill(destination, skill_name):
        raise RuntimeError(
            f"Refusing to replace an unmanaged path: {destination}. "
            "Move it aside or rerun with --force."
        )


def _copy_tree(source, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        if child.name == "__pycache__" or child.name.endswith((".pyc", ".pyo")):
            continue
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
        if child.name == "__pycache__" or child.name.endswith((".pyc", ".pyo")):
            continue
        relative = f"{prefix}/{child.name}" if prefix else child.name
        if child.is_dir():
            yield from _walk_files(child, relative)
        elif child.is_file():
            yield relative, child


def _is_managed_skill(path: Path, skill_name: str) -> bool:
    skill_file = path / "SKILL.md"
    if not skill_file.is_file():
        return False
    try:
        return f"name: {skill_name}" in skill_file.read_text(encoding="utf-8")[:500]
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
