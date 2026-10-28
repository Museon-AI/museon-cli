"""Protect complete IP workflows, bounded reads and credential confidentiality."""

import asyncio
import copy
import json
import stat

import httpx
import pytest

import museoncli.main as cli
from museoncli.config import AuthState, Config, WorkspaceState

HTTP_CLIENT = httpx.AsyncClient
SUPPLIER = "40000000-0000-4000-8000-000000000004"


def setup(monkeypatch, handler):
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: Config(
            api_base_url="https://api.example.test/api/v1", auth=AuthState(api_key="test-only")
        ),
    )
    monkeypatch.setattr(
        cli.httpx,
        "AsyncClient",
        lambda **kw: HTTP_CLIENT(**kw, transport=httpx.MockTransport(handler)),
    )


def invoke(resource, action, *args):
    return asyncio.run(
        cli.dispatch(cli.build_parser().parse_args(["cloud-phone", resource, "+" + action, *args]))
    )


def views():
    proxy = {
        "id": "123456",
        "server": "203.0.113.5",
        "group_id": "0",
        "group_name": "Unassigned",
        "scheme": "socks5",
        "port": 1080,
        "username": "user",
        "check": {
            "health_state": "healthy",
            "outbound_ip": "198.51.100.7",
            "country_code": "US",
            "checked_at": "2030-01-01T00:00:00Z",
        },
    }
    phone = {
        "provider_device_id": "987654",
        "name": "Test phone",
        "serial_no": "42",
        "has_proxy": True,
        "proxy_id": proxy["id"],
        "accounts": [{"username": "alice"}],
        "moved_recently": False,
    }
    return {
        "generated_at": "now",
        "phones_fetched_at": "now",
        "stale": False,
        "writes_enabled": True,
        "phones_per_proxy": 5,
        "phones": [phone],
        "proxies": [{"id": proxy["id"], "used": 1}],
        "attention": [],
    }, {"proxies": [proxy], "groups": [], "generated_at": "now", "writes_enabled": True}


def test_phone_query_returns_exit_ip_and_accounts_without_n_plus_one(monkeypatch):
    fleet, pool = views()
    fleet["phones"] *= 100
    calls = []

    def handler(req):
        calls.append(req.url.path)
        return httpx.Response(200, json=fleet if req.url.path.endswith("/fleet") else pool)

    setup(monkeypatch, handler)
    result = invoke("phone", "list", "--search", "alice", "--country", "us", "--page-size", "100")
    assert result["data"]["total"] == 100
    item = result["data"]["items"][0]
    assert item["provider_device_id"] == "987654"
    assert item["proxy"]["check"]["outbound_ip"] == "198.51.100.7"
    assert item["proxy"]["server"] == "203.0.113.5"
    assert len(calls) == 2
    assert result["workspace"] is None


def test_file_import_preserves_secrets_on_wire_and_redacts_dry_run(monkeypatch, tmp_path):
    requests = []

    def handler(req):
        requests.append(json.loads(req.content))
        return httpx.Response(
            200,
            json={"results": [{"status": "added"}, {"status": "exists"}, {"status": "invalid"}]},
        )

    setup(monkeypatch, handler)
    source = tmp_path / "ips.csv"
    source.write_text(
        "server,scheme,port,username,password\n203.0.113.5,socks5,1080,user,example-secret\n"
    )
    result = invoke("proxy", "add", "--entries-file", str(source))
    assert requests[0]["entries"][0]["password"] == "example-secret"
    assert [r["status"] for r in result["data"]["results"]] == ["added", "exists", "invalid"]
    result = invoke(
        "proxy", "add", "--args-json", json.dumps({"entries": requests[0]["entries"]}), "--dry-run"
    )
    assert "example-secret" not in json.dumps(result)
    assert len(requests) == 1


def test_credential_export_is_private_and_cannot_overwrite(monkeypatch, tmp_path):
    setup(
        monkeypatch,
        lambda req: httpx.Response(
            200, json={"id": "123456", "username": "user", "password": "example-secret"}
        ),
    )
    target = tmp_path / "proxy.json"
    with pytest.raises(RuntimeError, match="confirmation_required"):
        invoke("proxy", "export-credentials", "--id", "123456", "--output", str(target))
    result = invoke(
        "proxy", "export-credentials", "--id", "123456", "--output", str(target), "--yes"
    )
    assert "example-secret" not in json.dumps(result)
    assert json.loads(target.read_text())["password"] == "example-secret"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        invoke("proxy", "export-credentials", "--id", "123456", "--output", str(target), "--yes")


