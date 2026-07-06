# Flow Documentation

> **📖 Complete Parsing Reference**: For detailed information about the
> `.flowsy` file format, indentation rules, and expression syntax, see
> [FLOW_PARSING.MD](FLOW_PARSING.MD).

## 1. FLOW BASICS

### What is a Flow?

A **Flow** is a directed graph of nodes that defines a workflow.

Think of it as a flowchart where each box is a node, and arrows between boxes
are edges. The flow processes data stored in a shared **context** dictionary.

*Components:*

- **name** & **description**: Flow metadata
- **nodes**: Processing steps (the boxes in your flowchart)
- **context_in**: Required input objects (e.g., `email: Email`)
- **context**: Shared data dictionary that flows through all nodes

### What is a Node?

A **Node** is a single processing step in your flow.

Each node has:

- **name**: Unique identifier (e.g., `classify_email`, `handle_sales`)
- **actions**: List of operations to execute (e.g., classify text, send email,
  load file)
- **edges**: Routing rules that determine which node to execute next

### What is an Action?

An **Action** is a single operation executed within a node.

Actions can:

- Call functions:
  `classify(input_text=email.text, categories=["sales", "support"])`
- Call object methods: `email.reply("Thank you")`
- Load files: `load_files_text("data/document.pdf")`
- Assign results to variables: `category = classify(...)`

### What is an Edge?

An **Edge** is a routing rule that determines the next node to execute.

Format: `condition: target_node`

Examples:

- `confidence < 0.7: manual_review` - If confidence is low, go to manual_review
- `category == "sales": handle_sales` - If category is sales, go to handle_sales
- `True: next_step` - If none of the conditions before apply go to next_step

### Flow Execution

*Input:*

```python
from agy import Flow

# Load flow
flow = Flow.from_flowsy("my_flow.flowsy")

# Execute
context = await flow.run(context_in={"email": email_instance})
```

*Output:*

- Returns the final `context` dictionary containing all variables and results
- Default keys in context: `result`, `success`, `error_msg`, `confidence`

### Flow Lifecycle

1. **Load**: `Flow.from_flowsy()` parses FLOWSY file and creates Flow object
2. **Initialize**: `flow.run(...)` validates `context_in` and registers actions
3. **Execute**: Starts at first node, executes actions, follows edges until
   termination
4. **Return**: Final context dictionary with all results

### Flow Validation

Validate a flow before execution with `Flow.validate()` to catch errors early.
For reusable flows, prefer validating against context classes once, then execute
with concrete instances as often as needed:

```python
result = Flow.validate("my_flow.flowsy", context_in={"email": Email}, action_types=[...])
if not result.is_valid:
    for error in result.errors:
        print(f"Line {error.line_number}: {error.message}")

flow = Flow.from_flowsy("my_flow.flowsy")
for email in emails:
    context = await flow.run(context_in={"email": email}, action_types=[...])
```

Instance-based validation remains supported for backwards compatibility, but
class-based validation is the preferred way to check the flow contract without
creating real accounts, clients or data objects.

*What gets validated:*

- Syntax is correct and all mandatory fields present (name, nodes)
- Flow has nodes (not empty)
- Edge targets exist
- Variables are defined (in context_in or previous actions)
- Functions are registered (contrib or custom action_types)
- Function signatures (required arguments provided)
- Object attributes/methods exist
- File paths exist (instruction_file, load_files_text)
- LLM API keys set (for used provider)

### Flow Structure Example

Here's how a flow is structured - nodes contain actions, nodes are connected by
edges:

