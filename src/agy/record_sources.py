"""RecordSource adapters for existing Agy integrations."""

from __future__ import annotations

import platform
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from agy.integrations.email import Attachment, Email, EmailAccount
from agy.records import (
    Record,
    RecordSet,
    RecordSource,
    RecordType,
    SearchQuery,
    SourceType,
)
from agy.utils.file_readers import load_files_as_text


class EmailRecordSource(RecordSource):
    """RecordSource adapter backed by an EmailAccount."""

    def __init__(self, account: EmailAccount):
        """Create an email source from an existing account."""
        self.account = account

    def search(self, query: SearchQuery, *, batch_size: int = 10) -> RecordSet:
        """Search emails and return them as a RecordSet."""
        filters = dict(query.filters)
        max_results = int(filters.pop("max_results", 100))
        emails = self.account.find_emails(
            folders=filters.pop("folders", None),
            max_results=max_results,
            to_contains=filters.pop("to_contains", None),
            from_contains=filters.pop("from_contains", None),
            cc_contains=filters.pop("cc_contains", None),
            subject_contains=filters.pop("subject_contains", None),
            body_contains=filters.pop("body_contains", None),
            has_attachments=filters.pop("has_attachments", None),
            email_contains=query.query or filters.pop("email_contains", None),
        )
        records = [
            email_to_record(email, record_id=f"email_{idx + 1}")
            for idx, email in enumerate(emails)
        ]
        return RecordSet(
            records=records,
            source=self,
            query=query,
            batch_size=batch_size,
        )

    def load_full(self, record_set: RecordSet, ids: list[str]) -> list[Record]:
        """Load full email content and attachments for selected records."""
        selected = record_set.get_by_ids(ids)
        loaded: list[Record] = []
        for record in selected:
            email = record.value
            if isinstance(email, Email):
                self.account.fetch_attachments(email)
                loaded.append(email_to_record(email, record_id=record.id))
            else:
                record.content_loaded = True
                loaded.append(record)
        return loaded


class FileRecordSource(RecordSource):
    """RecordSource adapter backed by local filesystem search."""

    def __init__(self, root_path: str | Path = "."):
        """Create a file source rooted at a local directory."""
        self.root_path = Path(root_path).expanduser().resolve()

    def search(self, query: SearchQuery, *, batch_size: int = 10) -> RecordSet:
        """Search files and directories and return them as a RecordSet."""
        filters = dict(query.filters)
        max_results = int(filters.pop("max_results", 100))
        root_path = Path(filters.pop("root_path", self.root_path)).expanduser().resolve()
        name_contains = _normalize_string_list(filters.pop("name_contains", None))
        file_extensions = _normalize_extensions(filters.pop("file_extensions", None))
        date_from = _parse_date(filters.pop("date_from", None))
        date_to = _parse_date(filters.pop("date_to", None))

        if query.query:
            name_contains.append(query.query)

        records: list[Record] = []
        for path in _search_file_paths(
            root_path,
            name_contains=name_contains,
            file_extensions=file_extensions,
            date_from=date_from,
            date_to=date_to,
        ):
            if not _matches_file_filters(
                path,
                name_contains=name_contains,
                file_extensions=file_extensions,
                date_from=date_from,
                date_to=date_to,
            ):
                continue
            records.append(file_to_record(path, record_id=f"file_{len(records) + 1}"))
            if len(records) >= max_results:
                break

        return RecordSet(
            records=records,
            source=self,
            query=query,
            batch_size=batch_size,
        )

    def load_full(self, record_set: RecordSet, ids: list[str]) -> list[Record]:
        """Load text content for selected file records."""
        selected = record_set.get_by_ids(ids)
        loaded: list[Record] = []
        for record in selected:
            path_raw = record.source_ref.get("path")
            if not path_raw:
                loaded.append(record)
                continue

            path = Path(path_raw)
            if path.is_dir():
                record.content_loaded = True
                loaded.append(record)
                continue

            text = load_files_as_text([path])
            loaded.append(
                file_to_record(
                    path,
                    record_id=record.id,
                    text=text,
                    content_loaded=True,
                )
            )
        return loaded


