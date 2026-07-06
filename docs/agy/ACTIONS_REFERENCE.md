# AGY Actions Reference

Complete reference for all built-in and custom actions in AGY flows.

## Action Execution Flow

1. **Sequential Execution**: Actions in a node are executed **one by one** in
   the order they appear
2. **Context Updates**: Each action can read from and write to the shared
   context dictionary
3. **Error Handling**: If an action fails (`success=False` in context):
   - Remaining actions in the node are **skipped**
   - Execution **jumps to edge evaluation**
   - Edges can route to error handling nodes
4. **Termination**: The `end()` action immediately terminates the flow with
   custom context values

*Example:*

```flowsy
nodes:
  example_node:
    actions:
      - result1 = action1()  # Executes first
      - result2 = action2()  # Executes only if action1 succeeded
      - action3()            # Executes only if action1 & action2 succeeded
```

## Action Types

*Two types of actions:*

1. **Global Functions** (`global_function` actions)
   - Registered in `ActionRegistry`
   - Called by name: `classify()`, `respond()`, `show()`
   - Built-in contrib actions are auto-loaded
   - Custom actions passed via `flow.run(action_types=[...])`

2. **Object Methods**
   - Called on objects from `context_in`
   - Syntax: `object_name.method_name(args)`
   - Example: `email.reply("Thanks")`, `document.save()`

Stochastic nodes are intentionally **not** modeled as actions. They are a node
control type (`type: stochastic`) that delegates natural-language `requests` to
an agent object from `context_in`, normalizes the result, and then uses the same
edge routing semantics as deterministic nodes. See `docs/agy/FLOW.md` for the
node-level syntax.

## Built-in Actions (Global Functions)

### Simple LLM Actions

All LLM actions (`classify`, `respond`, `extract`) share common behavior:

*Return Structure:*

- Main result is assigned to the output variable (or `context["result"]` if no
  assignment)
- `confidence` (0.0-1.0) is always written to `context["confidence"]`
- This allows direct access to confidence in edges:
  `- confidence < 0.7: manual_review`

*Two-Layer Prompt System:*

1. **Generic Base Prompt**: Built-in template (`generic_xxx_instruction.md`)
   with:
   - Task description and output format (JSON)
   - Confidence guidelines (0.0 to 1.0 scale)
   - Structured placeholders for specific instructions and augmentation

2. **Specific Instructions**: Your custom guidance via:
   - `instruction` parameter: Inline text
   - `instruction_file` parameter: External file (e.g.,
     `"prompts/my_instruction.md"`)

The generic prompt ensures consistent JSON output and confidence scoring, while
your specific instructions customize the LLM's behavior for your use case.

#### `classify()`

**Purpose**: Categorize text into predefined categories

*Parameters:*

- `input_text` (str): Text to classify
- `categories` (list): List of category strings
- `instruction` (str, optional): Classification guidance
- `instruction_file` (str, optional): Path to instruction file
- `augmentation` (str, optional): Additional context

*Returns:*

- Assigned variable (or `result`) = category string (e.g., `"urgent"`)
- `context["confidence"]` = float 0-1

**Confidence** (0.0 to 1.0):

- `0.0-0.2`: No or low match, or ambiguous between multiple classes
- `0.5`: Medium match with one class
- `0.7`: High match but other classes not excluded
- `0.9-1.0`: Very high match, minimal ambiguity

*Examples:*

```flowsy
# Simple classification (with assignment for clarity)
- priority = classify(input_text=document.text, categories=["urgent", "normal", "low"])
  edges:
    - confidence < 0.6: manual_review
    - priority == "urgent": escalate

# With instruction file
- sentiment = classify(input_text=feedback, categories=["positive", "negative", "neutral"], instruction_file="prompts/sentiment_instruction.md")

# With augmentation
- doc_type = classify(input_text=document.text, categories=["legal", "business", "financial"], instruction_file="prompts/classification_guidelines_acme.md", augmentation=company_context)
```

#### `respond()`

**Purpose**: Generate text based on input

*Parameters:*

- `input_text` (str): Input text to process
- `instruction` (str, optional): Generation instructions
- `instruction_file` (str, optional): Path to instruction file
- `augmentation` (str, optional): Additional context/data

*Returns:*

- Assigned variable (or `result`) = generated text string
- `context["confidence"]` = float 0-1

**Confidence** (0.0 to 1.0):

- `0.0-0.2`: No or low relevant information available
- `0.5`: Partial confidence, ambiguous interpretation
- `0.7`: Strong confidence, minor uncertainty
- `0.9-1.0`: Very strong confidence, minimal ambiguity

*Examples:*