```text
Flow: Insurance Claim Processing
├── Context In: claim (InsuranceClaim object)
│
├── Node: classify_claim
│   ├── Actions:
│   │   └── category = classify(
│   │           input_text=claim.description,
│   │           categories=["vehicle", "property"],
│   │           instruction_file="prompts/claim_classify.md"
│   │       )
│   └── Edges:
│       ├── confidence < 0.8 → manual_review
│       ├── category == "vehicle" → handle_vehicle
│       └── category == "property" → handle_property
│
├── Node: handle_vehicle
│   ├── Actions:
│   │   ├── damage_assessment = extract(
│   │   │       input_text=claim.description,
│   │   │       values_to_extract={"damage_type": "str", "estimated_cost": "float"}
│   │   │   )
│   │   ├── claim.assign_to_department("vehicle_claims")
│   │   └── claim.set_status("processing")
│   └── Edges:
│       └── end(success=True, result=damage_assessment)
│
├── Node: handle_property
│   ├── Actions:
│   │   ├── property_info = extract(
│   │   │       input_text=claim.description,
│   │   │       values_to_extract={"property_type": "str", "damage_area": "str"}
│   │   │   )
│   │   ├── claim.assign_to_department("property_claims")
│   │   └── claim.set_status("processing")
│   └── Edges:
│       └── end(success=True, result=property_info)
│
└── Node: manual_review
    ├── Actions:
    │   ├── claim.set_status("needs_review")
    │   └── claim.assign_to_department("manual_review")
    └── Edges:
        └── end(success=False, error_msg="Low confidence classification")
```

---

## 2. FLOW DEFINITION

### FLOWSY Structure

```flowsy
name: string                    # Flow name
description: string             # Flow description
context_in:                     # Required input objects (validated at runtime)
  object_name: TypeName         # e.g., email: Email
context:                        # Optional additional context keys
  key: TypeName                 # e.g., pricing_data: PricingTable

nodes:
  node_name:                    # Unique node identifier (dictionary-style)
    actions:                    # List of action calls
      - action_call_1
      - action_call_2
    edges:                      # Routing conditions
      - condition: target_node
      - True: default_target          # Default edge (condition: True)
```

Stochastic nodes use the same node/edge structure, but delegate one or more
natural-language requests to an agent object from `context_in`. The agent must
expose `run(...)`; `requests:` is the FLOWSY list of instructions passed to that
method. Request entries may also be Python expressions evaluated with the
current flow context; evaluated request expressions must return a string:

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
      - "Create a Markdown table of yesterday's inbound emails."
      - "Add an answered column based on outbound emails."
    output: email_report_md
    message: agent_message
    edges:
      - success == True: send_report
      - end(success=False, error_msg=error_msg)
```

### Context Definition Rules

**context_in** (Required inputs):

- Keys must be provided when calling `flow.run(context_in=...)`
- Values are object instances (e.g., `email`, `document`)
- Validated at runtime: missing or extra keys cause `ValueError`

**context** (Additional keys):

- Optional context keys that are allowed but not required
- Initialized to `None` in the flow
- Can be set by actions during execution

**Default keys** (Always available):

```python
{
    "result": None,
    "success": False,
    "error_msg": "",
    "confidence": None
}
```

*Example:*

```flowsy
context_in:
  email: Email              # Required: must provide email instance
  user: User                # Required: must provide user instance
context:
  pricing_table: PricingTable   # Optional: can be set by actions
  invoice_data: dict            # Optional: can be set by actions
```

### Action Call Format

Actions are function calls with optional variable assignment:

```flowsy
actions:
  # Simple call (result stored in 'result' variable)
  - show("Processing email")

  # With variable assignment
  - category = classify(input_text=email.text, categories=["sales", "support"])

  # Object method call
  - email.reply("Thank you")

  # Nested object access
  - carrier = shipment_data.carrier.name

  # Multiple arguments
  - result = process(email.text, user.id, threshold=0.8)
```

*Syntax Rules:*

- Optional assignment: `variable_name =` (spaces around `=` optional)
- Function name: alphanumeric + underscore
- Arguments: positional and keyword arguments supported
- Strings: use quotes for literal strings
- Context references: unquoted names resolve to context variables
- Object access: use dot notation (e.g., `email.text`, `user.profile.name`)

### Edge Definition Rules

Edges define routing between nodes. Format: `condition: target_node`

```flowsy
edges:
  # Conditional edges
  - confidence < 0.7: low_confidence_handler
  - category == "sales": handle_sales
  - success: next_step

  # Default edge (always matches if previous edges don't)
  - True: fallback_node

  # Termination (special end nodes)
  - not success: end(success=False, error_msg="Failed")
  - end(success=True)
