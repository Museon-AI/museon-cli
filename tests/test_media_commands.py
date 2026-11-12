"""Protect file ingestion across argv, organization addressing and HTTP transport.

The expected API payloads are handwritten from the existing endpoint contract,
not derived from the command builder. No real uploads or network calls are made.
"""

from __future__ import annotations

import asyncio
import argparse
from email.parser import BytesParser
from email.policy import default
import json

import httpx
import pytest

from museoncli.config import AuthState, Config, OrganizationState
from museoncli.domains import get_command_spec, schema_payload
import museoncli.main as cli

OTHER_ORG = "20000000-0000-4000-8000-000000000002"
MEDIA = "30000000-0000-4000-8000-000000000003"
RETIRED = (
    "asset",
    "generation",
    "account-publish",
    "account-operation",
    "product",
    "evaluator",
)


@pytest.mark.parametrize(
    "command,request_fields,local_fields",
    [
        (
            "upload",
            {"file", "file_id", "media_type", "title", "description"},
            {"dry_run"},
        ),
        (
            "generate",
            {"type", "prompt", "model", "duration_seconds", "aspect_ratio", "idempotency_key"},
            {"dry_run"},
        ),
        ("status", {"task_id"}, set()),
        ("import", {"url", "source_page_url"}, {"dry_run"}),
        ("get", {"id", "kind"}, set()),
    ],
)
def test_declared_media_inputs_match_the_transport_cases(command, request_fields, local_fields):
    """New declarations require extending the independent HTTP cases below.

    Request fields are asserted by the upload/readback and import tests;
    organization addressing and dry-run behavior have separate assertions there.
    """
    spec = get_command_spec(f"media.{command}")
    parser = argparse.ArgumentParser(add_help=False)
    spec.add_arguments(parser)
    declared = {action.dest for action in parser._actions}
    assert declared == request_fields | local_fields
    assert set(spec.input_schema["properties"]) == request_fields


def transport_fixture(monkeypatch, handler):
    cfg = Config(
        api_base_url="https://api.example.test/api/v1",
        auth=AuthState(api_key="test-only"),
        organization=OrganizationState(id="org-1", name="MuseOn"),
    )
    monkeypatch.setattr(cli, "load_config", lambda: cfg)
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        cli.httpx, "AsyncClient", lambda **kwargs: real_client(**kwargs, transport=transport)
    )


def run(argv):
    return asyncio.run(cli.dispatch(cli.build_parser().parse_args(argv)))


def multipart(request):
    message = BytesParser(policy=default).parsebytes(
        f"Content-Type: {request.headers['content-type']}\r\n\r\n".encode() + request.content
    )
    return {
        part.get_param("name", header="content-disposition"): part.get_payload(decode=True)
        for part in message.iter_parts()
    }