```flowsy
# Simple generation
- answer = respond(input_text=question, instruction="Provide a helpful answer")

# With augmentation (e.g., search results)
- response = respond(input_text=user_query, instruction_file="prompts/search_response.md", augmentation=web_search_results)
```

#### `extract()`

**Purpose**: Extract structured data from text

*Parameters:*

- `input_text` (str): Text to extract from
- `values_to_extract` (dict): Schema of values to extract (e.g.,
  `{"name": "str", "age": "int"}`)
- `instruction` (str, optional): Extraction guidance
- `instruction_file` (str, optional): Path to instruction file
- `augmentation` (str, optional): Additional context

*Returns:*

- Assigned variable (or `result`) = dictionary with extracted values (e.g.,
  `{"name": "John", "age": 30}`). Missing keys and JSON `null` for schema fields
  are coerced to type sentinels (`""`, `0.0`, `0`, `[]`, `{}`) before return.
- `context["confidence"]` = float 0-1

**Confidence** (0.0 to 1.0):

- `0.0-0.2`: No or low evidence for extracted values
- `0.5`: Partial evidence or ambiguous interpretation
- `0.7`: Strong evidence but not conclusive
- `0.9-1.0`: Very strong evidence, minimal ambiguity

*Examples:*

```flowsy
# Extract contact info (with assignment)
- contact = extract(input_text=document.text, values_to_extract={"name": "str", "company": "str", "phone": "str"})
  # Access: contact.name, contact["company"], etc.

# Extract invoice data
- invoice = extract(input_text=pdf_text, values_to_extract={"invoice_number": "str", "total": "float", "date": "str"}, instruction_file="prompts/invoice_extraction.md")
  edges:
    - confidence < 0.8: manual_verification
    - invoice.total > 10000: approval_required
```

### I/O Actions

#### `load_files_text()`

**Purpose**: Load and parse files

*Parameters:*

- `*file_paths` (str): One or more file paths to load

**Supported formats:** `.txt`, `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.html`

**Returns:** Concatenated text content (str)

*Examples:*

```flowsy
# Load single file
- docs = load_files_text("data/manual.pdf")

# Load multiple files
- faqs = load_files_text("data/faq1.pdf", "data/faq2.pdf", "data/faq3.pdf")
```

#### `show()`

**Purpose**: Print debug information

*Parameters:*

- `*args`: Values to print

**Returns:** None (prints to stdout and INFO log)

*Examples:*

```flowsy
# Simple print
- show("Processing started")

# Print variables
- show("Category:", category, "Confidence:", confidence)
```

### Flow Control Actions

#### `end()`

**Purpose**: Explicitly terminate flow with custom context values

*Parameters:*

- `**kwargs`: Any key-value pairs to write to context before termination

**Returns:** Dictionary with
`{"result": None, "context": {...}, "flow_control": "TERMINATE"}`

*Behavior:*

- Returns a dictionary that signals flow termination to the `ActionExecutor`
- The `ActionExecutor` recognizes the `flow_control: "TERMINATE"` flag and
  terminates the flow
- All keyword arguments are written to the flow context before termination

*Examples:*

```flowsy
# Terminate with error
- end(success=False, error_msg="Validation failed")

# Terminate with custom data
- end(success=True, final_result=answer, processed_count=10)
```

### Sub-Flow and Batch Actions

#### `run_flow()`

**Purpose**: Call another flow (or re-enter the current flow at a specific node)
and return its final context.

*Parameters:*

- `flow` (str | None): Path to a `.flowsy` file, or `None` to use the current
  flow
- `node` (str | None): Optional start node in the target flow
- `**context_in`: Key-value pairs passed as `context_in` to the sub-flow

At least one of `flow` or `node` must be provided.

**Returns:** The sub-flow's final context dictionary.

*Examples:*

```flowsy
# Call external sub-flow
- sub = run_flow(flow="detail_check.flowsy", ticket=ticket, jira=jira)

# Re-enter current flow at a specific node
- sub = run_flow(node="validate", invoice=invoice)
```

#### `run_flow_batch()`

**Purpose**: Run a sub-flow once per element in a list, collecting all results.

*Parameters:*

- `items` (list): The list to iterate over
- `element` (str): Context key name for the current item (default: `"item"`)
- `flow` (str | None): Path to `.flowsy`, or `None` for current flow
- `node` (str | None): Optional start node
- `mode` (str): `"sequential"` (default) or `"parallel"`
- `on_error` (str): `"continue"` (default) or `"fail_fast"`
- `**context_in`: Additional key-value pairs passed to every sub-flow

**Returns:** List of context dictionaries, one per iteration.

*Examples:*

