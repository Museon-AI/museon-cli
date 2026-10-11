"""Upload local finished videos and register durable account publication tasks."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from museoncli.domains.hireaicreator import B, DT, S, TZ, U, EXECUTORS, _command, arr, obj
from museoncli.envelopes import direct_api_envelope
from museoncli.execution import CommandContext


_CAMPAIGN_REQUIRED = "UPLOADED_CAMPAIGN_REQUIRED"


def _digest_file(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _save(path: Path, record: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False))
    temporary.replace(path)


async def _publish(ctx: CommandContext) -> dict[str, Any]:
    args = ctx.arguments
    workspace_id = str(args.get("workspace_id") or ctx.workspace_id or "").strip()
    if not workspace_id:
        raise RuntimeError("missing_workspace")
    campaign_id = args["campaign_id"]
    items = args["items"]
    account_ids = sorted({value for item in items for value in item["account_ids"]})
    if len(account_ids) > 200:
        raise ValueError("Select at most 200 accounts per batch")
    fingerprint_items = []
    for item in items:
        path = Path(item["file"]).expanduser().resolve(strict=True)
        if not path.is_file():
            raise ValueError(f"Not a file: {path}")
        if bool(item.get("now")) == bool(item.get("scheduled_at")):
            raise ValueError("Each item requires exactly one of now=true or scheduled_at")
        fingerprint_items.append({**item, "file": str(path), "sha256": _digest_file(path)})
    fingerprint = hashlib.sha256(json.dumps(fingerprint_items, sort_keys=True).encode()).hexdigest()
    identity = json.dumps([ctx.cfg.api_base_url, workspace_id, args["idempotency_key"]])
    key = hashlib.sha256(identity.encode()).hexdigest()
    receipt_dir = (
        Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "museoncli" / "publication"
    )
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / f"{key}.json"
    lock_path = receipt_dir / f"{key}.lock"
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(
            f"Publication is already running, or interrupted; inspect {lock_path} before retrying"
        ) from exc
    os.close(lock_fd)
    try:
        record = (
            json.loads(receipt_path.read_text())
            if receipt_path.exists()
            else {"fingerprint": fingerprint, "uploaded": {}, "scheduled_now": None}
        )
        if record["fingerprint"] != fingerprint:
            raise ValueError("Idempotency key was already used for different files or targets")
        # Kept outside the fingerprint so receipts written before campaigns were
        # required stay readable; the server rejects a batch it already accepted.
        if record.get("campaign_id") not in (None, campaign_id):
            raise ValueError("Idempotency key was already used for a different campaign")
        if "receipt" in record:
            return record["receipt"]
        # A receipt that reached submission without a campaign predates the
        # requirement: the server may hold that batch, and only its original
        # body replays it.
        replay_legacy = "campaign_id" not in record and record["scheduled_now"] is not None
        if not replay_legacy:
            record["campaign_id"] = campaign_id
        settings = await ctx.api_data_v2(
            ctx.cfg,
            "POST",
            "/pool-accounts/publication-settings:read",
            json_body={"workspace_id": workspace_id, "account_ids": account_ids},
            unwrap_success=True,
        )
        blocked = [row["id"] for row in settings["items"] if not row["ready"]]
        if blocked:
            raise ValueError("Accounts are not ready for publication: " + ", ".join(blocked))
        _save(receipt_path, record)
        payload_items = []
        for item in fingerprint_items:
            digest = item["sha256"]
            if digest not in record["uploaded"]:
                upload = await ctx.upload_media_file(
                    ctx.cfg,
                    workspace_id=workspace_id,
                    arguments={"file": item["file"], "media_type": "video"},
                )
                record["uploaded"][digest] = upload["data"]["asset"]["media_id"]
                _save(receipt_path, record)
            payload_items.append(
                {
                    "media_id": record["uploaded"][digest],
                    "publishing_account_ids": item["account_ids"],
                    "caption": item["caption"],
                    "scheduled_at": item.get("scheduled_at") or "now",
                    "schedule_timezone": item.get("schedule_timezone", "UTC"),
                }
            )
        if record["scheduled_now"] is None:
            record["scheduled_now"] = (datetime.now(UTC) + timedelta(seconds=30)).isoformat()
            _save(receipt_path, record)
        for item in payload_items:
            if item["scheduled_at"] == "now":
                item["scheduled_at"] = record["scheduled_now"]
        body = {"workspace_id": workspace_id, "items": payload_items}

        async def submit(json_body: dict[str, Any]) -> Any:
            return await ctx.api_data_v2(
                ctx.cfg,
                "POST",
                "/ai-hook-videos/from-upload",
                json_body=json_body,
                idempotency_key=args["idempotency_key"],
                unwrap_success=True,
            )

        raw = None
        if replay_legacy:
            try:
                raw = await submit(body)
            except RuntimeError as exc:
                detail = getattr(exc, "detail", None)
                if (
                    getattr(exc, "status_code", None) != 409
                    or not isinstance(detail, dict)
                    or detail.get("code") != _CAMPAIGN_REQUIRED
                ):
                    raise
                # Never accepted, so it is new work and takes the campaign.
                record["campaign_id"] = campaign_id
                _save(receipt_path, record)
        if raw is None:
            raw = await submit({**body, "campaign_id": campaign_id})
        receipt = direct_api_envelope(
            ctx.spec.schema_name, workspace_id, raw, site_url=ctx.cfg.site_url
        )
        receipt["warnings"].append(
            "Accepted publication tasks, not proof of public posts. Read each video for final delivery state."
        )
        record["receipt"] = receipt
        _save(receipt_path, record)
        return receipt
    finally:
        lock_path.unlink(missing_ok=True)


def specs():
    spec = _command(
        "video",
        "publish-local",
        "POST",
        "/ai-hook-videos/from-upload",
        {
            "campaign_id": U,
            "items": arr(
                obj(
                    {
                        "file": S,
                        "account_ids": arr(U, 1, 100),
                        "caption": S,
                        "scheduled_at": DT,
                        "now": B,
                        "schedule_timezone": TZ,
                    },
                    ("file", "account_ids", "caption"),
                ),
                1,
                50,
            ),
        },
        required=("campaign_id", "items"),
        workspace="body",
        write=True,
        idempotent=True,
        summary="Upload local finished videos into a campaign and schedule each on explicit accounts. Requires campaign_id; each item has file, account_ids, caption, and either now=true or scheduled_at. Uses account publication settings; disabled/unready accounts fail before upload. Local receipts reuse uploads on retry; retain the idempotency key and files unchanged.",
        readback="Use hireaicreator video +get for returned video IDs; drafts are not public posts.",
    )
    EXECUTORS[spec.schema_name] = _publish
    return [spec]
