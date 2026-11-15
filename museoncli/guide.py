"""The task guide: which command to use for a job, in what order, and what to watch.

``contracts/task-index.yaml`` is written by hand: chapters of tasks, each an ordered
list of catalog commands with a one-line gotcha, plus topics for the concepts every
task shares (which id is which, the confirmation rule, organizations, overlapping
commands). Everything else (a command's usage line, risk, confirmation and summary)
comes from the live registry, so the guide never restates what the catalog owns.

``museoncli guide`` reads it locally; ``scripts/gen_task_index.py`` renders the same
data as the Agent Skill reference, ``docs/guide.md`` and ``docs/llms.txt``.
"""

from __future__ import annotations

import difflib
import fnmatch
import re
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

from museoncli.domains import (
    CommandSpec,
    command_specs,
    discoverable_command_specs,
)
from museoncli.domains._discovery import generated_example

INDEX_RESOURCE = "task_index.yaml"
SOURCE_INDEX = Path(__file__).resolve().parents[1] / "contracts" / "task-index.yaml"
GUIDE_URL = "https://www.museon.ai/cli/guide.md"
LLMS_URL = "https://www.museon.ai/cli/llms.txt"
INSTALL_URL = "https://www.museon.ai/cli/install.md"

# Commands about the CLI itself, which the registry does not describe.
BUILTINS: dict[str, dict[str, Any]] = {
    "guide": {
        "usage": "museoncli guide [<task-id>] [--search <words>]",
        "risk_level": "read",
        "summary": "Which command to use for a task: chapters and tasks, one task's ordered steps, "
        "or a search over tasks and commands. Local; needs no login.",
    },
    "schema": {
        "usage": "museoncli schema [<command>] [--compact] [--search <words>]",
        "risk_level": "read",
        "summary": "Describe commands: one command's inputs and outputs, a domain, or the whole "
        "catalog (--compact drops the authorization block; --search ranks matches). Local.",
    },
    "auth start": {
        "usage": "museoncli auth start",
        "risk_level": "write",
        "summary": "Start browser approval for this CLI and return the verification link to show "
        "the user.",
    },
    "auth finish": {
        "usage": "museoncli auth finish --wait",
        "risk_level": "write",
        "summary": "Finish the approval started by auth start; --wait waits up to five minutes.",
    },
    "auth status": {
        "usage": "museoncli auth status",
        "risk_level": "read",
        "summary": "Whether this CLI holds a credential, how it got it, and when it expires.",
    },
    "auth logout": {
        "usage": "museoncli auth logout",
        "risk_level": "write",
        "summary": "Delete the stored credential.",
    },
    "whoami": {
        "usage": "museoncli whoami",
        "risk_level": "read",
        "summary": "The signed-in user and the organizations this login can act in.",
    },
    "org list": {
        "usage": "museoncli org list",
        "risk_level": "read",
        "summary": "Organizations this login can act in.",
    },
    "org current": {
        "usage": "museoncli org current",
        "risk_level": "read",
        "summary": "The organization commands act in now.",
    },
    "org select": {
        "usage": "museoncli org select --id <organization-id>",
        "risk_level": "write",
        "summary": "Select the organization every later command acts in (or --name, exact).",
    },
    "version": {
        "usage": "museoncli version",
        "risk_level": "read",
        "summary": "This CLI's version, the latest release, how it was installed and the "
        "command that upgrades it.",
    },
    "upgrade": {
        "usage": "museoncli upgrade",
        "risk_level": "write",
        "summary": "Upgrade to the latest stable release, or print the command your installer "
        "needs.",
    },
    "setup": {
        "usage": "museoncli setup --agent <codex|claude-code|cursor|all>",
        "risk_level": "write",
        "summary": "Install the bundled Agent Skills for a host Agent.",
    },
}


class GuideError(ValueError):
    """The hand-written index disagrees with itself or with the command registry."""


# -- loading -----------------------------------------------------------------


def _index_text() -> str:
    packaged = files("museoncli") / INDEX_RESOURCE
    if packaged.is_file():
        return packaged.read_text(encoding="utf-8")
    # A source checkout: the wheel force-includes contracts/task-index.yaml as above.
    return SOURCE_INDEX.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def load_index() -> dict[str, Any]:
    data = yaml.safe_load(_index_text())
    if not isinstance(data, dict):
        raise GuideError("task index must be a mapping")
    return data


