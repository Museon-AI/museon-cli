"""Publish finished videos to a workspace's bound social accounts on a schedule."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from museoncli.domains._model import CommandSpec, Domain
from museoncli.domains.hireaicreator import (
    B,
    DT,
    EXECUTORS,
    S,
    SEARCH_PAGE,
    PAGE,
    U,
    _command,
    arr,
    enum,
    obj,
)
from museoncli.envelopes import direct_api_envelope
from museoncli.execution import CommandContext

# One API batch holds at most 100 posts (one post = one video or photo set on one account).
_MAX_POSTS = 100
# A TikTok photo set holds at most 30 images through the cloud phone.
_MAX_IMAGES = 30
_SOURCES = ("file", "media_id", "image_files", "image_media_ids")
_PRODUCT_ID = {"type": "string", "pattern": r"^\d+$", "maxLength": 64}
_CAPTION = {"type": "string", "minLength": 1, "maxLength": 2200}
_MUSIC_URL = {
    "type": "string",
    "minLength": 1,
    "maxLength": 2048,
    "description": (
        "TikTok post link (tiktok.com/@user/video/<id> or /photo/<id>) whose sound the "
        "cloud phone reuses as background music, like tapping 'use this sound'."
    ),
}
_TIKTOK_POST_PATH = re.compile(r"/(?:video|photo)/(\d+)(?:/|$)")
_DELIVERY = (
    "delivery.stage tells where the post stands: verifying means the publishing service "
    "already reported its result (delivery.upstream) and Museon is confirming the post on the "
    "platform until delivery.verification.deadline_at; published, failed and cancelled are "
    "final. delivery is null for older jobs."
)
_POST_ITEM = obj(
    {
        "file": S,
        "media_id": U,
        "image_files": arr(S, 1, _MAX_IMAGES),
        "image_media_ids": arr(U, 1, _MAX_IMAGES),
        "account_ids": arr(U, 1, _MAX_POSTS),
        "caption": _CAPTION,
        "scheduled_at": DT,
        "product_id": _PRODUCT_ID,
        "music_url": _MUSIC_URL,
    },
    ("account_ids", "caption"),
)


def _digest_file(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _local_file(value: str) -> Path:
    path = Path(value).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"Not a file: {path}")
    return path


def _save(path: Path, record: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False))
    temporary.replace(path)


def _sound_video_id(url: str) -> str:
    """The TikTok post whose sound a cloud phone reuses; it takes a post, not a sound."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not (
        host == "tiktok.com" or host.endswith(".tiktok.com")
    ):
        raise ValueError(f"music_url must be a TikTok post link, got {url!r}")
    if match := _TIKTOK_POST_PATH.search(parts.path):
        return match.group(1)
    if parts.path.startswith("/music/"):
        raise ValueError(
            "music_url takes a post, not a sound page: open the sound, pick a post that uses "
            "it (listen for the version you want), and pass that post's link"
        )
    raise ValueError(
        f"Could not read a post id from music_url {url!r}; open short links (vm.tiktok.com, "
        "tiktok.com/t/) and pass the full tiktok.com/@user/video/<id> link"
    )


def _check_items(payload: dict[str, Any]) -> None:
    now = bool(payload.get("now"))
    posts = 0
    for item in payload["items"]:
        if sum(source in item for source in _SOURCES) != 1:
            raise ValueError(
                "Each item takes exactly one of file, media_id, image_files or image_media_ids"
            )
        images = item.get("image_files") or item.get("image_media_ids")
        if images is not None and len(set(images)) != len(images):
            raise ValueError("A photo set must not repeat an image")
        if images is not None and "product_id" in item:
            raise ValueError("product_id attaches only to video posts")
        if "music_url" in item:
            _sound_video_id(item["music_url"])
        if now == ("scheduled_at" in item):
            raise ValueError(
                "Give every item a scheduled_at, or pass now=true and omit scheduled_at"
            )
        if len(set(item["account_ids"])) != len(item["account_ids"]):
            raise ValueError("account_ids must not repeat within an item")
        posts += len(item["account_ids"])
    if posts > _MAX_POSTS:
        raise ValueError(f"A batch holds at most {_MAX_POSTS} posts (videos x accounts)")


