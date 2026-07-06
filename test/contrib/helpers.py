"""Shared helpers for contrib/integration tests."""

from __future__ import annotations


def fake_llm_call(prompt: str, model: str = "gpt-5-mini") -> str:
    """Fake LLM call that returns the prompt."""
    return prompt


def fake_llm_call_classifier(prompt: str, model: str = "gpt-5-mini") -> str:
    """Fake LLM call that returns a valid classify-like JSON payload."""
    if "## Classes" in prompt:
        classes_section = prompt.split("## Classes", maxsplit=1)[1]
        if "## Text to classify" in classes_section:
            classes_section = classes_section.split("## Text to classify", maxsplit=1)[
                0
            ]
        for line in classes_section.splitlines():
            if line.strip().startswith("- "):
                class_name = line.strip()[2:].strip()
                if class_name and not class_name.startswith("*"):
                    return f'{{"category": "{class_name}", "confidence": 0.95}}'
    return '{"category": "unknown", "confidence": 0.5}'


def issue_dict(
    key: str = "PROJ-1",
    summary: str = "Test summary",
    status: str = "Open",
) -> dict:
    """Build issue as dict (atlassian get_issue / atlassian-python-api response shape)."""
    return {
        "key": key,
        "fields": {
            "summary": summary,
            "status": {"name": status},
            "issuetype": {"name": "Task"},
            "assignee": {"displayName": "Alice"},
            "reporter": {"displayName": "bob"},
            "description": "",
        },
    }
