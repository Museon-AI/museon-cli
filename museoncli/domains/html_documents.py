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
_DOCUMENT = "11111111-1111-4111-8111-111111111111"
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
    "private": {
        "type": "boolean",
        "default": False,
        "description": (
            "Keep the upload inside the organization. By default it is shared: anyone with "
            "the returned share_url can open it without signing in."
        ),
    },
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
_SHARE = {
    "id": uuid_property("Document to share or stop sharing (html-documents +list)."),
    "dry_run": DRY_RUN_PROPERTY,
}


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


def _id_lookup_hint() -> str:
    """Name only the list/get shortcuts this domain actually registers."""
    present = {
        spec.shortcut
        for spec in specs()
        if spec.resource is None and spec.shortcut in {"+list", "+get"}
    }
    names = [name for name in ("+list", "+get") if name in present]
    which = " or ".join(names) if names else "+list"
    return f"Look the ID up first with the matching {which} command."


def _blank_query() -> None:
    from museoncli.main import UsageError

    raise UsageError("--q must be 1-200 characters.", command="html-documents.list")


def _folder_argument(value: str) -> str:
    """``root`` in any case, or a folder id. Anything else says ``root`` is valid."""
    if value.lower() == "root":
        return "root"
    try:
        return uuid_arg(value, flag="--folder", lookup=_id_lookup_hint())
    except ValueError:
        raise ValueError(
            "--folder must be the literal root or a canonical UUID "
            f"(e.g. {_FOLDER}), got {value!r}. {_id_lookup_hint()}"
        ) from None


def _folder_id_argument(value: str) -> str:
    return uuid_arg(value, flag="--folder-id", lookup=_id_lookup_hint())


# -- executors ---------------------------------------------------------------


async def _execute_upload(ctx: CommandContext) -> Any:
    arguments = ctx.arguments
    raw_path = str(arguments["file"])
    html = _read_html(Path(raw_path).expanduser())
    body: dict[str, Any] = {
        "title": arguments["title"],
        "html": html,
        "is_shared": not arguments.get("private", False),
    }
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
    return _sharing_result(data, shared=not arguments.get("private", False))


def _sharing_result(data: Any, *, shared: bool) -> tuple[Any, list[str], list[str]]:
    share_url = data.get("share_url") if isinstance(data, dict) else None
    warnings = []
    if shared and not share_url:
        warnings.append(
            "No share URL was returned. Check html-documents +list before retrying; "
            "this response does not confirm public sharing."
        )
    next_steps = ["museoncli html-documents +list"]
    if share_url:
        next_steps.insert(0, f"Share this link with your customer: {share_url}")
    return data, warnings, next_steps


async def _execute_share(ctx: CommandContext) -> Any:
    data = await ctx.api_data(
        ctx.cfg,
        "POST",
        f"{_library(require_organization(ctx))}/{ctx.arguments['id']}/share",
    )
    return _sharing_result(data, shared=True)


async def _execute_unshare(ctx: CommandContext) -> Any:
    return await ctx.api_data(
        ctx.cfg,
        "DELETE",
        f"{_library(require_organization(ctx))}/{ctx.arguments['id']}/share",
    )


async def _execute_list(ctx: CommandContext) -> Any:
    arguments = ctx.arguments
    folder = arguments.get("folder")
    if isinstance(folder, str) and folder.strip():
        folder = _folder_argument(folder.strip())
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
    parser.add_argument(
        "--private",
        action="store_true",
        help="Keep this upload private. By default anyone with its share link can view it.",
    )
    parser.add_argument("--dry-run", action="store_true")


def _build_upload_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ("file", "title", "filename", "folder_id", "private"))
    reject_unknown(payload, _UPLOAD)
    require(payload, "file", "title")
    private = payload.setdefault("private", False)
    if not isinstance(private, bool):
        raise ValueError("private must be a boolean (true or false).")
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
        payload["folder_id"] = _folder_id_argument(str(payload["folder_id"]))
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
        if not query:
            _blank_query()
        if len(query) > 200:
            raise ValueError("--q must be at most 200 characters.")
        payload["q"] = query
    folder = payload.get("folder")
    if isinstance(folder, str):
        folder = folder.strip()
        if not folder:
            payload.pop("folder", None)
        else:
            payload["folder"] = _folder_argument(folder)
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


