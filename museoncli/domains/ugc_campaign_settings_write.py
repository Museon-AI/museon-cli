"""UGC Campaign setup writes, each saved the way the web's Campaign setup page saves it.

- `campaign-settings +update`: the settings object (`PUT /campaigns/{id}/settings`),
  merged from the live settings with only the passed fields changed, plus the
  publishing-platform pay rule (`PATCH /campaigns/{id}/pricing`), in the page's order.
- `campaign-staff +set`: the Campaign team, PMs and OPs (`PUT .../staff`).
- `delivery-target`: the delivery targets (`/campaigns/{id}/targets`).
- `contract-template +set`: the creator contract (`PUT .../contract-template`).
- `discord-server`: the Campaign's Discord server (`.../discord/guild-link`, `.../guild/initialize`).
- `dm-rule`: the Comment-to-DM rule (`.../dm-rules`).
- `payscale` and `pay-rate`: who is paid what (`/campaigns/{id}/payscales`, `/payscales/{id}`,
  `/pay-rates/{id}`).

Reads for these settings are `ugc` read commands; the dry run of every write here
also returns what it read. Permissions are decided by the server.
"""

from __future__ import annotations

import argparse
import re
from typing import Any
from urllib.parse import urlparse

from museoncli.domains import _ugc_write as w
from museoncli.domains._model import CommandSpec
from museoncli.domains._shared import dekebab, kebab_choices
from museoncli.domains.ugc import _with_notes
from museoncli.execution import CommandContext

# -- campaign settings -------------------------------------------------------

SETTINGS_FIELDS = (
    "name",
    "campaign_type",
    "allowed_platforms",
    "content_languages",
    "target_countries",
    "required_platforms",
    "files_only",
    "content_intake",
    "brief_mode",
    "join_mode",
    "approval_mode",
    "stay_rules",
    "warmup_rules",
    "trial_rules",
    "post_grouping",
    "view_tracking_days",
    "pay_trial_reels",
    "payout_release",
    "budget_cap_cents",
    "discord_onboarding_enabled",
)
"""`CampaignSettingsWrite`: the whole object the page writes back."""
JSON_SETTINGS = {
    "content_intake",
    "stay_rules",
    "warmup_rules",
    "trial_rules",
    "application_form",
    "content_languages",
    "target_countries",
}
"""Fields only `--settings-json` sets (the flags cover the rest). The paid view window and the
Trial Reels switch are not editable on the setup page, so not here either."""
APPROVAL_MODES = ["auto", "manual"]
JOIN_MODES = ["open", "invite_only"]
POST_GROUPINGS = ["highest_platform", "combined_views", "per_post"]
BRIEF_MODES = ["creator_choice", "written"]
TEAM_SETTINGS = (
    "join_mode",
    "approval_mode",
    "stay_rules",
    "warmup_rules",
    "trial_rules",
    "budget_cap_cents",
    "discord_onboarding_enabled",
    "application_form",
)
_LANGUAGE = re.compile(r"^[a-z]{2}$")
_COUNTRY = re.compile(r"^[A-Z]{2}$")


def _platforms_of_rules(rules: Any) -> set[str]:
    if not isinstance(rules, dict):
        return set()
    return {
        platform
        for rule in w._dicts(rules.get("rules"))
        for platform in rule.get("platforms") or []
    }


def _validate_settings(settings: dict[str, Any], edited: set[str]) -> None:
    """The page's checks on what this write changes; the workbench checks them again."""
    allowed = settings.get("allowed_platforms") or []
    if "allowed_platforms" in edited and not allowed:
        raise ValueError("A Campaign needs at least one allowed platform.")
    if edited & {"allowed_platforms", "required_platforms"}:
        missing = [p for p in settings.get("required_platforms") or [] if p not in allowed]
        if missing:
            raise ValueError(
                "Required platforms must be allowed platforms too: "
                f"{', '.join(missing)} is not allowed."
            )
    languages = settings.get("content_languages") or []
    if "content_languages" in edited and (
        len(languages) > 10 or not all(_LANGUAGE.match(str(item)) for item in languages)
    ):
        raise ValueError("content_languages takes at most 10 two-letter lowercase codes (en, zh).")
    countries = settings.get("target_countries") or []
    if "target_countries" in edited and (
        len(countries) > 50 or not all(_COUNTRY.match(str(item)) for item in countries)
    ):
        raise ValueError("target_countries takes at most 50 two-letter uppercase codes (US, GB).")


def _merge_settings(current: dict[str, Any], edits: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current)
    for field, value in edits.items():
        if isinstance(value, dict) and isinstance(current.get(field), dict):
            # A nested rule set changes only the keys given.
            merged[field] = {**current[field], **value}
        else:
            merged[field] = value
    return merged


async def _execute_settings_update(ctx: CommandContext) -> Any:
    args = ctx.arguments
    campaign_id = args["campaign_id"]
    view = await w.read_campaign(ctx, campaign_id)
    campaign = view["campaign"]
    stored = view.get("settings") if isinstance(view.get("settings"), dict) else {}
    token = w.check_token("updated_at", campaign.get("updated_at"), args.get("expected_updated_at"))
    current = {field: stored.get(field) for field in SETTINGS_FIELDS}
    edits: dict[str, Any] = dict(args.get("edits") or {})
    rules = args.get("platform_pay_rules", ...)
    merged = _merge_settings(current, edits)
    _validate_settings(merged, set(edits))
    diff = w.changes(current, merged, [*SETTINGS_FIELDS])
    if "application_form" in edits:
        diff.append({"field": "application_form", "before": stored.get("application_form"), "after": edits["application_form"]})
    rules_change = None
    if rules is not ... and rules != stored.get("platform_pay_rules"):
        rules_change = {"field": "platform_pay_rules", "before": stored.get("platform_pay_rules"), "after": rules}
        unknown = _platforms_of_rules(rules) - set(merged.get("allowed_platforms") or [])
        if unknown:
            raise ValueError(
                "A platform pay rule names platforms the Campaign does not allow: "
                f"{', '.join(sorted(unknown))}."
            )
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "campaign": w.campaign_line(campaign),
        "expected_updated_at": token,
        "changes": [*diff, *([rules_change] if rules_change else [])],
    }
    if not data["changes"]:
        return data, [w.nothing_to_write("the current settings")], []
    warnings: list[str] = []
    if any(change["field"] in TEAM_SETTINGS for change in data["changes"]):
        warnings.append(
            "Who joins and how they are approved, the stay, warmup and trial rules, the budget "
            "cap and Discord onboarding are the operating team's settings; a brand editor's "
            "change to them is refused."
        )
    if args["dry_run"]:
        data["settings"] = current
        return data, warnings, w.ask("these setting changes")

    async def write_settings(at: str) -> str:
        body = {**merged, "expected_updated_at": at}
        if "application_form" in edits:
            body["application_form"] = edits["application_form"]
        written = await w.call(ctx, "PUT", f"/campaigns/{campaign_id}/settings", body=body)
        return written.get("updated_at") if isinstance(written, dict) else at

    async def write_rules(at: str) -> str:
        written = await w.call(
            ctx,
            "PATCH",
            f"/campaigns/{campaign_id}/pricing",
            body={"platform_pay_rules": rules, "expected_updated_at": at},
        )
        return written.get("updated_at") if isinstance(written, dict) else at

    # As the page saves: the pay rule first when it fits the platforms stored now (so a save that
    # drops a platform and fixes its rule passes), else after the settings move the platforms.
    rules_first = rules_change is not None and _platforms_of_rules(rules) <= set(
        stored.get("allowed_platforms") or []
    )
    if rules_first:
        token = await write_rules(token)
    if diff:
        token = await write_settings(token)
    if rules_change is not None and not rules_first:
        token = await write_rules(token)
    data["updated_at"] = token
    return data, warnings, []


# -- campaign staff ----------------------------------------------------------

MAX_STAFF = 20


def _people(value: Any) -> list[dict[str, Any]]:
    return [{"id": item.get("id"), "name": item.get("name")} for item in w._dicts(value)]


async def _execute_staff_set(ctx: CommandContext) -> Any:
    args = ctx.arguments
    campaign_id = args["campaign_id"]
    stored = await w.call(ctx, "GET", f"/campaigns/{campaign_id}/staff")
    stored = stored if isinstance(stored, dict) else {}
    token = w.check_token("updated_at", stored.get("updated_at"), args.get("expected_updated_at"))
    before = {
        "manager_user_ids": [item["id"] for item in _people(stored.get("managers"))],
        "operator_user_ids": [item["id"] for item in _people(stored.get("operators"))],
    }
    after = {key: args.get(key, before[key]) for key in before}
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "before": {"managers": _people(stored.get("managers")), "operators": _people(stored.get("operators"))},
        "after": after,
        "expected_updated_at": token,
    }
    if all(sorted(after[key]) == sorted(before[key]) for key in before):
        return data, [w.nothing_to_write("the current team")], []
    if args["dry_run"]:
        return data, [], w.ask("the PMs and OPs before and after")
    written = await w.call(
        ctx, "PUT", f"/campaigns/{campaign_id}/staff", body={**after, "expected_updated_at": token}
    )
    data["staff"] = written
    return data, [], []


# -- delivery targets --------------------------------------------------------

