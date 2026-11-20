"""HTML document library commands against the organization routes from museon #7516."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest
from routes_stub import ORG, Server, body, query, run

import museoncli.main as cli
from museoncli.config import AuthState, Config, OrganizationState
from museoncli.domains.html_documents import MAX_HTML_BYTES
from museoncli.main import ApiRequestError, UsageError

FOLDER = "72defd40-39ad-40d3-8105-8f23a9a016da"
OTHER = "70000000-0000-4000-8000-000000000002"
DOC = "11111111-1111-4111-8111-111111111111"
SHARE_URL = "https://museon.ai/share/html/test-random-token"
LIBRARY = f"/api/v1/organizations/{ORG}/html-documents"


def _library(payload: dict) -> dict:
    return {"success": True, "data": payload}


def _document(html: str) -> dict:
    return _library(
        {
            "id": DOC,
            "title": "Architecture notes",
            "filename": "guide.html",
            "folder_id": FOLDER,
            "slug": None,
            "updated_at": "2026-11-17T12:00:00Z",
            "html": html,
            "share_url": SHARE_URL,
        }
    )


def test_upload_posts_title_html_basename_and_folder(monkeypatch, tmp_path: Path) -> None:
    html = "<p>Hi</p>\n"
    path = tmp_path / "nested" / "guide.html"
    path.parent.mkdir()
    path.write_text(html, encoding="utf-8")
    server = Server({("POST", LIBRARY): _document(html)})

    result = run(
        monkeypatch,
        server,
        [
            "html-documents",
            "+upload",
            "--file",
            str(path),
            "--title",
            "  Architecture notes  ",
            "--folder-id",
            FOLDER,
        ],
    )

    sent = server.requests[0]
    assert sent.headers["X-Organization-Id"] == ORG
    assert body(sent) == {
        "title": "Architecture notes",
        "filename": "guide.html",
        "folder_id": FOLDER,
        "html": html,
        "is_shared": True,
    }
    assert "parent_id" not in body(sent)
    assert result["data"]["id"] == DOC
    assert result["next_steps"] == [
        f"Share this link with your customer: {SHARE_URL}",
        "museoncli html-documents +list",
    ]


@pytest.mark.parametrize("share_url", ["https://museon.ai/share/academy", SHARE_URL, None])
def test_update_replaces_content_on_the_existing_document(
    monkeypatch, tmp_path: Path, share_url: str | None
) -> None:
    path = tmp_path / "new-courses.html"
    html = "<h1>New courses</h1>"
    path.write_text(html, encoding="utf-8")
    document_path = f"/api/v1/organizations/{OTHER}/html-documents/{DOC}"
    server = Server({("PATCH", document_path): _library({"id": DOC, "share_url": share_url})})

    result = run(
        monkeypatch,
        server,
        [
            "html-documents",
            "+update",
            "--organization-id",
            OTHER,
            "--args-json",
            json.dumps({"id": DOC, "file": str(path)}),
        ],
    )

    (sent,) = server.requests
    assert sent.headers["X-Organization-Id"] == OTHER
    assert body(sent) == {"html": html}
    assert result["data"] == {"id": DOC, "share_url": share_url}


def test_update_dry_run_validates_without_sending_a_request(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "academy.html"
    path.write_text("<p>Courses</p>", encoding="utf-8")
    server = Server({})
    argv = ["html-documents", "+update", "--id", DOC, "--file", str(path), "--dry-run"]

    result = run(monkeypatch, server, argv)
    assert result["data"]["dry_run"] is True

    path.write_text(" ", encoding="utf-8")
    with pytest.raises(ValueError, match="--file"):
        run(monkeypatch, server, argv)
    assert server.requests == []


def test_upload_omits_filename_when_the_basename_is_not_one_html_name(
    monkeypatch, tmp_path: Path
) -> None:
    notes = tmp_path / "notes.md"
    dotted = tmp_path / "my..guide.html"
    notes.write_text("<p>Notes</p>", encoding="utf-8")
    dotted.write_text("<p>Dotted</p>", encoding="utf-8")
    server = Server({("POST", LIBRARY): _library({"id": DOC})})

    run(
        monkeypatch, server, ["html-documents", "+upload", "--file", str(notes), "--title", "Notes"]
    )
    run(
        monkeypatch,
        server,
        ["html-documents", "+upload", "--file", str(dotted), "--title", "Dotted"],
    )

    assert [body(request) for request in server.requests] == [
        {"title": "Notes", "html": "<p>Notes</p>", "is_shared": True},
        {"title": "Dotted", "html": "<p>Dotted</p>", "is_shared": True},
    ]


@pytest.mark.parametrize(
    ("filename", "sent"),
    [
        ("docs/custom.html", "custom.html"),
        ("../secret.html", "secret.html"),
        ("a/../../etc.html", "etc.html"),
        ("custom.htm", "custom.htm"),
    ],
)
def test_upload_sends_only_a_safe_basename_from_an_explicit_filename(
    monkeypatch, tmp_path: Path, filename: str, sent: str
) -> None:
    path = tmp_path / "notes.md"
    path.write_text("<p>Notes</p>", encoding="utf-8")
    server = Server({("POST", LIBRARY): _library({"id": DOC, "filename": sent})})

    run(
        monkeypatch,
        server,
        [
            "html-documents",
            "+upload",
            "--file",
            str(path),
            "--title",
            "Notes",
            "--filename",
            filename,
        ],
    )

    assert body(server.requests[0])["filename"] == sent


@pytest.mark.parametrize(
    "filename",
    ["notes.txt", "my..file.html", "..", "guide.html/extra"],
)
def test_upload_rejects_an_unsafe_explicit_filename(
    monkeypatch, tmp_path: Path, filename: str
) -> None:
    path = tmp_path / "guide.html"
    path.write_text("<p>Hi</p>", encoding="utf-8")
    server = Server({})

    with pytest.raises(ValueError, match="--filename"):
        run(
            monkeypatch,
            server,
            [
                "html-documents",
                "+upload",
                "--file",
                str(path),
                "--title",
                "Notes",
                "--filename",
                filename,
            ],
        )

    assert server.requests == []


def test_upload_dry_run_reads_the_file_and_sends_nothing(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "guide.html"
    path.write_text("<p>Hi</p>", encoding="utf-8")
    server = Server({})

    result = run(
        monkeypatch,
        server,
        [
            "html-documents",
            "+upload",
            "--file",
            str(path),
            "--title",
            "Notes",
            "--filename",
            "docs/custom.html",
            "--dry-run",
        ],
    )

    assert server.requests == []
    arguments = result["data"]["arguments"]
    assert arguments["filename"] == "custom.html"
    assert arguments["dry_run"] is True
    assert "html" not in arguments
    assert "parent_id" not in arguments
    assert arguments["private"] is False


@pytest.mark.parametrize("privacy_args", [["--private"], ["--args-json", '{"private":true}']])
def test_private_upload_never_enables_sharing(monkeypatch, tmp_path: Path, privacy_args) -> None:
    path = tmp_path / "private.html"
    path.write_text("<p>Internal notes</p>", encoding="utf-8")

    def answer(request: httpx.Request) -> dict:
        assert body(request)["is_shared"] is False
        return _library({"id": DOC, "share_url": None})

    server = Server({("POST", LIBRARY): answer})
    result = run(
        monkeypatch,
        server,
        ["html-documents", "+upload", "--file", str(path), "--title", "Notes", *privacy_args],
    )
    assert result["data"]["share_url"] is None
    assert result["warnings"] == []
    assert result["next_steps"] == ["museoncli html-documents +list"]


@pytest.mark.parametrize("private", ["false", "true", None, 0, 1])
def test_upload_rejects_ambiguous_privacy_values(monkeypatch, tmp_path: Path, private) -> None:
    path = tmp_path / "private.html"
    path.write_text("<p>Internal notes</p>", encoding="utf-8")
    server = Server({})
    with pytest.raises(ValueError, match="private must be a boolean"):
        run(
            monkeypatch,
            server,
            [
                "html-documents",
                "+upload",
                "--file",
                str(path),
                "--title",
                "Notes",
                "--args-json",
                json.dumps({"private": private}),
            ],
        )
    assert server.requests == []


def test_upload_without_returned_share_link_does_not_claim_publication(
    monkeypatch, tmp_path: Path
) -> None:
    path = tmp_path / "guide.html"
    path.write_text("<p>Notes</p>", encoding="utf-8")
    server = Server({("POST", LIBRARY): _library({"id": DOC})})
    result = run(
        monkeypatch,
        server,
        ["html-documents", "+upload", "--file", str(path), "--title", "Notes"],
    )
    assert len(server.writes()) == 1
    assert result["warnings"] and "No share URL" in result["warnings"][0]
    assert result["next_steps"] == ["museoncli html-documents +list"]


@pytest.mark.parametrize(
    ("command", "method", "share_url"),
    [("+share", "POST", SHARE_URL), ("+unshare", "DELETE", None)],
)
def test_sharing_targets_explicit_organization_without_rebuilding_links(
    monkeypatch, command: str, method: str, share_url: str | None
) -> None:
    path = f"/api/v1/organizations/{OTHER}/html-documents/{DOC}/share"
    server = Server({(method, path): _library({"id": DOC, "share_url": share_url})})
    result = run(
        monkeypatch,
        server,
        ["html-documents", command, "--id", DOC, "--organization-id", OTHER],
    )
    assert len(server.requests) == 1
    request = server.requests[0]
    assert request.headers["X-Organization-Id"] == OTHER
    assert not request.content
    assert result["data"]["share_url"] == share_url
    assert result["organization"] == {"id": OTHER, "name": None}
    if share_url:
        assert share_url in result["next_steps"][0]
    else:
        assert result["next_steps"] == []


@pytest.mark.parametrize("command", ["+share", "+unshare"])
def test_sharing_dry_run_does_not_change_visibility(monkeypatch, command: str) -> None:
    server = Server({})
    result = run(monkeypatch, server, ["html-documents", command, "--id", DOC, "--dry-run"])
    assert result["data"]["dry_run"] is True
    assert server.requests == []


@pytest.mark.parametrize("command", ["+share", "+unshare"])
def test_sharing_refuses_noncanonical_document_ids(monkeypatch, command: str) -> None:
    server = Server({})
    with pytest.raises(ValueError, match=r"--id.*canonical UUID"):
        run(monkeypatch, server, ["html-documents", command, "--id", "customer-doc"])
    assert server.requests == []


@pytest.mark.parametrize("private", [False, True])
def test_upload_custom_name_does_not_override_privacy(monkeypatch, tmp_path: Path, private) -> None:
    path = tmp_path / "proposal.html"
    path.write_text("<p>Proposal</p>", encoding="utf-8")
    share_url = None if private else "https://museon.ai/share/manus-proposal"
    server = Server(
        {
            ("POST", LIBRARY): _library(
                {
                    "id": DOC,
                    "share_slug": "manus-proposal",
                    "share_url": share_url,
                }
            )
        }
    )
    result = run(
        monkeypatch,
        server,
        [
            "html-documents",
            "+upload",
            "--file",
            str(path),
            "--title",
            "Proposal",
            "--share-slug",
            " Manus-Proposal ",
            *(["--private"] if private else []),
        ],
    )
    sent = body(server.requests[0])
    assert sent["share_slug"] == "manus-proposal"
    assert sent["is_shared"] is not private
    assert result["data"]["share_url"] == share_url


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ([], None),
        (["--share-slug", " Manus-Proposal "], {"share_slug": "manus-proposal"}),
        (["--args-json", '{"share_slug":"manus-proposal"}'], {"share_slug": "manus-proposal"}),
        (["--random-link"], {"share_slug": None}),
        (["--args-json", '{"share_slug":null}'], {"share_slug": None}),
        (["--args-json", '{"random_link":true}'], {"share_slug": None}),
        (["--args-json", '{"random_link":false}'], None),
    ],
)
def test_share_distinguishes_keep_name_rename_and_clear(monkeypatch, options, expected) -> None:
    server = Server(
        {("POST", f"{LIBRARY}/{DOC}/share"): _library({"id": DOC, "share_url": SHARE_URL})}
    )
    run(monkeypatch, server, ["html-documents", "+share", "--id", DOC, *options])
    assert len(server.requests) == 1
    assert body(server.requests[0]) == expected


@pytest.mark.parametrize(
    "slug", ["", "ab", "a" * 81, "has space", "../page", "a--b", "-abc", "abc-", 4]
)
def test_share_rejects_invalid_custom_name_without_a_write(monkeypatch, slug) -> None:
    server = Server({})
    with pytest.raises(ValueError, match="--share-slug"):
        run(
            monkeypatch,
            server,
            [
                "html-documents",
                "+share",
                "--id",
                DOC,
                "--args-json",
                json.dumps({"share_slug": slug}),
            ],
        )
    assert server.requests == []


@pytest.mark.parametrize(
    "payload",
    [
        {"share_slug": "manus-proposal", "random_link": True},
        {"share_slug": None, "random_link": True},
        {"random_link": "false"},
    ],
)
def test_share_rejects_ambiguous_link_choices(monkeypatch, payload) -> None:
    server = Server({})
    with pytest.raises(ValueError):
        run(
            monkeypatch,
            server,
            [
                "html-documents",
                "+share",
                "--id",
                DOC,
                "--args-json",
                json.dumps(payload),
            ],
        )
    assert server.requests == []


def test_custom_name_dry_run_does_not_reserve_name(monkeypatch) -> None:
    server = Server({})
    result = run(
        monkeypatch,
        server,
        [
            "html-documents",
            "+share",
            "--id",
            DOC,
            "--share-slug",
            "manus-proposal",
            "--dry-run",
        ],
    )
    assert result["data"]["arguments"]["share_slug"] == "manus-proposal"
    assert server.requests == []


@pytest.mark.parametrize(
    ("code", "status", "message"),
    [
        (
            "share_slug_taken",
            409,
            "This share link name belongs to another document. Choose another name.",
        ),
        ("share_slug_reserved", 422, "This share link name is reserved. Choose another name."),
        (
            "invalid_share_slug",
            422,
            "Use a share link name of 3-80 letters/digits separated by single hyphens.",
        ),
    ],
)
def test_custom_name_refusals_preserve_server_code_without_retry(
    monkeypatch, code, status, message
) -> None:
    requests = []

    def answer(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, json={"detail": {"code": code}})

    payload = _refused(
        monkeypatch,
        answer,
        [
            "html-documents",
            "+share",
            "--id",
            DOC,
            "--share-slug",
            "manus-proposal",
        ],
    )
    assert payload["error"]["server_code"] == code
    assert payload["error"]["message"] == message
    assert len(requests) == 1


@pytest.mark.parametrize(
    "prepare",
    [
        lambda path: None,
        lambda path: path.write_text("   \n", encoding="utf-8"),
        lambda path: path.write_bytes(b"\xff"),
        lambda path: path.write_bytes(b"x" * (MAX_HTML_BYTES + 1)),
    ],
)
def test_upload_rejects_a_file_the_library_would_not_store(
    monkeypatch, tmp_path: Path, prepare
) -> None:
    path = tmp_path / "guide.html"
    prepare(path)
    server = Server({})

    with pytest.raises(ValueError, match="--file"):
        run(
            monkeypatch,
            server,
            ["html-documents", "+upload", "--file", str(path), "--title", "Notes"],
        )

    assert server.requests == []


def test_upload_refuses_parent_id(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "guide.html"
    path.write_text("<p>Hi</p>", encoding="utf-8")
    server = Server({})

    with pytest.raises(ValueError, match="parent_id"):
        run(
            monkeypatch,
            server,
            [
                "html-documents",
                "+upload",
                "--file",
                str(path),
                "--args-json",
                json.dumps({"title": "Notes", "parent_id": FOLDER}),
            ],
        )

    assert server.requests == []


def test_list_sends_q_and_folder_and_nothing_else(monkeypatch) -> None:
    server = Server({("GET", LIBRARY): _library({"folders": [], "root_count": 0, "documents": []})})

    result = run(
        monkeypatch,
        server,
        ["html-documents", "+list", "--q", " 100%_done ", "--folder", "root"],
    )

    sent = server.requests[0]
    assert (sent.method, sent.url.path) == ("GET", LIBRARY)
    assert query(sent) == {"q": "100%_done", "folder": "root"}
    assert sent.headers["X-Organization-Id"] == ORG
    assert result["data"]["root_count"] == 0


def test_list_with_no_filters_sends_no_query(monkeypatch) -> None:
    server = Server({("GET", LIBRARY): _library({"folders": [], "root_count": 1, "documents": []})})

    run(monkeypatch, server, ["html-documents", "+list", "--folder", " "])

    assert query(server.requests[0]) == {}


@pytest.mark.parametrize("blank", ["", " ", "\t", "\n"])
def test_list_rejects_an_empty_search(monkeypatch, capsys, blank: str) -> None:
    server = Server({("GET", LIBRARY): _library({"folders": [], "documents": []})})

    with pytest.raises(UsageError, match="--q"):
        run(monkeypatch, server, ["html-documents", "+list", "--q", blank])
    assert server.requests == []

    cfg = Config(
        api_base_url="https://api.example.test/api/v1",
        auth=AuthState(api_key="test-only"),
        organization=OrganizationState(id=ORG, name="MuseOn"),
    )
    monkeypatch.setattr(cli, "load_config", lambda: cfg)
    monkeypatch.setattr(sys, "argv", ["museoncli", "html-documents", "+list", "--q", blank])
    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "usage_error"
    assert payload["command"] == "html-documents.list"
    assert payload["error"]["code"] == "usage_error"
    assert payload["error"]["message"] == "--q must be 1-200 characters."
    assert "html-documents +list --help" in payload["error"]["hint"]


def test_list_rejects_a_blank_search_from_args_json(monkeypatch) -> None:
    server = Server({})

    with pytest.raises(UsageError, match="--q"):
        run(
            monkeypatch,
            server,
            ["html-documents", "+list", "--args-json", json.dumps({"q": "  "})],
        )

    assert server.requests == []


@pytest.mark.parametrize("literal", ["root", "ROOT", "Root", "rOoT"])
def test_list_accepts_root_in_any_case(monkeypatch, literal: str) -> None:
    server = Server({("GET", LIBRARY): _library({"folders": [], "root_count": 0, "documents": []})})

    run(monkeypatch, server, ["html-documents", "+list", "--folder", literal])

    assert query(server.requests[0]) == {"folder": "root"}


def test_list_accepts_a_folder_id_and_rejects_anything_else(monkeypatch) -> None:
    server = Server({("GET", LIBRARY): _library({"folders": [], "root_count": 0, "documents": []})})

    run(monkeypatch, server, ["html-documents", "+list", "--folder", FOLDER])
    assert query(server.requests[0]) == {"folder": FOLDER}

    with pytest.raises(ValueError, match="--folder") as exc_info:
        run(monkeypatch, server, ["html-documents", "+list", "--folder", "not-a-folder"])
    message = str(exc_info.value)
    assert "root" in message
    assert "+list" in message
    assert "+get" not in message
    assert len(server.requests) == 1


def test_upload_folder_id_hint_names_only_list(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "guide.html"
    path.write_text("<p>Hi</p>", encoding="utf-8")
    server = Server({})

    with pytest.raises(ValueError, match="--folder-id") as exc_info:
        run(
            monkeypatch,
            server,
            [
                "html-documents",
                "+upload",
                "--file",
                str(path),
                "--title",
                "Notes",
                "--folder-id",
                "nope",
            ],
        )

    message = str(exc_info.value)
    assert "+list" in message
    assert "+get" not in message
    assert server.requests == []


def test_shared_uuid_hint_still_names_list_and_get() -> None:
    from museoncli.domains._writes import uuid_arg

    with pytest.raises(ValueError, match=r"\+list or \+get"):
        uuid_arg("nope", flag="--id")


def test_folder_create_posts_the_name_only(monkeypatch) -> None:
    server = Server(
        {
            ("POST", f"{LIBRARY}/folders"): _library(
                {"id": FOLDER, "name": "Guides", "document_count": 0}
            )
        }
    )

    result = run(monkeypatch, server, ["html-documents", "folder", "+create", "--name", " Guides "])

    sent = server.requests[0]
    assert sent.url.path == f"{LIBRARY}/folders"
    assert body(sent) == {"name": "Guides"}
    assert result["data"]["id"] == FOLDER


def test_folder_create_rejects_a_parent(monkeypatch) -> None:
    server = Server({})

    with pytest.raises(ValueError, match="parent_id"):
        run(
            monkeypatch,
            server,
            [
                "html-documents",
                "folder",
                "+create",
                "--args-json",
                json.dumps({"name": "Guides", "parent_id": FOLDER}),
            ],
        )

    assert server.requests == []


def test_install_defaults_posts_no_body_for_the_addressed_organization(monkeypatch) -> None:
    path = f"/api/v1/organizations/{OTHER}/html-documents/defaults"
    server = Server({("POST", path): _library({"folders": [], "root_count": 3, "documents": []})})

    result = run(
        monkeypatch,
        server,
        ["html-documents", "+install-defaults", "--organization-id", OTHER],
    )

    sent = server.requests[0]
    assert (sent.method, sent.url.path) == ("POST", path)
    assert not sent.content
    assert query(sent) == {}
    assert sent.headers["X-Organization-Id"] == OTHER
    assert result["data"]["root_count"] == 3
    assert result["organization"] == {"id": OTHER, "name": None}


def test_install_defaults_dry_run_sends_nothing(monkeypatch) -> None:
    server = Server({})

    result = run(monkeypatch, server, ["html-documents", "+install-defaults", "--dry-run"])

    assert server.requests == []
    assert result["data"]["dry_run"] is True


def _refused(monkeypatch, answer, argv: list[str]) -> dict:
    with pytest.raises(ApiRequestError) as caught:
        run(monkeypatch, answer, argv)
    payload, _code = cli.error_envelope(caught.value, command="html-documents.list")
    return payload


def test_folder_not_found_is_a_sentence_and_a_server_code(monkeypatch, tmp_path: Path) -> None:
    """The API returns {"detail": {"code": ...}} and no message. 2.3.0 printed that object."""
    path = tmp_path / "guide.html"
    path.write_text("<p>Hi</p>", encoding="utf-8")

    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "detail": {"code": "folder_not_found"},
                "error": {
                    "code": "folder_not_found",
                    "message": "{'code': 'folder_not_found'}",
                    "retryable": False,
                },
            },
        )

    payload = _refused(
        monkeypatch,
        answer,
        [
            "html-documents",
            "+upload",
            "--file",
            str(path),
            "--title",
            "Notes",
            "--folder-id",
            FOLDER,
        ],
    )

    assert payload["reason"] == "not_found"
    assert payload["error"]["server_code"] == "folder_not_found"
    assert payload["error"]["message"] == "Folder not found"
    assert payload["error"]["http_status"] == 404
    assert "folder_not_found" not in payload["error"]["message"]


def test_a_json_encoded_folder_name_taken_body_is_decoded(monkeypatch) -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": json.dumps({"code": "folder_name_taken"})})

    payload = _refused(
        monkeypatch, answer, ["html-documents", "folder", "+create", "--name", "Guides"]
    )

    assert payload["reason"] == "conflict"
    assert payload["error"]["server_code"] == "folder_name_taken"
    assert payload["error"]["message"] == "A folder with this name already exists"
    assert payload["detail"] == '{"code": "folder_name_taken"}'


_PRIVATE = {
    "html-documents.upload",
    "html-documents.update",
    "html-documents.list",
    "html-documents.share",
    "html-documents.unshare",
    "html-documents.folder-create",
    "html-documents.install-defaults",
}


def test_private_management_catalog_requires_staff_and_stays_organization_bound() -> None:
    """Staff is catalog metadata. Organization asset checks stay, and the server enforces both."""
    from museoncli.domains import command_specs
    from museoncli.domains._shared import _spec_schema_payload

    html = [spec for spec in command_specs() if spec.domain.value == "html-documents"]
    assert {spec.schema_name for spec in html} == _PRIVATE
    for spec in html:
        assert spec.required_roles == ("staff",)
        assert spec.organization_bound is True
        assert spec.resource_policy == "staff_with_organization_asset_access"
        assert spec.required_scopes == ("agent_cli.access",)
        authorization = _spec_schema_payload(spec)["authorization"]
        assert authorization == {
            "authentication_required": True,
            "required_scopes": ["agent_cli.access"],
            "required_roles": ["staff"],
            "organization_bound": True,
            "resource_policy": "staff_with_organization_asset_access",
            "enforcement": "museon_server",
        }
        assert "Museon staff only" in spec.summary
        assert "organization" in spec.summary

    skills = next(spec for spec in command_specs() if spec.schema_name == "skills.list")
    assert skills.required_roles == ("organization_member",)
    assert skills.resource_policy == "server_evaluated_organization_and_resource_access"


def test_listing_does_not_stop_a_caller_the_cli_cannot_tell_is_staff(monkeypatch) -> None:
    """A non-staff denial is the server's 403. The CLI still sends the organization request."""
    server = Server({("GET", LIBRARY): _library({"folders": [], "root_count": 0, "documents": []})})

    run(monkeypatch, server, ["html-documents", "+list"])

    sent = server.requests[0]
    assert (sent.method, sent.url.path) == ("GET", LIBRARY)
    assert sent.headers["X-Organization-Id"] == ORG
    assert "is_staff" not in {name.lower() for name in sent.headers}
