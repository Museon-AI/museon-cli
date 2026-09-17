"""Format maintenance and warmup diagnostics using the existing v2 API."""

from dataclasses import replace

from museoncli.domains._model import CommandSpec
from museoncli.domains.hireaicreator import POSITIVE_INT, U, _command, arr, enum, nullable


def specs() -> list[CommandSpec]:
    patch = _command(
        "format",
        "patch",
        "PATCH",
        "/ai-hook-formats/{id}",
        {
            "expected_version": nullable(POSITIVE_INT),
            "name": nullable({"type": "string", "minLength": 1, "maxLength": 200}),
            "bgm_id": nullable(U),
            "pov_id": nullable(U),
            "viral_playbook_override": nullable({"type": "string", "maxLength": 2000}),
        },
        write=True,
        summary="Edit Format name, BGM, POV or playbook. Supply the read version to detect stale edits. Empty playbook string clears its override; null does not clear links.",
        readback="hireaicreator format +get --id FORMAT_ID; verify version and edited fields, then check +warmup-readiness.",
    )
    original_build = patch.build_arguments

    def build(args):
        payload = original_build(args)
        if all(
            payload.get(key) is None
            for key in ("name", "bgm_id", "pov_id", "viral_playbook_override")
        ):
            raise ValueError("Provide name, bgm_id, pov_id, or viral_playbook_override")
        if payload.get("name") is not None and not payload["name"].strip():
            raise ValueError("name must not be blank")
        return payload

    return [
        _command(
            "format",
            "tags",
            "GET",
            "/ai-hook-formats/tags",
            {},
            summary="List the workspace's existing Format tags.",
        ),
        _command(
            "format",
            "warmup-readiness",
            "POST",
            "/ai-hook-formats/warmup-readiness",
            {"format_ids": arr(U, 1)},
            required=("format_ids",),
            workspace="body",
            summary="Read Format readiness, revisions and issues for warmup; does not start generation.",
        ),
        replace(patch, build_arguments=build),
        _command(
            "format",
            "retry",
            "POST",
            "/ai-hook-formats/{id}/retry",
            {"step": enum("ingest", "hook", "pov", "bgm", "viral")},
            required=("step",),
            write=True,
            requires_confirmation=True,
            summary="Retry one Format processing step; may incur generation work and requires --yes. No server version or idempotency key is supported.",
            readback="hireaicreator format +get --id FORMAT_ID; poll the selected step and errors before retrying again.",
        ),
        _command(
            "format",
            "delete",
            "DELETE",
            "/ai-hook-formats/{id}",
            {},
            write=True,
            destructive=True,
            summary="Delete a Format from this workspace; requires --yes. Read current details first; no server version or idempotency key is supported.",
            readback="hireaicreator format +get --id FORMAT_ID; verify not_found.",
        ),
    ]