TARGET_FIELDS = ("target_views", "target_posts", "target_creators", "start_date", "due_date")
_TARGET_MAX = {"target_views": 9007199254740991, "target_posts": 2147483647, "target_creators": 100000}


def _validate_target(target: dict[str, Any]) -> None:
    if not any(target.get(field) is not None for field in _TARGET_MAX):
        raise ValueError("A target needs at least one of --target-views, --target-posts, --target-creators.")
    for field, maximum in _TARGET_MAX.items():
        value = target.get(field)
        if value is not None and not 0 < value <= maximum:
            raise ValueError(f"{field} must be between 1 and {maximum}.")
    start, due = target.get("start_date"), target.get("due_date")
    if start and due and start > due:
        raise ValueError("The start date must not be after the due date.")


async def _targets(ctx: CommandContext, campaign_id: str) -> dict[str, Any]:
    view = await w.call(ctx, "GET", f"/campaigns/{campaign_id}/targets")
    return view if isinstance(view, dict) else {}


def _find_target(view: dict[str, Any], target_id: str) -> dict[str, Any]:
    found = next((item for item in w._dicts(view.get("items")) if item.get("id") == target_id), None)
    if found is None:
        raise RuntimeError("not_found: campaign_target_not_found: no such target in this Campaign")
    return found


async def _execute_target_create(ctx: CommandContext) -> Any:
    args = ctx.arguments
    campaign_id = args["campaign_id"]
    view = await _targets(ctx, campaign_id)
    target = {field: args["target"].get(field) for field in TARGET_FIELDS}
    _validate_target(target)
    body = {**target, "sets_campaign_start": args["sets_campaign_start"]}
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "target": body,
        "existing_targets": len(w._dicts(view.get("items"))),
        "started_on": view.get("started_on"),
    }
    warnings = (
        ["The Campaign's start day moves to this target's start date; an earlier start owes the "
         "posts since then (history is backfilled)."]
        if args["sets_campaign_start"]
        else []
    )
    if args["dry_run"]:
        return data, warnings, w.ask("the new target")
    data["target"] = await w.call(ctx, "POST", f"/campaigns/{campaign_id}/targets", body=body)
    return data, warnings, []


async def _execute_target_update(ctx: CommandContext) -> Any:
    args = ctx.arguments
    campaign_id, target_id = args["campaign_id"], args["id"]
    stored = _find_target(await _targets(ctx, campaign_id), target_id)
    token = w.check_token("updated_at", stored.get("updated_at"), args.get("expected_updated_at"))
    before = {field: stored.get(field) for field in TARGET_FIELDS}
    after = {**before, **args["target"]}
    _validate_target(after)
    diff = w.changes(before, after, TARGET_FIELDS)
    data: dict[str, Any] = {"dry_run": args["dry_run"], "id": target_id, "changes": diff, "expected_updated_at": token}
    if not diff and not args["sets_campaign_start"]:
        return data, [w.nothing_to_write("the current target")], []
    if args["dry_run"]:
        return data, [], w.ask("the target changes")
    body = {**after, "sets_campaign_start": args["sets_campaign_start"], "expected_updated_at": token}
    data["target"] = await w.call(ctx, "PUT", f"/campaigns/{campaign_id}/targets/{target_id}", body=body)
    return data, [], []


async def _execute_target_delete(ctx: CommandContext) -> Any:
    args = ctx.arguments
    campaign_id, target_id = args["campaign_id"], args["id"]
    stored = _find_target(await _targets(ctx, campaign_id), target_id)
    token = w.check_token("updated_at", stored.get("updated_at"), args.get("expected_updated_at"))
    data: dict[str, Any] = {"dry_run": args["dry_run"], "target": stored}
    if args["dry_run"]:
        return data, [], w.ask("the target that would be deleted")
    await w.call(
        ctx,
        "DELETE",
        f"/campaigns/{campaign_id}/targets/{target_id}",
        params={"expected_updated_at": token},
    )
    data["deleted"] = True
    return data, [], []


# -- contract template -------------------------------------------------------

CONTRACT_SOURCES = ["default", "custom"]


def _terms_of(view: Any) -> list[dict[str, Any]]:
    return [
        {key: item.get(key) for key in ("name", "label", "default_value", "states_pay")}
        for item in w._dicts(view.get("terms") if isinstance(view, dict) else None)
    ]


def _validate_terms(terms: list[dict[str, Any]]) -> None:
    for term in terms:
        name, label = str(term.get("name") or ""), str(term.get("label") or "")
        if not name or len(name) > 40:
            raise ValueError("Every contract term needs a name of at most 40 characters.")
        if not label or len(label) > 80:
            raise ValueError(f"Contract term {name}: label is required, at most 80 characters.")
        if not str(term.get("default_value") or "") or len(str(term["default_value"])) > 2000:
            raise ValueError(f"Contract term {name}: default_value is required, at most 2000 characters.")


async def _execute_contract_set(ctx: CommandContext) -> Any:
    args = ctx.arguments
    campaign_id = args["campaign_id"]
    stored = await w.call(ctx, "GET", f"/campaigns/{campaign_id}/contract-template")
    stored = stored if isinstance(stored, dict) else {}
    source = args["source"]
    if source == "default":
        body: dict[str, Any] = {"source": "default"}
    else:
        text = args.get("body")
        if text is None:
            if stored.get("source") != "custom":
                raise ValueError("--source custom needs --body or --body-file.")
            text = stored.get("body") or ""
        terms = args.get("terms")
        if terms is None:
            terms = _terms_of(stored)
        _validate_terms(terms)
        body = {"source": "custom", "body": text, "terms": terms}
    before = {"source": stored.get("source"), "body": stored.get("body"), "terms": _terms_of(stored)}
    after = {"source": source, "body": body.get("body"), "terms": body.get("terms", [])}
    diff = w.changes(before, after, ["source", "body", "terms"] if source == "custom" else ["source"])
    data: dict[str, Any] = {"dry_run": args["dry_run"], "changes": diff}
    if not diff:
        return data, [w.nothing_to_write("the current contract")], []
    warnings = ["Contracts already sent keep their wording; contracts sent from now on use the new one."]
    if args["dry_run"]:
        if source == "custom":
            # The page's preview: the body filled the way sending fills it, for an example creator.
            data["preview"] = await w.call(
                ctx,
                "POST",
                f"/campaigns/{campaign_id}/contract-template/preview",
                body={"body": body["body"], "terms": body["terms"]},
            )
        return data, warnings, w.ask("the contract changes and the filled preview")
    data["contract_template"] = await w.call(
        ctx, "PUT", f"/campaigns/{campaign_id}/contract-template", body=body
    )
    return data, warnings, []


# -- discord server ----------------------------------------------------------

GUILD_FIELDS = (
    "welcome_channel_id",
    "help_channel_id",
    "content_review_channel_id",
    "creator_role_id",
    "visitor_role_id",
    "ops_role_id",
)


async def _guild_link(ctx: CommandContext, campaign_id: str) -> dict[str, Any] | None:
    link = await w.call(ctx, "GET", f"/campaigns/{campaign_id}/discord/guild-link")
    return link if isinstance(link, dict) else None


def _layout(link: dict[str, Any] | None) -> dict[str, Any]:
    link = link or {}
    return {field: link.get(field) for field in ("guild_id", *GUILD_FIELDS, "invite_url")}


async def _execute_discord_set(ctx: CommandContext) -> Any:
    args = ctx.arguments
    campaign_id = args["campaign_id"]
    link = await _guild_link(ctx, campaign_id)
    before = _layout(link)
    # The layout is saved whole; on the same server the ids not passed keep their value.
    base = before if before.get("guild_id") == args["guild_id"] else _layout(None)
    after = {**base, **args["layout"], "guild_id": args["guild_id"]}
    diff = w.changes(before, after, list(after))
    data: dict[str, Any] = {"dry_run": args["dry_run"], "changes": diff}
    if not diff:
        return data, [w.nothing_to_write("the current Discord server")], []
    warnings = [
        "The workbench checks with Discord that the server, channels and roles exist and that "
        "the MuseOn bot is in the server before saving."
    ]
    if before.get("guild_id") and before["guild_id"] != args["guild_id"]:
        warnings.append("This replaces the Campaign's current Discord server.")
    if args["dry_run"]:
        return data, warnings, w.ask("the Discord server layout before and after")
    data["guild_link"] = await w.call(
        ctx, "PUT", f"/campaigns/{campaign_id}/discord/guild-link", body=after
    )
    return data, [], []


async def _execute_discord_initialize(ctx: CommandContext) -> Any:
    args = ctx.arguments
    campaign_id = args["campaign_id"]
    link = await _guild_link(ctx, campaign_id)
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "guild_id": args["guild_id"],
        "current": _layout(link) if link else None,
    }
    warnings = [
        "Initializing creates the onboarding channels and roles in that Discord server and "
        "saves them as the Campaign's server; the MuseOn bot must already be in it."
    ]
    if link and link.get("guild_id") != args["guild_id"]:
        warnings.append("This replaces the Campaign's current Discord server.")
    if args["dry_run"]:
        return data, warnings, w.ask("which Discord server would be set up")
    data["guild_link"] = await w.call(
        ctx,
        "POST",
        f"/campaigns/{campaign_id}/discord/guild/initialize",
        body={"guild_id": args["guild_id"]},
    )
    return data, [], []


