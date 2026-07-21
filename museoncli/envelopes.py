"""Part of the museoncli domains/executors architecture (see docs/museoncli-optimization-plan.md)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from museoncli.config import DEFAULT_SITE_URL


GENERATION_RECOMMENDED_WAKEUP_DELAY_SECONDS = 300


def domain_command_dry_run_envelope(
    command_name: str,
    workspace_id: str | None,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    return {
        "command": command_name,
        "workspace": {"id": workspace_id} if workspace_id else None,
        "data": {
            "dry_run": True,
            "arguments": arguments,
            "would_execute": command_name,
        },
        "run": None,
        "warnings": [],
        "next_steps": ["Re-run without --dry-run to execute."],
    }


def domain_command_envelope(
    command_name: str,
    adapter_response: Any,
    *,
    site_url: str = DEFAULT_SITE_URL,
) -> dict[str, Any]:
    response = adapter_response if isinstance(adapter_response, dict) else {}
    job = response.get("job")
    data = response.get("result")
    if command_name.startswith("generation.") or _is_async_generation_command(command_name):
        data = add_generation_refs(data, site_url=site_url)
    run = None
    if isinstance(job, dict):
        run_id = job.get("id")
        run = {
            "id": run_id,
            "status": job.get("status"),
        }
    elif _is_async_generation_command(command_name):
        run = _generation_run_from_data(data)
    return {
        "command": command_name,
        "workspace": response.get("workspace"),
        "data": without_provider_metadata(data) if not isinstance(job, dict) else None,
        "run": run,
        "warnings": [],
        "next_steps": _generation_next_steps(run) if run else [],
    }


def direct_api_envelope(
    command_name: str,
    workspace_id: str | None,
    data: Any,
    *,
    site_url: str = DEFAULT_SITE_URL,
) -> dict[str, Any]:
    if command_name.startswith("generation.") or _is_async_generation_command(command_name):
        data = add_generation_refs(data, site_url=site_url)
    if _is_async_generation_command(command_name):
        run = _generation_run_from_data(data)
    elif command_name == "content-analysis.run":
        run = _content_analysis_run_from_data(data)
    elif command_name in {
        "social-account.profile-edit-submit",
        "social-account.profile-edit-batch-submit",
    }:
        run = _profile_edit_run_from_data(data)
    elif command_name == "social-account.avatar-generate-batch":
        run = _avatar_generate_run_from_data(data)
    elif command_name == "account-publish.asset-pools-batch-set":
        run = _asset_pools_batch_run_from_data(data)
    elif command_name == "account-publish.schedule-plan-batch":
        run = _schedule_plan_run_from_data(data)
    else:
        run = None
    warnings = _direct_api_warnings(command_name)
    return {
        "command": command_name,
        "workspace": {"id": workspace_id} if workspace_id else None,
        "data": without_provider_metadata(data),
        "run": run,
        "warnings": warnings,
        "next_steps": (
            _run_next_steps(run) if run else _social_auth_next_steps(command_name, data)
        ),
    }


_PROVIDER_METADATA_KEYS = {
    "provider",
    "provider_name",
    "auth_provider",
    "fallback_provider",
    "console_url",
    "dataset_url",
}

_PROVIDER_NEUTRAL_KEYS = {
    "provider_status": "delivery_status",
    "provider_status_code": "upstream_status_code",
    "provider_semantics": "delivery_semantics",
    "provider_breakdown": "delivery_breakdown",
    "provider_error": "delivery_error",
    "provider_error_code": "delivery_error_code",
    "from_provider": "from_external_service",
    "raw_provider_payload_available": "raw_external_payload_available",
    "provider_executing": "delivery_executing",
    "provider_succeeded_awaiting_visibility": "delivery_succeeded_awaiting_visibility",
}


def without_provider_metadata(value: Any) -> Any:
    """Hide provider identity while preserving the public result's semantics."""
    if isinstance(value, dict):
        return {
            _PROVIDER_NEUTRAL_KEYS.get(key, key): without_provider_metadata(item)
            for key, item in value.items()
            if key not in _PROVIDER_METADATA_KEYS
        }
    if isinstance(value, list):
        return [without_provider_metadata(item) for item in value]
    return value