def test_supplier_password_file_is_only_read_at_execution(monkeypatch, tmp_path):
    bodies = []

    def handler(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(200, json={"id": SUPPLIER, "name": "Example"})

    setup(monkeypatch, handler)
    path = tmp_path / "password.txt"
    path.write_text("example-secret\n")
    invoke("supplier", "create", "--name", "Example", "--password-file", str(path), "--dry-run")
    assert not bodies
    invoke("supplier", "create", "--name", "Example", "--password-file", str(path))
    assert bodies[0]["password"] == "example-secret"
    assert "password_file" not in bodies[0]


def test_change_ip_keeps_per_phone_failure_and_opaque_ids(monkeypatch):
    items = [
        {"phone_id": "987654", "proxy_id": "123456"},
        {"phone_id": "987655", "proxy_id": "123456"},
    ]

    def handler(req):
        assert json.loads(req.content)["items"][0] == {
            "provider_device_id": "987654",
            "proxy_id": "123456",
            "reason": "manual",
        }
        return httpx.Response(
            200,
            json={
                "outcomes": [{"result": "succeeded"}, {"result": "skipped", "code": "PROXY_FULL"}]
            },
        )

    setup(monkeypatch, handler)
    result = invoke("phone", "set-proxy", "--args-json", json.dumps({"items": items}), "--yes")
    assert result["data"]["outcomes"][1]["code"] == "PROXY_FULL"
    assert result["data"]["status"] == "partial"
    assert result["warnings"]
    with pytest.raises(ValueError):
        invoke("phone", "get", "--id", "../escape")


def test_check_wait_requires_a_new_check_for_every_ip(monkeypatch):
    _, pool = views()
    snapshots = 0

    def handler(req):
        nonlocal snapshots
        if req.method == "POST":
            return httpx.Response(200, json={"accepted": 1})
        snapshots += 1
        current = copy.deepcopy(pool)
        if snapshots > 1:
            current["proxies"][0]["check"]["checked_at"] = "2030-01-01T00:01:00Z"
            current["proxies"][0]["check"]["health_state"] = "down"
        return httpx.Response(200, json=current)

    setup(monkeypatch, handler)
    result = invoke("proxy", "check", "--id", "123456", "--wait")
    assert result["data"]["status"] == "completed"
    assert result["data"]["items"][0]["check"]["health_state"] == "down"


def test_recovery_export_downloads_csv_privately_without_overwriting(monkeypatch, tmp_path):
    setup(
        monkeypatch,
        lambda req: httpx.Response(
            200, content=b"job_id,status\ntest,completed\n", headers={"content-type": "text/csv"}
        ),
    )
    target = tmp_path / "history.csv"
    invoke("recovery-job", "export", "--output", str(target))
    assert target.read_text().startswith("job_id,status")
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        invoke("recovery-job", "export", "--output", str(target))


def test_all_snapshot_rows_are_returned_from_one_pair_of_reads(monkeypatch):
    fleet, pool = views()
    fleet["phones"] *= 2387
    calls = []

    def handler(req):
        calls.append(req.url.path)
        return httpx.Response(200, json=fleet if req.url.path.endswith("/fleet") else pool)

    setup(monkeypatch, handler)
    result = invoke("phone", "list", "--all")
    assert len(result["data"]["items"]) == 2387
    assert result["page_info"]["complete"]
    assert len(calls) == 2


def test_recovery_retries_keep_body_idempotency_and_never_resubmit_when_polling(monkeypatch):
    workspace = "50000000-0000-4000-8000-000000000005"
    job = "60000000-0000-4000-8000-000000000006"
    setup(monkeypatch, lambda req: httpx.Response(500))
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: Config(
            api_base_url="https://api.example.test/api/v1",
            auth=AuthState(api_key="test-only"),
            workspace=WorkspaceState(id=workspace),
        ),
    )
    submitted = []

    def handler(req):
        if req.method == "POST":
            body = json.loads(req.content)
            assert body["idempotency_key"] == "recovery-stable-key"
            submitted.append(body)
        return httpx.Response(200, json={"id": job, "status": "completed", "items": []})

    monkeypatch.setattr(
        cli.httpx,
        "AsyncClient",
        lambda **kw: HTTP_CLIENT(**kw, transport=httpx.MockTransport(handler)),
    )
    args = {
        "account_ids": [SUPPLIER],
        "device_ids": [SUPPLIER],
        "idempotency_key": "recovery-stable-key",
    }
    for _ in range(2):
        assert (
            invoke("recovery-job", "create", "--args-json", json.dumps(args), "--yes")["data"]["id"]
            == job
        )
    assert submitted[0] == submitted[1]
    assert submitted[0]["workspace_id"] == workspace and submitted[0]["scope"] == "global"
    invoke(
        "recovery-job", "retry", "--id", job, "--idempotency-key", "recovery-stable-key", "--yes"
    )
    assert submitted[-1] == {"idempotency_key": "recovery-stable-key"}
    count = len(submitted)
    invoke("recovery-job", "get", "--id", job)
    assert len(submitted) == count