```

As a friendlier shorthand, the final fallback edge may omit `True:`:

```flowsy
edges:
  - confidence < 0.7: low_confidence_handler
  - fallback_node  # Same as True: fallback_node; only valid as the last edge
```

*Edge Evaluation:*

- Edges are evaluated **in order**
- First matching edge is taken
- A conditionless edge is allowed only as the final edge and is treated as
  `True: target`
- If no edge matches: execution raises a `ValueError` (`No edge condition matched ...`)

*No-Edge Behavior:*

- If a node has no `edges` defined, flow execution terminates automatically after
  the node actions.

### Special End Nodes

Two terminal nodes are automatically created when referenced:

**`end()`** - Terminate flow with custom context values

```flowsy
- end(success=True)
- end(success=False, error_msg="Validation failed")
- end(success=True, result=final_answer)
```

The `end()` action:

- Accepts any keyword arguments that update the context
- Returns a dictionary with
  `{"result": None, "context": {...}, "flow_control": "TERMINATE"}`
- ActionExecutor recognizes the `flow_control` flag and terminates the flow
- Can be called directly in actions or referenced in edges

**Legacy nodes** (deprecated, use `end()` instead):

- `terminate_success`: Equivalent to `end(success=True)`
- `terminate_error`: Equivalent to `end(success=False)`

### Node Definition Examples

*Minimal node:*

```flowsy
process_email:
  actions:
    - show("Processing")
```

*Node with classification:*

```flowsy
classify_email:
  actions:
    - category = classify(
        input_text=email.text,
        categories=["sales", "support", "billing"],
        instruction_file="prompts/email_classify.md"
      )
  edges:
    - confidence < 0.8: manual_review
    - category == "sales": handle_sales
    - category == "support": handle_support
    - handle_billing
```

*Node with explicit termination:*

```flowsy
validation:
  actions:
    - is_valid = validate(email.text)
  edges:
    - not is_valid: end(success=False, error_msg="Invalid input")
    - continue_processing
```

---

## 3. FLOW VERIFICATION

Current verification includes:

- Structural checks (flow has nodes, edge targets exist)
- Variable checks (undefined variables in expressions)
- Callable checks (registered functions and object methods/attributes)
- Function signature checks (required arguments)
- File checks for file-based actions/instructions
- Environment warnings for configured LLM providers

---

## 4. FLOW EXECUTION

### Execution Flow

1. **Validation**: Validate `context_in` keys match flow definition
2. **Registration**: Register contrib actions + custom actions
3. **Context Initialization**: Copy flow.context + merge context_in objects
4. **Node Execution Loop**:
   - Execute all actions in current node sequentially
   - Evaluate edges in order
   - Select first matching edge
   - Move to target node or terminate
5. **Termination**: Return final context

You can optionally start at a specific node:

```python
context = await flow.run(context_in={"email": email_instance}, node="manual_review")
```

### Execution Rules

*Node Execution:*

- Actions execute **sequentially** in definition order
- Each action can modify the context
- Errors in actions propagate up (flow terminates with exception)
- Stochastic nodes execute their `requests` sequentially against the configured
  agent and then use the same edge evaluation rules.

*Edge Evaluation:*

```python
# Edges are Python expressions - variables are directly accessible
# Example edge: "confidence < 0.7: low_confidence"
if confidence < 0.7:  # Direct variable access, not context["confidence"]
    next_node = "low_confidence"
```

*Evaluation order:*

1. Edges are evaluated **top to bottom**
2. First edge with `True` condition is selected
3. If no edge matches: flow terminates
4. Special handling for `end()`: terminates immediately

*Example:*

```flowsy
edges:
  - confidence < 0.5: very_low      # Checked first
  - confidence < 0.8: medium_low    # Checked second
  - category == "sales": handle_sales
  - default_handler                 # Final fallback, same as True: default_handler