def _direct_api_warnings(command_name: str) -> list[str]:
    if command_name in {
        "campaign-monitor.post-list",
        "campaign-monitor.creator-performance-get",
        "campaign-monitor.post-performance-get",
    }:
        return [
            (
                "This command reads Museon's synced monitor store only; use "
                "campaign-monitor +content-list/+creator-list/+summary for "
                "campaign-scoped collections and research +social-media-search "
                "for external discovery."
            )
        ]
    return []


# Asset types that render as embeddable resource cards in artifacts (each gets a
# ready-made `ref`). bgm / tag are intentionally excluded: the web app has no
# card renderer or `/<section>/<id>` detail route for them, so a ref would only
# produce a dead / 404 link.
EMBEDDABLE_ASSET_TYPES = {"product", "persona", "topic", "format"}


# Resource type -> museon.ai URL section. Shared contract with the web frontend;
# keep in sync when adding embeddable resource types.
RESOURCE_TYPE_TO_SECTION = {
    "generation": "generations",
    "persona": "personas",
    "product": "products",
    "topic": "topics",
    "schedule": "routines",
    "work": "posts",
    "format": "formats",
}


def resource_ref_url(site_url: str, resource_type: str, encoded_resource_id: str) -> str:
    section = RESOURCE_TYPE_TO_SECTION.get(resource_type, resource_type)
    base = site_url.rstrip("/")
    if resource_type in EMBEDDABLE_ASSET_TYPES:
        return f"{base}/assets/{section}/{encoded_resource_id}"
    return f"{base}/{section}/{encoded_resource_id}"


_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]+")


_WHITESPACE_RE = re.compile(r"\s+")


def add_asset_refs(data: Any, *, asset_type: Any, site_url: str = DEFAULT_SITE_URL) -> Any:
    if not isinstance(asset_type, str) or asset_type not in EMBEDDABLE_ASSET_TYPES:
        return data
    if isinstance(data, list):
        for item in data:
            add_asset_ref_to_resource(item, asset_type=asset_type, site_url=site_url)
        return data
    if isinstance(data, dict):
        if isinstance(data.get("items"), list):
            for item in data["items"]:
                add_asset_ref_to_resource(item, asset_type=asset_type, site_url=site_url)
            return data
        add_asset_ref_to_resource(data, asset_type=asset_type, site_url=site_url)
    return data


def add_asset_ref_to_resource(
    resource: Any, *, asset_type: str, site_url: str = DEFAULT_SITE_URL
) -> None:
    if not isinstance(resource, dict):
        return
    resource_id = resource.get("id")
    if resource_id is None:
        return
    resource_id_text = str(resource_id).strip()
    if not resource_id_text:
        return
    display_name = resource.get("title") or resource.get("name") or resource_id_text
    display_name_text = normalize_asset_ref_label(str(display_name)) or resource_id_text
    encoded_resource_id = quote(resource_id_text, safe="")
    url = resource_ref_url(site_url, asset_type, encoded_resource_id)
    resource["ref"] = f"[{markdown_link_label(display_name_text)}]({url})"


def add_routine_refs(data: Any, *, site_url: str = DEFAULT_SITE_URL) -> Any:
    if isinstance(data, list):
        for item in data:
            add_routine_ref_to_resource(item, site_url=site_url)
        return data
    if isinstance(data, dict):
        if isinstance(data.get("items"), list):
            for item in data["items"]:
                add_routine_ref_to_resource(item, site_url=site_url)
            return data
        add_routine_ref_to_resource(data, site_url=site_url)
    return data


def add_routine_ref_to_resource(resource: Any, *, site_url: str = DEFAULT_SITE_URL) -> None:
    if not isinstance(resource, dict):
        return
    resource_id = resource.get("id")
    if resource_id is None:
        return
    resource_id_text = str(resource_id).strip()
    if not resource_id_text:
        return
    display_name = resource.get("name") or resource_id_text
    display_name_text = normalize_asset_ref_label(str(display_name)) or resource_id_text
    encoded_resource_id = quote(resource_id_text, safe="")
    url = resource_ref_url(site_url, "schedule", encoded_resource_id)
    resource["ref"] = f"[{markdown_link_label(display_name_text)}]({url})"
    add_routine_owner_anchor_labels(resource)


