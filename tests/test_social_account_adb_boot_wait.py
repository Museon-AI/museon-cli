"""+connect-adb waits out a cold cloud phone, and not forever.

Regressions prevented: a first connection to a stopped phone failing although the
phone is on its way up, and an agent's shell tool killing a command that waits too
long, which loses the answer.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import Any

import pytest

from museoncli.domains import social_account
from museoncli.main import ApiRequestError, error_envelope


def _booting(retry_after: Any = 10) -> ApiRequestError:
    return ApiRequestError(
        503,
        {
            "code": "CLOUD_PHONE_BOOTING",
            "message": "This cloud phone is still booting.",
            "retryable": True,
            "retry_after_seconds": retry_after,
        },
    )


class _Clock:
    """Advances only when the code under test sleeps or a request takes time."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

        async def _sleep(seconds: float) -> None:
            self.sleeps.append(seconds)
            self.now += seconds

        monkeypatch.setattr(social_account.time, "monotonic", lambda: self.now)
        monkeypatch.setattr(social_account.asyncio, "sleep", _sleep)


def _api(answers: list[Any], clock: _Clock, seconds_per_request: float = 35.0) -> Any:
    calls: list[tuple[str, str]] = []

    async def api_data(_cfg: Any, method: str, path: str, **_request: Any) -> Any:
        calls.append((method, path))
        clock.now += seconds_per_request
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    api_data.calls = calls  # type: ignore[attr-defined]
    return api_data


def _request(api_data: Any) -> Any:
    return asyncio.run(
        social_account._request_adb_credentials(
            api_data, None, "/adb", params={"workspace_id": "w"}
        )
    )


def test_a_booting_phone_is_asked_again_with_growing_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock(monkeypatch)
    api_data = _api([_booting(), _booting(), {"serial": "ready"}], clock, seconds_per_request=20)

    assert _request(api_data) == {"serial": "ready"}

    assert clock.sleeps == [10.0, 20.0]
    assert api_data.calls == [("POST", "/adb")] * 3


def test_the_wait_ends_at_its_ceiling_even_inside_a_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(social_account, "ADB_BOOT_WAIT_SECONDS", 0.3)
    calls = 0

    async def api_data(_cfg: Any, _method: str, _path: str, **_request: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 3:
            await asyncio.Event().wait()
        raise _booting(0.02)

    started = time.monotonic()
    with pytest.raises(ApiRequestError) as exc_info:
        _request(api_data)

    assert 0.3 <= time.monotonic() - started < 1.0
    assert calls == 3
    payload, _exit_code = error_envelope(exc_info.value, command="social-account.connect-adb")
    assert payload["error"]["server_code"] == "CLOUD_PHONE_BOOTING"
    assert payload["error"]["retryable"] is True


def test_the_ceiling_stays_under_an_agent_shell_tools_limit() -> None:
    assert social_account.ADB_BOOT_WAIT_SECONDS < 120


def test_no_retry_is_started_when_its_delay_would_pass_the_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock(monkeypatch)
    api_data = _api([_booting(retry_after=600)], clock)

    with pytest.raises(ApiRequestError):
        _request(api_data)

    assert len(api_data.calls) == 1
    assert clock.sleeps == []


@pytest.mark.parametrize(
    "error",
    [
        ApiRequestError(502, {"code": "CLOUD_PHONE_ADB_CONNECT_FAILED", "message": "failed"}),
        ApiRequestError(503, {"code": "SOMETHING_ELSE", "message": "unavailable"}),
        ApiRequestError(504, {"code": "API_REQUEST_TIMEOUT", "message": "budget"}),
        ApiRequestError(503, "plain text"),
    ],
)
def test_other_errors_are_not_retried(
    monkeypatch: pytest.MonkeyPatch, error: ApiRequestError
) -> None:
    clock = _Clock(monkeypatch)
    api_data = _api([error], clock)

    with pytest.raises(ApiRequestError) as exc_info:
        _request(api_data)

    assert exc_info.value is error
    assert clock.sleeps == []


@pytest.mark.parametrize("retry_after", [None, 0, -5, "soon", True])
def test_a_missing_retry_hint_falls_back_to_the_default(
    monkeypatch: pytest.MonkeyPatch, retry_after: Any
) -> None:
    clock = _Clock(monkeypatch)
    api_data = _api([_booting(retry_after), {"serial": "ready"}], clock)

    assert _request(api_data) == {"serial": "ready"}
    assert clock.sleeps == [social_account.ADB_BOOT_RETRY_AFTER_FALLBACK_SECONDS]


@pytest.mark.parametrize(
    "arguments",
    [
        {"account_id": "10000000-0000-4000-8000-000000000001"},
        {"handle": "@creator", "platform": "tiktok"},
    ],
)
def test_connect_adb_retries_for_both_ways_of_naming_the_account(
    monkeypatch: pytest.MonkeyPatch, arguments: dict[str, str]
) -> None:
    clock = _Clock(monkeypatch)
    connection = {
        "success": True,
        "result": {
            "serial": "203.0.113.9:12345",
            "password": "p",
            "account_id": "10000000-0000-4000-8000-000000000001",
        },
    }
    api_data = _api([_booting(), connection], clock)

    async def _connect_adb(found: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        return {"serial": found["serial"]}

    monkeypatch.setattr(social_account, "_connect_adb", _connect_adb)
    monkeypatch.setattr(social_account, "agent_domain_result", lambda data: data["result"])
    ctx = SimpleNamespace(
        cfg=None,
        arguments=arguments,
        workspace_id="workspace-1",
        spec=SimpleNamespace(schema_name="social-account.connect-adb"),
        api_data=api_data,
    )

    result = asyncio.run(social_account._execute_adb_connect(ctx))  # type: ignore[arg-type]

    assert result["serial"] == "203.0.113.9:12345"
    assert len(api_data.calls) == 2