@lru_cache(maxsize=1)
def _specs_by_key() -> dict[str, CommandSpec]:
    return {spec.schema_name: spec for spec in command_specs()}


def _steps(task: dict[str, Any]) -> list[tuple[str, str]]:
    """A task's steps as (command, gotcha); a step is `command` or `{command: gotcha}`."""
    result = []
    for step in task.get("steps") or []:
        if isinstance(step, str):
            result.append((step, ""))
        elif isinstance(step, dict) and len(step) == 1:
            ((command, note),) = step.items()
            result.append((str(command), str(note or "").strip()))
        else:
            raise GuideError(f"task {task.get('id')}: a step is `command` or `{{command: note}}`")
    return result


def chapters() -> list[dict[str, Any]]:
    return list(load_index().get("chapters") or [])


def topics() -> list[dict[str, Any]]:
    return list(load_index().get("topics") or [])


def tasks() -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Every task with the chapter it sits in, in reading order."""
    return [(chapter, task) for chapter in chapters() for task in chapter.get("tasks") or []]


def unlisted() -> list[dict[str, Any]]:
    return list(load_index().get("unlisted") or [])


# -- what the registry knows about a command ---------------------------------


def usage(spec: CommandSpec) -> str:
    """The command with every required input; --yes is the user's call, never shown."""
    line = generated_example(spec)
    return line.removesuffix(" --yes")


def first_sentence(text: str, limit: int = 140) -> str:
    match = re.search(r"(?<!\be\.g)(?<!\bi\.e)(?<!\betc)(?<!\bvs)\.(\s|$)", text)
    sentence = text[: match.start() + 1] if match else text
    if len(sentence) > limit:
        cut = sentence[: limit - 1].rsplit(" ", 1)[0]
        sentence = cut.rstrip(",;:") + "…"
    return sentence


def risk_label(risk_level: str, requires_confirmation: bool) -> str:
    return f"{risk_level}, needs --yes" if requires_confirmation else risk_level


def command_card(command: str, *, full: bool = True) -> dict[str, Any]:
    """What the guide shows for one step's command."""
    if command in BUILTINS:
        entry = BUILTINS[command]
        return {
            "command": command,
            "usage": entry["usage"],
            "risk": entry["risk_level"],
            "needs_yes": False,
            "summary": entry["summary"],
        }
    spec = _specs_by_key().get(command)
    if spec is None:
        raise GuideError(f"unknown command in task index: {command}")
    return {
        "command": spec.schema_name,
        "usage": usage(spec),
        "risk": spec.risk_level,
        "needs_yes": spec.requires_confirmation,
        "summary": spec.summary if full else first_sentence(spec.summary),
    }


def compact_entry(spec: CommandSpec) -> dict[str, Any]:
    """`schema --compact`: enough to pick and call a command, without its contract."""
    return {
        "name": spec.schema_name,
        "usage": usage(spec),
        "risk_level": spec.risk_level,
        "requires_confirmation": spec.requires_confirmation,
        "summary": spec.summary,
    }


# -- validation (tests and the generator run it; `guide` trusts a built index) ----


def validate() -> list[str]:
    """Every problem with the index, empty when it is sound."""
    problems: list[str] = []
    index = load_index()
    seen: set[str] = set()

    def claim(kind: str, identifier: Any) -> None:
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", identifier):
            problems.append(f"{kind} id must be kebab-case: {identifier!r}")
            return
        if identifier in seen:
            problems.append(f"duplicate id: {identifier}")
        seen.add(identifier)

    for topic in topics():
        claim("topic", topic.get("id"))
        if not topic.get("title") or not (topic.get("body") or topic.get("rows")):
            problems.append(f"topic {topic.get('id')} needs a title and a body or rows")
        for row in topic.get("rows") or []:
            for key in [row.get("use"), *(row.get("not") or [])]:
                if key not in _specs_by_key() and key not in BUILTINS:
                    problems.append(f"topic {topic.get('id')}: unknown command {key}")
    for chapter in chapters():
        claim("chapter", chapter.get("id"))
        if not chapter.get("title") or not chapter.get("summary"):
            problems.append(f"chapter {chapter.get('id')} needs a title and a summary")
        if not chapter.get("tasks"):
            problems.append(f"chapter {chapter.get('id')} has no tasks")
    for _chapter, task in tasks():
        claim("task", task.get("id"))
        if not task.get("title") or not task.get("when"):
            problems.append(f"task {task.get('id')} needs a title and when keywords")
        try:
            steps = _steps(task)
        except GuideError as exc:
            problems.append(str(exc))
            continue
        if not steps:
            problems.append(f"task {task.get('id')} has no steps")
        for command, _note in steps:
            if command not in _specs_by_key() and command not in BUILTINS:
                problems.append(f"task {task.get('id')}: unknown command {command}")
    known = seen
    for chapter in chapters():
        for ref in chapter.get("see") or []:
            if ref not in known:
                problems.append(f"chapter {chapter.get('id')}: see {ref} does not exist")
    for _chapter, task in tasks():
        for ref in task.get("see") or []:
            if ref not in known:
                problems.append(f"task {task.get('id')}: see {ref} does not exist")
    for entry in unlisted():
        if not entry.get("match") or not entry.get("reason"):
            problems.append(f"unlisted entry needs match and reason: {entry!r}")
        elif not any(fnmatch.fnmatchcase(key, entry["match"]) for key in _specs_by_key()):
            problems.append(f"unlisted {entry['match']} matches no command")
    for key in uncovered_commands():
        problems.append(f"command in no task and not unlisted: {key}")
    if not isinstance(index.get("intro"), str):
        problems.append("index needs an intro")
    return problems