def test_app_versions_are_read_for_repeated_targets_in_one_call(monkeypatch):
    requests = []

    def handler(req):
        requests.append(req)
        return httpx.Response(
            200,
            json={
                "phones": [
                    {
                        "phone_id": "987654",
                        "apps": [
                            {
                                "app": "youtube",
                                "installed_version": "20.41.0",
                                "pinned_version": "21.15.285",
                                "state": "outdated",
                            }
                        ],
                        "error": None,
                    },
                    {"phone_id": "987655", "apps": [], "error": "phone is offline"},
                ],
                "unresolved": ["987656"],
            },
        )

    setup(monkeypatch, handler)
    result = invoke(
        "app",
        "list",
        "--phone-id",
        "987654",
        "--phone-id",
        "987655",
        "--phone-id",
        "987656",
        "--account-id",
        SUPPLIER,
        "--app",
        "youtube",
    )
    (request,) = requests
    assert request.method == "GET"
    assert request.url.path == "/api/v1/agent-cli/cloud-phones/apps"
    assert request.url.params.get_list("phone_ids") == ["987654", "987655", "987656"]
    assert request.url.params.get_list("account_ids") == [SUPPLIER]
    assert request.url.params.get_list("apps") == ["youtube"]
    assert result["data"]["phones"][0]["apps"][0]["state"] == "outdated"
    assert len(result["warnings"]) == 2


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--app", "youtube"], "at least one"),
        (["--phone-id", "987654"], "apps"),
        (
            [
                "--args-json",
                json.dumps(
                    {
                        "phone_ids": [str(n) for n in range(30)],
                        "account_ids": [f"40000000-0000-4000-8000-{n:012d}" for n in range(21)],
                        "apps": ["youtube"],
                    }
                ),
            ],
            "at most 50",
        ),
    ],
)
def test_app_upgrade_targets_are_checked_before_any_request(monkeypatch, args, message):
    requests = []
    setup(monkeypatch, lambda req: requests.append(req) or httpx.Response(500))
    with pytest.raises(ValueError, match=message):
        invoke("app-upgrade", "preview", *args)
    assert requests == []


def test_app_upgrade_keeps_body_idempotency_and_points_progress_at_app_list(monkeypatch):
    submitted = []
    plan = {
        "phones": [
            {
                "phone_id": "987654",
                "apps": [
                    {
                        "app": "youtube",
                        "installed_version": "20.41.0",
                        "pinned_version": "21.15.285",
                        "state": "outdated",
                    }
                ],
            }
        ],
        "skipped": {"987655": "already current"},
        "unresolved": [],
    }

    def handler(req):
        assert "Idempotency-Key" not in req.headers
        submitted.append((req.url.path, json.loads(req.content)))
        return httpx.Response(202 if req.url.path.endswith("/app-upgrades") else 200, json=plan)

    setup(monkeypatch, handler)
    target = ["--phone-id", "987654", "--phone-id", "987655", "--app", "youtube"]
    preview = invoke("app-upgrade", "preview", *target)
    assert submitted[0] == (
        "/api/v1/agent-cli/cloud-phones/app-upgrades/preview",
        {"phone_ids": ["987654", "987655"], "apps": ["youtube"]},
    )
    assert preview["data"]["skipped"] == {"987655": "already current"}

    create = [*target, "--idempotency-key", "youtube-pin-20261028"]
    with pytest.raises(RuntimeError, match="confirmation_required"):
        invoke("app-upgrade", "create", *create)
    invoke("app-upgrade", "create", *create, "--dry-run")
    assert len(submitted) == 1
    for _ in range(2):
        result = invoke("app-upgrade", "create", *create, "--yes")
    assert submitted[1] == submitted[2] == (
        "/api/v1/agent-cli/cloud-phones/app-upgrades",
        {
            "phone_ids": ["987654", "987655"],
            "apps": ["youtube"],
            "idempotency_key": "youtube-pin-20261028",
        },
    )
    assert result["next_steps"][0].startswith(
        "museoncli cloud-phone app +list --phone-id 987654 --app youtube"
    )
