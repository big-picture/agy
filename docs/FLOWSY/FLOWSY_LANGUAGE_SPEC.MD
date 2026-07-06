# FLOWSY (Flows. Simple. YAMLish) — Specification v0.1

## 0. Status
This document specifies **FLOWSY v0.1**. FLOWSY is a strict, indentation-based description format for agentic flows.

FLOWSY is **YAML-like in appearance**, but **not YAML** and does not inherit YAML parsing rules.

---

## 1. Purpose
A FLOWSY document defines:

- Flow metadata (`name`, optional `description`)
- Input context (`context_in`)
- A set of named nodes (`nodes`) with:
  - `actions`: ordered statements (stored as raw strings)
  - stochastic request fields (`type`, `agent`, `requests`, optional `options`,
    `output`, `message`)
  - `edges`: ordered conditional transitions

---

## 2. Meta Section (Concrete Syntax Controls)

### 2.1 `meta` block
FLOWSY supports an optional `meta` block that controls concrete parsing rules.

```text
meta:
  indentation: 2
  dict_separator: ":"
  list_bullet: "-"
```

### 2.2 Semantics (v0.1 constraints)
- `meta.indentation`
  - **MAY** be specified.
  - If omitted, it defaults to `2`.
  - **MUST** be a positive integer.
  - Controls the number of spaces per indentation level.

- `meta.dict_separator`
  - **MAY** be specified.
  - If omitted, it defaults to `":"`.
  - **MUST** be `":"` in v0.1 (reserved for future versions).

- `meta.list_bullet`
  - **MAY** be specified.
  - If omitted, it defaults to `"-"`.
  - **MUST** be `"-"` in v0.1 (reserved for future versions).

Rationale: v0.1 stays YAML-like and deterministic; future versions may relax these constraints.

---

## 3. Lexical Rules

### 3.1 Lines
A FLOWSY document is a sequence of lines separated by `\n`.

### 3.2 Whitespace and indentation
- Tabs are **forbidden**.
- Indentation consists of spaces only.
- A line’s indentation is measured in leading spaces.

Let `N = meta.indentation` (default `2`).

FLOWSY uses discrete indentation levels: `0, N, 2N, 3N, ...`.

A parser **MUST** treat indentation as structural:
- A block begins after a key line ending in `:` with no inline value.
- A block ends when indentation decreases to a previous level.

### 3.3 Blank lines
Blank lines (empty or whitespace-only) are allowed and ignored.

### 3.4 Comments
A comment line is any line which, after removing leading whitespace, begins with `#`.
Comment lines are ignored.

Inline comments (e.g. `x: y  # comment`) are **not** specified in v0.1.

### 3.5 Identifiers
Unless stated otherwise:
- Keys and node names are identifiers matching: `[A-Za-z_][A-Za-z0-9_]*`.

---

## 4. Primitive Content Types

FLOWSY’s meta-grammar uses these primitive content types:

### 4.1 `scalar`
A `scalar` is a raw string captured from the source line.
FLOWSY does not interpret the scalar content.

### 4.2 `list`
A `list` is a block of list items. A list item line begins with:

```
<indent><meta.list_bullet><space>
```

In v0.1, that is:

```
<indent>-
```

The remainder of the line after the bullet+space is the list item payload.

### 4.3 `dict`
A `dict` is a block of key entries.

A dict entry is either:

1) **Inline entry**
```
<indent><key>:<space?><value>
```

2) **Block entry**
```
<indent><key>:
<indent+N>...
```

In a block entry, the value is the nested block.

### 4.4 `key_value_pair`
A `key_value_pair` is a single line that is split into `key` and `value` using a separator.
In v0.1 the separator is `meta.dict_separator` which is `:`.

Because `:` may appear inside Python-ish expressions, FLOWSY defines a *top-level* scanning rule.

#### 4.4.1 Separator definition (v0.1 implementation)
In v0.1, the reference implementation uses a simplified rule:

A `:` is considered a separator if it is **not** inside:
- single quotes `'...'`
- double quotes `"..."`

Implementations MAY add full nesting-awareness for `()[]{}` in later versions.

#### 4.4.2 `parsing: left` vs `parsing: right`
- `parsing: left` means: split on the **first** separator `:` that is not inside quotes
- `parsing: right` means: split on the **last** separator `:` that is not inside quotes