async def _schedule(ctx: CommandContext) -> dict[str, Any]:
    args = ctx.arguments
    workspace_id = str(args.get("workspace_id") or ctx.workspace_id or "").strip()
    if not workspace_id:
        raise RuntimeError("missing_workspace")
    now = bool(args.get("now"))
    items = []
    for item in args["items"]:
        if "file" in item:
            path = _local_file(item["file"])
            item = {**item, "file": str(path), "sha256": _digest_file(path)}
        if "image_files" in item:
            paths = [_local_file(value) for value in item["image_files"]]
            item = {
                **item,
                "image_files": [str(path) for path in paths],
                "image_sha256": [_digest_file(path) for path in paths],
            }
        items.append(item)
    fingerprint = hashlib.sha256(
        json.dumps(
            {"now": now, "ai_tag": bool(args.get("ai_tag")), "items": items}, sort_keys=True
        ).encode()
    ).hexdigest()
    identity = json.dumps([ctx.cfg.api_base_url, workspace_id, args["idempotency_key"]])
    key = hashlib.sha256(identity.encode()).hexdigest()
    receipt_dir = (
        Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "museoncli" / "publish"
    )
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / f"{key}.json"
    lock_path = receipt_dir / f"{key}.lock"
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(
            f"Publish is already running, or was interrupted; inspect {lock_path} before retrying"
        ) from exc
    os.close(lock_fd)
    try:
        record = (
            json.loads(receipt_path.read_text())
            if receipt_path.exists()
            else {"fingerprint": fingerprint, "uploaded": {}}
        )
        if record["fingerprint"] != fingerprint:
            raise ValueError("Idempotency key was already used for different files or targets")
        if "receipt" in record:
            return record["receipt"]
        _save(receipt_path, record)
        wire_items = []

        async def uploaded(path: str, digest: str, media_type: str) -> str:
            if digest not in record["uploaded"]:
                upload = await ctx.upload_media_file(
                    ctx.cfg,
                    workspace_id=workspace_id,
                    arguments={"file": path, "media_type": media_type},
                )
                record["uploaded"][digest] = upload["data"]["asset"]["media_id"]
                _save(receipt_path, record)
            return str(record["uploaded"][digest])

        for item in items:
            image_ids: list[str] | None = item.get("image_media_ids")
            if "image_files" in item:
                image_ids = [
                    await uploaded(path, digest, "image")
                    for path, digest in zip(item["image_files"], item["image_sha256"], strict=True)
                ]
            media_id = item.get("media_id")
            if "file" in item:
                media_id = await uploaded(item["file"], item["sha256"], "video")
            for account_id in item["account_ids"]:
                wire_items.append(
                    {
                        "content_id": image_ids[0] if image_ids else media_id,
                        "content_type": "image" if image_ids else "video",
                        **({"image_media_ids": image_ids} if image_ids else {}),
                        "account_id": account_id,
                        # The server ignores scheduled times for an immediate batch,
                        # but still requires the field.
                        "scheduled_at": item.get("scheduled_at") or "1970-01-01T00:00:00Z",
                        "caption": item["caption"],
                        **({"product_id": item["product_id"]} if "product_id" in item else {}),
                        **(
                            {"bgm_config": {"ref_video_id": _sound_video_id(item["music_url"])}}
                            if "music_url" in item
                            else {}
                        ),
                    }
                )
        body = {
            "workspace_id": workspace_id,
            "items": wire_items,
            "ai_tag": bool(args.get("ai_tag")),
            "publish_immediately": now,
        }
        # The server stores the same key and replays the batch it first accepted,
        # so a retry after a lost response cannot create a second post.
        raw = await ctx.api_data_v2(
            ctx.cfg,
            "POST",
            "/pool-accounts/publish",
            json_body=body,
            idempotency_key=args["idempotency_key"],
            unwrap_success=False,
        )
        receipt = direct_api_envelope(
            ctx.spec.schema_name, workspace_id, raw, site_url=ctx.cfg.site_url
        )
        receipt["warnings"].append(
            "Accepted publish tasks, not proof of public posts. Read each task for its final state."
        )
        receipt["next_steps"].append(
            "museoncli publish job +list --task-id TASK_ID; each job reports its status and error."
        )
        record["receipt"] = receipt
        _save(receipt_path, record)
        return receipt
    finally:
        lock_path.unlink(missing_ok=True)