def email_to_record(email: Email, *, record_id: str) -> Record:
    """Project an Email object into a generic Record."""
    children = [
        attachment_to_record(attachment, record_id=f"{record_id}_attachment_{idx + 1}")
        for idx, attachment in enumerate(email.attachments)
    ]
    return Record(
        id=record_id,
        record_type=RecordType.EMAIL,
        source_type=SourceType.EMAIL_SYSTEM,
        title=email.subject,
        text=email.text,
        summary=_summarize_text(email.text),
        metadata={
            "sender": email.sender,
            "recipient": email.recipient,
            "cc": email.cc,
            "reply_to": email.reply_to,
            "subject": email.subject,
            "message_id": email.message_id,
            "body_type": email.body_type,
            "folder": email._folder,
            "is_unread": email._is_unread,
            "labels": list(email._labels),
            "attachment_count": len(email.attachments),
        },
        source_ref={
            "provider": type(email.account).__name__ if email.account else None,
            "message_id": email.message_id,
            "folder": email._folder,
        },
        children=children,
        content_loaded=True,
        value=email,
    )


def file_to_record(
    path: Path,
    *,
    record_id: str,
    text: str | None = None,
    content_loaded: bool = False,
) -> Record:
    """Project a filesystem path into a generic Record."""
    stat = path.stat()
    return Record(
        id=record_id,
        record_type=_record_type_from_path(path),
        source_type=SourceType.FILESYSTEM,
        title=path.name,
        text=text,
        summary=_summarize_text(text or "") if text else None,
        metadata={
            "path": str(path),
            "filename": path.name,
            "file_extension": path.suffix.lower().lstrip("."),
            "size": stat.st_size,
            "is_directory": path.is_dir(),
            "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        },
        source_ref={
            "path": str(path),
        },
        content_loaded=content_loaded,
        value=path,
    )


def attachment_to_record(attachment: Attachment, *, record_id: str) -> Record:
    """Project an Attachment object into a generic child Record."""
    return Record(
        id=record_id,
        record_type=_record_type_from_content_type(attachment.content_type),
        source_type=SourceType.EMAIL_ATTACHMENT,
        title=attachment.filename,
        text=None,
        metadata={
            "filename": attachment.filename,
            "content_type": attachment.content_type,
            "size": len(attachment.content),
        },
        source_ref={
            "filename": attachment.filename,
            "content_type": attachment.content_type,
        },
        content_loaded=bool(attachment.content),
        value=attachment,
    )


def search_emails(
    account: EmailAccount,
    query: str | None = None,
    batch_size: int = 10,
    **filters: Any,
) -> RecordSet:
    """Search emails and return a readable RecordSet for batched flow processing."""
    source = EmailRecordSource(account)
    return source.search(SearchQuery(query=query, filters=filters), batch_size=batch_size)


def search_files(
    root_path: str | Path = ".",
    query: str | None = None,
    batch_size: int = 10,
    **filters: Any,
) -> RecordSet:
    """Search local files and return a readable RecordSet for batched flows."""
    source = FileRecordSource(root_path)
    filters = {"root_path": root_path, **filters}
    return source.search(SearchQuery(query=query, filters=filters), batch_size=batch_size)


def _summarize_text(text: str, max_chars: int = 300) -> str:
    """Create a compact summary fallback without invoking a model."""
    normalized = " ".join((text or "").split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def _search_file_paths(
    root_path: Path,
    *,
    name_contains: list[str],
    file_extensions: list[str],
    date_from: datetime | None,
    date_to: datetime | None,
) -> list[Path]:
    """Search paths using Spotlight on macOS, with portable fallback."""
    if root_path.is_file():
        return [root_path]
    if not root_path.exists():
        raise FileNotFoundError(f"File search root does not exist: {root_path}")

    if platform.system() == "Darwin":
        spotlight_paths = _search_file_paths_mdfind(
            root_path,
            name_contains=name_contains,
            file_extensions=file_extensions,
            date_from=date_from,
            date_to=date_to,
        )
        if spotlight_paths:
            return spotlight_paths

    return _search_file_paths_rglob(root_path)


def _search_file_paths_rglob(root_path: Path) -> list[Path]:
    """Yield candidate paths under a root path."""
    return sorted(root_path.rglob("*"))


def _search_file_paths_mdfind(
    root_path: Path,
    *,
    name_contains: list[str],
    file_extensions: list[str],
    date_from: datetime | None,
    date_to: datetime | None,
) -> list[Path]:
    """Search files with macOS Spotlight."""
    query = _build_mdfind_query(
        name_contains=name_contains,
        file_extensions=file_extensions,
        date_from=date_from,
        date_to=date_to,
    )
    if not query:
        return []

    result = subprocess.run(
        ["mdfind", "-onlyin", str(root_path), query],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []

    return sorted(Path(line).expanduser().resolve() for line in result.stdout.splitlines() if line)


def _build_mdfind_query(
    *,
    name_contains: list[str],
    file_extensions: list[str],
    date_from: datetime | None,
    date_to: datetime | None,
) -> str:
    """Build an mdfind query equivalent to the portable filters."""
    query_parts: list[str] = []

    if name_contains:
        name_query_parts = [
            f'kMDItemDisplayName == "*{_escape_mdfind_value(name_part)}*"c'
            for name_part in name_contains
        ]
        query_parts.append("(" + " || ".join(name_query_parts) + ")")

    if file_extensions:
        extension_query_parts = [
            f'kMDItemFSName == "*.{_escape_mdfind_value(file_extension)}"'
            for file_extension in file_extensions
        ]
        query_parts.append("(" + " || ".join(extension_query_parts) + ")")

    if date_from is not None:
        from_date = date_from.strftime("%Y-%m-%dT00:00:00Z")
        query_parts.append(f'kMDItemFSContentChangeDate >= "$time.iso({from_date})"')
    if date_to is not None:
        to_date = date_to.strftime("%Y-%m-%dT23:59:59Z")
        query_parts.append(f'kMDItemFSContentChangeDate <= "$time.iso({to_date})"')

    return " && ".join(query_parts)


def _escape_mdfind_value(value: str) -> str:
    """Escape double quotes for mdfind string fragments."""
    return value.replace('"', '\\"')


def _matches_file_filters(
    path: Path,
    *,
    name_contains: list[str],
    file_extensions: list[str],
    date_from: datetime | None,
    date_to: datetime | None,
) -> bool:
    """Return whether a filesystem path matches the search filters."""
    if name_contains and not any(part.lower() in path.name.lower() for part in name_contains):
        return False

    if file_extensions and path.is_file():
        if path.suffix.lower().lstrip(".") not in file_extensions:
            return False
    elif file_extensions and path.is_dir():
        return False

    modified_at = datetime.fromtimestamp(path.stat().st_mtime)
    if date_from and modified_at.date() < date_from.date():
        return False
    if date_to and modified_at.date() > date_to.date():
        return False
    return True


def _normalize_string_list(value: Any) -> list[str]:
    """Normalize scalar/list filter values to a list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def _normalize_extensions(value: Any) -> list[str]:
    """Normalize file extension filters without leading dots."""
    return [item.lower().lstrip(".") for item in _normalize_string_list(value)]


def _parse_date(value: Any) -> datetime | None:
    """Parse optional ISO date/datetime filters."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _record_type_from_path(path: Path) -> RecordType:
    """Map a filesystem path to a coarse RecordType."""
    if path.is_dir():
        return RecordType.DIRECTORY

    suffix = path.suffix.lower()
    suffix_map = {
        ".txt": RecordType.TEXT,
        ".md": RecordType.TEXT,
        ".csv": RecordType.CSV,
        ".pdf": RecordType.PDF,
        ".docx": RecordType.WORD,
        ".doc": RecordType.WORD,
        ".xlsx": RecordType.EXCEL,
        ".xls": RecordType.EXCEL,
        ".pptx": RecordType.POWERPOINT,
        ".ppt": RecordType.POWERPOINT,
        ".htm": RecordType.HTML,
        ".html": RecordType.HTML,
    }
    return suffix_map.get(suffix, RecordType.FILE)


def _record_type_from_content_type(content_type: str) -> RecordType:
    """Map attachment content types to coarse RecordType values."""
    content_type_lower = (content_type or "").lower()
    if "pdf" in content_type_lower:
        return RecordType.PDF
    if "word" in content_type_lower or "document" in content_type_lower:
        return RecordType.WORD
    if "spreadsheet" in content_type_lower or "excel" in content_type_lower:
        return RecordType.EXCEL
    if "presentation" in content_type_lower or "powerpoint" in content_type_lower:
        return RecordType.POWERPOINT
    if "csv" in content_type_lower:
        return RecordType.CSV
    if "html" in content_type_lower:
        return RecordType.HTML
    if "text" in content_type_lower:
        return RecordType.TEXT
    return RecordType.ATTACHMENT