def referenced_commands() -> set[str]:
    referenced = {command for _chapter, task in tasks() for command, _ in _steps(task)}
    for topic in topics():
        for row in topic.get("rows") or []:
            referenced.update([row.get("use"), *(row.get("not") or [])])
    return referenced


def unlisted_reason(key: str) -> str | None:
    for entry in unlisted():
        if fnmatch.fnmatchcase(key, str(entry.get("match", ""))):
            return str(entry.get("reason", ""))
    return None


def uncovered_commands() -> list[str]:
    referenced = referenced_commands()
    return [
        spec.schema_name
        for spec in discoverable_command_specs()
        if spec.schema_name not in referenced and unlisted_reason(spec.schema_name) is None
    ]


# -- what `museoncli guide` prints ----------------------------------------------


def _task_line(task: dict[str, Any]) -> dict[str, str]:
    return {"id": task["id"], "title": task["title"]}


def overview() -> dict[str, Any]:
    index = load_index()
    return {
        "intro": index["intro"].strip(),
        "next": [
            "museoncli guide <task-id>   # the ordered commands for one task",
            "museoncli guide --search <words>   # find a task or command (English or 中文)",
            "museoncli schema <command>   # one command's full inputs and outputs",
        ],
        "topics": [{"id": topic["id"], "title": topic["title"]} for topic in topics()],
        "chapters": [
            {
                "id": chapter["id"],
                "title": chapter["title"],
                "tasks": [_task_line(task) for task in chapter.get("tasks") or []],
            }
            for chapter in chapters()
        ],
        "unlisted": [
            {"match": entry["match"], "reason": entry["reason"]} for entry in unlisted()
        ],
    }


def _see(refs: list[str]) -> list[dict[str, str]]:
    titles = {topic["id"]: topic["title"] for topic in topics()}
    titles.update({chapter["id"]: chapter["title"] for chapter in chapters()})
    titles.update({task["id"]: task["title"] for _chapter, task in tasks()})
    return [{"id": ref, "title": titles[ref]} for ref in refs if ref in titles]


def task_detail(task: dict[str, Any], chapter: dict[str, Any]) -> dict[str, Any]:
    steps = []
    for number, (command, note) in enumerate(_steps(task), start=1):
        card = command_card(command)
        steps.append({"step": number, **card, **({"note": note} if note else {})})
    return {
        "kind": "task",
        "id": task["id"],
        "title": task["title"],
        "chapter": {"id": chapter["id"], "title": chapter["title"]},
        "when": list(task.get("when") or []),
        **({"before": task["before"].strip()} if task.get("before") else {}),
        "steps": steps,
        "see": _see(list(task.get("see") or [])),
    }


def chapter_detail(chapter: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "chapter",
        "id": chapter["id"],
        "title": chapter["title"],
        "summary": chapter["summary"].strip(),
        "tasks": [
            {**_task_line(task), "when": list(task.get("when") or [])}
            for task in chapter.get("tasks") or []
        ],
        "see": _see(list(chapter.get("see") or [])),
    }