async def _execute_discord_remove(ctx: CommandContext) -> Any:
    args = ctx.arguments
    campaign_id = args["campaign_id"]
    link = await _guild_link(ctx, campaign_id)
    data: dict[str, Any] = {"dry_run": args["dry_run"], "current": _layout(link) if link else None}
    if link is None:
        return data, ["The Campaign has no Discord server; nothing was written."], []
    warnings = ["The Campaign stops using this server; its channels and roles stay in Discord."]
    if args["dry_run"]:
        return data, warnings, w.ask("which Discord server the Campaign would stop using")
    data["guild_link"] = await w.call(ctx, "DELETE", f"/campaigns/{campaign_id}/discord/guild-link")
    return data, [], []


# -- comment-to-DM rule ------------------------------------------------------

MATCH_MODES = ["contains", "exact", "word"]
DM_STATUSES = ["active", "paused", "archived"]
UTM_PARAMETERS = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_source_platform"]
DM_FIELDS = (
    "keywords",
    "match_mode",
    "any_comment",
    "dm_message",
    "comment_replies",
    "button_title",
    "destination_url",
    "utm_medium",
    "utm_campaign",
    "utm_parameters",
    "utm_source_platform",
    "status",
)
_PLACEHOLDER = re.compile(r"\{\{.*?\}\}")
_ACCOUNT_TOKEN = "{{account}}"


def _validate_dm_rule(rule: dict[str, Any]) -> None:
    """The setup page's checks (`ugc-setup-dm.tsx`); the workbench checks them again."""
    keywords = rule.get("keywords") or []
    if not keywords and not rule.get("any_comment"):
        raise ValueError("Pass at least one --keyword, or --any-comment.")
    if len(keywords) > 20 or any(len(keyword) > 50 for keyword in keywords):
        raise ValueError("At most 20 keywords of at most 50 characters each.")
    message = str(rule.get("dm_message") or "")
    if not message.strip():
        raise ValueError("--dm-message is required.")
    if len(message) > 607:
        raise ValueError("--dm-message is at most 607 characters.")
    replies = rule.get("comment_replies") or []
    if len(replies) > 6 or any(len(reply) > 300 for reply in replies):
        raise ValueError("At most 6 comment replies of at most 300 characters each.")
    title = str(rule.get("button_title") or "").strip()
    if not title or len(title) > 20:
        raise ValueError("--button-title is required, at most 20 characters.")
    url = str(rule.get("destination_url") or "").strip()
    if urlparse(url).scheme != "https" or not urlparse(url).netloc:
        raise ValueError("--destination-url must be an https:// link.")
    for field in ("utm_medium", "utm_source_platform"):
        value = str(rule.get(field) or "")
        if _PLACEHOLDER.search(value) or len(value) > 100:
            raise ValueError(f"{field} takes no {{{{...}}}} placeholder and at most 100 characters.")
    campaign = str(rule.get("utm_campaign") or "").strip()
    if any(token != _ACCOUNT_TOKEN for token in _PLACEHOLDER.findall(campaign)):
        raise ValueError(f"utm_campaign takes only the {_ACCOUNT_TOKEN} placeholder.")
    if "utm_campaign" in (rule.get("utm_parameters") or []) and not campaign:
        raise ValueError("--utm-campaign is required while links carry utm_campaign.")
    # The page counts {{account}} as an Instagram username's 30 characters.
    if len(campaign.replace(_ACCOUNT_TOKEN, "x" * 30)) > 100:
        raise ValueError("--utm-campaign is at most 100 characters ({{account}} counts as 30).")


async def _dm_rules(ctx: CommandContext, campaign_id: str) -> list[dict[str, Any]]:
    return w._dicts(await w.call(ctx, "GET", f"/campaigns/{campaign_id}/dm-rules"))


_DM_DEFAULTS = {
    "match_mode": "contains",
    "any_comment": False,
    "comment_replies": [],
    "utm_medium": "dm",
    "utm_campaign": None,
    "utm_parameters": ["utm_source", "utm_medium", "utm_campaign"],
    "utm_source_platform": "museon",
    "status": "active",
}


async def _execute_dm_create(ctx: CommandContext) -> Any:
    args = ctx.arguments
    campaign_id = args["campaign_id"]
    existing = [item for item in await _dm_rules(ctx, campaign_id) if item.get("status") != "archived"]
    rule = {**_DM_DEFAULTS, "keywords": [], **args["rule"]}
    _validate_dm_rule(rule)
    data: dict[str, Any] = {"dry_run": args["dry_run"], "rule": rule}
    warnings: list[str] = []
    if existing:
        warnings.append(
            "The Campaign already has an open Comment-to-DM rule; the workbench holds one per "
            "Campaign and refuses this (dm_rule_exists). Change it with ugc dm-rule +update."
        )
        data["existing_rule_id"] = existing[0].get("id")
    if rule["status"] == "active":
        warnings.append(
            "An active rule DMs everyone whose comment matches, from every eligible Instagram "
            "and Facebook account in the Campaign."
        )
    if args["dry_run"]:
        return data, warnings, w.ask("the rule and who it would message")
    data["rule"] = await w.call(ctx, "POST", f"/campaigns/{campaign_id}/dm-rules", body=rule)
    return data, [], []


async def _execute_dm_update(ctx: CommandContext) -> Any:
    args = ctx.arguments
    campaign_id, rule_id = args["campaign_id"], args["id"]
    stored = next((item for item in await _dm_rules(ctx, campaign_id) if item.get("id") == rule_id), None)
    if stored is None:
        raise RuntimeError("not_found: dm_rule_not_found: no such rule in this Campaign")
    token = w.check_token("updated_at", stored.get("updated_at"), args.get("expected_updated_at"))
    before = {field: stored.get(field) for field in DM_FIELDS}
    after = {**before, **args["rule"]}
    _validate_dm_rule(after)
    diff = w.changes(before, after, DM_FIELDS)
    data: dict[str, Any] = {"dry_run": args["dry_run"], "id": rule_id, "changes": diff, "expected_updated_at": token}
    if not diff:
        return data, [w.nothing_to_write("the current rule")], []
    warnings: list[str] = []
    if after["status"] == "archived":
        warnings.append("Archiving the rule is final; it stops DMing and cannot be reopened.")
    elif after["status"] == "active":
        warnings.append("An active rule DMs everyone whose comment matches.")
    if args["dry_run"]:
        return data, warnings, w.ask("the rule changes")
    # Only the changed fields: an omitted one keeps its value.
    body = {change["field"]: change["after"] for change in diff}
    data["rule"] = await w.call(
        ctx,
        "PATCH",
        f"/campaigns/{campaign_id}/dm-rules/{rule_id}",
        body={**body, "expected_updated_at": token},
    )
    return data, [], []


# -- payscales and pay rates -------------------------------------------------

RATE_KINDS = ["anything_else", "video_content", "lifetime_views"]
RATE_FIELDS = (
    "name",
    "description",
    "base_rate_mode",
    "base_fee_cents",
    "base_min_views",
    "base_platforms_excluded",
    "cap_per_video_cents",
    "cpm_enabled",
    "cpm_cents",
    "cpm_min_views",
    "cpm_max_views",
    "ladder_enabled",
    "ladder",
    "saves_ladder_enabled",
    "saves_ladder",
    "min_creator_views",
    "performance_mode",
    "platform_overrides",
    "retainer_cents",
    "retainer_videos_per_month",
    "strategist_original_base_fee_cents",
)
"""`PayRateUpdate`: a rate's editable half, written whole."""


async def _payscales(ctx: CommandContext, campaign_id: str) -> list[dict[str, Any]]:
    return w._dicts(await w.call(ctx, "GET", f"/campaigns/{campaign_id}/payscales"))


def _payscale_line(scale: dict[str, Any]) -> dict[str, Any]:
    return {
        key: scale.get(key)
        for key in ("id", "name", "kind", "cap_per_creator_cents", "cap_reset_days")
    } | {"rates": len(w._dicts(scale.get("rates")))}


def _find_payscale(scales: list[dict[str, Any]], payscale_id: str) -> dict[str, Any]:
    found = next((item for item in scales if item.get("id") == payscale_id), None)
    if found is None:
        raise RuntimeError("not_found: payscale_not_found: no such payscale in this Campaign")
    return found


async def _execute_payscale_create(ctx: CommandContext) -> Any:
    args = ctx.arguments
    campaign_id = args["campaign_id"]
    scales = await _payscales(ctx, campaign_id)
    body = args["payscale"]
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "payscale": body,
        "existing": [_payscale_line(scale) for scale in scales],
    }
    warnings = (
        [f"A payscale named {body['name']!r} already exists."]
        if any(scale.get("name") == body["name"] for scale in scales)
        else []
    )
    if args["dry_run"]:
        return data, warnings, w.ask("the new payscale")
    data["payscale"] = await w.call(ctx, "POST", f"/campaigns/{campaign_id}/payscales", body=body)
    return data, warnings, [
        "Add its pay rates with ugc pay-rate +create --payscale-id <data.payscale.id>."
    ]