```flowsy
# Sequential batch
- results = run_flow_batch(emails, element="email", flow="process.flowsy")

# Parallel batch with extra context
- results = run_flow_batch(tickets, element="ticket", node="classify", mode="parallel", jira=jira)

# Stop on first failure
- results = run_flow_batch(items, element="item", flow="validate.flowsy", on_error="fail_fast")
```

### Advanced LLM Actions

#### `set_model_call()`

**Purpose**: Configure the LLM provider/model/parameters for all subsequent LLM
actions

*Parameters:*

- `provider` (str, optional): Provider name (`"openai"`, `"openai_azure"`,
  `"gemini"`, `"anthropic"`, `"fake"`)
- `model` (str, optional): Model name (uses config default if not provided)
- `callable` (callable, optional): Custom callable function (overrides provider)
- `**kwargs`: Model parameters (e.g., `temperature=0.7`, `max_tokens=1000`,
  `top_p=0.9`)

**Returns:** `{"success": True}`

*Behavior:*

- Sets the `model_call` for **all following LLM actions** in the flow
  (`classify`, `respond`, `extract`, `model_call`)
- Applies from the point it's called until the end of the flow (or until another
  `set_model_call` is called)
- If not called, uses defaults from `pyproject.toml` `[tool.agy.llm]` or falls
  back to OpenAI `gpt-5-mini`

*Examples:*

```flowsy
# Set provider and model at flow start
- set_model_call(provider="anthropic", model="claude-3-opus-20240229", temperature=0.3)
- category = classify(input_text=email.text, categories=["sales", "support"])
  # ↑ Uses Anthropic Claude

# Switch to different provider mid-flow with parameters
- set_model_call(provider="gemini", model="gemini-pro", temperature=0.7, max_tokens=2000)
- response = respond(input_text=query)
  # ↑ Uses Google Gemini

# Use fake provider for testing
- set_model_call(provider="fake")
- result = model_call(prompt="test")
  # ↑ Returns prompt as-is (for testing)
```

**Config Defaults** (`pyproject.toml`):

```toml
[tool.agy.llm]
default_provider = "openai"
default_model = "gpt-5-mini"
default_params = {}  # Optional: {"temperature": 0.7, "max_tokens": 1000}

[providers.openai]
api_key_env = "OPENAI_API_KEY"

[providers.openai_azure]
api_key_env = "AZURE_OPENAI_API_KEY"
endpoint_env = "AZURE_OPENAI_ENDPOINT"

[providers.gemini]
api_key_env = "GEMINI_API_KEY"

[providers.anthropic]
api_key_env = "ANTHROPIC_API_KEY"
```

#### `model_call()`

**Purpose**: Direct LLM call with full prompt control

*Parameters:*

- `prompt` (str): The prompt to send
- `output` (str): `"str"` (default) returns raw response, `"json"` parses as
  JSON
- `**kwargs`: Additional parameters (e.g., `temperature=0.7`, `max_tokens=1000`)

*Returns:*

- `str` if `output="str"` (default)
- `dict` or `list` if `output="json"` (parsed JSON)

*Behavior:*

- Uses the currently configured `model_call` (set via `set_model_call()` or from
  config defaults)
- Additional `**kwargs` are merged with provider/model parameters
- With `output="json"`: Automatically strips markdown code blocks
  (` ```json ... ``` `) before parsing

*Examples:*

```flowsy
# Simple direct call (uses default from config)
- result = model_call(prompt="Analyze this data and return key insights")

# With JSON output parsing
- data = model_call(prompt="Return analysis as JSON: {name, score}", output="json")
  # ↑ Returns parsed dict, e.g., {"name": "Test", "score": 85}

# With additional parameters
- analysis = model_call(prompt="...", temperature=0.7, max_tokens=2000)

# After setting provider
- set_model_call(provider="anthropic", model="claude-haiku-4-5-20251001")
- response = model_call(prompt="Explain quantum computing")
  # ↑ Uses Anthropic with the configured model
```

#### `get_prompt_from_str()`

**Purpose**: Format template string with variables

*Parameters:*

- `template` (str): Template with `{placeholders}`
- `**kwargs`: Values to fill placeholders

**Returns:** Formatted string

*Example:*

```flowsy
- prompt = get_prompt_from_str(
    template="Analyze {data_type} for {customer_name}",
    data_type="sales report",
    customer_name="ACME Corp"
  )
```

#### `get_prompt_from_file()`

**Purpose**: Load and format template file with variables

*Parameters:*

- `file_path` (str): Path to template file
- `**kwargs`: Values to fill placeholders

**Returns:** Formatted string

*Example:*

```flowsy
- prompt = get_prompt_from_file(
    file_path="prompts/analysis_prompt.md",
    input_fields=input_fields,
    output_fields=output_fields,
    few_shots=few_shots,
    current_record_input=data_from_report
  )
```