def topic_detail(topic: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"kind": "topic", "id": topic["id"], "title": topic["title"]}
    if topic.get("body"):
        result["body"] = topic["body"].strip()
    if topic.get("rows"):
        result["rows"] = [
            {
                "need": row["need"],
                "use": row["use"],
                **({"not": list(row["not"])} if row.get("not") else {}),
                **({"why": row["why"]} if row.get("why") else {}),
            }
            for row in topic["rows"]
        ]
    if topic.get("aliases"):
        result["renamed"] = renamed_commands()
    return result


def renamed_commands() -> list[dict[str, str]]:
    """Old command paths that still answer, and the name to use instead."""
    return [
        {"old": spec.legacy_cli_path(legacy), "use": spec.cli_path}
        for spec in discoverable_command_specs()
        for legacy in spec.legacy_shortcuts
    ]


def lookup(identifier: str) -> dict[str, Any]:
    wanted = identifier.strip()
    for chapter, task in tasks():
        if task["id"] == wanted:
            return task_detail(task, chapter)
    for chapter in chapters():
        if chapter["id"] == wanted:
            return chapter_detail(chapter)
    for topic in topics():
        if topic["id"] == wanted:
            return topic_detail(topic)
    ids = [task["id"] for _c, task in tasks()] + [c["id"] for c in chapters()]
    ids += [t["id"] for t in topics()]
    close = difflib.get_close_matches(wanted, ids, n=3, cutoff=0.5)
    hint = f" Did you mean {', '.join(close)}?" if close else ""
    raise LookupError(
        f"not_found: no task, chapter or topic named {wanted!r}.{hint} Run `museoncli guide` "
        f"for the list or `museoncli guide --search {wanted}`."
    )


# -- search ------------------------------------------------------------------


_CJK = re.compile(r"[\u3400-\u9fff]")


def _terms(words: list[str]) -> list[str]:
    terms: list[str] = []
    for word in words:
        for part in re.split(r"[\s,，、/]+", word.lower()):
            part = part.strip("+").strip()
            if part and part not in terms:
                terms.append(part)
    return terms


def _hits(term: str, text: str) -> bool:
    if _CJK.search(term):
        return term in text
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}", text) is not None


def _score(terms: list[str], weighted: list[tuple[int, str]]) -> int:
    score = 0
    matched = 0
    for term in terms:
        best = max((weight for weight, text in weighted if _hits(term, text)), default=0)
        if best:
            matched += 1
            score += best
    if not matched:
        return 0
    # A result that covers every word outranks one that repeats a single word.
    return score + (10 if matched == len(terms) else 0) * matched


def search(words: list[str], *, task_limit: int = 8, command_limit: int = 10) -> dict[str, Any]:
    terms = _terms(words)
    if not terms:
        raise ValueError("guide --search needs at least one word")
    phrase = " ".join(terms)
    ranked_tasks = []
    for chapter, task in tasks():
        when = " | ".join(task.get("when") or []).lower()
        steps = _steps(task)
        commands = " ".join(command for command, _ in steps).lower()
        notes = " ".join(note for _, note in steps).lower()
        weighted = [(6, when), (5, task["title"].lower()), (3, commands), (2, notes)]
        score = _score(terms, weighted) + (8 if _hits(phrase, when) else 0)
        if score:
            ranked_tasks.append((score, chapter, task))
    ranked_tasks.sort(key=lambda item: -item[0])
    # The commands of the best-matching tasks are what the guide would send you to.
    favoured = {
        command for _score_value, _chapter, task in ranked_tasks[:3] for command, _ in _steps(task)
    }
    ranked_commands = []
    for spec in discoverable_command_specs():
        legacy = " ".join(spec.legacy_cli_path(name) for name in spec.legacy_shortcuts)
        weighted = [
            (6, spec.cli_path.lower()),
            (5, spec.schema_name.lower()),
            (4, legacy.lower()),
            (2, spec.summary.lower()),
        ]
        score = _score(terms, weighted)
        if score:
            ranked_commands.append((score + (8 if spec.schema_name in favoured else 0), spec))
    ranked_commands.sort(key=lambda item: -item[0])
    task_ids_for = _tasks_by_command()
    return {
        "query": phrase,
        "tasks": [
            {
                **_task_line(task),
                "chapter": chapter["id"],
                "commands": [command for command, _ in _steps(task)],
            }
            for _score_value, chapter, task in ranked_tasks[:task_limit]
        ],
        "commands": [
            {
                "name": spec.schema_name,
                "usage": usage(spec),
                "risk": risk_label(spec.risk_level, spec.requires_confirmation),
                "summary": first_sentence(spec.summary),
                **(
                    {"in_tasks": task_ids_for[spec.schema_name]}
                    if spec.schema_name in task_ids_for
                    else {}
                ),
                **(
                    {"note": unlisted_reason(spec.schema_name)}
                    if unlisted_reason(spec.schema_name)
                    else {}
                ),
            }
            for _score_value, spec in ranked_commands[:command_limit]
        ],
        "next": "museoncli guide <task-id> for the steps; museoncli schema <name> for inputs.",
    }