def add_routine_owner_anchor_labels(resource: dict[str, Any]) -> None:
    owner_user_id = _clean_label_value(resource.get("created_by_user_id"))
    owner_display_name = _clean_label_value(resource.get("owner_display_name"))
    if owner_user_id or owner_display_name:
        resource["owner_label"] = owner_display_name or owner_user_id

    trigger = resource.get("active_trigger")
    if not isinstance(trigger, dict):
        return
    source = _clean_label_value(trigger.get("source_conversation_id"))
    source_message = _clean_label_value(trigger.get("source_channel_message_id"))
    target = _routine_target_label(trigger)
    if source or source_message or target:
        source_label = source or (f"message:{source_message}" if source_message else "source")
        target_label = target or "source"
        resource["anchor_label"] = f"source={source_label}; target={target_label}"


def _routine_target_label(trigger: dict[str, Any]) -> str | None:
    other_scope_conversation_id = _clean_label_value(trigger.get("other_scope_conversation_id"))
    result_delivery_mode = _clean_label_value(trigger.get("result_delivery_mode"))
    if other_scope_conversation_id:
        suffix = f":{result_delivery_mode}" if result_delivery_mode else ""
        return f"other_scope:{other_scope_conversation_id}{suffix}"
    if result_delivery_mode:
        return f"source:{result_delivery_mode}"
    target_conversation_id = _clean_label_value(trigger.get("target_conversation_id"))
    if target_conversation_id:
        return target_conversation_id
    target_channel_chat_id = _clean_label_value(trigger.get("target_channel_chat_id"))
    if not target_channel_chat_id:
        return None
    target_channel_id = _clean_label_value(trigger.get("target_channel_id"))
    if target_channel_id:
        return f"{target_channel_id}/{target_channel_chat_id}"
    return target_channel_chat_id


def _clean_label_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def add_generation_refs(data: Any, *, site_url: str = DEFAULT_SITE_URL) -> Any:
    if isinstance(data, list):
        for item in data:
            add_generation_ref_to_resource(item, site_url=site_url)
        return data
    if isinstance(data, dict):
        if isinstance(data.get("items"), list):
            for item in data["items"]:
                add_generation_ref_to_resource(item, site_url=site_url)
            return data
        for key in ("resource", "row", "generation"):
            nested = data.get(key)
            if isinstance(nested, dict):
                add_generation_ref_to_resource(nested, site_url=site_url)
                return data
        add_generation_ref_to_resource(data, site_url=site_url)
    return data


def add_generation_ref_to_resource(resource: Any, *, site_url: str = DEFAULT_SITE_URL) -> None:
    if not isinstance(resource, dict):
        return
    resource_id = resource.get("generation_id") or resource.get("id")
    if resource_id is None:
        return
    resource_id_text = str(resource_id).strip()
    if not resource_id_text:
        return
    display_name = (
        resource.get("title")
        or resource.get("name")
        or _generation_snapshot_name(resource)
        or resource_id_text
    )
    display_name_text = normalize_asset_ref_label(str(display_name)) or resource_id_text
    encoded_resource_id = quote(resource_id_text, safe="")
    url = resource_ref_url(site_url, "generation", encoded_resource_id)
    resource["ref"] = f"[{markdown_link_label(display_name_text)}]({url})"


def _generation_snapshot_name(resource: dict[str, Any]) -> str | None:
    for key in ("content_topic_snapshot", "format_snapshot"):
        snapshot = resource.get(key)
        if not isinstance(snapshot, dict):
            continue
        for name_key in ("title", "name"):
            value = snapshot.get(name_key)
            if isinstance(value, str) and value.strip():
                return value
    return None


def normalize_asset_ref_label(value: str) -> str:
    without_controls = _CONTROL_CHARS_RE.sub(" ", value)
    return _WHITESPACE_RE.sub(" ", without_controls).strip()


