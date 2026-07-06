# AGY Flow Parsing - Complete Reference

## Overview

AGY uses a **hybrid parsing approach** combining FLOWSY structure parsing with AST-based expression evaluation. FLOWSY (Flows. Simple. YAMLish) is a strict, indentation-based format that allows the flow structure to be parsed reliably while supporting any valid Python expression in actions and edges.

## Architecture

### Two-Phase Parsing

1. **Phase 1: Structure Parsing** (FLOWSY parser)
   - Parses FLOWSY structure (name, description, context_in, nodes) using schema-driven parser
   - Extracts actions and edges as raw strings
   - Uses strict indentation rules (0, 2, 4, 6 spaces)
   - Quote-aware colon splitting for key-value pairs

2. **Phase 2: Expression Parsing** (AST-based)
   - Parses actions and edges using Python AST
   - Converts expressions to evaluable code strings
   - Validates syntax but doesn't restrict functionality

## File Structure

### Top-Level Keys

The flow file starts with these keys at **0 spaces** indentation:

```flowsy
name: Flow Name                    # Flow identifier (required)
description: Flow description     # Human-readable description (optional)
context_in:                       # Required input objects (optional)
  variable_name: TypeName         # Variable definitions (2 spaces)
nodes:                            # Flow nodes (required)
  node_name:                      # Node definition (2 spaces, dictionary-style)
    type: stochastic              # Optional: deterministic (default) or stochastic
    agent: consc                  # Required for stochastic nodes
    requests:                     # Required for stochastic nodes
      - "Natural-language request"
    actions:                      # Node actions (4 spaces, optional)
      - action_string             # Action expression (6 spaces)
    edges:                        # Node edges (4 spaces, optional)
      - condition: target        # Edge definition (6 spaces)
      - fallback_target          # Final fallback shorthand (6 spaces)
```

### Required vs Optional Fields

**Required Fields:**
- `name`: Flow identifier (string)
- `nodes`: List of nodes (at least one node required)

**Optional Fields:**
- `description`: Human-readable description (string, defaults to empty string)
- `context_in`: Input object definitions (dictionary, defaults to empty)

**Node Required Fields:**
- `name`: Node identifier (string)

**Node Optional Fields:**
- `type`: Node type (`deterministic` by default, or `stochastic`)
- `agent`: Context key of the agent object for stochastic nodes
- `requests`: Natural-language requests for stochastic nodes
- `options`: Optional key-value options passed to the agent request
- `output`: Context key receiving the final agent output
- `message`: Context key receiving the final agent message
- `actions`: List of actions (defaults to empty list)
- `edges`: List of edges (defaults to empty list)
- `outputs`: Output definitions (defaults to empty dictionary)
- `instruction`: Instruction for stochastic nodes (defaults to `None`)

### Indentation Rules

**Strict YAML-style indentation** (each level adds 2 spaces):

- **0 Spaces**: Top-level keys (`name:`, `description:`, `context_in:`, `nodes:`)
- **2 Spaces**:
  - Context entries: `variable_name: TypeName`
  - Node list items: `- node_name:`
- **4 Spaces**:
  - Node keys: `actions:`, `edges:`
- **6 Spaces**:
  - Action list items: `- action_expression`
  - Edge list items: `- condition: target`

**Example:**
```flowsy
nodes:                    # 0 spaces
  classify:              # 2 spaces (dictionary-style, not list-style)
    actions:              # 4 spaces
      - show("x")         # 6 spaces
    edges:                # 4 spaces
      - x == y: process_z # 6 spaces
      - fallback          # 6 spaces, final fallback shorthand
```

## Context Input (`context_in`)

Defines required input objects that must be provided when executing the flow.

**Format:**
```flowsy
context_in:
  variable_name: TypeName
  another_var: AnotherType
```

**Rules:**
- Each entry on **2 spaces** indentation
- Format: `variable_name: TypeName`
- Variable name must be a valid Python identifier
- Type name is a string (used for type checking/documentation)

**Example:**
```flowsy
context_in:
  email: Email
  user_id: int
  config: Config
```

## Nodes

Nodes define the workflow steps. Each node has:
- **Name**: Unique identifier
- **Actions**: List of expressions to execute
- **Edges**: Conditional transitions to other nodes

