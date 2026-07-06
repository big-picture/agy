"""Generic record search results for batch-oriented flows."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class RecordType(StrEnum):
    """Domain type of a record independent of the backing system."""

    EMAIL = "email"
    ATTACHMENT = "attachment"
    FILE = "file"
    DIRECTORY = "directory"
    TEXT = "text"
    HTML = "html"
    PDF = "pdf"
    WORD = "word"
    EXCEL = "excel"
    POWERPOINT = "powerpoint"
    CSV = "csv"
    WEBPAGE = "webpage"
    PAPER = "paper"
    TICKET = "ticket"
    OTHER = "other"


class SourceType(StrEnum):
    """Technical origin of a record."""

    EMAIL_SYSTEM = "email_system"
    EMAIL_ATTACHMENT = "email_attachment"
    FILESYSTEM = "filesystem"
    WEB = "web"
    WEB_DOWNLOAD = "web_download"
    API = "api"
    DATABASE = "database"
    GENERATED = "generated"
    OTHER = "other"


@dataclass
class SearchQuery:
    """Search parameters used to produce a RecordSet."""

    query: str | None = None
    filters: dict[str, Any] = field(default_factory=dict)


@dataclass
class Record:
    """Neutral information object used by Agy flows."""

    id: str
    record_type: RecordType
    source_type: SourceType
    title: str = ""
    text: str | None = None
    summary: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    source_ref: dict[str, Any] = field(default_factory=dict)
    children: list[Record] = field(default_factory=list)
    content_loaded: bool = False
    value: Any | None = field(default=None, repr=False, compare=False)

    def short_text(self, max_chars: int = 500) -> str:
        """Return compact text suitable for batch screening."""
        text = self.summary or self.text or ""
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 3].rstrip() + "..."

    def to_prompt_dict(self, max_chars: int = 500) -> dict[str, Any]:
        """Return a compact, model-friendly representation."""
        return {
            "id": self.id,
            "record_type": self.record_type.value,
            "source_type": self.source_type.value,
            "title": self.title,
            "text": self.short_text(max_chars=max_chars),
            "metadata": self.metadata,
            "children": [
                {
                    "id": child.id,
                    "record_type": child.record_type.value,
                    "title": child.title,
                    "content_loaded": child.content_loaded,
                }
                for child in self.children
            ],
            "content_loaded": self.content_loaded,
        }


@runtime_checkable
class RecordSource(Protocol):
    """Adapter that knows how to search and fully load records."""

    def search(self, query: SearchQuery, *, batch_size: int = 10) -> RecordSet:
        """Search this source and return a RecordSet."""
        ...

    def load_full(self, record_set: RecordSet, ids: list[str]) -> list[Record]:
        """Load full content for records in a RecordSet."""
        ...


@dataclass
class RecordSet:
    """Search result with cursor, batching and lazy-loading support."""

    records: list[Record]
    source: RecordSource | None = None
    query: SearchQuery = field(default_factory=SearchQuery)
    batch_size: int = 10
    cursor: int = 0

    def __len__(self) -> int:
        """Return number of records in this result set."""
        return len(self.records)

    def __iter__(self):
        """Iterate over all records."""
        return iter(self.records)

    def __getitem__(self, index: int) -> Record:
        """Return a record by list index."""
        return self.records[index]

    def get_current_batch(self) -> list[Record]:
        """Return the current batch without advancing the cursor."""
        return self.records[self.cursor : self.cursor + self.batch_size]

    def get_next_batch(self) -> list[Record]:
        """Return the next batch and advance the cursor deterministically."""
        batch = self.get_current_batch()
        self.cursor += len(batch)
        return batch

    def has_next_batch(self) -> bool:
        """Return whether another batch can be read."""
        return self.cursor < len(self.records)

    def reset(self) -> None:
        """Reset the cursor to the first record."""
        self.cursor = 0

    def get_by_ids(self, ids: list[str]) -> list[Record]:
        """Return records matching ids in the requested order."""
        by_id = {record.id: record for record in self.records}
        return [by_id[record_id] for record_id in ids if record_id in by_id]

    def load_full(self, ids: list[str] | str) -> list[Record]:
        """Load full content for selected records via the backing source."""
        record_ids = _normalize_ids(ids)
        if self.source is None:
            return self.get_by_ids(record_ids)

        loaded = self.source.load_full(self, record_ids)
        self._replace_records(loaded)
        return loaded

    def _replace_records(self, loaded_records: list[Record]) -> None:
        """Replace loaded records in-place while preserving result ordering."""
        if not loaded_records:
            return

        by_id = {record.id: record for record in loaded_records}
        self.records = [by_id.get(record.id, record) for record in self.records]


def _normalize_ids(ids: list[str] | str) -> list[str]:
    """Normalize model or flow-provided ids to a list of strings."""
    if isinstance(ids, str):
        return [part.strip() for part in ids.split(",") if part.strip()]
    return [str(record_id) for record_id in ids]