def _add_share_arguments(parser: argparse.ArgumentParser) -> None:
    add_structured_arguments(parser)
    parser.add_argument("--id")
    parser.add_argument("--dry-run", action="store_true")


def _build_share_arguments(args: argparse.Namespace) -> dict[str, Any]:
    payload = merged_input(args, ("id",))
    reject_unknown(payload, _SHARE)
    require(payload, "id")
    payload["id"] = uuid_arg(str(payload["id"]), flag="--id", lookup=_id_lookup_hint())
    _dry_run(args, payload)
    return payload


def specs() -> list[CommandSpec]:
    domain = Domain.HTML_DOCUMENTS
    return [
        CommandSpec(
            domain=domain,
            shortcut="+upload",
            summary=(
                "Upload one local HTML file with --title and return a Museon share_url that "
                "customers can open without signing in. Anyone with the link can view it; "
                "use --private to keep it inside the organization. The stored filename is "
                "--filename, or the file's basename when it is "
                "one *.html or *.htm name with no '..' or slash; otherwise the server names it "
                "from the title. Titles may repeat, so a second upload is a second document: "
                "after an unknown outcome, +list before retrying." + _EDIT
            ),
            risk_level="write",
            execution="direct",
            adapter_tool_name="html_documents_upload",
            input_schema=schema(_UPLOAD, ["file", "title"]),
            output_schema=output_schema(
                "data: id, title, filename, folder_id, slug, updated_at, html, share_url. "
                "Give the customer share_url exactly as returned; it is null for private uploads."
            ),
            examples=[
                'museoncli html-documents +upload --file ./proposal.html --title "Customer proposal"',
                (
                    "museoncli html-documents +upload --file ./guide.html "
                    f'--title "Architecture notes" --private --filename guide.html --folder-id {_FOLDER}'
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
                "(id, title, filename, folder_id, slug, updated_at, share_url). "
                "share_url is null when sharing is off."
            ),
            examples=["museoncli html-documents +list --q architecture --folder root"],
            add_arguments=_add_list_arguments,
            build_arguments=_build_list_arguments,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+share",
            summary=(
                "Enable customer sharing for one existing HTML document. Anyone with the "
                "returned share_url can view it without signing in. An active link is reused; "
                "after +unshare this creates a new link and the old one stays invalid." + _EDIT
            ),
            risk_level="write",
            execution="direct",
            adapter_tool_name="html_documents_share",
            input_schema=schema(_SHARE, ["id"]),
            output_schema=output_schema(
                "data: the document with share_url. Give this URL to the customer exactly as returned."
            ),
            examples=[f"museoncli html-documents +share --id {_DOCUMENT}"],
            add_arguments=_add_share_arguments,
            build_arguments=_build_share_arguments,
            supports_dry_run=True,
        ),
        CommandSpec(
            domain=domain,
            shortcut="+unshare",
            summary=(
                "Stop customer sharing for one HTML document. Its current link stops working "
                "for new visits; already downloaded copies cannot be recalled. The document "
                "stays in the organization library. Sharing it again creates a new link." + _EDIT
            ),
            risk_level="write",
            execution="direct",
            adapter_tool_name="html_documents_unshare",
            input_schema=schema(_SHARE, ["id"]),
            output_schema=output_schema("data: the document with share_url set to null."),
            examples=[f"museoncli html-documents +unshare --id {_DOCUMENT}"],
            add_arguments=_add_share_arguments,
            build_arguments=_build_share_arguments,
            supports_dry_run=True,
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
    "html-documents.share": with_notes(_execute_share),
    "html-documents.unshare": direct_enveloped(_execute_unshare),
    "html-documents.folder-create": with_notes(_execute_folder_create),
    "html-documents.install-defaults": direct_enveloped(_execute_install_defaults),
}