### Node Definition

**Format:**
```flowsy
nodes:
  node_name:
    actions:
      - action_expression_1
      - action_expression_2
    edges:
      - condition_1: target_node_name_1
      - condition_2: target_node_name_2
```

**Rules:**
- Node definition uses dictionary-style at **2 spaces** (not list-style with `-`)
- Node name followed by `:`
- `actions:` and `edges:` at **4 spaces**
- Actions and edges at **6 spaces**

### Stochastic Nodes

Stochastic nodes do not run deterministic action expressions. Instead, they call
an agent object from `context_in` with one or more natural-language requests.
The agent must expose `run(...)`; the FLOWSY `requests:` field remains the list
of instructions passed to that method. Request entries may be plain text or
Python expressions evaluated with the current flow context. Evaluated request
expressions must return a string.

**Format:**

```flowsy
context_in:
  consc: Consciousness
  project_name: str

nodes:
  summarize_yesterday:
    type: stochastic
    agent: consc
    requests:
      - f'Find all mails discussing {project_name} in all different spellings in the mails of the last two weeks.'
      - "Read yesterday's inbound emails and write a Markdown table."
      - "Add an answered column based on outbound emails."
    options:
      mode: careful
    output: email_report_md
    message: agent_message
    edges:
      - success == True: send_report
      - end(success=False, error_msg=error_msg)
```

**Behavior:**
- Requests are executed sequentially.
- The previous request's output is passed to agents that accept
  `previous_output`.
- Agent return values are normalized to `AgentRequestResult`.
- The final output is written to the configured `output` key, the final message
  to the configured `message` key, and all request outputs to `agent_outputs`.
- `success`, `error_msg` and `result` are written before edge evaluation.

### Actions

Actions are **any valid Python expression** that will be evaluated at runtime.

#### Assignment Actions

**Format:** `variable = expression`

**Behavior:**
- Expression is evaluated with flow context
- Result is assigned to `variable` in context
- Also written to `context["result"]`

**Examples:**
```flowsy
- category = classify(input_text=email.text, categories=["sales", "support"])
- missing_list = validation["missing_fields"]
- text = ", ".join(missing_list)
- answer = f"Category: {category}"
- count = len(data)
```

#### Expression Actions

**Format:** `expression` (no assignment)

**Behavior:**
- Expression is evaluated with flow context
- Result is written to `context["result"]` only

**Examples:**
```flowsy
- show("Processing email")
- email.forward("billing@acme.com")
- classify(input_text=email.text, categories=["sales", "support"])
```

#### Supported Expression Types

**ALL valid Python expressions are supported**, including:

- **Function calls**: `func(args)`, `obj.method(args)`
- **Method calls on literals**: `", ".join(list)`, `"text".upper()`
- **Dictionary/list access**: `obj["key"]`, `list[0]`
- **Attribute access**: `obj.attr`, `obj.method()`
- **F-Strings**: `f"Text {var}"`
- **Binary operations**: `a + b`, `a * b`, `a == b`
- **Built-in functions**: `len()`, `str()`, `list()`, `dict()`, `min()`, `max()`, etc.
- **Complex expressions**: `len(data) > 0 and data[0] == "value"`

#### Safe Built-ins

The following built-in functions are available in expressions:

- **Type constructors**: `str()`, `int()`, `float()`, `bool()`, `list()`, `dict()`, `tuple()`, `set()`
- **Common functions**: `len()`, `min()`, `max()`, `sum()`, `abs()`, `round()`, `sorted()`, `reversed()`, `enumerate()`, `zip()`, `range()`
- **Type checking**: `isinstance()`, `type()`
- **Constants**: `None`, `True`, `False`

**Security**: Dangerous built-ins like `open()`, `__import__()`, `exec()`, `eval()` are **NOT available**.

### Edges

Edges define conditional transitions between nodes.

**Format:** `condition_expression : target_node`

**Rules:**
- Condition is **any valid Python expression** that evaluates to a boolean
- Separator is `:` (colon)
- Target is a node name or `end(...)`
- If condition contains colons (e.g., in strings), the **last** colon is used as separator
- The final edge may omit the condition entirely. This is shorthand for
  `True: target` and is only valid as the last edge.