After splitting:
- `key = left_part.strip()`
- `value = right_part.strip()`

If no top-level separator exists, parsing fails.

Note: The reference implementation treats backslash-escaped quotes (`\"` / `\'`) as non-terminating quote characters.

---

## 5. Document Model (Abstract Syntax)

FLOWSY documents can be normalized into a structured representation.

Note: The **reference parser implementation** in this repository returns a tuple `(parsed_dict, source_spans)`.

### 5.1 Parsed Dictionary

The first element is the simplified shape used by `reference_flow_parsed.json`:

```json
{
  "name": "string",
  "description": "string",
  "context_in": { "string": "string" },
  "nodes": {
    "NodeName": {
      "type": "deterministic | stochastic",
      "agent": "string",
      "requests": ["string", "..."],
      "options": { "string": "string" },
      "output": "string",
      "message": "string",
      "actions": ["string", "..."],
      "edges": [
        { "string": "string" },
        "string"
      ]
    }
  }
}
```

For deterministic nodes, `type` may be omitted and defaults to
`deterministic`. For stochastic nodes, `type: stochastic` selects the agent
run runtime instead of deterministic action execution. The agent must expose
`run(...)`; `requests:` remains the list of natural-language instructions.

Stochastic node example:

```flowsy
nodes:
  summarize_yesterday:
    type: stochastic
    agent: consc
    requests:
      - "Create a Markdown table of yesterday's inbound emails."
      - "Add an answered column based on outbound emails."
    output: email_report_md
    message: agent_message
    edges:
      - success == True: send_report
      - end(success=False, error_msg=error_msg)
```

Edge entries are normally key-value pairs:

```flowsy
edges:
  - confidence < 0.7: manual_review
  - True: default_handler
```

The final edge may be written as a bare target string. This is normalized to an
unconditional fallback (`True: target`) and is valid only as the last edge:

```flowsy
edges:
  - confidence < 0.7: manual_review
  - default_handler
```

### 5.2 Source Spans

The second element is a dictionary mapping **paths** to **SourceSpan** objects. This enables precise error reporting with line numbers.

#### 5.2.1 SourceSpan Structure

```python
class SourceSpan(TypedDict):
    file_name: str    # Path to the .flowsy file
    start_line: int   # First line number (1-based)
    end_line: int     # Last line number (1-based, equals start_line for single-line elements)
    content: str      # Raw content (one or more lines)
```

#### 5.2.2 Path Format

Paths use dot notation for nested keys and bracket notation for list indices:

| Path | Description |
|------|-------------|
| `""` | Root flow element (not currently stored) |
| `name` | The `name` scalar |
| `description` | The `description` scalar |
| `context_in` | The `context_in` dict |
| `context_in.email` | A key in `context_in` |
| `nodes` | The `nodes` dict |
| `nodes.classify_email` | A specific node |
| `nodes.classify_email.actions` | The actions list of a node |
| `nodes.classify_email.actions[0]` | First action in the list |
| `nodes.classify_email.edges` | The edges list of a node |
| `nodes.classify_email.edges[0]` | First edge in the list |

#### 5.2.3 Example

For a flow file:

```yaml
name: Test Flow
nodes:
  first_node:
    actions:
      - action_one()
      - action_two()
```

The `source_spans` would include:

```python
{
    "name": {
        "file_name": "flow.flowsy",
        "start_line": 1,
        "end_line": 1,
        "content": "name: Test Flow"
    },
    "nodes.first_node.actions[0]": {
        "file_name": "flow.flowsy",
        "start_line": 5,
        "end_line": 5,
        "content": "      - action_one()"
    },
    "nodes.first_node.actions[1]": {
        "file_name": "flow.flowsy",
        "start_line": 6,
        "end_line": 6,
        "content": "      - action_two()"
    },
    # ... more spans
}
```

#### 5.2.4 Multiline Elements

For elements spanning multiple lines (e.g., nodes with actions and edges), `start_line` and `end_line` differ:

```python
"nodes.first_node": {
    "file_name": "flow.flowsy",
    "start_line": 3,   # Line where "first_node:" appears
    "end_line": 6,     # Last line of the node's content
    "content": "  first_node:\n    actions:\n      - action_one()\n      - action_two()"
}
```