def markdown_link_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _is_async_generation_command(command_name: str) -> bool:
    return command_name in {
        "generation.create",
        "social-account.schedule-generate",
    }


def _generation_run_from_data(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    row = data.get("row")
    nested_generation = data.get("generation")
    if isinstance(row, dict):
        generation = row
    elif isinstance(nested_generation, dict):
        generation = nested_generation
    else:
        generation = data
    nested_resource = data.get("resource")
    if isinstance(nested_resource, dict):
        generation = nested_resource
    generation_id = generation.get("generation_id") or generation.get("id")
    if not generation_id and generation is not data:
        generation_id = data.get("generation_id")
    if not generation_id:
        return None
    run = {
        "id": generation_id,
        "type": "slideshow_generation",
        "status": generation.get("status"),
        "watch_command": (f"museoncli generation +get --type slideshow --id {generation_id}"),
        "recommended_wakeup_delay_seconds": GENERATION_RECOMMENDED_WAKEUP_DELAY_SECONDS,
    }
    ref = generation.get("ref")
    if isinstance(ref, str) and ref:
        run["ref"] = ref
    return run


def _generation_next_steps(run: dict[str, Any] | None) -> list[str]:
    if not run:
        return []
    steps: list[str] = []
    ref = run.get("ref")
    if isinstance(ref, str) and ref:
        steps.append(
            "Include run.ref in the customer-facing final response now. Tell the customer "
            "generation is in progress and this link shows live generation progress."
        )
    watch_command = run.get("watch_command")
    wakeup_delay = run.get("recommended_wakeup_delay_seconds")
    if isinstance(watch_command, str) and watch_command:
        if isinstance(wakeup_delay, int) and wakeup_delay > 0:
            steps.append(
                f"Schedule a wakeup in {wakeup_delay} seconds, then poll with: {watch_command}"
            )
        else:
            steps.append(f"Poll with: {watch_command}")
        return steps
    steps.append("Poll the returned generation id with generation +get.")
    return steps


def _content_analysis_run_from_data(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    run_id = data.get("run_id")
    if not run_id:
        return None
    return {
        "id": run_id,
        "kind": "content_analysis",
        "type": data.get("analysis_type"),
        "status": data.get("status"),
        "cached": data.get("cached"),
        "watch_command": f"museoncli content-analysis +get --id {run_id}",
    }


def _profile_edit_run_from_data(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    task_id = _profile_edit_task_id(data)
    if not task_id:
        return None
    provider_status = data.get("provider_status")
    summary = provider_status.get("summary") if isinstance(provider_status, dict) else None
    return {
        "id": task_id,
        "type": "pool_account_profile_edit",
        "status": _profile_edit_run_status(
            data=data,
            provider_status=provider_status,
            summary=summary,
        ),
        "watch_command": f"museoncli social-account +profile-edit-status --id {task_id}",
    }


def _avatar_generate_run_from_data(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    task_id = _profile_edit_task_id(data)
    if not task_id:
        return None
    provider_status = data.get("provider_status")
    summary = provider_status.get("summary") if isinstance(provider_status, dict) else None
    return {
        "id": task_id,
        "type": "pool_account_avatar_generation",
        "status": _avatar_generate_run_status(
            data=data,
            provider_status=provider_status,
            summary=summary,
        ),
        "watch_command": f"museoncli social-account +avatar-generate-status --id {task_id}",
    }


def _avatar_generate_run_status(
    *,
    data: dict[str, Any],
    provider_status: Any,
    summary: Any,
) -> str | None:
    if isinstance(provider_status, dict) and provider_status.get("timed_out") is True:
        return "timed_out"
    if not isinstance(summary, dict):
        status_value = data.get("status")
        return str(status_value) if status_value is not None else None

    succeeded = int(summary.get("succeeded") or 0)
    failed = int(summary.get("failed") or 0)
    settled = summary.get("settled") is True
    if not settled:
        return "running"
    if failed > 0 and succeeded > 0:
        return "partial_failed"
    if failed > 0:
        return "failed"
    if succeeded > 0:
        return "completed"
    return "completed" if settled else "running"


def _schedule_plan_run_from_data(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    nested_job = data.get("job")
    job = nested_job if isinstance(nested_job, dict) else data
    job_id = job.get("job_id") or job.get("id") or data.get("job_id")
    if not job_id:
        return None
    run: dict[str, Any] = {
        "id": job_id,
        "type": "account_publish_schedule_plan",
        "status": job.get("status") or data.get("status"),
        "watch_command": f"museoncli account-publish +schedule-plan-status --id {job_id}",
    }
    delay = job.get("recommended_wakeup_delay_seconds") or data.get(
        "recommended_wakeup_delay_seconds"
    )
    if isinstance(delay, int) and delay > 0:
        run["recommended_wakeup_delay_seconds"] = delay
    return run


def _asset_pools_batch_run_from_data(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    nested_job = data.get("job")
    job = nested_job if isinstance(nested_job, dict) else data
    job_id = job.get("job_id") or job.get("id") or data.get("job_id")
    if not job_id:
        return None
    run: dict[str, Any] = {
        "id": job_id,
        "type": "account_publish_asset_pools_batch",
        "status": job.get("status") or data.get("status"),
        "watch_command": f"museoncli account-publish +asset-pools-batch-status --id {job_id}",
    }
    delay = job.get("recommended_wakeup_delay_seconds") or data.get(
        "recommended_wakeup_delay_seconds"
    )
    if isinstance(delay, int) and delay > 0:
        run["recommended_wakeup_delay_seconds"] = delay
    return run


def _profile_edit_run_status(
    *,
    data: dict[str, Any],
    provider_status: Any,
    summary: Any,
) -> str | None:
    if isinstance(provider_status, dict) and provider_status.get("timed_out") is True:
        return "timed_out"
    if not isinstance(summary, dict):
        status_value = data.get("status")
        return str(status_value) if status_value is not None else None

    completed = int(summary.get("completed") or 0)
    failed = int(summary.get("failed") or 0)
    pending = int(summary.get("pending") or 0)
    settled = summary.get("settled") is True
    if pending > 0 or not settled:
        return "running"
    if failed > 0 and completed > 0:
        return "partial_failed"
    if failed > 0:
        return "failed"
    if completed > 0:
        return "completed"
    return "completed" if settled else "running"


def _run_next_steps(run: dict[str, Any] | None) -> list[str]:
    if not run:
        return []
    if run.get("type") == "pool_account_profile_edit":
        watch_command = run.get("watch_command")
        if isinstance(watch_command, str) and watch_command:
            return [f"Check profile edit status with: {watch_command}"]
        return ["Check the returned task id with social-account +profile-edit-status."]
    if run.get("type") == "pool_account_avatar_generation":
        watch_command = run.get("watch_command")
        if isinstance(watch_command, str) and watch_command:
            return [
                f"Poll avatar generation with: {watch_command}. Then feed the "
                "succeeded accounts' avatar_url into social-account "
                "+profile-edit-batch-submit."
            ]
        return ["Poll the returned task id with social-account +avatar-generate-status."]
    if run.get("kind") == "content_analysis":
        status_value = str(run.get("status") or "").lower()
        if status_value in {"completed", "failed", "cancelled", "canceled"}:
            return []
        watch_command = run.get("watch_command")
        if isinstance(watch_command, str) and watch_command:
            return [f"Poll with: {watch_command}"]
        return ["Poll the returned run id with content-analysis +get."]
    if run.get("type") == "account_publish_schedule_plan":
        watch_command = run.get("watch_command")
        wakeup_delay = run.get("recommended_wakeup_delay_seconds")
        if isinstance(watch_command, str) and watch_command:
            if isinstance(wakeup_delay, int) and wakeup_delay > 0:
                return [
                    f"Schedule one batch wakeup in {wakeup_delay} seconds, then poll only with: "
                    f"{watch_command}"
                ]
            return [f"Poll only with: {watch_command}"]
        return ["Poll the returned job id with account-publish +schedule-plan-status."]
    if run.get("type") == "account_publish_asset_pools_batch":
        watch_command = run.get("watch_command")
        wakeup_delay = run.get("recommended_wakeup_delay_seconds")
        if isinstance(watch_command, str) and watch_command:
            if isinstance(wakeup_delay, int) and wakeup_delay > 0:
                return [
                    f"Schedule one batch wakeup in {wakeup_delay} seconds, then poll only with: "
                    f"{watch_command}"
                ]
            return [f"Poll only with: {watch_command}"]
        return ["Poll the returned job id with account-publish +asset-pools-batch-status."]
    return _generation_next_steps(run)


def _social_auth_next_steps(command_name: str, data: Any) -> list[str]:
    if not isinstance(data, dict):
        return []
    if command_name == "social-account.connect-link-create":
        link_id = data.get("id")
        url = data.get("url")
        status_check_supported = data.get("status_check_supported") is not False
        steps: list[str] = []
        if isinstance(url, str) and url:
            steps.append(f"Open the returned url to authorize: {url}")
        if status_check_supported and isinstance(link_id, str) and link_id:
            steps.append(
                "Poll with: museoncli social-account +connect-link-status "
                f"--id {link_id} --wait --timeout 300"
            )
        return steps
    if command_name == "social-account.connect-link-status" and data.get("status") == "pending":
        link_id = data.get("link_id")
        if isinstance(link_id, str) and link_id:
            return [
                "Still pending. Poll with: museoncli social-account +connect-link-status "
                f"--id {link_id} --wait --timeout 300"
            ]
    if command_name == "social-account.performance-get":
        return _performance_page_next_steps(data)
    return []


def _performance_page_next_steps(data: dict[str, Any]) -> list[str]:
    steps: list[str] = []
    account = data.get("account")
    account_id = str(account.get("id") or "") if isinstance(account, dict) else ""
    page = data.get("page")
    if isinstance(page, dict) and page.get("has_more"):
        next_cursor = page.get("next_cursor")
        if isinstance(next_cursor, str) and next_cursor and account_id:
            steps.append(
                "More posts available: museoncli social-account +performance-get "
                f"--id {account_id} --cursor {next_cursor}"
            )
    if isinstance(account, dict) and account.get("auth_status") == "expired":
        steps.append(
            "Account authorization is expired; renew it with "
            "social-account +connect-link-create before relying on this data."
        )
    return steps


def format_create_envelope(
    command_name: str,
    workspace_id: str,
    api_response: Any,
) -> dict[str, Any]:
    response = api_response if isinstance(api_response, dict) else {}
    format_id = response.get("format_id")
    return {
        "command": command_name,
        "workspace": {"id": workspace_id},
        "data": response,
        "run": {
            "id": format_id,
            "type": "format_analysis",
            "status": response.get("status"),
            "watch_command": (
                f"museoncli asset +get --type format --id {format_id}" if format_id else None
            ),
        },
        "warnings": [],
        "next_steps": [
            f"Poll with: museoncli asset +get --type format --id {format_id}"
            if format_id
            else "Poll the returned format_id with asset +get --type format."
        ],
    }


def run_status_envelope(command_name: str, adapter_response: Any) -> dict[str, Any]:
    response = adapter_response if isinstance(adapter_response, dict) else {}
    run_id = response.get("run_id") or response.get("job_id") or response.get("id")
    run_type = response.get("run_type") or response.get("job_type")
    data = {
        "run_id": run_id,
        "status": response.get("status"),
        "run_type": run_type,
        "found": response.get("found", True),
        "result": response.get("result"),
        "error": response.get("error"),
        "execution_ref": response.get("execution_ref", {}),
        "current_stages": response.get("current_stages", []),
        "summary": response.get("summary", {}),
    }
    return {
        "command": command_name,
        "workspace": None,
        "data": data,
        "run": {
            "id": run_id,
            "status": response.get("status"),
        },
        "warnings": [],
        "next_steps": [],
    }


def _profile_edit_task_id(result: Any) -> str | None:
    if not isinstance(result, dict):
        return None
    task_id = result.get("task_id")
    if isinstance(task_id, str) and task_id:
        return task_id
    task = result.get("task")
    if isinstance(task, dict):
        nested_id = task.get("id")
        if isinstance(nested_id, str) and nested_id:
            return nested_id
    return None
