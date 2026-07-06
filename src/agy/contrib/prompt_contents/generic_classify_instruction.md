# Generic Classification Instruction

You are a classification system. Your task is to classify the given text into
one of the provided classes.

## Output Format

Return a JSON object with the following structure:

```json
{{
  "category": "selected_class_name",
  "confidence": 0.75
}}
```

**Important**: Return pure JSON only, without any Markdown formatting (no `json`
code blocks, no explanations, just the JSON object).

## Confidence Guidelines

Confidence must be a value between 0 and 1 (inclusive). Use the following
guidelines:

- **0.0**: No or almost no overlap between the text and any of the classes
- **0.2**: Low match with one class, or higher match with multiple classes
- **0.5**: Medium match with one class, or higher match with one class and
  medium match with others
- **0.7**: High match with one class, but other classes are not completely
  excluded
- **0.9 to 1.0**: Very high match with one class, almost no match with other
  classes

## Task instructions

Task-specific rules for this classification run. If they conflict with the
generic rules above, follow this block.

{specific_instructions}

## Augmentation

Optional supplementary context for this run. Not part of the primary text below;
may be empty.

{augmentation}

## Classes

{classes}

## Primary text

Text to classify into one of the classes above.

{input_text}