def search_commands(words: list[str], *, limit: int = 20) -> list[dict[str, Any]]:
    """`schema --search`: the best-matching commands, compact."""
    found = search(words, task_limit=0, command_limit=limit)["commands"]
    specs = _specs_by_key()
    return [compact_entry(specs[item["name"]]) for item in found]


@lru_cache(maxsize=1)
def _tasks_by_command() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for _chapter, task in tasks():
        for command, _ in _steps(task):
            result.setdefault(command, [])
            if task["id"] not in result[command]:
                result[command].append(task["id"])
    return result


def guide_payload(task_id: str | None, search_words: list[str] | None) -> dict[str, Any]:
    if search_words:
        return search(search_words)
    if task_id:
        return lookup(task_id)
    return overview()


# -- Markdown renderings (scripts/gen_task_index.py writes them) ------------------


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _topic_markdown(topic: dict[str, Any], level: str) -> list[str]:
    lines = [f"{level} {topic['title']}", ""]
    if topic.get("body"):
        lines += [topic["body"].strip(), ""]
    if topic.get("rows"):
        lines += ["| Need | Use | Not | Why |", "|---|---|---|---|"]
        for row in topic["rows"]:
            not_ = ", ".join(f"`{_cli(key)}`" for key in row.get("not") or []) or "—"
            lines.append(
                f"| {_md_escape(row['need'])} | `{_cli(row['use'])}` | {not_} "
                f"| {_md_escape(row.get('why', ''))} |"
            )
        lines.append("")
    if topic.get("aliases"):
        lines += ["| Old name (still answers, deprecated) | Use |", "|---|---|"]
        for row in renamed_commands():
            # Without the `museoncli` prefix: docs name only commands that exist.
            old = row["old"].removeprefix("museoncli ")
            lines.append(f"| `{old}` | `{row['use']}` |")
        lines.append("")
    return lines


def _cli(command: str) -> str:
    if command in BUILTINS:
        return f"museoncli {command}"
    return _specs_by_key()[command].cli_path


GENERATED_NOTE = (
    "<!-- Generated by scripts/gen_task_index.py from contracts/task-index.yaml. "
    "Do not edit by hand. -->"
)


def render_skill_reference() -> str:
    """The Agent Skill's reference: every task as one line of commands, plus the topics."""
    from museoncli import __version__

    index = load_index()
    lines = [
        GENERATED_NOTE,
        "",
        f"# Task index (Museon CLI {__version__})",
        "",
        index["intro"].strip(),
        "",
        "Run `museoncli guide <task-id>` for a task's steps with each command's required flags, "
        "risk and gotcha; `museoncli guide --search <words>` finds a task from the user's words.",
        "",
    ]
    for chapter in chapters():
        lines += [f"## {chapter['title']}", "", chapter["summary"].strip(), ""]
        for task in chapter.get("tasks") or []:
            chain = " → ".join(f"`{_cli(command)}`" for command, _ in _steps(task))
            lines.append(f"- **{task['title']}** (`{task['id']}`): {chain}")
        lines.append("")
    lines += ["## Topics", ""]
    for topic in topics():
        if topic.get("aliases"):
            lines += [
                f"### {topic['title']}",
                "",
                topic["body"].strip(),
                "",
                "`museoncli guide --search <old name>` names the command to use instead.",
                "",
            ]
            continue
        lines += _topic_markdown(topic, "###")
    lines += ["## Not in this index", ""]
    for entry in unlisted():
        lines.append(f"- `{entry['match']}`: {entry['reason']}")
    lines.append("")
    return "\n".join(lines)


def _anchor(text: str) -> str:
    slug = re.sub(r"[^\w\- ]", "", text.lower()).strip().replace(" ", "-")
    return re.sub(r"-+", "-", slug)