async def _execute_payscale_update(ctx: CommandContext) -> Any:
    args = ctx.arguments
    scale = _find_payscale(await _payscales(ctx, args["campaign_id"]), args["id"])
    edits = args["edits"]
    before = {field: scale.get(field) for field in edits}
    diff = w.changes(before, edits, list(edits))
    data: dict[str, Any] = {"dry_run": args["dry_run"], "payscale": _payscale_line(scale), "changes": diff}
    if not diff:
        return data, [w.nothing_to_write("the current payscale")], []
    warnings = []
    if "cap_per_creator_cents" in edits or "cap_reset_days" in edits:
        warnings.append(
            "The creator cap moves as a pair: clearing the amount clears the window, and an "
            "amount without a window takes the default window."
        )
    if args["dry_run"]:
        return data, warnings, w.ask("the payscale changes")
    # Only the fields passed: the route tells "not mentioned" from "cleared".
    data["payscale"] = await w.call(ctx, "PATCH", f"/payscales/{args['id']}", body=edits)
    return data, [], []


async def _execute_payscale_delete(ctx: CommandContext) -> Any:
    args = ctx.arguments
    scale = _find_payscale(await _payscales(ctx, args["campaign_id"]), args["id"])
    data: dict[str, Any] = {"dry_run": args["dry_run"], "payscale": _payscale_line(scale)}
    if scale.get("kind") != "custom":
        raise RuntimeError(
            f"conflict: payscale_not_custom: the {scale.get('kind')} payscale cannot be deleted; "
            "only custom ones can."
        )
    warnings = ["A payscale a creator is still on is refused (entity_in_use); move them first."]
    if args["dry_run"]:
        return data, warnings, w.ask("the payscale that would be deleted")
    await w.call(ctx, "DELETE", f"/payscales/{args['id']}")
    data["deleted"] = True
    return data, [], []


def _find_rate(scales: list[dict[str, Any]], rate_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    for scale in scales:
        for rate in w._dicts(scale.get("rates")):
            if rate.get("id") == rate_id:
                return scale, rate
    raise RuntimeError("not_found: pay_rate_not_found: no such pay rate in this Campaign")


async def _rate_preview(ctx: CommandContext, campaign_id: str, rate: dict[str, Any]) -> Any:
    """What a video would earn under the rate, priced unsaved (the rate dialog's preview)."""
    return await w.call(
        ctx, "POST", f"/campaigns/{campaign_id}/pay-preview/draft", body={"rate": rate}
    )


async def _execute_rate_create(ctx: CommandContext) -> Any:
    args = ctx.arguments
    campaign_id = args["campaign_id"]
    scale = _find_payscale(await _payscales(ctx, campaign_id), args["payscale_id"])
    rate = {**args["rate"], "kind": args["kind"]}
    data: dict[str, Any] = {"dry_run": args["dry_run"], "payscale": _payscale_line(scale), "rate": rate}
    if args["dry_run"]:
        data["preview"] = await _rate_preview(ctx, campaign_id, rate)
        return data, [], w.ask("the new pay rate and what a video would earn under it")
    data["rate"] = await w.call(ctx, "POST", f"/payscales/{args['payscale_id']}/rates", body=rate)
    return data, ["Creators on this payscale are paid by the new rate from now on."], []


async def _execute_rate_update(ctx: CommandContext) -> Any:
    args = ctx.arguments
    campaign_id = args["campaign_id"]
    scale, stored = _find_rate(await _payscales(ctx, campaign_id), args["id"])
    before = {field: stored.get(field) for field in RATE_FIELDS}
    after = {**before, **args["rate"]}
    diff = w.changes(before, after, RATE_FIELDS)
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "payscale": _payscale_line(scale),
        "id": args["id"],
        "changes": diff,
    }
    if not diff:
        return data, [w.nothing_to_write("the current pay rate")], []
    if args["dry_run"]:
        data["preview"] = await _rate_preview(ctx, campaign_id, {**after, "kind": stored.get("kind")})
        return data, [], w.ask("the pay rate changes and what a video would earn under it")
    data["rate"] = await w.call(ctx, "PUT", f"/pay-rates/{args['id']}", body=after)
    return data, ["Creators on this payscale are paid by the changed rate from now on."], []


async def _execute_rate_delete(ctx: CommandContext) -> Any:
    args = ctx.arguments
    scale, stored = _find_rate(await _payscales(ctx, args["campaign_id"]), args["id"])
    data: dict[str, Any] = {
        "dry_run": args["dry_run"],
        "payscale": _payscale_line(scale),
        "rate": {key: stored.get(key) for key in ("id", "name", "kind")},
    }
    if args["dry_run"]:
        return data, [], w.ask("the pay rate that would be deleted")
    await w.call(ctx, "DELETE", f"/pay-rates/{args['id']}")
    data["deleted"] = True
    return data, [], []


# -- arguments ---------------------------------------------------------------