```

### Context Flow

Context is a shared dictionary that flows through the entire execution. **In
FLOWSY, you access variables directly by name** (not via `context["..."]`):

```flowsy
# In FLOWSY: direct variable access
edges:
  - confidence < 0.8: manual_review   # ✓ Direct access
  - category == "sales": handle_sales  # ✓ Direct access
```

**Internally**, the executor manages context like this (for understanding only):

```python
# Internal representation (you don't write this)
context = {
    "result": None,
    "success": False,
    "error_msg": "",
    "confidence": None,
    "email": email_instance,  # from context_in
}
# After: category = classify(...) → context["category"] = "sales"
```

*Variable Access Rules:*

- Variables from `context_in` are directly accessible (e.g., `email.text`)
- Variables assigned in actions are accessible in later actions/edges
- Default variables: `result`, `success`, `error_msg`, `confidence`

### Action Execution Details

*Types of actions:*

1. **Contrib actions** (auto-loaded):

```yaml
- category = classify(input_text=email.text, categories=["a", "b"])
- data = load_files_text("data/file.pdf")
```

1. **Object methods** (from context_in):

```yaml
- email.reply("Thank you")
- email.move("processed")
```

1. **User defined functions** (ActionTypes registered by users):

```yaml
- result = my_function(arg1, arg2)
```

*Action execution steps:*

1. Parse action string using AST → `ActionCall` object with `__eval__` method
2. Evaluate Python expression with context (variables, functions, etc.)
3. Execute function/method or evaluate expression result
4. Write result to context (variable name or `"result"`)

*Variable Resolution:*

```yaml
# Unquoted → variable lookup
- result = process(email.text) # 'email' from context_in, access .text attribute

# Quoted → literal string
- result = process("hello") # Uses string "hello"

# Numbers → literal
- result = calculate(42, 3.14) # Uses numbers directly
```

### Flow Termination

*Normal termination:*

- Reach a node with no matching edges
- Execute `end()` action
- Reference `end()` in an edge

*Termination with `end()`:*

```flowsy
# In actions:
- end(success=True, result=answer)
```

*In edges:*

```flowsy
- not success: end(success=False, error_msg="Failed")
```

*Error termination:*

- Exception in action execution
- Context validation failure
- `FlowTerminationError` raised by ActionExecutor when
  `flow_control == "TERMINATE"`

The `end()` action returns a dictionary with `flow_control: "TERMINATE"`, which
is recognized by `ActionExecutor` to gracefully terminate the flow.

---

## 5. FLOW VARIABLES

### Variable Declaration

Variables are **implicitly declared** by assignment in actions:

```flowsy
actions:
  # Assigns result to 'category' variable
  - category = classify(input_text=email.text, categories=["sales", "support"])

  # Assigns result to 'response' variable
  - response = respond(input_text=email.text, instruction="Be helpful")

  # Assigns result to 'data' variable
  - data = load_files_text("data/prices.xlsx")
```

### Variable Scope

Variables are **globally scoped** within the flow:

- Once assigned, available in all subsequent nodes
- No local scope: all variables are in the shared `context` dictionary
- Variables persist across node boundaries

*Example:*

```flowsy
nodes:
  node_1:
    actions:
      - category = classify(...)  # Declares "category"

  node_2:
    actions:
      - show(category)  # Uses "category" from node_1
    edges:
      - category == "sales": handle_sales  # References "category"
```

### Variable Naming Rules

*Allowed in context:*

- Keys defined in `context_in`
- Keys defined in `context`
- Default keys: `result`, `success`, `error_msg`, `confidence`
- Variables assigned in actions

*Naming conventions:*

- Use snake_case: `email_category`, `user_input`
- Alphanumeric + underscore only
- Cannot start with a number

### Variable Types

Variables are **dynamically typed** (Python):

```flowsy
actions:
  # String
  - category = classify(...)           # Returns string

  # Dictionary
  - data = extract(...)                # Returns dict

  # Object
  - email                              # From context_in

  # Boolean
  - is_valid = validate(...)           # Returns bool

  # Number
  - score = calculate(...)             # Returns int/float
