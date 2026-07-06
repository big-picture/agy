from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

import agy.record_sources as record_sources
from agy import (
    Flow,
    Record,
    RecordSet,
    RecordType,
    SourceType,
    search_emails,
    search_files,
)
from agy.contrib.action_types import get_contrib_action_types
from agy.integrations.email import Attachment, MockEmailAccount


def test_record_set_batches_advance_deterministically() -> None:
    records = [
        Record(
            id=f"record_{idx}",
            record_type=RecordType.TEXT,
            source_type=SourceType.GENERATED,
            title=f"Record {idx}",
        )
        for idx in range(1, 6)
    ]
    record_set = RecordSet(records=records, batch_size=2)

    assert [record.id for record in record_set.get_current_batch()] == [
        "record_1",
        "record_2",
    ]
    assert [record.id for record in record_set.get_next_batch()] == [
        "record_1",
        "record_2",
    ]
    assert [record.id for record in record_set.get_next_batch()] == [
        "record_3",
        "record_4",
    ]
    assert record_set.has_next_batch() is True
    assert [record.id for record in record_set.get_next_batch()] == ["record_5"]
    assert record_set.has_next_batch() is False


def test_search_emails_returns_record_set_with_email_records() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        account = MockEmailAccount(base_path=tmpdir, user_email="user@example.com")
        account.add_email(
            folder="inbox",
            sender="alice@example.com",
            recipient="user@example.com",
            subject="Customs transfer request",
            text="Please review the customs transfer documents.",
        )
        account.add_email(
            folder="inbox",
            sender="bob@example.com",
            recipient="user@example.com",
            subject="Lunch",
            text="Lunch tomorrow?",
        )

        retrieved_emails = search_emails(
            account,
            query="customs transfer",
            folders=["inbox"],
            batch_size=10,
        )

    assert isinstance(retrieved_emails, RecordSet)
    assert len(retrieved_emails) == 1
    assert retrieved_emails[0].id == "email_1"
    assert retrieved_emails[0].record_type is RecordType.EMAIL
    assert retrieved_emails[0].metadata["sender"] == "alice@example.com"


def test_email_record_set_load_full_fetches_candidate_attachments() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        account = MockEmailAccount(base_path=tmpdir, user_email="user@example.com")
        account.add_email(
            folder="inbox",
            sender="alice@example.com",
            recipient="user@example.com",
            subject="Attachment candidate",
            text="Please inspect the attachment.",
        )

        def fetch_attachments(email):
            email.attachments.append(
                Attachment(
                    filename="customs.pdf",
                    content=b"%PDF-1.4",
                    content_type="application/pdf",
                )
            )

        account.fetch_attachments = fetch_attachments

        retrieved_emails = search_emails(account, query="attachment", folders=["inbox"])
        candidate_emails = retrieved_emails.load_full(["email_1"])

    assert len(candidate_emails) == 1
    assert candidate_emails[0].content_loaded is True
    assert candidate_emails[0].children[0].title == "customs.pdf"
    assert candidate_emails[0].children[0].record_type is RecordType.PDF
    assert retrieved_emails[0].children[0].title == "customs.pdf"


def test_search_files_returns_record_set_with_file_records() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "customs_transfer.md").write_text(
            "customs transfer checklist",
            encoding="utf-8",
        )
        (root / "lunch.txt").write_text("lunch plans", encoding="utf-8")

        retrieved_files = search_files(
            root_path=root,
            name_contains=["customs"],
            file_extensions=["md"],
            batch_size=10,
        )

    assert isinstance(retrieved_files, RecordSet)
    assert len(retrieved_files) == 1
    assert retrieved_files[0].id == "file_1"
    assert retrieved_files[0].record_type is RecordType.TEXT
    assert retrieved_files[0].source_type is SourceType.FILESYSTEM
    assert retrieved_files[0].content_loaded is False
    assert retrieved_files[0].metadata["filename"] == "customs_transfer.md"


def test_search_files_filters_real_files_by_substring_extension_and_nested_dirs() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        nested = root / "nested"
        nested.mkdir()
        (root / "customs_invoice.pdf").write_text("pdf placeholder", encoding="utf-8")
        (nested / "customs_notes.md").write_text("notes", encoding="utf-8")
        (nested / "customs_other.txt").write_text("text", encoding="utf-8")
        (root / "customs_archive").mkdir()
        (root / "lunch_invoice.pdf").write_text("lunch", encoding="utf-8")

        retrieved_files = search_files(
            root_path=root,
            name_contains=["customs"],
            file_extensions=["pdf", "md"],
            batch_size=10,
        )

    filenames = {record.metadata["filename"] for record in retrieved_files}
    assert filenames == {"customs_invoice.pdf", "customs_notes.md"}
    assert all(record.source_type is SourceType.FILESYSTEM for record in retrieved_files)
    assert all(record.content_loaded is False for record in retrieved_files)