def test_artifact_upload_uses_artifact_endpoint_and_public_form_contract(monkeypatch, tmp_path):
    report = tmp_path / "delivery.md"
    report.write_text("# Delivery\n", encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/agent-cli/artifacts/upload"
        parts = multipart(request)
        assert "workspace_id" not in parts
        assert parts["artifact_type"] == b"file"
        assert parts["public"] == b"true"
        assert parts["title"] == b"Release acceptance"
        assert "file_id" not in parts
        assert parts["file"] == b"# Delivery\n"
        return httpx.Response(200, json={"success": True, "data": {"public_url": "https://x"}})

    transport_fixture(monkeypatch, handler)
    result = asyncio.run(
        cli.upload_artifact_file(
            cli.load_config(),
            arguments={
                "file": str(report),
                "artifact_type": "file",
                "title": "Release acceptance",
                "public": True,
            },
        )
    )
    assert result == {"public_url": "https://x"}


@pytest.mark.parametrize(
    "media_type,suffix", [("video", "mp4"), ("audio", "mp3"), ("image", "png")]
)
def test_upload_and_readback_preserve_file_type_metadata_and_organization(
    monkeypatch,
    tmp_path,
    media_type,
    suffix,
):
    file = tmp_path / f"reference.{suffix}"
    file.write_bytes(b"local-media-body")
    requests = []

    def handler(request):
        requests.append(request)
        asset = (
            {
                "id": MEDIA,
                "media_type": media_type,
                "status": "completed",
                "media_url": "https://example.test/stored-media",
            }
            if request.method == "GET"
            else {"media_id": MEDIA, "media_url": "https://example.test/stored-media"}
        )
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "type": "media",
                    "asset": asset,
                },
            },
        )

    transport_fixture(monkeypatch, handler)
    receipt = run(
        [
            "media",
            "+upload",
            "--organization-id",
            OTHER_ORG,
            "--file",
            str(file),
            "--media-type",
            media_type,
            "--title",
            "0",
            "--description",
            "",
        ]
    )
    readback = run(
        ["media", "+get", "--organization-id", OTHER_ORG, "--id", receipt["data"]["asset"]["media_id"]]
    )
    assert readback["data"]["asset"] == {
        "id": MEDIA,
        "media_type": media_type,
        "status": "completed",
        "media_url": "https://example.test/stored-media",
    }
    assert len(requests) == 2
    upload, read = requests
    assert upload.method == "POST"
    assert upload.url.path == "/api/v1/agent-cli/assets/media/upload"
    assert upload.headers["X-Museon-CLI-Command"] == "media.upload"
    assert upload.headers["X-Organization-Id"] == OTHER_ORG
    assert multipart(upload) == {
        "media_type": media_type.encode(),
        "title": b"0",
        "description": b"",
        "file": b"local-media-body",
    }
    assert read.method == "GET"
    assert read.url.path == f"/api/v1/agent-cli/assets/media/{MEDIA}"
    assert dict(read.url.params) == {}
    assert read.headers["X-Organization-Id"] == OTHER_ORG
    assert read.headers["X-Museon-CLI-Command"] == "media.get"


@pytest.mark.parametrize("source_page", [None, "https://example.test/page?a=0&b=false"])
def test_image_import_forwards_only_supported_fields(monkeypatch, source_page):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"success": True, "data": {"asset": {"media_id": MEDIA}}})

    transport_fixture(monkeypatch, handler)
    argv = ["media", "+import", "--url", "https://example.test/image.jpg?a=0&b=false"]
    if source_page is not None:
        argv += ["--source-page-url", source_page]
    run(argv)
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.url.path == "/api/v1/agent-cli/assets"
    expected = {"url": "https://example.test/image.jpg?a=0&b=false"}
    if source_page is not None:
        expected["source_page_url"] = source_page
    assert json.loads(request.content) == {
        "type": "media",
        "payload": expected,
    }


def test_content_analysis_still_uploads_video_and_preserves_false_force(monkeypatch, tmp_path):
    file = tmp_path / "video.mp4"
    file.write_bytes(b"video")
    requests = []

    def handler(request):
        requests.append(request)
        data = (
            {"asset": {"media_id": MEDIA}}
            if len(requests) == 1
            else {"run_id": MEDIA, "status": "pending"}
        )
        return httpx.Response(200, json={"success": True, "data": data})

    transport_fixture(monkeypatch, handler)
    run(["content-analysis", "+run", "--type", "content-analysis", "--file", str(file)])
    assert len(requests) == 2
    assert multipart(requests[0]) == {
        "media_type": b"video",
        "file": b"video",
    }
    payload = json.loads(requests[1].content)["payload"]
    assert payload["media_id"] == MEDIA
    assert payload["force_reanalysis"] is False
    assert "file" not in payload


@pytest.mark.parametrize(
    "argv",
    [
        ["media", "+import", "--url", "https://example.test/a.jpg", "--media-type", "video"],
        ["media", "+import", "--url", "https://example.test/a.jpg", "--title", "ignored"],
        [
            "media",
            "+import",
            "--url",
            "https://example.test/a.jpg",
            "--args-json",
            '{"force":false}',
        ],
        ["media", "+upload", "--file", "video.mp4"],
        ["media", "+upload", "--file", "video.mp4", "--media-type", "0"],
    ],
)
def test_unsupported_or_missing_parameters_fail_at_parser(argv):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(argv)