```

### Reading Variables

*In actions:*

```flowsy
# Direct reference (unquoted)
- process(category)
- email.reply(response)

# Object attribute access
- carrier = shipment_data.carrier.name
- show(user.profile.email)

# Complex expressions (now supported with AST parsing)
- result = count + 1
- total = price * quantity
- message = f"Status: {status}, Count: {count}"
- missing_str = ", ".join(missing_list)
- sorted_data = sorted(data, key=lambda x: x["value"])
- is_valid = len(data) > 0 and data[0] == "value"
```

*In edges:*

```flowsy
edges:
  # Comparisons
  - confidence < 0.8: low_confidence
  - category == "sales": handle_sales

  # Boolean
  - success: next_step
  - not is_valid: error_handler

  # Combined conditions
  - confidence > 0.9 and category == "sales": priority_sales
```

### Writing Variables

*Explicit assignment:*

```flowsy
# LLM actions automatically write to assigned variable
- category = classify(...)
# Writes: context["category"] = "sales"
#         context["confidence"] = 0.95

- data = extract(...)
# Writes: context["data"] = {...}
#         context["confidence"] = 0.88

- answer = respond(...)
# Writes: context["answer"] = "The answer is..."
#         context["confidence"] = 0.92
```

*Implicit assignment (no variable name):*

```flowsy
# Result goes to context["result"]
- classify(...)
# Writes: context["result"] = "sales"
#         context["confidence"] = 0.95
```

**Special behavior of LLM actions:** All high-level LLM actions (`classify`,
`respond`, `extract`) write two values:

1. **Main result** → assigned variable (or `"result"` if no assignment)
2. **`confidence`** → always written to `context["confidence"]`

### Variable Lifecycle

1. **Initialization**: Context keys defined in flow are set to `None`
2. **Assignment**: First write creates/updates the variable
3. **Usage**: Read by subsequent actions and edge conditions
4. **Persistence**: Survives across all nodes until flow terminates
5. **Return**: Final context contains all variables

*Example:*

```flowsy
name: Email Processing
context_in:
  email: Email

nodes:
  classify_email:
    actions:
      - category = classify(input_text=email.text, categories=["sales", "support"])
      # context["category"] = "sales"
      # context["confidence"] = 0.95
    edges:
      - category == "sales": handle_sales

  handle_sales:
    actions:
      - show(category)  # Uses "category" from previous node
      - response = respond(input_text=email.text, instruction="Sales response")
      # context["response"] = "Thank you for your interest..."
      # context["confidence"] = 0.88 (overwrites previous confidence)
    edges:
      - end(success=True, result=response)
```

*Final context:*

```python
{
    "email": <Email object>,
    "category": "sales",
    "confidence": 0.88,
    "response": "Thank you for your interest...",
    "result": "Thank you for your interest...",
    "success": True,
    "error_msg": ""
}
```

### Sub-Flow Calls

Use `run_flow()` to call another flow from within a running flow and get its
result back. The sub-flow runs with its own isolated context.

```flowsy
nodes:
  dispatch:
    actions:
      - sub = run_flow(flow="detail_check.flowsy", ticket=ticket, jira=jira)
    edges:
      - sub["success"]: finalize
      - True: escalate
```

To re-enter the current flow at a different node:

```flowsy
    actions:
      - sub = run_flow(node="validate", invoice=invoice)
```

Parameters:

- `flow` (str | None): path to a `.flowsy` file, or `None` to use the current flow
- `node` (str | None): optional start node in the target flow
- `**context_in`: all key-value pairs passed as `context_in` to the sub-flow

At least one of `flow` or `node` must be provided.

### Batch Processing

Use `run_flow_batch()` to run a sub-flow once per element in a list:

```flowsy
nodes:
  process_all:
    actions:
      - results = run_flow_batch(emails, element="email", flow="process.flowsy", jira=jira)
      - failed = [r for r in results if not r.get("success")]
    edges:
      - len(failed) == 0: end(success=True, result=results)
      - True: end(success=False, error_msg="Some items failed", result=results)