#### Combining Prompt Templates with Model Calls

For advanced use cases, combine `get_prompt_from_file` with `model_call` for
full control:

**Template file** (`prompts/analysis_prompt.md`):

```markdown
# Analysis Task

## Input Fields

{input_fields}

## Output Fields

{output_fields}

## Examples

{few_shots}

## Current Record

{current_record_input}

Return a JSON object with the extracted output fields.
```

*Flow YAML:*

```flowsy
nodes:
  - analyze_data:
      actions:
        - prompt = get_prompt_from_file(file_path="prompts/analysis_prompt.md", input_fields=input_fields, output_fields=output_fields, few_shots=few_shots, current_record_input=data_from_report)
        - extracted_dict = model_call(prompt=prompt)
```

This pattern allows:

- ✅ Reusable prompt templates
- ✅ Dynamic variable injection
- ✅ Full prompt control
- ✅ Custom output formats (JSON, text, etc.)

## Custom Actions

Define custom actions using `ActionType`:

```python
from agy import ActionType, Flow

def calculate_score(value: int, multiplier: int = 2) -> int:
    """Custom scoring function"""
    return value * multiplier

# Create ActionType
score_action = ActionType(
    object_name="global_function",
    method_name="calculate_score",
    kwargs={"value": int, "multiplier": int},
    callable=calculate_score,
    description="Calculate a score"
)

# Execute with custom actions
flow = Flow.from_flowsy("my_flow.flowsy")
context = await flow.run(action_types=[score_action], context_in={})
```

Use in YAML:

```flowsy
actions:
  - score = calculate_score(value=points, multiplier=3)
```

### Using a Custom Model Call Provider

Register your custom provider in code, then use it via `set_model_call()`:

```python
from agy.contrib.llm_call import LLMCall

# Define custom provider callable
def mistral_llm_call(prompt: str, model: str = "mistral-large-latest", **params) -> str:
    """Custom LLM call using Mistral AI API."""
    import os
    from mistralai import Mistral

    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise ValueError("Missing MISTRAL_API_KEY environment variable")

    client = Mistral(api_key=api_key)
    response = client.chat.complete(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=params.get("max_tokens", 1024),
        temperature=params.get("temperature", 0.7),
    )
    return response.choices[0].message.content

# Register provider
llm = LLMCall()
llm.register_provider("mistral", mistral_llm_call)

# Now use in flow YAML:
# - set_model_call(provider="mistral", model="mistral-large-latest")
```

**Note**: The `model_call` ActionType is automatically used by LLM functions
(`classify`, `respond`, `extract`). When you use `set_model_call()`, your custom
implementation is used automatically.

*Contrib ActionTypes Auto-Loading Order:*

1. Contrib ActionTypes (from `agy.contrib.action_types`) are loaded first
2. Your custom ActionTypes (passed to `flow.run(...)`) are loaded second and can
   override contrib types

This means you can override any contrib ActionType by providing your own with
the same `method_name`.

## Action Resolution & Context Access

Actions are evaluated as **Python expressions** using AST-based parsing. This
allows full Python expression support, including arithmetic, string formatting,
method calls, and complex data access.

*Supported Expression Types:*

- **Literals**: Strings in quotes, numbers, booleans → `"hello"`, `42`, `True`
- **Variables**: Simple names → `email`, `result`, `data`
- **Attributes**: Dot notation → `email.text`, `user.name`
- **Dict/list access**: Bracket notation → `data["key"]`, `items[0]`
- **Complex paths**: Combined access → `email.attachments[0].filename`
- **Arithmetic**: Binary operations → `count + 1`, `total * 1.1`,
  `len(data) > 0`
- **String formatting**: F-strings → `f"Status: {status}"`, `f"Count: {count}"`
- **Method calls**: On literals and variables → `", ".join(missing_list)`,
  `"text".upper()`

*Examples:*

```flowsy
actions:
  # Literal strings
  - show("Starting process")

  # Context variable
  - show(document_text)

  # Attribute access
  - show(request.url, request.method)

  # Dict/list access
  - status = response_data["status"]
  - first_result = search_results[0]

  # Arithmetic expressions (now supported with AST parsing)
  - count = count + 1
  - total = price * quantity
  - is_valid = len(data) > 0

  # String formatting (now supported with AST parsing)
  - message = f"Status: {status}, Count: {count}"
  - summary = f"Processed {len(items)} items"

  # Method calls on literals and variables (now supported with AST parsing)
  - missing_str = ", ".join(missing_list)
  - upper_text = "hello".upper()
  - sorted_data = sorted(data, key=lambda x: x["value"])
```