def test_dry_run_never_writes_and_invalid_url_still_fails(monkeypatch):
    def forbidden(request):
        pytest.fail("dry run performed network IO")

    transport_fixture(monkeypatch, forbidden)
    run(["media", "+upload", "--file", "missing.mp4", "--media-type", "video", "--dry-run"])
    run(["media", "+import", "--url", "https://example.test/a.jpg", "--dry-run"])
    with pytest.raises(ValueError, match="HTTP"):
        run(["media", "+import", "--url", "file:///a.jpg", "--dry-run"])


@pytest.mark.parametrize("domain", RETIRED)
def test_retired_domains_have_no_parser_or_schema(domain):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([domain, "+list"])
    with pytest.raises(ValueError, match="Unknown"):
        schema_payload(domain)


def test_legacy_campaign_alias_is_also_removed():
    for action in ("+proposal-get", "+proposal-withdraw"):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args(["agentic-campaign", action, "--id", MEDIA])


def test_upload_failure_receipt_is_not_presented_as_success(monkeypatch, tmp_path):
    file = tmp_path / "clip.mp4"
    file.write_bytes(b"video")
    transport_fixture(
        monkeypatch,
        lambda request: httpx.Response(
            200, json={"success": False, "data": {"asset": {"media_id": MEDIA}}}
        ),
    )
    with pytest.raises(RuntimeError, match="media_upload_failed"):
        run(["media", "+upload", "--file", str(file), "--media-type", "video"])


@pytest.mark.parametrize(
    "receipt",
    [
        {"success": False, "data": {"asset": {"media_id": MEDIA}}},
        {"success": True, "data": {"asset": {}}},
        {"success": True, "data": {"asset": {"media_id": "not-an-id"}}},
    ],
)
def test_unverified_upload_never_starts_downstream_analysis(monkeypatch, tmp_path, receipt):
    file = tmp_path / "clip.mp4"
    file.write_bytes(b"video")
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=receipt)

    transport_fixture(monkeypatch, handler)
    with pytest.raises(RuntimeError, match="media_upload_(failed|unverified)"):
        run(["content-analysis", "+run", "--type", "content-analysis", "--file", str(file)])
    assert len(requests) == 1
    assert requests[0].url.path == "/api/v1/agent-cli/assets/media/upload"


def test_import_without_a_real_id_is_unverified(monkeypatch):
    transport_fixture(
        monkeypatch,
        lambda request: httpx.Response(
            200, json={"success": True, "data": {"asset": {"media_id": None}}}
        ),
    )
    with pytest.raises(RuntimeError, match="media_import_unverified"):
        run(["media", "+import", "--url", "https://example.test/image.jpg"])


@pytest.mark.parametrize(
    "kind,extra,expected",
    [
        ("image", ["--model", "gpt-image-2.5-sunburst"], {"model": "gpt-image-2.5-sunburst"}),
        (
            "video",
            ["--model", "kling-3.0-standard", "--duration-seconds", "13", "--aspect-ratio", "16:9"],
            {"model": "kling-3.0-standard", "duration_seconds": 13, "aspect_ratio": "16:9"},
        ),
    ],
)
def test_generation_argv_reaches_request_and_status(monkeypatch, kind, extra, expected):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            202 if request.method == "POST" else 200,
            json={
                "task_id": MEDIA,
                "media_id": MEDIA,
                "status": "pending",
                "phase": "queued",
                "media_ready": False,
            },
        )

    transport_fixture(monkeypatch, handler)
    receipt = run(
        [
            "media",
            "+generate",
            "--type",
            kind,
            "--prompt",
            "Literal 0 false $HOME",
            "--idempotency-key",
            "caller-same-key",
            *extra,
        ]
    )
    assert receipt["data"]["media_ready"] is False
    run(["media", "+get-generation", "--task-id", MEDIA])
    assert requests[0].url.path == "/api/v1/media/generations"
    assert requests[0].headers["Idempotency-Key"] == "caller-same-key"
    assert json.loads(requests[0].content) == {
        "type": kind,
        "prompt": "Literal 0 false $HOME",
        **expected,
    }
    assert requests[1].url.path == f"/api/v1/media/generations/{MEDIA}"
    assert dict(requests[1].url.params) == {}