```

Parameters:

- `items` (list): the list to iterate over
- `element` (str): context key name for the current item (default: `"item"`)
- `flow` (str | None): path to `.flowsy`, or `None` for current flow
- `node` (str | None): optional start node
- `mode` (str): `"sequential"` (default) or `"parallel"`
- `on_error` (str): `"continue"` (default) or `"fail_fast"`
- `**context_in`: additional key-value pairs passed to every sub-flow

Each iteration gets its own fresh context — no bleed between iterations and no
writes back to the parent context. Results are returned as a list of context
dicts.

### Searchable RecordSets

Use `search_emails()` when the flow should first screen a larger set of emails
and only load candidates for deeper review. It returns a `RecordSet`: a
search result with a deterministic cursor and readable methods like
`get_next_batch()`, `has_next_batch()` and `load_full(...)`.

Existing single-item flows stay unchanged. A flow that receives `email: Email`
still works with the regular `Email` object and can call methods such as
`email.reply(...)` or `email.move(...)`.

```flowsy
context_in:
  account: EmailAccount
  consc: Consciousness

nodes:
  retrieve_emails:
    actions:
      - retrieved_emails = search_emails(account, query="customs transfer", folders=["inbox"], batch_size=10)
      - current_email_batch = retrieved_emails.get_next_batch()
    edges:
      - screen_batch

  screen_batch:
    type: stochastic
    agent: consc
    requests:
      - "Review the current email batch and return the ids of emails that mention customs transfers."
    output: candidate_email_ids
    message: screening_message
    edges:
      - len(candidate_email_ids) > 0: load_candidate_emails
      - retrieved_emails.has_next_batch(): next_email_batch
      - finalize_not_found

  next_email_batch:
    actions:
      - current_email_batch = retrieved_emails.get_next_batch()
    edges:
      - screen_batch

  load_candidate_emails:
    actions:
      - candidate_emails = retrieved_emails.load_full(candidate_email_ids)
    edges:
      - deep_review
```

Prefer domain-specific variable names in FLOWSY:
`retrieved_emails`, `current_email_batch`, `candidate_email_ids` and
`candidate_emails`. The internal model name `RecordSet` is useful in Python,
but flow examples should read like business logic.

Use `search_files()` the same way for local file screening. The first search
returns metadata records; `load_full(ids)` loads full text only for selected
candidates.

```flowsy
context_in:
  root_path: str
  consc: Consciousness

nodes:
  retrieve_files:
    actions:
      - retrieved_files = search_files(root_path=root_path, query="customs", file_extensions=["pdf", "docx", "md"], batch_size=10)
      - current_file_batch = retrieved_files.get_next_batch()
    edges:
      - screen_file_batch

  screen_file_batch:
    type: stochastic
    agent: consc
    requests:
      - "Review the current file batch and return the ids of files that mention customs transfers."
    output: candidate_file_ids
    message: file_screening_message
    edges:
      - len(candidate_file_ids) > 0: load_candidate_files
      - retrieved_files.has_next_batch(): next_file_batch
      - finalize_not_found

  load_candidate_files:
    actions:
      - candidate_files = retrieved_files.load_full(candidate_file_ids)
    edges:
      - deep_review
```

### Best Practices

1. **Explicit assignment**: Always assign to named variables for clarity

   ```flowsy
   # Good
   - category = classify(...)

   # Less clear
   - classify(...)  # Goes to context["result"]
   ```

2. **Descriptive names**: Use meaningful variable names

   ```flowsy
   # Good
   - email_category = classify(...)
   - user_response = respond(...)

   # Less clear
   - cat = classify(...)
   - resp = respond(...)
   ```

3. **Check confidence**: Use confidence for routing

   ```flowsy
   edges:
     - confidence < 0.7: manual_review
     - category == "sales": handle_sales
   ```

4. **Declare context keys**: Pre-declare optional keys in flow `context`

   ```flowsy
   context:
     invoice_data: dict
     pricing_info: PricingTable
   ```