def render_guide_markdown() -> str:
    """docs/guide.md: the whole index, each step with its usage line and gotcha."""
    from museoncli import __version__

    index = load_index()
    lines = [
        GENERATED_NOTE,
        "",
        f"# Museon CLI task guide ({__version__})",
        "",
        index["intro"].strip(),
        "",
        "The same guide runs locally: `museoncli guide`, `museoncli guide <task-id>`, "
        "`museoncli guide --search <words>`. `museoncli schema <command>` gives one command's "
        "full inputs and outputs.",
        "",
        "## Contents",
        "",
    ]
    for chapter in chapters():
        lines.append(f"- [{chapter['title']}](#{_anchor(chapter['title'])})")
    lines += ["- [Topics](#topics)", "- [Not in this guide](#not-in-this-guide)", ""]
    for chapter in chapters():
        lines += [f"## {chapter['title']}", "", chapter["summary"].strip(), ""]
        if chapter.get("see"):
            lines += ["See: " + ", ".join(f"`{ref}`" for ref in chapter["see"]), ""]
        for task in chapter.get("tasks") or []:
            lines += [f"### {task['title']}", ""]
            lines += [f"`museoncli guide {task['id']}` · when: {'; '.join(task['when'])}", ""]
            if task.get("before"):
                lines += [task["before"].strip(), ""]
            for number, (command, note) in enumerate(_steps(task), start=1):
                card = command_card(command)
                risk = risk_label(card["risk"], card["needs_yes"])
                text = f"{number}. `{card['usage']}` ({risk})"
                if note:
                    text += f": {note}"
                lines.append(text)
            if task.get("see"):
                lines += ["", "See: " + ", ".join(f"`{ref}`" for ref in task["see"])]
            lines.append("")
    lines += ["## Topics", ""]
    for topic in topics():
        lines += _topic_markdown(topic, "###")
    lines += ["## Not in this guide", ""]
    for entry in unlisted():
        lines.append(f"- `{entry['match']}`: {entry['reason']}")
    lines.append("")
    return "\n".join(lines)


def render_llms_txt() -> str:
    """docs/llms.txt: the short index the llms.txt convention asks for."""
    from museoncli import __version__

    index = load_index()
    lines = [
        "# Museon CLI",
        "",
        f"> {index['llms_summary'].strip()}",
        "",
        index["intro"].strip(),
        "",
        "## Start",
        "",
        f"- [Install guide]({INSTALL_URL}): install the CLI and its Agent Skills, sign in, "
        "choose an organization.",
        f"- [Task guide]({GUIDE_URL}): every task as ordered commands with their required flags, "
        f"risk and gotchas (Museon CLI {__version__}).",
        "- Offline, the CLI answers the same: `museoncli guide`, `museoncli guide <task-id>`, "
        "`museoncli guide --search <words>`, `museoncli schema <command>`.",
        "",
        "## Tasks",
        "",
    ]
    for chapter in chapters():
        ids = ", ".join(f"`{task['id']}`" for task in chapter.get("tasks") or [])
        lines.append(
            f"- [{chapter['title']}]({GUIDE_URL}#{_anchor(chapter['title'])}): "
            f"{first_sentence(chapter['summary'].strip(), 320)} Tasks: {ids}."
        )
    lines += ["", "## Optional", ""]
    lines.append(
        f"- [Topics]({GUIDE_URL}#topics): "
        + "; ".join(topic["title"] for topic in topics())
        + "."
    )
    lines.append(
        "- [Source and command contract](https://github.com/Museon-AI/museon-cli): "
        "`contracts/command-catalog.json` lists every command's schema."
    )
    lines.append("")
    return "\n".join(lines)


def compact_schema(name: str | None) -> dict[str, Any]:
    """`schema --compact`: the catalog, a domain or one command without schemas."""
    from museoncli.cli_commands import CLI_COMMANDS, cli_command, cli_command_summary
    from museoncli.domains import get_command_spec, specs_by_domain

    grouped = {
        domain: [compact_entry(spec) for spec in specs if spec.discoverable]
        for domain, specs in specs_by_domain().items()
    }
    if not name:
        return {
            "commands": {domain: entries for domain, entries in grouped.items() if entries},
            "cli": [cli_command_summary(entry) for entry in CLI_COMMANDS],
        }
    normalized = name.replace(".+", ".").strip().removeprefix("museoncli ").strip()
    entry = cli_command(normalized)
    if entry is not None:
        return cli_command_summary(entry)
    if normalized in grouped:
        return {"domain": normalized, "commands": grouped[normalized]}
    return compact_entry(get_command_spec(name))
