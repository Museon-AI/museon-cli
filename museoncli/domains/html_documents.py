"""An organization's HTML document library.

Documents and one-level folders belong to the organization in the path. The CLI
sends that organization as ``X-Organization-Id`` and never a workspace or a
``parent_id``. Reads need asset read and writes need asset edit; the server decides.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains._org_commands import (
    DRY_RUN_PROPERTY,
    add_structured_arguments,
    merged_input,
    output_schema,
    reject_unknown,
    require,
    require_organization,
    schema,
    string_property,
    uuid_property,
    with_notes,
)
from museoncli.domains._writes import uuid_arg
from museoncli.execution import CommandContext, direct_enveloped

MAX_HTML_BYTES = 1_500_000
_MAX_FILENAME = 180
_FOLDER = "72defd40-39ad-40d3-8105-8f23a9a016da"
_EDIT = " Needs asset edit on the organization; the server decides."

_UPLOAD = {
    "file": string_property("Local HTML file to upload.", max_length=4096),
    "title": string_property("Document title.", max_length=200),
    "filename": string_property(
        "Stored filename. A path is reduced to its basename, and only a single "
        "*.html or *.htm name with no '..' or slash is sent. Omit it to use that "
        "basename when the file has one, or to let the server name the file from the title.",
        max_length=_MAX_FILENAME,
    ),
    "folder_id": uuid_property("Folder to store the document in (html-documents +list)."),
    "dry_run": DRY_RUN_PROPERTY,
}
_LIST = {
    "q": string_property(
        "Search document titles. The title matches when it contains this text.", max_length=200
    ),
    "folder": string_property(
        "Which documents to list: omit for all, root for documents in no folder, or a folder id.",
        max_length=80,
    ),
}
_FOLDER_CREATE = {
    "name": string_property(
        "Folder name. Folders are one level and cannot contain a folder.", max_length=80
    ),
    "dry_run": DRY_RUN_PROPERTY,
}
_INSTALL = {"dry_run": DRY_RUN_PROPERTY}


def _basename(value: str) -> str:
    return value.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def _acceptable_filename(name: str) -> bool:
    return (
        bool(name)
        and len(name) <= _MAX_FILENAME
        and "/" not in name
        and "\\" not in name
        and "\x00" not in name
        and name not in {".", ".."}
        and ".." not in name
        and name.lower().endswith((".html", ".htm"))
    )


def filename_to_send(path: str, explicit: str | None) -> str | None:
    """The filename to store, or None so the server names the file from the title.

    A path contributes its basename only when that basename is one ``*.html`` or
    ``*.htm`` name with no ``..`` or slash.
    """
    raw = explicit.strip() if explicit is not None else path.strip()
    given = explicit is not None and bool(explicit.strip())
    if not given:
        raw = path.strip()
    if _acceptable_filename(raw):
        return raw
    base = _basename(raw)
    if _acceptable_filename(base):
        return base
    if given:
        raise ValueError("--filename must be a single *.html or *.htm name with no '..' or slash.")
    return None


def _read_html(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"--file is not a file: {path}")
    if path.stat().st_size > MAX_HTML_BYTES:
        raise ValueError(f"--file is larger than {MAX_HTML_BYTES} bytes.")
    try:
        html = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("--file must be UTF-8 HTML.") from exc
    if not html.strip() or "\x00" in html or len(html.encode("utf-8")) > MAX_HTML_BYTES:
        raise ValueError("--file must be non-empty UTF-8 HTML.")
    return html


def _library(organization_id: str) -> str:
    return f"/organizations/{organization_id}/html-documents"


# -- executors ---------------------------------------------------------------


async def _execute_upload(ctx: CommandContext) -> Any:
    arguments = ctx.arguments
    raw_path = str(arguments["file"])
    html = _read_html(Path(raw_path).expanduser())
    body: dict[str, Any] = {"title": arguments["title"], "html": html}
    filename = filename_to_send(raw_path, arguments.get("filename"))
    if filename is not None:
        body["filename"] = filename
    if arguments.get("folder_id"):
        body["folder_id"] = arguments["folder_id"]
    data = await ctx.api_data(
        ctx.cfg,
        "POST",
        _library(require_organization(ctx)),
        json_body=body,
    )
    return data, [], ["museoncli html-documents +list"]


async def _execute_list(ctx: CommandContext) -> Any:
    arguments = ctx.arguments
    folder = arguments.get("folder")
    if isinstance(folder, str) and folder != "root":
        folder = uuid_arg(folder, flag="--folder")
    params: dict[str, Any] = {}
    if arguments.get("q"):
        params["q"] = arguments["q"]
    if folder:
        params["folder"] = folder
    return await ctx.api_data(
        ctx.cfg,
        "GET",
        _library(require_organization(ctx)),
        params=params or None,
    )


async def _execute_folder_create(ctx: CommandContext) -> Any:
    data = await ctx.api_data(
        ctx.cfg,
        "POST",
        f"{_library(require_organization(ctx))}/folders",
        json_body={"name": ctx.arguments["name"]},
    )
    return (
        data,
        [
            "Creating a folder has no idempotency key: after an unknown outcome, run "
            "html-documents +list before trying again."
        ],
        ["museoncli html-documents +list"],
    )


async def _execute_install_defaults(ctx: CommandContext) -> Any:
    return await ctx.api_data(ctx.cfg, "POST", f"{_library(require_organization(ctx))}/defaults")


def _dry_run(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["dry_run"] = bool(getattr(args, "dry_run", False) or payload.get("dry_run"))


def _add_upload_arguments(parser: argparse.ArgumentParser) -> None:
    add_structured_arguments(parser)
    parser.add_argument("--file")
    parser.add_argument("--title")
    parser.add_argument("--filename")
    parser.add_argument("--folder-id", dest="folder_id")
    parser.add_argument("--dry-run", action="store_true")


def _build_upload_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ("file", "title", "filename", "folder_id"))
    reject_unknown(payload, _UPLOAD)
    require(payload, "file", "title")
    title = str(payload["title"]).strip()
    if not 1 <= len(title) <= 200:
        raise ValueError("--title must be 1-200 characters.")
    payload["title"] = title
    explicit = payload.get("filename")
    resolved = filename_to_send(
        str(payload["file"]), explicit if isinstance(explicit, str) else None
    )
    if resolved is None:
        payload.pop("filename", None)
    else:
        payload["filename"] = resolved
    if payload.get("folder_id"):
        payload["folder_id"] = uuid_arg(payload["folder_id"], flag="--folder-id")
    else:
        payload.pop("folder_id", None)
    _read_html(Path(str(payload["file"])).expanduser())
    _dry_run(args, payload)
    return payload


def _add_list_arguments(parser: argparse.ArgumentParser) -> None:
    add_structured_arguments(parser)
    parser.add_argument("--q")
    parser.add_argument("--folder")


def _build_list_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ("q", "folder"))
    reject_unknown(payload, _LIST)
    query = payload.get("q")
    if isinstance(query, str):
        query = query.strip()
        if query:
            if len(query) > 200:
                raise ValueError("--q must be at most 200 characters.")
            payload["q"] = query
        else:
            payload.pop("q", None)
    folder = payload.get("folder")
    if isinstance(folder, str):
        folder = folder.strip()
        if not folder:
            payload.pop("folder", None)
        elif folder != "root":
            payload["folder"] = uuid_arg(folder, flag="--folder")
        else:
            payload["folder"] = folder
    return payload


def _add_folder_arguments(parser: argparse.ArgumentParser) -> None:
    add_structured_arguments(parser)
    parser.add_argument("--name")
    parser.add_argument("--dry-run", action="store_true")


def _build_folder_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ("name",))
    reject_unknown(payload, _FOLDER_CREATE)
    require(payload, "name")
    name = str(payload["name"]).strip()
    if not 1 <= len(name) <= 80:
        raise ValueError("--name must be 1-80 characters.")
    payload["name"] = name
    _dry_run(args, payload)
    return payload


def _add_install_arguments(parser: argparse.ArgumentParser) -> None:
    add_structured_arguments(parser)
    parser.add_argument("--dry-run", action="store_true")


def _build_install_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ())
    reject_unknown(payload, _INSTALL)
    _dry_run(args, payload)
    return payload


def specs() -> list[CommandSpec]:
    domain = Domain.HTML_DOCUMENTS
    return [
        CommandSpec(
            domain=domain,
            shortcut="+upload",
            summary=(
                "Upload one local HTML file into this organization's document library with "
                "--title. The stored filename is --filename, or the file's basename when it is "
                "one *.html or *.htm name with no '..' or slash; otherwise the server names it "
                "from the title. Titles may repeat, so a second upload is a second document: "
                "after an unknown outcome, +list before retrying." + _EDIT
            ),
            risk_level="write",
            execution="direct",
            adapter_tool_name="html_documents_upload",
            input_schema=schema(_UPLOAD, ["file", "title"]),
            output_schema=output_schema(
                "data: id, title, filename, folder_id, slug, updated_at, html."
            ),
            examples=[
                'museoncli html-documents +upload --file ./guide.html --title "Architecture notes"',
                (
                    "museoncli html-documents +upload --file ./guide.html "
                    f'--title "Architecture notes" --filename guide.html --folder-id {_FOLDER}'
                ),
            ],
            add_arguments=_add_upload_arguments,
            build_arguments=_build_upload_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+list",
            summary=(
                "List this organization's HTML documents and its one-level folders. --q searches "
                "titles. --folder is omitted (every document), root (no folder), or a folder id. "
                "Anyone who can read the organization's assets can list; the server decides."
            ),
            risk_level="read",
            execution="direct",
            adapter_tool_name="html_documents_list",
            input_schema=schema(_LIST),
            output_schema=output_schema(
                "data: folders (id, name, document_count), root_count, and documents "
                "(id, title, filename, folder_id, slug, updated_at)."
            ),
            examples=["museoncli html-documents +list --q architecture --folder root"],
            add_arguments=_add_list_arguments,
            build_arguments=_build_list_arguments,
        ),
        CommandSpec(
            domain=domain,
            resource="folder",
            shortcut="+create",
            summary=(
                "Create one folder in this organization's HTML document library. Folders do not "
                "nest, and the request sends the name only. No idempotency key: after an unknown "
                "outcome, +list before retrying." + _EDIT
            ),
            risk_level="write",
            execution="direct",
            adapter_tool_name="html_documents_folder_create",
            input_schema=schema(_FOLDER_CREATE, ["name"]),
            output_schema=output_schema("data: id, name, document_count."),
            examples=["museoncli html-documents folder +create --name Guides"],
            add_arguments=_add_folder_arguments,
            build_arguments=_build_folder_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+install-defaults",
            summary=(
                "Copy the three built-in HTML guides into this organization. Running it again "
                "does not add duplicates." + _EDIT
            ),
            risk_level="write",
            execution="direct",
            adapter_tool_name="html_documents_install_defaults",
            input_schema=schema(_INSTALL),
            output_schema=output_schema(
                "data: the library after the guides are copied (folders, root_count, documents)."
            ),
            examples=["museoncli html-documents +install-defaults"],
            add_arguments=_add_install_arguments,
            build_arguments=_build_install_arguments,
            supports_dry_run=True,
        ),
    ]


EXECUTORS = {
    "html-documents.upload": with_notes(_execute_upload),
    "html-documents.list": direct_enveloped(_execute_list),
    "html-documents.folder-create": with_notes(_execute_folder_create),
    "html-documents.install-defaults": direct_enveloped(_execute_install_defaults),
}
