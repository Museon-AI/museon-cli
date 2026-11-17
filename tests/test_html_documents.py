"""HTML document library commands against the organization routes from museon #7516."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from routes_stub import ORG, Server, body, query, run

from museoncli.domains.html_documents import MAX_HTML_BYTES

FOLDER = "72defd40-39ad-40d3-8105-8f23a9a016da"
OTHER = "70000000-0000-4000-8000-000000000002"
DOC = "11111111-1111-4111-8111-111111111111"
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
    }
    assert "parent_id" not in body(sent)
    assert result["data"]["id"] == DOC
    assert result["next_steps"] == ["museoncli html-documents +list"]


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
        {"title": "Notes", "html": "<p>Notes</p>"},
        {"title": "Dotted", "html": "<p>Dotted</p>"},
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

    run(monkeypatch, server, ["html-documents", "+list", "--q", "  ", "--folder", " "])

    assert query(server.requests[0]) == {}


def test_list_accepts_a_folder_id_and_rejects_anything_else(monkeypatch) -> None:
    server = Server({("GET", LIBRARY): _library({"folders": [], "root_count": 0, "documents": []})})

    run(monkeypatch, server, ["html-documents", "+list", "--folder", FOLDER])
    assert query(server.requests[0]) == {"folder": FOLDER}

    with pytest.raises(ValueError, match="--folder"):
        run(monkeypatch, server, ["html-documents", "+list", "--folder", "not-a-folder"])
    assert len(server.requests) == 1


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