def _schedule_spec() -> CommandSpec:
    base = _command(
        "post",
        "schedule",
        "POST",
        "/pool-accounts/publish",
        {
            "items": arr(_POST_ITEM, 1, _MAX_POSTS),
            "now": {**B, "description": "Publish at once instead of at each scheduled_at."},
            "ai_tag": {**B, "description": "Mark the posts as AI-generated on the platform."},
        },
        required=("items",),
        workspace="body",
        write=True,
        idempotent=True,
        domain=Domain.PUBLISH,
        summary=(
            "Upload local videos or photo sets (or reuse media IDs) and schedule each on the "
            "workspace's bound accounts with a caption. Each item takes one of file / media_id "
            "(a video) or image_files / image_media_ids (a TikTok photo set of 1-30 images, in "
            "order), plus account_ids, caption, and scheduled_at with a timezone offset; or pass "
            "now=true to publish at once. At most 100 posts per batch, 2 per account per day, "
            "120 minutes apart, up to 7 days ahead. ai_tag marks the posts as AI-generated; "
            "product_id attaches a TikTok Shop product to a video; music_url, a TikTok post "
            "link, gives the post that post's sound on a cloud-phone account (other accounts "
            "publish without it). "
            "Retry with the same idempotency key and unchanged files: uploads are reused and the "
            "server returns the batch it already accepted."
        ),
        readback="museoncli publish job +list --task-id TASK_ID; scheduled posts are not public yet.",
    )
    original_build = base.build_arguments

    def build(args: Any) -> dict[str, Any]:
        payload = original_build(args)
        _check_items(payload)
        return payload

    EXECUTORS[base.schema_name] = _schedule
    return replace(base, build_arguments=build)


def specs() -> list[CommandSpec]:
    return [
        _command(
            "account",
            "list",
            "GET",
            "/pool-accounts/workspace-accounts",
            {
                **SEARCH_PAGE,
                "platform": arr(S),
                "device_kind": arr(enum("cloud-phone", "real-device")),
                "is_active": B,
            },
            domain=Domain.PUBLISH,
            summary=(
                "List the social accounts bound to this workspace, which are the accounts it "
                "can publish to. Filter by platform (tiktok) and device kind; follow every page "
                "before choosing accounts."
            ),
        ),
        _schedule_spec(),
        _command(
            "job",
            "list",
            "GET",
            "/pool-accounts/jobs",
            {**PAGE, "task_id": U, "status": S},
            domain=Domain.PUBLISH,
            summary=(
                "List publish jobs (one per video and account) with status, scheduled time, "
                "error and delivery; --task-id narrows to one batch returned by publish post "
                f"+schedule. {_DELIVERY}"
            ),
        ),
        _command(
            "job",
            "get",
            "GET",
            "/pool-accounts/jobs/{id}",
            {},
            domain=Domain.PUBLISH,
            summary=f"Read one publish job's status, scheduled time, error and delivery. {_DELIVERY}",
        ),
        _command(
            "job",
            "cancel",
            "POST",
            "/pool-accounts/jobs/{id}/cancel",
            {},
            write=True,
            domain=Domain.PUBLISH,
            summary=(
                "Cancel a publish job that has not been published yet (scheduled no more than an "
                "hour ago). Requires a workspace editor."
            ),
            readback="museoncli publish job +get --id JOB_ID; verify status cancelled.",
        ),
    ]