def _add_expected_updated_at(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--expected-updated-at")


def _common(args: argparse.Namespace) -> dict[str, Any]:
    out: dict[str, Any] = {
        "campaign_id": w._uuid(args.campaign_id, flag="--campaign-id"),
        "dry_run": bool(args.dry_run),
    }
    if getattr(args, "expected_updated_at", None):
        out["expected_updated_at"] = args.expected_updated_at
    if getattr(args, "id", None) is not None:
        out["id"] = w._uuid(args.id, flag="--id")
    return out


def _add_settings_arguments(parser: argparse.ArgumentParser) -> None:
    w.add_campaign_id(parser)
    parser.add_argument("--approval-mode", choices=APPROVAL_MODES)
    parser.add_argument("--join-mode", choices=kebab_choices(JOIN_MODES))
    parser.add_argument("--budget-cap-cents")
    parser.add_argument("--post-grouping", choices=kebab_choices(POST_GROUPINGS))
    parser.add_argument("--brief-mode", choices=kebab_choices(BRIEF_MODES))
    parser.add_argument("--allowed-platform", action="append", choices=w.PLATFORMS, dest="allowed_platforms")
    parser.add_argument("--required-platform", action="append", choices=w.PLATFORMS, dest="required_platforms")
    parser.add_argument("--no-required-platforms", action="store_true")
    parser.add_argument("--files-only", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--discord-onboarding", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--settings-json")
    parser.add_argument("--platform-pay-rules-json")
    _add_expected_updated_at(parser)
    w.add_dry_run(parser)


def _build_settings_arguments(args: argparse.Namespace) -> dict[str, Any]:
    edits: dict[str, Any] = {}
    extra = w.json_object(args.settings_json, flag="--settings-json") or {}
    unknown = sorted(set(extra) - JSON_SETTINGS)
    if unknown:
        raise ValueError(
            f"--settings-json does not take {', '.join(unknown)}; it takes "
            f"{', '.join(sorted(JSON_SETTINGS))} (the rest have their own flags; the name "
            "changes with ugc campaign +rename)."
        )
    edits.update(extra)
    if args.approval_mode:
        edits["approval_mode"] = args.approval_mode
    if args.join_mode:
        edits["join_mode"] = dekebab(args.join_mode)
    cap = w.optional_int(args.budget_cap_cents, flag="--budget-cap-cents")
    if cap is not ...:
        edits["budget_cap_cents"] = cap
    if args.post_grouping:
        edits["post_grouping"] = dekebab(args.post_grouping)
    if args.brief_mode:
        edits["brief_mode"] = dekebab(args.brief_mode)
    if args.allowed_platforms:
        edits["allowed_platforms"] = list(dict.fromkeys(args.allowed_platforms))
    if args.no_required_platforms and args.required_platforms:
        raise ValueError("Pass --required-platform or --no-required-platforms, not both.")
    if args.required_platforms:
        edits["required_platforms"] = list(dict.fromkeys(args.required_platforms))
    if args.no_required_platforms:
        edits["required_platforms"] = []
    if args.files_only is not None:
        edits["files_only"] = bool(args.files_only)
    if args.discord_onboarding is not None:
        edits["discord_onboarding_enabled"] = bool(args.discord_onboarding)
    out = {**_common(args), "edits": edits}
    rules = w.json_value(args.platform_pay_rules_json, flag="--platform-pay-rules-json")
    if rules is not ...:
        if not isinstance(rules, dict) or "single_bps" not in rules:
            raise ValueError(
                '--platform-pay-rules-json must be an object like {"single_bps": 10000, '
                '"rules": [{"count": 2, "multiplier_bps": 12000}]}.'
            )
        out["platform_pay_rules"] = rules
    if not edits and "platform_pay_rules" not in out:
        raise ValueError("Pass at least one setting to change.")
    return out


def _add_staff_arguments(parser: argparse.ArgumentParser) -> None:
    w.add_campaign_id(parser)
    parser.add_argument("--manager-user-id", action="append", dest="manager_user_ids")
    parser.add_argument("--operator-user-id", action="append", dest="operator_user_ids")
    parser.add_argument("--no-managers", action="store_true")
    parser.add_argument("--no-operators", action="store_true")
    _add_expected_updated_at(parser)
    w.add_dry_run(parser)


def _build_staff_arguments(args: argparse.Namespace) -> dict[str, Any]:
    out = _common(args)
    for key, clear, flag in (
        ("manager_user_ids", args.no_managers, "--manager-user-id"),
        ("operator_user_ids", args.no_operators, "--operator-user-id"),
    ):
        values = getattr(args, key)
        if clear and values:
            raise ValueError(f"Pass {flag} or its --no-* flag, not both.")
        if clear:
            out[key] = []
        elif values:
            ids = w.uuids(values, flag=flag)
            if len(ids) > MAX_STAFF:
                raise ValueError(f"At most {MAX_STAFF} people per role.")
            out[key] = ids
    if "manager_user_ids" not in out and "operator_user_ids" not in out:
        raise ValueError(
            "Pass the PMs (--manager-user-id) or OPs (--operator-user-id) to set, or "
            "--no-managers / --no-operators to clear a role."
        )
    return out


def _add_target_arguments(*, create: bool):
    def add(parser: argparse.ArgumentParser) -> None:
        w.add_campaign_id(parser)
        if not create:
            parser.add_argument("--id", required=True)
            _add_expected_updated_at(parser)
        parser.add_argument("--target-views")
        parser.add_argument("--target-posts")
        parser.add_argument("--target-creators")
        parser.add_argument("--start-date")
        parser.add_argument("--due-date")
        parser.add_argument("--sets-campaign-start", action="store_true")
        w.add_dry_run(parser)

    return add


def _date(value: str | None, *, flag: str) -> Any:
    text = w.optional_text(value)
    if text is ... or text is None:
        return text
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        raise ValueError(f"{flag} must be a date, YYYY-MM-DD, or 'none'.")
    return text


def _build_target_arguments(args: argparse.Namespace) -> dict[str, Any]:
    target = w.passed(
        {
            "target_views": w.optional_int(args.target_views, flag="--target-views", minimum=1),
            "target_posts": w.optional_int(args.target_posts, flag="--target-posts", minimum=1),
            "target_creators": w.optional_int(args.target_creators, flag="--target-creators", minimum=1),
            "start_date": _date(args.start_date, flag="--start-date"),
            "due_date": _date(args.due_date, flag="--due-date"),
        }
    )
    if not target and not args.sets_campaign_start and getattr(args, "id", None):
        raise ValueError("Pass at least one figure or date to change.")
    return {**_common(args), "target": target, "sets_campaign_start": bool(args.sets_campaign_start)}


def _add_target_delete_arguments(parser: argparse.ArgumentParser) -> None:
    w.add_campaign_id(parser)
    parser.add_argument("--id", required=True)
    _add_expected_updated_at(parser)
    w.add_dry_run(parser)
    w.add_yes(parser)


def _build_id_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return _common(args)


def _add_contract_arguments(parser: argparse.ArgumentParser) -> None:
    w.add_campaign_id(parser)
    parser.add_argument("--source", choices=CONTRACT_SOURCES, required=True)
    body = parser.add_mutually_exclusive_group()
    body.add_argument("--body")
    body.add_argument("--body-file")
    parser.add_argument("--terms-json")
    w.add_dry_run(parser)


def _build_contract_arguments(args: argparse.Namespace) -> dict[str, Any]:
    out = _common(args) | {"source": args.source}
    text = args.body if args.body is not None else (w.read_text(args.body_file) if args.body_file else None)
    terms = w.json_value(args.terms_json, flag="--terms-json")
    if args.source == "default" and (text is not None or terms is not ...):
        raise ValueError("--source default takes no --body or --terms-json.")
    if text is not None:
        if not text.strip() or len(text) > 100000:
            raise ValueError("The contract body must not be blank, at most 100000 characters.")
        out["body"] = text
    if terms is not ...:
        if not isinstance(terms, list) or not all(isinstance(item, dict) for item in terms):
            raise ValueError("--terms-json must be a JSON array of {name, label, default_value, states_pay}.")
        out["terms"] = [
            {
                "name": item.get("name"),
                "label": item.get("label"),
                "default_value": item.get("default_value"),
                "states_pay": bool(item.get("states_pay", False)),
            }
            for item in terms
        ]
    return out


def _snowflake(value: str | None, *, flag: str) -> Any:
    text = w.optional_text(value)
    if text is ... or text is None:
        return text
    if not w.SNOWFLAKE.match(text):
        raise ValueError(f"{flag} must be a Discord id (17 to 20 digits) or 'none'.")
    return text


def _add_discord_set_arguments(parser: argparse.ArgumentParser) -> None:
    w.add_campaign_id(parser)
    parser.add_argument("--guild-id", required=True)
    for field in GUILD_FIELDS:
        parser.add_argument(f"--{field.replace('_', '-')}")
    parser.add_argument("--invite-url")
    w.add_dry_run(parser)


def _guild(args: argparse.Namespace) -> str:
    value = _snowflake(args.guild_id, flag="--guild-id")
    if not value:
        raise ValueError("--guild-id is required: the Discord server id.")
    return value


def _build_discord_set_arguments(args: argparse.Namespace) -> dict[str, Any]:
    layout = w.passed(
        {field: _snowflake(getattr(args, field), flag=f"--{field.replace('_', '-')}") for field in GUILD_FIELDS}
        | {"invite_url": w.optional_text(args.invite_url)}
    )
    invite = layout.get("invite_url")
    if invite and urlparse(invite).scheme != "https":
        raise ValueError("--invite-url must be an https:// Discord invite link.")
    return _common(args) | {"guild_id": _guild(args), "layout": layout}


def _add_discord_initialize_arguments(parser: argparse.ArgumentParser) -> None:
    w.add_campaign_id(parser)
    parser.add_argument("--guild-id", required=True)
    w.add_dry_run(parser)
    w.add_yes(parser)


def _build_discord_initialize_arguments(args: argparse.Namespace) -> dict[str, Any]:
    return _common(args) | {"guild_id": _guild(args)}


def _add_campaign_confirm_arguments(parser: argparse.ArgumentParser) -> None:
    w.add_campaign_id(parser)
    w.add_dry_run(parser)
    w.add_yes(parser)


def _add_dm_arguments(*, create: bool):
    def add(parser: argparse.ArgumentParser) -> None:
        w.add_campaign_id(parser)
        if not create:
            parser.add_argument("--id", required=True)
            _add_expected_updated_at(parser)
        parser.add_argument("--keyword", action="append", dest="keywords")
        parser.add_argument("--any-comment", action=argparse.BooleanOptionalAction, default=None)
        parser.add_argument("--match-mode", choices=MATCH_MODES)
        parser.add_argument("--dm-message")
        parser.add_argument("--dm-message-file")
        parser.add_argument("--comment-reply", action="append", dest="comment_replies")
        parser.add_argument("--no-comment-replies", action="store_true")
        parser.add_argument("--button-title")
        parser.add_argument("--destination-url")
        parser.add_argument("--utm-medium")
        parser.add_argument("--utm-campaign")
        parser.add_argument(
            "--utm-parameter", action="append", dest="utm_parameters", choices=kebab_choices(UTM_PARAMETERS)
        )
        parser.add_argument(
            "--status", choices=DM_STATUSES if not create else ["active", "paused"]
        )
        parser.add_argument("--utm-source-platform")
        w.add_dry_run(parser)
        w.add_yes(parser)

    return add


def _build_dm_arguments(args: argparse.Namespace) -> dict[str, Any]:
    rule: dict[str, Any] = {}
    if args.keywords:
        rule["keywords"] = [keyword.strip() for keyword in args.keywords if keyword.strip()]
    if args.any_comment is not None:
        rule["any_comment"] = bool(args.any_comment)
    if args.match_mode:
        rule["match_mode"] = args.match_mode
    if args.dm_message_file:
        rule["dm_message"] = w.read_text(args.dm_message_file)
    elif args.dm_message is not None:
        rule["dm_message"] = args.dm_message
    if args.no_comment_replies:
        rule["comment_replies"] = []
    elif args.comment_replies:
        rule["comment_replies"] = [reply for reply in args.comment_replies if reply.strip()]
    for field in ("button_title", "destination_url", "utm_medium", "utm_source_platform"):
        value = getattr(args, field)
        if value is not None:
            rule[field] = value.strip()
    if args.utm_campaign is not None:
        rule["utm_campaign"] = args.utm_campaign.strip() or None
    if args.utm_parameters:
        rule["utm_parameters"] = list(dict.fromkeys(dekebab(item) for item in args.utm_parameters))
    if args.status:
        rule["status"] = args.status
    if not rule:
        raise ValueError("Pass at least one field of the rule.")
    return _common(args) | {"rule": rule}


def _add_payscale_arguments(*, create: bool):
    def add(parser: argparse.ArgumentParser) -> None:
        w.add_campaign_id(parser)
        if not create:
            parser.add_argument("--id", required=True)
        parser.add_argument("--name", required=create)
        parser.add_argument("--cap-per-creator-cents")
        parser.add_argument("--cap-reset-days")
        w.add_dry_run(parser)

    return add


def _build_payscale_arguments(args: argparse.Namespace) -> dict[str, Any]:
    fields = w.passed(
        {
            "name": w.optional_text(args.name),
            "cap_per_creator_cents": w.optional_int(args.cap_per_creator_cents, flag="--cap-per-creator-cents"),
            "cap_reset_days": w.optional_int(args.cap_reset_days, flag="--cap-reset-days", minimum=1),
        }
    )
    if "name" in fields and not fields["name"]:
        raise ValueError("--name must not be blank.")
    out = _common(args)
    if getattr(args, "id", None) is None:
        return out | {"payscale": {"name": fields.pop("name"), **fields}}
    if not fields:
        raise ValueError("Pass --name, --cap-per-creator-cents or --cap-reset-days.")
    return out | {"edits": fields}


def _add_payscale_delete_arguments(parser: argparse.ArgumentParser) -> None:
    w.add_campaign_id(parser)
    parser.add_argument("--id", required=True)
    w.add_dry_run(parser)
    w.add_yes(parser)


def _rate_json(value: str | None) -> dict[str, Any]:
    rate = w.json_object(value, flag="--rate-json") or {}
    unknown = sorted(set(rate) - set(RATE_FIELDS))
    if unknown:
        raise ValueError(
            f"--rate-json does not take {', '.join(unknown)} (kind is --kind, set on create only)."
        )
    return rate


def _add_rate_arguments(*, create: bool):
    def add(parser: argparse.ArgumentParser) -> None:
        w.add_campaign_id(parser)
        if create:
            parser.add_argument("--payscale-id", required=True)
            parser.add_argument("--kind", choices=kebab_choices(RATE_KINDS), required=True)
        else:
            parser.add_argument("--id", required=True)
        parser.add_argument("--rate-json", required=create)
        w.add_dry_run(parser)

    return add


def _build_rate_arguments(args: argparse.Namespace) -> dict[str, Any]:
    rate = _rate_json(args.rate_json)
    out = _common(args) | {"rate": rate}
    if getattr(args, "payscale_id", None) is not None:
        if not str(rate.get("name") or "").strip():
            raise ValueError('--rate-json needs a "name".')
        out |= {"payscale_id": w._uuid(args.payscale_id, flag="--payscale-id"), "kind": dekebab(args.kind)}
    elif not rate:
        raise ValueError("--rate-json must name at least one field to change.")
    return out


def _add_rate_delete_arguments(parser: argparse.ArgumentParser) -> None:
    w.add_campaign_id(parser)
    parser.add_argument("--id", required=True)
    w.add_dry_run(parser)
    w.add_yes(parser)


# -- specs -------------------------------------------------------------------

_TEAM_ROLE = " Role: owner, admin, or an operator on the Campaign; the server decides."
_SETTINGS_ROLE = (
    " Role: owner, admin, or an operator on the Campaign; a brand editor may change only the "
    "non-team settings. The server decides."
)
_STRING = {"type": "string"}
_ID = w.uuid_property


def _int_or_none(description: str) -> dict[str, Any]:
    return {"type": ["integer", "string", "null"], "description": description + " 'none' clears it."}


def specs() -> list[CommandSpec]:
    c = w.CAMPAIGN
    o = w.OTHER
    eua = {"expected_updated_at": w.EXPECTED_UPDATED_AT}
    return [
        w.spec(
            resource="campaign-settings",
            shortcut="+update",
            summary=(
                "Change a UGC Campaign's settings as its setup page saves them: the whole settings "
                "object is written back with only the passed fields changed (approval and join "
                "mode, budget cap, post grouping, Format mode, platforms, Discord onboarding, and "
                "via --settings-json languages, countries, stay/warmup/trial rules, content intake "
                "and the apply form), plus the publishing-platform pay rule. --dry-run returns "
                "the changes and the current settings without writing." + w.CONFIRM_FIRST
                + _SETTINGS_ROLE
            ),
            adapter="ugc_campaign_settings_update",
            properties={
                "campaign_id": w.CAMPAIGN_ID,
                "approval_mode": {"type": "string", "enum": APPROVAL_MODES, "description": "auto approves applicants; manual waits for a reviewer."},
                "join_mode": {"type": "string", "enum": kebab_choices(JOIN_MODES), "description": "open (anyone with the apply link) or invite-only."},
                "budget_cap_cents": _int_or_none("Campaign budget cap in cents."),
                "post_grouping": {"type": "string", "enum": kebab_choices(POST_GROUPINGS), "description": "How a creative's posts on several platforms are counted for pay."},
                "brief_mode": {"type": "string", "enum": kebab_choices(BRIEF_MODES), "description": "Whether creators pick a Format or get one written for them."},
                "allowed_platforms": {"type": "array", "items": {"type": "string", "enum": w.PLATFORMS}, "description": "The platforms creators post on (replaces the list)."},
                "required_platforms": {"type": "array", "items": {"type": "string", "enum": w.PLATFORMS}, "description": "Platforms a creator must connect before starting; a subset of allowed_platforms."},
                "no_required_platforms": {"type": "boolean", "description": "Require no platform."},
                "files_only": {"type": "boolean", "description": "Creators deliver files instead of posting."},
                "discord_onboarding": {"type": "boolean", "description": "Onboard creators through the Campaign's Discord server."},
                "settings_json": {
                    "type": "string",
                    "description": (
                        "JSON object of other settings: content_languages (['en']), "
                        "target_countries (['US']), content_intake, stay_rules, warmup_rules, trial_rules (each changes only "
                        "the keys given) and application_form (replaced whole)."
                    ),
                },
                "platform_pay_rules_json": {
                    "type": "string",
                    "description": (
                        'Pay by number of platforms a video is on: {"single_bps": 10000, "rules": '
                        '[{"count": 2, "multiplier_bps": 12000, "platforms": null}]} (bps of the '
                        "video's pay)."
                    ),
                },
                **eua,
                "dry_run": w.DRY_RUN,
            },
            required=["campaign_id"],
            output_description="dry_run, campaign, expected_updated_at, changes (field, before, after); settings on a dry run.",
            examples=[
                f"museoncli ugc campaign-settings +update --campaign-id {c} --approval-mode manual --budget-cap-cents 500000 --dry-run",
                f"museoncli ugc campaign-settings +update --campaign-id {c} --settings-json '{{\"stay_rules\": {{\"inactivity_days\": 7}}}}' --dry-run",
            ],
            add_arguments=_add_settings_arguments,
            build_arguments=_build_settings_arguments,
            kind=w.WRITE,
        ),
        w.spec(
            resource="campaign-staff",
            shortcut="+set",
            summary=(
                "Set a Campaign's team: its PMs (--manager-user-id) and OPs (--operator-user-id), "
                "at most 20 each; a role not passed keeps its people, --no-managers / "
                "--no-operators empties it. --dry-run returns the team before and after without "
                "writing." + w.CONFIRM_FIRST + _TEAM_ROLE
            ),
            adapter="ugc_campaign_staff_set",
            properties={
                "campaign_id": w.CAMPAIGN_ID,
                "manager_user_ids": {"type": "array", "items": {"type": "string", "format": "uuid"}, "maxItems": MAX_STAFF, "description": "User IDs of the PMs (replaces the list)."},
                "operator_user_ids": {"type": "array", "items": {"type": "string", "format": "uuid"}, "maxItems": MAX_STAFF, "description": "User IDs of the OPs (replaces the list)."},
                "no_managers": {"type": "boolean", "description": "Remove every PM."},
                "no_operators": {"type": "boolean", "description": "Remove every OP."},
                **eua,
                "dry_run": w.DRY_RUN,
            },
            required=["campaign_id"],
            output_description="dry_run, before (managers, operators), after (user ids), expected_updated_at.",
            examples=[f"museoncli ugc campaign-staff +set --campaign-id {c} --manager-user-id {w.USER} --dry-run"],
            add_arguments=_add_staff_arguments,
            build_arguments=_build_staff_arguments,
            kind=w.WRITE,
        ),
        w.spec(
            resource="delivery-target",
            shortcut="+create",
            summary=(
                "Add a delivery target to a Campaign: views, posts and/or creators to reach "
                "between --start-date and --due-date (UTC days, inclusive; either side may stay "
                "open). --sets-campaign-start also moves the Campaign's start day to its start. "
                "--dry-run returns the target without writing." + w.CONFIRM_FIRST + _TEAM_ROLE
            ),
            adapter="ugc_delivery_target_create",
            properties={
                "campaign_id": w.CAMPAIGN_ID,
                "target_views": {"type": "integer", "minimum": 1, "description": "Views to reach."},
                "target_posts": {"type": "integer", "minimum": 1, "description": "Posts to reach."},
                "target_creators": {"type": "integer", "minimum": 1, "maximum": 100000, "description": "Creators to reach."},
                "start_date": {"type": "string", "format": "date", "description": "First day counted."},
                "due_date": {"type": "string", "format": "date", "description": "Last day counted."},
                "sets_campaign_start": {"type": "boolean", "default": False, "description": "Make the start date the Campaign's start day."},
                "dry_run": w.DRY_RUN,
            },
            required=["campaign_id"],
            output_description="dry_run, target, existing_targets, started_on.",
            examples=[f"museoncli ugc delivery-target +create --campaign-id {c} --target-views 1000000 --due-date 2026-12-31 --dry-run"],
            add_arguments=_add_target_arguments(create=True),
            build_arguments=_build_target_arguments,
            kind=w.WRITE,
        ),
        w.spec(
            resource="delivery-target",
            shortcut="+update",
            summary=(
                "Change a Campaign's delivery target; figures and dates not passed keep their "
                "value, 'none' clears one. --dry-run returns the changes without writing."
                + w.CONFIRM_FIRST + _TEAM_ROLE
            ),
            adapter="ugc_delivery_target_update",
            properties={
                "campaign_id": w.CAMPAIGN_ID,
                "id": _ID("Target ID (from the dry run of +create or the Campaign's targets)."),
                "target_views": _int_or_none("Views to reach."),
                "target_posts": _int_or_none("Posts to reach."),
                "target_creators": _int_or_none("Creators to reach."),
                "start_date": {"type": "string", "format": "date", "description": "First day counted; 'none' opens it."},
                "due_date": {"type": "string", "format": "date", "description": "Last day counted; 'none' opens it."},
                "sets_campaign_start": {"type": "boolean", "default": False, "description": "Make the start date the Campaign's start day."},
                **eua,
                "dry_run": w.DRY_RUN,
            },
            required=["campaign_id", "id"],
            output_description="dry_run, id, changes, expected_updated_at, target.",
            examples=[f"museoncli ugc delivery-target +update --campaign-id {c} --id {o} --target-posts 300 --dry-run"],
            add_arguments=_add_target_arguments(create=False),
            build_arguments=_build_target_arguments,
            kind=w.WRITE,
        ),
        w.spec(
            resource="delivery-target",
            shortcut="+delete",
            summary=(
                "Delete a Campaign's delivery target. --dry-run returns the target without "
                "writing." + w.CONFIRM_YES + _TEAM_ROLE
            ),
            adapter="ugc_delivery_target_delete",
            properties={"campaign_id": w.CAMPAIGN_ID, "id": _ID("Target ID."), **eua, "dry_run": w.DRY_RUN},
            required=["campaign_id", "id"],
            output_description="dry_run, target, deleted.",
            examples=[f"museoncli ugc delivery-target +delete --campaign-id {c} --id {o} --dry-run"],
            add_arguments=_add_target_delete_arguments,
            build_arguments=_build_id_arguments,
            kind=w.DESTRUCTIVE,
        ),
        w.spec(
            resource="contract-template",
            shortcut="+set",
            summary=(
                "Set the contract creators sign for a Campaign: --source default (the standard "
                "contract) or custom (--body/--body-file with {{term}} fields from --terms-json; "
                "body or terms not passed keep the current custom ones). --dry-run returns the "
                "changes and, for custom, the body filled the way sending fills it, without "
                "writing. Contracts already sent keep their wording." + w.CONFIRM_FIRST + _TEAM_ROLE
            ),
            adapter="ugc_contract_template_set",
            properties={
                "campaign_id": w.CAMPAIGN_ID,
                "source": {"type": "string", "enum": CONTRACT_SOURCES, "description": "default or custom."},
                "body": {"type": "string", "maxLength": 100000, "description": "The custom contract text, with {{name}} fields."},
                "body_file": {"type": "string", "description": "Path to a UTF-8 file holding the custom contract text."},
                "terms_json": {
                    "type": "string",
                    "description": (
                        'JSON array of the custom fields: [{"name": "fee", "label": "Fee", '
                        '"default_value": "$100", "states_pay": true}] (replaces the list).'
                    ),
                },
                "dry_run": w.DRY_RUN,
            },
            required=["campaign_id", "source"],
            output_description="dry_run, changes, preview (custom, dry run), contract_template.",
            examples=[
                f"museoncli ugc contract-template +set --campaign-id {c} --source custom --body-file ./contract.md --dry-run",
                f"museoncli ugc contract-template +set --campaign-id {c} --source default --dry-run",
            ],
            add_arguments=_add_contract_arguments,
            build_arguments=_build_contract_arguments,
            kind=w.WRITE,
        ),
        w.spec(
            resource="discord-server",
            shortcut="+set",
            summary=(
                "Connect a Campaign to a Discord server whose channels and roles already exist: "
                "--guild-id plus the welcome, help and content-review channel ids, the creator, "
                "visitor and ops role ids and the invite link. On the same server, ids not "
                "passed keep their value; 'none' clears one. The workbench checks them with "
                "Discord first. --dry-run returns the layout before and after without writing."
                + w.CONFIRM_FIRST + _TEAM_ROLE
            ),
            adapter="ugc_discord_server_set",
            properties={
                "campaign_id": w.CAMPAIGN_ID,
                "guild_id": {"type": "string", "pattern": "^[0-9]{17,20}$", "description": "Discord server id."},
                **{
                    field: {"type": "string", "description": f"Discord {field.removesuffix('_id').replace('_', ' ')} id; 'none' clears it."}
                    for field in GUILD_FIELDS
                },
                "invite_url": {"type": "string", "description": "https:// invite link creators join with."},
                "dry_run": w.DRY_RUN,
            },
            required=["campaign_id", "guild_id"],
            output_description="dry_run, changes, guild_link.",
            examples=[f"museoncli ugc discord-server +set --campaign-id {c} --guild-id 123456789012345678 --welcome-channel-id 223456789012345678 --dry-run"],
            add_arguments=_add_discord_set_arguments,
            build_arguments=_build_discord_set_arguments,
            kind=w.WRITE,
        ),
        w.spec(
            resource="discord-server",
            shortcut="+initialize",
            summary=(
                "Build the onboarding channels and roles in a Discord server the MuseOn bot is "
                "already in, and make it the Campaign's server. --dry-run returns the server it "
                "would set up and the current one without writing." + w.CONFIRM_YES + _TEAM_ROLE
            ),
            adapter="ugc_discord_server_initialize",
            properties={
                "campaign_id": w.CAMPAIGN_ID,
                "guild_id": {"type": "string", "pattern": "^[0-9]{17,20}$", "description": "Discord server id."},
                "dry_run": w.DRY_RUN,
            },
            required=["campaign_id", "guild_id"],
            output_description="dry_run, guild_id, current, guild_link.",
            examples=[f"museoncli ugc discord-server +initialize --campaign-id {c} --guild-id 123456789012345678 --dry-run"],
            add_arguments=_add_discord_initialize_arguments,
            build_arguments=_build_discord_initialize_arguments,
            kind=w.CONFIRMED_WRITE,
        ),
        w.spec(
            resource="discord-server",
            shortcut="+remove",
            summary=(
                "Stop using the Campaign's Discord server; its channels and roles stay in "
                "Discord. --dry-run returns the current server without writing." + w.CONFIRM_YES
                + _TEAM_ROLE
            ),
            adapter="ugc_discord_server_remove",
            properties={"campaign_id": w.CAMPAIGN_ID, "dry_run": w.DRY_RUN},
            required=["campaign_id"],
            output_description="dry_run, current, guild_link (the revoked link).",
            examples=[f"museoncli ugc discord-server +remove --campaign-id {c} --dry-run"],
            add_arguments=_add_campaign_confirm_arguments,
            build_arguments=_build_id_arguments,
            kind=w.DESTRUCTIVE,
        ),
        w.spec(
            resource="dm-rule",
            shortcut="+create",
            summary=(
                "Create a Campaign's Comment-to-DM rule (one open rule per Campaign): when a "
                "comment on a Campaign post matches --keyword (or --any-comment), every eligible "
                "Instagram/Facebook account DMs the commenter --dm-message with a --button-title "
                "button to --destination-url (https), and may reply publicly. Active by default. "
                "--dry-run returns the rule without writing." + w.CONFIRM_YES + _TEAM_ROLE
            ),
            adapter="ugc_dm_rule_create",
            properties=_dm_properties(create=True),
            required=["campaign_id", "dm_message", "button_title", "destination_url"],
            output_description="dry_run, rule, existing_rule_id.",
            examples=[
                f"museoncli ugc dm-rule +create --campaign-id {c} --keyword link --dm-message 'Here you go {{{{name}}}}' --button-title 'Shop now' --destination-url https://brand.example/shop --dry-run"
            ],
            add_arguments=_add_dm_arguments(create=True),
            build_arguments=_build_dm_arguments,
            kind=w.CONFIRMED_WRITE,
        ),
        w.spec(
            resource="dm-rule",
            shortcut="+update",
            summary=(
                "Change a Campaign's Comment-to-DM rule; fields not passed keep their value. "
                "--status paused stops it, active resumes it, archived ends it for good. "
                "--dry-run returns the changes without writing." + w.CONFIRM_YES + _TEAM_ROLE
            ),
            adapter="ugc_dm_rule_update",
            properties=_dm_properties(create=False),
            required=["campaign_id", "id"],
            output_description="dry_run, id, changes, expected_updated_at, rule.",
            examples=[f"museoncli ugc dm-rule +update --campaign-id {c} --id {o} --status paused --dry-run"],
            add_arguments=_add_dm_arguments(create=False),
            build_arguments=_build_dm_arguments,
            kind=w.CONFIRMED_WRITE,
        ),
        w.spec(
            resource="payscale",
            shortcut="+create",
            summary=(
                "Add a custom payscale to a Campaign, with an optional per-creator cap "
                "(--cap-per-creator-cents over --cap-reset-days). Add its rates with ugc pay-rate "
                "+create. --dry-run returns it and the existing payscales without writing."
                + w.CONFIRM_FIRST + _TEAM_ROLE
            ),
            adapter="ugc_payscale_create",
            properties={
                "campaign_id": w.CAMPAIGN_ID,
                "name": {"type": "string", "description": "Payscale name."},
                "cap_per_creator_cents": {"type": "integer", "minimum": 0, "description": "Most a creator earns per window, in cents."},
                "cap_reset_days": {"type": "integer", "minimum": 1, "description": "The cap's window in days."},
                "dry_run": w.DRY_RUN,
            },
            required=["campaign_id", "name"],
            output_description="dry_run, payscale, existing.",
            examples=[f"museoncli ugc payscale +create --campaign-id {c} --name 'Top creators' --dry-run"],
            add_arguments=_add_payscale_arguments(create=True),
            build_arguments=_build_payscale_arguments,
            kind=w.WRITE,
        ),
        w.spec(
            resource="payscale",
            shortcut="+update",
            summary=(
                "Rename a Campaign's payscale or change its per-creator cap ('none' removes the "
                "cap); only the fields passed change. --dry-run returns the changes without "
                "writing." + w.CONFIRM_FIRST + _TEAM_ROLE
            ),
            adapter="ugc_payscale_update",
            properties={
                "campaign_id": w.CAMPAIGN_ID,
                "id": _ID("Payscale ID."),
                "name": {"type": "string", "description": "New name."},
                "cap_per_creator_cents": _int_or_none("Most a creator earns per window, in cents."),
                "cap_reset_days": _int_or_none("The cap's window in days."),
                "dry_run": w.DRY_RUN,
            },
            required=["campaign_id", "id"],
            output_description="dry_run, payscale, changes.",
            examples=[f"museoncli ugc payscale +update --campaign-id {c} --id {o} --cap-per-creator-cents 50000 --dry-run"],
            add_arguments=_add_payscale_arguments(create=False),
            build_arguments=_build_payscale_arguments,
            kind=w.WRITE,
        ),
        w.spec(
            resource="payscale",
            shortcut="+delete",
            summary=(
                "Delete a custom payscale nobody is on. --dry-run returns it without writing."
                + w.CONFIRM_YES + _TEAM_ROLE
            ),
            adapter="ugc_payscale_delete",
            properties={"campaign_id": w.CAMPAIGN_ID, "id": _ID("Payscale ID."), "dry_run": w.DRY_RUN},
            required=["campaign_id", "id"],
            output_description="dry_run, payscale, deleted.",
            examples=[f"museoncli ugc payscale +delete --campaign-id {c} --id {o} --dry-run"],
            add_arguments=_add_payscale_delete_arguments,
            build_arguments=_build_id_arguments,
            kind=w.DESTRUCTIVE,
        ),
        w.spec(
            resource="pay-rate",
            shortcut="+create",
            summary=(
                "Add a pay rate (pricing block) to a payscale: --kind anything-else (the "
                "fallback), video-content or lifetime-views, and its fields as --rate-json (name "
                "required; base fee, CPM, ladder, retainer, caps). --dry-run returns the rate and "
                "what a video would earn under it, without writing." + w.CONFIRM_FIRST + _TEAM_ROLE
            ),
            adapter="ugc_pay_rate_create",
            properties=_rate_properties(create=True),
            required=["campaign_id", "payscale_id", "kind", "rate_json"],
            output_description="dry_run, payscale, rate, preview (dry run).",
            examples=[
                f"museoncli ugc pay-rate +create --campaign-id {c} --payscale-id {o} --kind anything-else --rate-json '{{\"name\": \"Per video\", \"base_rate_mode\": \"per_video\", \"base_fee_cents\": 5000}}' --dry-run"
            ],
            add_arguments=_add_rate_arguments(create=True),
            build_arguments=_build_rate_arguments,
            kind=w.WRITE,
        ),
        w.spec(
            resource="pay-rate",
            shortcut="+update",
            summary=(
                "Change a pay rate: the fields in --rate-json change, the rest keep their value, "
                "and the rate is written whole (its kind never changes). --dry-run returns the "
                "changes and what a video would earn, without writing." + w.CONFIRM_FIRST + _TEAM_ROLE
            ),
            adapter="ugc_pay_rate_update",
            properties=_rate_properties(create=False),
            required=["campaign_id", "id", "rate_json"],
            output_description="dry_run, payscale, id, changes, preview (dry run), rate.",
            examples=[f"museoncli ugc pay-rate +update --campaign-id {c} --id {o} --rate-json '{{\"base_fee_cents\": 6000}}' --dry-run"],
            add_arguments=_add_rate_arguments(create=False),
            build_arguments=_build_rate_arguments,
            kind=w.WRITE,
        ),
        w.spec(
            resource="pay-rate",
            shortcut="+delete",
            summary=(
                "Delete a pay rate from its payscale. --dry-run returns it without writing."
                + w.CONFIRM_YES + _TEAM_ROLE
            ),
            adapter="ugc_pay_rate_delete",
            properties={"campaign_id": w.CAMPAIGN_ID, "id": _ID("Pay rate ID."), "dry_run": w.DRY_RUN},
            required=["campaign_id", "id"],
            output_description="dry_run, payscale, rate, deleted.",
            examples=[f"museoncli ugc pay-rate +delete --campaign-id {c} --id {o} --dry-run"],
            add_arguments=_add_rate_delete_arguments,
            build_arguments=_build_id_arguments,
            kind=w.DESTRUCTIVE,
        ),
    ]


def _dm_properties(*, create: bool) -> dict[str, Any]:
    properties: dict[str, Any] = {"campaign_id": w.CAMPAIGN_ID}
    if not create:
        properties["id"] = _ID("Rule ID.")
        properties["expected_updated_at"] = w.EXPECTED_UPDATED_AT
    properties |= {
        "keywords": {"type": "array", "items": {"type": "string", "maxLength": 50}, "maxItems": 20, "description": "Words a comment must carry (replaces the list)."},
        "any_comment": {"type": "boolean", "description": "Any comment triggers the DM."},
        "match_mode": {"type": "string", "enum": MATCH_MODES, "description": "How keywords match."},
        "dm_message": {"type": "string", "maxLength": 607, "description": "The DM; {{name}} is the commenter."},
        "dm_message_file": {"type": "string", "description": "Path to a UTF-8 file holding the DM."},
        "comment_replies": {"type": "array", "items": {"type": "string", "maxLength": 300}, "maxItems": 6, "description": "Public replies to the comment, used in turn."},
        "no_comment_replies": {"type": "boolean", "description": "Reply to no comment publicly."},
        "button_title": {"type": "string", "maxLength": 20, "description": "The DM's button label."},
        "destination_url": {"type": "string", "description": "https:// page the button opens."},
        "utm_medium": {"type": "string", "maxLength": 100, "description": "The link's UTM medium (default dm)."},
        "utm_campaign": {"type": "string", "maxLength": 100, "description": "The link's UTM campaign; {{account}} is the posting account."},
        "utm_parameters": {"type": "array", "items": {"type": "string", "enum": kebab_choices(UTM_PARAMETERS)}, "description": "UTM parameters the link carries (replaces the list)."},
        "utm_source_platform": {"type": "string", "maxLength": 100, "description": "The link's UTM source platform (default museon)."},
        "status": {"type": "string", "enum": DM_STATUSES if not create else ["active", "paused"], "description": "active DMs, paused stops; archived ends the rule."},
        "dry_run": w.DRY_RUN,
    }
    return properties


def _rate_properties(*, create: bool) -> dict[str, Any]:
    properties: dict[str, Any] = {"campaign_id": w.CAMPAIGN_ID}
    if create:
        properties["payscale_id"] = _ID("Payscale ID.")
        properties["kind"] = {"type": "string", "enum": kebab_choices(RATE_KINDS), "description": "What the block is; fixed once created."}
    else:
        properties["id"] = _ID("Pay rate ID.")
    properties["rate_json"] = {
        "type": "string",
        "description": (
            "JSON object of the rate's fields: name, description, base_rate_mode (off, per_video, "
            "monthly_retainer), base_fee_cents, base_min_views, cap_per_video_cents, cpm_enabled, "
            "cpm_cents, cpm_min_views, cpm_max_views, ladder_enabled, ladder, min_creator_views, "
            "performance_mode, platform_overrides, retainer_cents, retainer_videos_per_month. "
            "Read the payscale's rates for their current values."
        ),
    }
    properties["dry_run"] = w.DRY_RUN
    return properties


EXECUTORS = {
    "ugc.campaign-settings-update": _with_notes(_execute_settings_update),
    "ugc.campaign-staff-set": _with_notes(_execute_staff_set),
    "ugc.delivery-target-create": _with_notes(_execute_target_create),
    "ugc.delivery-target-update": _with_notes(_execute_target_update),
    "ugc.delivery-target-delete": _with_notes(_execute_target_delete),
    "ugc.contract-template-set": _with_notes(_execute_contract_set),
    "ugc.discord-server-set": _with_notes(_execute_discord_set),
    "ugc.discord-server-initialize": _with_notes(_execute_discord_initialize),
    "ugc.discord-server-remove": _with_notes(_execute_discord_remove),
    "ugc.dm-rule-create": _with_notes(_execute_dm_create),
    "ugc.dm-rule-update": _with_notes(_execute_dm_update),
    "ugc.payscale-create": _with_notes(_execute_payscale_create),
    "ugc.payscale-update": _with_notes(_execute_payscale_update),
    "ugc.payscale-delete": _with_notes(_execute_payscale_delete),
    "ugc.pay-rate-create": _with_notes(_execute_rate_create),
    "ugc.pay-rate-update": _with_notes(_execute_rate_update),
    "ugc.pay-rate-delete": _with_notes(_execute_rate_delete),
}
