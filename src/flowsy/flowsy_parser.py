"""Module for flowsy parser."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NamedTuple, TypedDict, cast

import yaml


@dataclass(frozen=True)
class FlowsyConfig:
    """Represents a FlowsyConfig object."""

    indentation: int
    dict_separator: str
    list_bullet: str


class Line(NamedTuple):
    """Represents a Line object."""

    line_num: int
    indent: int  # number of leading spaces
    text: str  # stripped content
    raw: str  # original line


class SourceSpan(TypedDict):
    """Source location information for a parsed object."""

    file_name: str
    start_line: int
    end_line: int
    content: str


Occurrence = Literal["1", "?"]


class EntrySpec(NamedTuple):
    """Represents a EntrySpec object."""

    key: str
    occurrence: Occurrence
    content_type: str


class EntitySpec(NamedTuple):
    """Represents a EntitySpec object."""

    name: str
    content_type: str
    fix_name_entries: list[EntrySpec]
    parsing: Literal["left", "right"] | None


class Schema(NamedTuple):
    """Represents a Schema object."""

    config: FlowsyConfig
    entities: dict[str, EntitySpec]


def parse_flowsy(
    grammar_filename: str | Path, flow_filename: str | Path
) -> tuple[dict[str, Any], dict[str, SourceSpan]]:
    """
    Schema-driven FLOWSY parser.

    - `grammar_filename` points to a schema file like `flowsy_grammar.v0.1.yaml`
    - `flow_filename` points to a `.flowsy` file
    - The parser does NOT hardcode keys like `name`/`description`; it follows the schema.
    - Strict behavior: unknown keys are errors unless the schema explicitly models a free dict
      (e.g. `content_type: dict node`).

    Returns:
        Tuple of (parsed_dict, source_spans)
        - parsed_dict: The parsed flow as a dictionary
        - source_spans: Dictionary mapping paths (e.g., "nodes.classify_email.actions[0]")
                        to SourceSpan objects with line information
    """
    flow_path = Path(flow_filename)
    schema = load_schema(grammar_filename)
    lines, all_raw_lines = _read_flow_lines(flow_path)
    parser = _Interpreter(
        schema=schema,
        lines=lines,
        all_raw_lines=all_raw_lines,
        file_name=str(flow_path),
    )

    value = parser.parse_entity("flow", expected_indent=0, path="")
    parser.assert_eof()
    if not isinstance(value, dict):
        raise ValueError("Schema entity 'flow' must produce a dict")
    return cast(dict[str, Any], value), parser.source_spans


def load_schema(grammar_filename: str | Path) -> Schema:
    """
    Load schema from YAML using PyYAML.

    This MUST be schema-driven: changing keys in the schema should change what the parser accepts/returns,
    without code changes.
    """

    path = Path(grammar_filename)
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("Grammar file must be a YAML mapping at top-level")

    meta = doc.get("meta", {}) or {}
    if not isinstance(meta, dict):
        raise ValueError("Grammar meta must be a mapping")

    indentation = int(meta.get("indentation", 2))
    dict_separator = str(meta.get("dict_separator", ":"))
    list_bullet = str(meta.get("list_bullet", "-"))
    if indentation <= 0:
        raise ValueError(f"Invalid meta.indentation: {indentation}")

    entities: dict[str, EntitySpec] = {}
    for key, value in doc.items():
        if key in {"flowsy_version", "meta"}:
            continue
        if not isinstance(value, dict):
            raise ValueError(f"Entity '{key}' must be a mapping")

        content_type = value.get("content_type")
        if not isinstance(content_type, str):
            raise ValueError(f"Entity '{key}' is missing a string content_type")

        parsing = value.get("parsing")
        if parsing is not None and parsing not in {"left", "right"}:
            raise ValueError(f"Entity '{key}' has invalid parsing: {parsing!r}")

        fix_entries_raw = value.get("fix_name_entries") or []
        fix_name_entries: list[EntrySpec] = []
        if fix_entries_raw:
            if not isinstance(fix_entries_raw, list):
                raise ValueError(f"Entity '{key}' fix_name_entries must be a list")
            for item in fix_entries_raw:
                if not isinstance(item, dict):
                    raise ValueError(
                        f"Entity '{key}' fix_name_entries item must be a mapping"
                    )

                # Support TWO equivalent schema encodings:
                #
                # A) nested single-key mapping (older drafts):
                #    - name:
                #        occurrence: "1"
                #        content_type: scalar
                #
                # B) flat mapping (current `flowsy.v0.1.YAML`):
                #    - name:
                #      occurrence: "1"
                #      content_type: scalar
                #
                # In YAML, keys do NOT include the ':' character, so both encode as "name".
                entry_key: str | None = None
                entry_body: dict[str, Any]

                if len(item) == 1:
                    # A) nested
                    only_key = next(iter(item.keys()))
                    only_val = item[only_key]
                    if isinstance(only_key, str) and isinstance(only_val, dict):
                        entry_key = only_key
                        entry_body = cast(dict[str, Any], only_val)
                    else:
                        entry_body = item  # fall through to flat handling
                else:
                    entry_body = item

                if entry_key is None:
                    # B) flat: find the single "entry name" key besides the known meta keys
                    meta_keys = {"occurrence", "content_type"}
                    candidate_keys = [
                        k for k in entry_body.keys() if k not in meta_keys
                    ]
                    if len(candidate_keys) != 1:
                        raise ValueError(
                            f"Entity '{key}' fix_name_entries item must contain exactly one entry key "
                            f"(besides {sorted(meta_keys)}): {item!r}"
                        )
                    entry_key = str(candidate_keys[0])

                entry_key = entry_key.rstrip(":")

                occurrence_raw = entry_body.get("occurrence")
                occurrence = str(occurrence_raw)
                if occurrence not in {"1", "?"}:
                    raise ValueError(
                        f"Entity '{key}' entry {entry_key!r} has invalid occurrence"
                    )
                entry_ct = entry_body.get("content_type")
                if not isinstance(entry_ct, str):
                    raise ValueError(
                        f"Entity '{key}' entry {entry_key!r} missing content_type"
                    )

                fix_name_entries.append(
                    EntrySpec(
                        key=entry_key,
                        occurrence=cast(Occurrence, occurrence),
                        content_type=entry_ct,
                    )
                )

        entities[key] = EntitySpec(
            name=key,
            content_type=content_type,
            fix_name_entries=fix_name_entries,
            parsing=cast(Literal["left", "right"] | None, parsing),
        )

    if "flow" not in entities:
        raise ValueError("Grammar must define a top-level 'flow' entity")

    return Schema(
        config=FlowsyConfig(
            indentation=indentation,
            dict_separator=dict_separator,
            list_bullet=list_bullet,
        ),
        entities=entities,
    )


def split_colon_left_quote_aware(s: str, *, sep: str = ":") -> tuple[str, str]:
    """
    Split `s` on the first separator that is NOT inside single/double quotes.

    TODO: Extend to also ignore separators inside (), [], {} (nesting-aware),
    if/when FLOWSY needs true "top-level" scanning.
    """

    if sep not in s:
        raise ValueError(f"Missing separator {sep!r}: {s!r}")

    in_quotes = False
    quote_char: str | None = None
    for i, ch in enumerate(s):
        if ch in ('"', "'") and (i == 0 or s[i - 1] != "\\"):
            if not in_quotes:
                in_quotes = True
                quote_char = ch
            elif ch == quote_char:
                in_quotes = False
                quote_char = None
        elif ch == sep and not in_quotes:
            return s[:i], s[i + 1 :]

    raise ValueError(f"Could not find valid separator {sep!r} outside quotes in: {s!r}")


def split_colon_right_quote_aware(s: str, *, sep: str = ":") -> tuple[str, str]:
    """
    Split `s` on the last separator that is NOT inside single/double quotes.

    Intentionally aligned with `agy/ast_parser.py::parse_edge_with_ast`.

    TODO: Extend to also ignore separators inside (), [], {} (nesting-aware),
    if/when FLOWSY needs true "top-level" scanning.
    """

    if sep not in s:
        raise ValueError(f"Missing separator {sep!r}: {s!r}")

    in_quotes = False
    quote_char: str | None = None
    for i in range(len(s) - 1, -1, -1):
        ch = s[i]
        if ch in ('"', "'") and (i == 0 or s[i - 1] != "\\"):
            if not in_quotes:
                in_quotes = True
                quote_char = ch
            elif ch == quote_char:
                in_quotes = False
                quote_char = None
        elif ch == sep and not in_quotes:
            return s[:i], s[i + 1 :]

    raise ValueError(f"Could not find valid separator {sep!r} outside quotes in: {s!r}")


def _read_flow_lines(flow_path: Path) -> tuple[list[Line], list[str]]:
    """Read flow file and return parsed lines and all raw lines.

    Returns:
        Tuple of (parsed_lines, all_raw_lines)
        - parsed_lines: List of Line objects (non-empty, non-comment lines)
        - all_raw_lines: All raw lines from the file (for content extraction)
    """
    all_raw_lines = flow_path.read_text(encoding="utf-8").splitlines()
    out: list[Line] = []
    for idx, raw in enumerate(all_raw_lines, start=1):
        if not raw.strip():
            continue
        if raw.lstrip().startswith("#"):
            continue
        if "\t" in raw:
            raise ValueError(
                f"Line {idx}: Tabs are forbidden\n  Line content: {raw.rstrip()}"
            )
        indent = len(raw) - len(raw.lstrip(" "))
        out.append(Line(idx, indent, raw.strip(), raw))
    return out, all_raw_lines


class _Interpreter:
    """Represents a Interpreter object."""

    def __init__(
        self,
        *,
        schema: Schema,
        lines: list[Line],
        all_raw_lines: list[str],
        file_name: str,
    ) -> None:
        """Initialize the object.

        Args:
            schema: schema.
            lines: lines.
            all_raw_lines: all raw lines.
            file_name: file name.
        """
        self.schema = schema
        self.lines = lines
        self.all_raw_lines = all_raw_lines
        self.file_name = file_name
        self.i = 0
        self.source_spans: dict[str, SourceSpan] = {}

    def _make_span(self, start_line: int, end_line: int) -> SourceSpan:
        """Create a SourceSpan from line range."""
        # Extract content from all_raw_lines (0-indexed)
        content_lines = self.all_raw_lines[start_line - 1 : end_line]
        content = "\n".join(content_lines)
        return SourceSpan(
            file_name=self.file_name,
            start_line=start_line,
            end_line=end_line,
            content=content,
        )

    def _record_span(self, path: str, start_line: int, end_line: int) -> None:
        """Record a SourceSpan for the given path."""
        self.source_spans[path] = self._make_span(start_line, end_line)

    def assert_eof(self) -> None:
        """Assert eof."""
        if self.i != len(self.lines):
            line = self.lines[self.i]
            raise ValueError(
                f"Line {line.line_num}: Unexpected trailing content\n  Line content: {line.raw.rstrip()}"
            )

    def _indent_multiple_ok(self, indent: int) -> None:
        """Indent multiple ok.

        Args:
            indent: indent.
        """
        n = self.schema.config.indentation
        if indent % n != 0:
            line = self._peek()
            line_info = ""
            if line:
                line_info = f"\n  Line content: {line.raw.rstrip()}"
            raise ValueError(
                f"Line {line.line_num if line else '?'}: Invalid indentation ({indent} spaces). Expected multiples of {n}.{line_info}"
            )

    def _peek(self) -> Line | None:
        """Peek.

        Returns:
            Line | None: Operation result.
        """
        if self.i >= len(self.lines):
            return None
        return self.lines[self.i]

    def _pop(self) -> Line:
        """Pop.

        Returns:
            Line: Operation result.
        """
        line = self.lines[self.i]
        self.i += 1
        return line

    def parse_entity(self, entity_name: str, *, expected_indent: int, path: str) -> Any:
        """Parse entity.

        Args:
            entity_name: entity name.
            expected_indent: expected indent.
            path: path.

        Returns:
            Any: Operation result.
        """
        if entity_name not in self.schema.entities:
            raise ValueError(f"Schema references unknown entity: {entity_name}")
        entity = self.schema.entities[entity_name]

        ct = entity.content_type
        if ct == "scalar":
            return self._parse_scalar(expected_indent=expected_indent, path=path)
        if ct == "key_value_pair":
            return self._parse_key_value_pair(
                entity, expected_indent=expected_indent, path=path
            )

        if ct.startswith("list "):
            elem_entity = ct.split(" ", 1)[1].strip()
            return self._parse_list(
                elem_entity, expected_indent=expected_indent, path=path
            )

        if ct == "dict":
            # fixed-key dict
            return self._parse_fixed_dict(
                entity, expected_indent=expected_indent, path=path
            )

        if ct.startswith("dict "):
            value_entity = ct.split(" ", 1)[1].strip()
            return self._parse_generic_dict(
                value_entity, expected_indent=expected_indent, path=path
            )

        raise ValueError(f"Unsupported content_type for entity '{entity_name}': {ct!r}")

    def _parse_scalar(self, *, expected_indent: int, path: str) -> str:
        """Parse scalar.

        Args:
            expected_indent: expected indent.
            path: path.

        Returns:
            str: Operation result.
        """
        line = self._peek()
        if not line:
            raise ValueError("Unexpected EOF while parsing scalar")
        self._indent_multiple_ok(line.indent)
        if line.indent != expected_indent:
            raise ValueError(
                f"Line {line.line_num}: Wrong indentation for scalar. Expected {expected_indent}, got {line.indent}\n  Line content: {line.raw.rstrip()}"
            )
        popped = self._pop()
        if path:
            self._record_span(path, popped.line_num, popped.line_num)
        return popped.text

    def _parse_key_value_pair(
        self, entity: EntitySpec, *, expected_indent: int, path: str
    ) -> dict[str, str]:
        """Parse key value pair.

        Args:
            entity: entity.
            expected_indent: expected indent.
            path: path.

        Returns:
            dict[str, str]: Operation result.
        """
        line = self._peek()
        if not line:
            raise ValueError("Unexpected EOF while parsing key_value_pair")
        self._indent_multiple_ok(line.indent)
        if line.indent != expected_indent:
            raise ValueError(
                f"Line {line.line_num}: Wrong indentation for key_value_pair. Expected {expected_indent}, got {line.indent}\n  Line content: {line.raw.rstrip()}"
            )
        popped = self._pop()
        text = popped.text
        sep = self.schema.config.dict_separator
        if sep not in text:
            raise ValueError(
                f"Line {line.line_num}: Missing separator {sep!r} in key_value_pair\n  Line content: {line.raw.rstrip()}"
            )
        if entity.parsing == "right":
            k, v = split_colon_right_quote_aware(text, sep=sep)
        else:
            # default to left
            k, v = split_colon_left_quote_aware(text, sep=sep)
        if path:
            self._record_span(path, popped.line_num, popped.line_num)
        return {k.strip(): v.strip()}

    def _parse_list(
        self, elem_entity: str, *, expected_indent: int, path: str
    ) -> list[Any]:
        """Parse list.

        Args:
            elem_entity: elem entity.
            expected_indent: expected indent.
            path: path.

        Returns:
            list[Any]: Operation result.
        """
        bullet = f"{self.schema.config.list_bullet} "
        items: list[Any] = []
        start_line: int | None = None
        end_line: int | None = None
        item_idx = 0

        while True:
            line = self._peek()
            if not line:
                break
            self._indent_multiple_ok(line.indent)
            if line.indent < expected_indent:
                break
            if line.indent > expected_indent:
                raise ValueError(
                    f"Line {line.line_num}: Unexpected indentation in list. Expected {expected_indent}, got {line.indent}\n  Line content: {line.raw.rstrip()}"
                )
            if not line.text.startswith(bullet):
                break

            popped = self._pop()
            if start_line is None:
                start_line = popped.line_num
            end_line = popped.line_num

            payload = popped.text[len(bullet) :].strip()
            if not payload:
                raise ValueError(
                    f"Line {line.line_num}: Empty list item\n  Line content: {line.raw.rstrip()}"
                )

            elem_spec = self.schema.entities.get(elem_entity)
            if not elem_spec:
                raise ValueError(
                    f"Schema references unknown list element entity: {elem_entity}"
                )

            # Record span for this list item
            item_path = f"{path}[{item_idx}]" if path else f"[{item_idx}]"
            self._record_span(item_path, popped.line_num, popped.line_num)

            if elem_spec.content_type == "scalar":
                items.append(payload)
            elif elem_spec.content_type == "key_value_pair":
                sep = self.schema.config.dict_separator
                if sep not in payload:
                    raise ValueError(
                        f"Line {line.line_num}: Missing separator {sep!r} in list key_value_pair\n  Line content: {line.raw.rstrip()}"
                    )
                if elem_spec.parsing == "right":
                    k, v = split_colon_right_quote_aware(payload, sep=sep)
                else:
                    k, v = split_colon_left_quote_aware(payload, sep=sep)
                items.append({k.strip(): v.strip()})
            elif elem_spec.content_type == "edge":
                sep = self.schema.config.dict_separator
                try:
                    if elem_spec.parsing == "right":
                        k, v = split_colon_right_quote_aware(payload, sep=sep)
                    else:
                        k, v = split_colon_left_quote_aware(payload, sep=sep)
                    items.append({k.strip(): v.strip()})
                except ValueError:
                    items.append(payload)
            else:
                # Not needed for v0.1; keep strict.
                raise ValueError(
                    f"Unsupported list element content_type '{elem_spec.content_type}' for entity '{elem_entity}'"
                )
            item_idx += 1

        # Record span for the entire list (only if we parsed items)
        if path and start_line is not None and end_line is not None:
            self._record_span(path, start_line, end_line)

        return items

    def _parse_fixed_dict(
        self, entity: EntitySpec, *, expected_indent: int, path: str
    ) -> dict[str, Any]:
        # Parse dict entries until indentation decreases.
        """Parse fixed dict.

        Args:
            entity: entity.
            expected_indent: expected indent.
            path: path.

        Returns:
            dict[str, Any]: Operation result.
        """
        out: dict[str, Any] = {}
        allowed = {e.key: e for e in entity.fix_name_entries}
        seen: dict[str, int] = {k: 0 for k in allowed.keys()}
        start_line: int | None = None
        end_line: int | None = None

        while True:
            line = self._peek()
            if not line:
                break
            self._indent_multiple_ok(line.indent)
            if line.indent < expected_indent:
                break
            if line.indent > expected_indent:
                raise ValueError(
                    f"Line {line.line_num}: Unexpected indentation in dict. Expected {expected_indent}, got {line.indent}\n  Line content: {line.raw.rstrip()}"
                )

            # key: value  OR  key:
            text = line.text
            if not text.endswith(":") and self.schema.config.dict_separator not in text:
                break

            if start_line is None:
                start_line = line.line_num

            # decide if inline or block by finding first separator outside quotes
            sep = self.schema.config.dict_separator
            key_part: str
            value_part: str | None
            key_line_num = line.line_num
            if text.endswith(":") and (
                sep not in text[:-1] or text.rstrip().endswith(":")
            ):
                # block entry (key:)
                key_part = text[:-1].strip()
                value_part = None
                self._pop()
            else:
                # inline entry (key: value)
                key_part, v = split_colon_left_quote_aware(text, sep=sep)
                key_part = key_part.strip()
                value_part = v.strip()
                self._pop()

            if key_part not in allowed:
                raise ValueError(
                    f"Line {line.line_num}: Unknown key '{key_part}' for entity '{entity.name}'\n  Line content: {line.raw.rstrip()}"
                )
            spec = allowed[key_part]
            seen[key_part] += 1
            if seen[key_part] > 1:
                raise ValueError(
                    f"Line {line.line_num}: Duplicate key '{key_part}' for entity '{entity.name}'\n  Line content: {line.raw.rstrip()}"
                )

            # Build path for this key
            key_path = f"{path}.{key_part}" if path else key_part

            if value_part is not None:
                # inline scalar only (v0.1 schema uses scalar at top-level here)
                if spec.content_type != "scalar":
                    raise ValueError(
                        f"Line {line.line_num}: Inline value not supported for content_type '{spec.content_type}'\n  Line content: {line.raw.rstrip()}"
                    )
                out[key_part] = value_part
                # Record span for inline scalar
                self._record_span(key_path, key_line_num, key_line_num)
                end_line = key_line_num
                continue

            # block value parsed by content_type
            nested_indent = expected_indent + self.schema.config.indentation
            out[key_part] = self._parse_value_by_content_type(
                spec.content_type, expected_indent=nested_indent, path=key_path
            )
            # Update end_line to include the block content
            if self.i > 0:
                end_line = self.lines[self.i - 1].line_num

        # required checks
        for k, spec in allowed.items():
            if spec.occurrence == "1" and seen[k] == 0:
                raise ValueError(
                    f"Missing required key '{k}' for entity '{entity.name}'"
                )

        # Record span for the entire dict
        if path and start_line is not None and end_line is not None:
            self._record_span(path, start_line, end_line)

        return out

    def _parse_generic_dict(
        self, value_entity: str, *, expected_indent: int, path: str
    ) -> dict[str, Any]:
        """Parse generic dict.

        Args:
            value_entity: value entity.
            expected_indent: expected indent.
            path: path.

        Returns:
            dict[str, Any]: Operation result.
        """
        out: dict[str, Any] = {}
        start_line: int | None = None
        end_line: int | None = None

        # If the value entity is a key_value_pair, the dict entry is directly produced from a single line.
        elem = self.schema.entities.get(value_entity)
        if not elem:
            raise ValueError(
                f"Schema references unknown dict value entity: {value_entity}"
            )

        while True:
            line = self._peek()
            if not line:
                break
            self._indent_multiple_ok(line.indent)
            if line.indent < expected_indent:
                break
            if line.indent > expected_indent:
                raise ValueError(
                    f"Line {line.line_num}: Unexpected indentation in dict. Expected {expected_indent}, got {line.indent}\n  Line content: {line.raw.rstrip()}"
                )

            if start_line is None:
                start_line = line.line_num

            if elem.content_type == "key_value_pair":
                key_path = (
                    f"{path}.{line.text.split(':')[0].strip()}"
                    if path
                    else line.text.split(":")[0].strip()
                )
                pair = self._parse_key_value_pair(
                    elem, expected_indent=expected_indent, path=key_path
                )
                # key_value_pair returns a single-entry dict
                ((k, v),) = pair.items()
                if k in out:
                    raise ValueError(
                        f"Line {line.line_num}: Duplicate key '{k}' in dict\n  Line content: {line.raw.rstrip()}"
                    )
                out[k] = v
                end_line = line.line_num
                continue

            # Otherwise: expect "key:" (block) or "key: value" (inline scalar)
            text = line.text
            if not text.endswith(":") and self.schema.config.dict_separator not in text:
                break

            sep = self.schema.config.dict_separator
            key_line_num = line.line_num
            if text.endswith(":") and (
                sep not in text[:-1] or text.rstrip().endswith(":")
            ):
                key = text[:-1].strip()
                self._pop()
                if not key:
                    raise ValueError(
                        f"Line {line.line_num}: Empty dict key\n  Line content: {line.raw.rstrip()}"
                    )
                if key in out:
                    raise ValueError(
                        f"Line {line.line_num}: Duplicate key '{key}' in dict\n  Line content: {line.raw.rstrip()}"
                    )
                nested_indent = expected_indent + self.schema.config.indentation
                key_path = f"{path}.{key}" if path else key
                # Track start of this key's block
                key_start_line = key_line_num
                out[key] = self.parse_entity(
                    value_entity, expected_indent=nested_indent, path=key_path
                )
                # Track end of this key's block
                if self.i > 0:
                    key_end_line = self.lines[self.i - 1].line_num
                    self._record_span(key_path, key_start_line, key_end_line)
                    end_line = key_end_line
            else:
                key_part, value_part = split_colon_left_quote_aware(text, sep=sep)
                key = key_part.strip()
                val = value_part.strip()
                self._pop()
                if key in out:
                    raise ValueError(
                        f"Line {line.line_num}: Duplicate key '{key}' in dict\n  Line content: {line.raw.rstrip()}"
                    )
                # Inline values are treated as scalar for now; if schema evolves, it can express scalar entities.
                if elem.content_type != "scalar":
                    raise ValueError(
                        f"Line {line.line_num}: Inline dict values require scalar value entity (got {elem.content_type})\n  Line content: {line.raw.rstrip()}"
                    )
                out[key] = val
                key_path = f"{path}.{key}" if path else key
                self._record_span(key_path, key_line_num, key_line_num)
                end_line = key_line_num

        # Record span for the entire dict
        if path and start_line is not None and end_line is not None:
            self._record_span(path, start_line, end_line)

        return out

    def _parse_value_by_content_type(
        self, content_type: str, *, expected_indent: int, path: str
    ) -> Any:
        """Parse value by content type.

        Args:
            content_type: content type.
            expected_indent: expected indent.
            path: path.

        Returns:
            Any: Operation result.
        """
        if content_type == "scalar":
            return self._parse_scalar(expected_indent=expected_indent, path=path)
        if content_type == "key_value_pair":
            # requires an entity to select parsing direction; enforce schema to use entity references.
            raise ValueError(
                "key_value_pair must be referenced via an entity name in schema"
            )
        if content_type.startswith("dict "):
            value_entity = content_type.split(" ", 1)[1].strip()
            return self._parse_generic_dict(
                value_entity, expected_indent=expected_indent, path=path
            )
        if content_type.startswith("list "):
            elem_entity = content_type.split(" ", 1)[1].strip()
            return self._parse_list(
                elem_entity, expected_indent=expected_indent, path=path
            )
        if content_type == "dict":
            raise ValueError(
                "Anonymous 'dict' blocks must be modeled as an entity with fix_name_entries"
            )

        # Otherwise treat it as an entity name (most flexible).
        return self.parse_entity(
            content_type, expected_indent=expected_indent, path=path
        )