def test_search_files_query_and_max_results_on_real_filesystem() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        for filename in [
            "alpha_customs.md",
            "beta_customs.md",
            "gamma_customs.md",
            "delta_other.md",
        ]:
            (root / filename).write_text(filename, encoding="utf-8")

        retrieved_files = search_files(
            root_path=root,
            query="customs",
            file_extensions=["md"],
            max_results=2,
            batch_size=10,
        )

    assert [record.metadata["filename"] for record in retrieved_files] == [
        "alpha_customs.md",
        "beta_customs.md",
    ]


def test_search_files_filters_real_files_by_modified_date_range() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        old_file = root / "customs_2020.md"
        current_file = root / "customs_2024.md"
        future_file = root / "customs_2026.md"
        for path in [old_file, current_file, future_file]:
            path.write_text(path.name, encoding="utf-8")

        _set_mtime(old_file, "2020-01-01T12:00:00")
        _set_mtime(current_file, "2024-06-01T12:00:00")
        _set_mtime(future_file, "2026-01-01T12:00:00")

        retrieved_files = search_files(
            root_path=root,
            name_contains=["customs"],
            file_extensions=["md"],
            date_from="2024-01-01",
            date_to="2024-12-31",
            batch_size=10,
        )

    assert [record.metadata["filename"] for record in retrieved_files] == [
        "customs_2024.md"
    ]


def test_file_record_set_load_full_loads_only_candidates() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "candidate.md").write_text(
            "important customs transfer content",
            encoding="utf-8",
        )
        (root / "other.md").write_text("other content", encoding="utf-8")

        retrieved_files = search_files(
            root_path=root,
            file_extensions=["md"],
            batch_size=10,
        )
        candidate_files = retrieved_files.load_full(["file_1"])

    assert len(candidate_files) == 1
    assert candidate_files[0].content_loaded is True
    assert "important customs transfer content" in (candidate_files[0].text or "")
    assert retrieved_files[0].content_loaded is True
    assert retrieved_files[1].content_loaded is False


def test_search_files_uses_mdfind_on_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_run(args, capture_output, text, check):
        captured["args"] = args
        assert capture_output is True
        assert text is True
        assert check is False
        return record_sources.subprocess.CompletedProcess(
            args,
            0,
            stdout="/tmp/customs_transfer.md\n",
            stderr="",
        )

    monkeypatch.setattr(record_sources.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(record_sources.subprocess, "run", fake_run)

    paths = record_sources._search_file_paths_mdfind(
        Path("/tmp"),
        name_contains=["customs"],
        file_extensions=["md"],
        date_from=None,
        date_to=None,
    )

    assert paths == [Path("/tmp/customs_transfer.md").resolve()]
    assert captured["args"][0:3] == ["mdfind", "-onlyin", "/tmp"]
    assert 'kMDItemDisplayName == "*customs*"c' in captured["args"][3]
    assert 'kMDItemFSName == "*.md"' in captured["args"][3]


@pytest.mark.asyncio
async def test_flow_can_search_email_batches_with_contrib_action() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        account = MockEmailAccount(base_path=tmpdir, user_email="user@example.com")
        account.add_email(
            folder="inbox",
            sender="alice@example.com",
            recipient="user@example.com",
            subject="Customs transfer",
            text="This email mentions customs transfer handling.",
        )
        flow = Flow.from_flowsy_string(
            """
name: Email Batch Test

context_in:
  account: EmailAccount

nodes:
  retrieve_emails:
    actions:
      - retrieved_emails = search_emails(account, query="customs transfer", folders=["inbox"], batch_size=10)
      - current_email_batch = retrieved_emails.get_next_batch()
"""
        )

        result = await flow.run(
            context_in={"account": account},
            action_types=get_contrib_action_types(),
        )

    assert result["success"] is True
    assert len(result["retrieved_emails"]) == 1
    assert result["current_email_batch"][0].metadata["subject"] == "Customs transfer"


@pytest.mark.asyncio
async def test_flow_can_search_file_batches_with_contrib_action() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "customs_transfer.md").write_text(
            "This file mentions customs transfer handling.",
            encoding="utf-8",
        )
        flow = Flow.from_flowsy_string(
            """
name: File Batch Test

context_in:
  root_path: str

nodes:
  retrieve_files:
    actions:
      - retrieved_files = search_files(root_path=root_path, query="customs", file_extensions=["md"], batch_size=10)
      - current_file_batch = retrieved_files.get_next_batch()
"""
        )

        result = await flow.run(
            context_in={"root_path": str(root)},
            action_types=get_contrib_action_types(),
        )

    assert result["success"] is True
    assert len(result["retrieved_files"]) == 1
    assert result["current_file_batch"][0].metadata["filename"] == "customs_transfer.md"


def _set_mtime(path: Path, iso_datetime: str) -> None:
    timestamp = datetime.fromisoformat(iso_datetime).timestamp()
    os.utime(path, (timestamp, timestamp))