@pytest.mark.parametrize(
    "extra",
    [
        ["--type", "video", "--duration-seconds", "0"],
        ["--type", "video", "--duration-seconds", "16"],
        ["--type", "image", "--duration-seconds", "5"],
        ["--type", "image", "--model", "kling-3.0-standard"],
    ],
)
def test_generation_invalid_options_are_rejected_even_during_dry_run(monkeypatch, extra):
    transport_fixture(monkeypatch, lambda request: pytest.fail("invalid request reached HTTP"))
    with pytest.raises(ValueError):
        run(
            [
                "media",
                "+generate",
                "--prompt",
                "test",
                "--idempotency-key",
                "stable",
                "--dry-run",
                *extra,
            ]
        )


def test_private_file_multipart_and_explicit_file_readback(monkeypatch, tmp_path):
    file = tmp_path / "private.md"
    file.write_bytes(b"# Private document")
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(
                201,
                json={
                    "kind": "file",
                    "artifact_id": MEDIA,
                    "is_public": False,
                    "download_url": "https://signed.test/temporary",
                },
            )
        return httpx.Response(
            200,
            json={
                "id": MEDIA,
                "render_kind": "download",
                "download_url": "https://signed.test/renewed",
            },
        )

    transport_fixture(monkeypatch, handler)
    receipt = run(
        [
            "media",
            "+upload",
            "--media-type",
            "file",
            "--file",
            str(file),
            "--file-id",
            MEDIA,
            "--title",
            "0",
        ]
    )
    assert receipt["data"]["kind"] == "file"
    run(["media", "+get", "--kind", "file", "--id", MEDIA])
    assert requests[0].url.path == "/api/v1/media/files"
    assert multipart(requests[0]) == {
        "file_id": MEDIA.encode(),
        "title": b"0",
        "file": b"# Private document",
    }
    assert requests[1].url.path == f"/api/v1/agent-artifacts/{MEDIA}"
    assert dict(requests[1].url.params) == {}


def test_file_timeout_preserves_recovery_id_without_second_upload(monkeypatch, tmp_path):
    file = tmp_path / "report.csv"
    file.write_text("a,b\n1,2")
    requests = []

    def handler(request):
        requests.append(request)
        raise httpx.ReadTimeout("receipt lost", request=request)

    transport_fixture(monkeypatch, handler)
    with pytest.raises(RuntimeError, match=f"artifact_id={MEDIA}"):
        run(["media", "+upload", "--media-type", "file", "--file", str(file), "--file-id", MEDIA])
    assert len(requests) == 1


@pytest.mark.parametrize("field,value", [("task_id", "bad"), ("media_id", None)])
def test_generation_bad_write_receipt_is_not_success(monkeypatch, field, value):
    payload = {"task_id": MEDIA, "media_id": MEDIA}
    payload[field] = value
    transport_fixture(monkeypatch, lambda request: httpx.Response(202, json=payload))
    with pytest.raises(RuntimeError, match="media_generation_unverified"):
        run(["media", "+generate", "--type", "image",
             "--prompt", "test", "--idempotency-key", "keep-this-key"])


@pytest.mark.parametrize("field,value", [("artifact_id", OTHER_ORG), ("kind", "media"), ("is_public", True)])
def test_private_file_receipt_must_prove_identity_and_privacy(monkeypatch, tmp_path, field, value):
    file = tmp_path / "private.txt"
    file.write_text("private")
    payload = {"artifact_id": MEDIA, "kind": "file", "is_public": False}
    payload[field] = value
    transport_fixture(monkeypatch, lambda request: httpx.Response(201, json=payload))
    with pytest.raises(RuntimeError, match="file_upload_unverified"):
        run(["media", "+upload", "--media-type", "file",
             "--file", str(file), "--file-id", MEDIA])


def test_generation_addresses_the_organization_and_needs_no_workspace_in_the_receipt(monkeypatch):
    """The organization comes from the header; a receipt is proven by its task and media ids."""
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(202, json={"task_id": MEDIA, "media_id": MEDIA})

    transport_fixture(monkeypatch, handler)
    receipt = run(["media", "+generate", "--type", "image", "--prompt", "test",
                   "--idempotency-key", "keep-this-key"])

    assert receipt["data"]["task_id"] == MEDIA
    assert "workspace_id" not in json.loads(requests[0].content)
    assert requests[0].headers["X-Organization-Id"] == "org-1"
