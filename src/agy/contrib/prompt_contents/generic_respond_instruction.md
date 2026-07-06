# Generic Generator Instruction

You are an assistant tasked with generating an appropriate response based on the
provided information.

## Output Format

Return a JSON object with the following structure:

```json
{{
  "result": "response text",
  "confidence": 0.75
}}
```

The `result` field must contain your generated response as a string.
`confidence` must be between 0 and 1.

## Confidence Guidelines

- **0.0**: No or almost no relevant information available
- **0.2**: Low confidence, conflicting signals
- **0.5**: Partial confidence, ambiguous interpretation
- **0.7**: Strong confidence, minor uncertainty remains
- **0.9 to 1.0**: Very strong confidence, minimal ambiguity

## Task instructions

Task-specific rules for this response. If they conflict with the generic rules
above, follow this block.

{specific_instructions}

## Augmentation

Optional supplementary context for this run. Not part of the primary text below;
may be empty.

{augmentation}

## Primary text

Text the generated response should address.

{input_text}