**Examples:**
```flowsy
edges:
  - category == "sales": handle_sales
  - validation["is_complete"] == True: complete_claim
  - len(missing_fields) > 0: request_info
  - True: end()  # Unconditional termination
  - show("Status: active"): next_node  # Colon in string is handled correctly
  - fallback_node  # Final fallback shorthand, same as True: fallback_node
```

**Edge Evaluation:**
- Condition is evaluated as Python expression with flow context
- Must evaluate to `True` or `False`
- If `True`, flow transitions to target node
- If `False`, next edge is checked
- If no edge matches, node terminates

**Special Targets:**
- `end()` or `end(...)`: Terminates the flow (calls `end()` action)

## Complete Example

```flowsy
name: Email Classification Flow
description: Classify and route emails
context_in:
  email: Email

nodes:
  classify:
    actions:
      - show("Starting classification")
      - category = classify(
          input_text=email.text,
          categories=["sales", "support", "billing"],
          instruction_file="prompts/classify.md"
        )
      - confidence_score = confidence
      - result_text = f"Category: {category}, Confidence: {confidence_score:.2f}"
      - show(result_text)
    edges:
      - category == "sales": handle_sales
      - category == "support": handle_support
      - category == "billing": handle_billing
      - confidence_score < 0.7: unclear
      - True: end()

  handle_sales:
    actions:
      - email.forward("sales@acme.com")
      - email.move("processed")
    edges:
      - True: end()

  handle_support:
    actions:
      - ticket_id = create_ticket(email.text)
      - email.reply(f"Ticket created: {ticket_id}")
      - email.move("processed")
    edges:
      - True: end()

  handle_billing:
    actions:
      - email.forward("billing@acme.com")
      - email.move("processed")
    edges:
      - True: end()

  unclear:
    actions:
      - email.enrich("Low confidence classification")
      - email.move("human_review")
    edges:
      - True: end()
```

## Parsing Process

### Step 1: Structure Parsing (FLOWSY parser)

1. Read file line by line
2. Count leading spaces to determine indentation level
3. Use quote-aware colon splitting to identify key-value pairs
4. Extract:
   - `name` and `description` (0 spaces)
   - `context_in` entries (2 spaces)
   - Node definitions (2 spaces, dictionary-style `node_name:`)
   - `actions:` and `edges:` keys (4 spaces)
   - Action and edge strings (6 spaces)
5. Return structured data as dictionary matching the flow structure

### Step 2: Action Parsing (`parse_action_with_ast()`)

1. Parse action string with `ast.parse()`
2. Check if it's an assignment or expression
3. Convert expression to Python code string with `ast.unparse()`
4. Create `ActionCall` with:
   - `object_name="global_function"`
   - `method_name="__eval__"`
   - `args=[(code_string, False)]`
   - `output=variable_name` or `"result"`

### Step 3: Edge Parsing (`parse_edge_with_ast()`)

1. Find last `:` that's not inside quotes
2. Split into condition and target
3. Validate condition is valid Python AST
4. Return `(condition_string, target_string)`

### Step 4: Execution (`ActionExecutor`)

1. For `__eval__` actions:
   - Get expression string from args
   - Evaluate with `eval(expr_str, {"__builtins__": SAFE_BUILTINS}, context)`
   - Write result to context variable or `context["result"]`

2. For edges:
   - Evaluate condition expression
   - If `True`, transition to target node
   - If `False`, check next edge

## Error Handling

- **Invalid Python syntax**: Raises `ValueError` with syntax error details
- **Invalid indentation**: Actions/edges not recognized (silently ignored or error)
- **Missing target node**: Raises `ValueError` when edge references non-existent node
- **Evaluation errors**: Raises `ValueError` with expression and error details

## Security Considerations

- Only safe built-ins are available (no `open()`, `__import__()`, etc.)
- Expressions run in isolated namespace with flow context
- No arbitrary code execution beyond flow-defined expressions
- Context is controlled by flow definition

## Limitations

- **No multiline expressions**: Each action/edge must be on a single line
- **No imports**: Cannot import modules in expressions
- **No file I/O**: Cannot read/write files (by design)
- **No network access**: Cannot make network calls (unless via custom actions)
