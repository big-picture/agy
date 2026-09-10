"""HTML and plain-text Graph sending through the public email API."""

from unittest.mock import MagicMock

import pytest

from agy.integrations.email import Attachment, Email, EmailBodyType, GraphEmailAccount

HTML_BODY = '<p>Footer <a href="https://example.com">Website</a></p>'


@pytest.fixture
def graph(monkeypatch):
    account = GraphEmailAccount(api=MagicMock(), user_email="agv@example.com")
    account.api.get_folder_id_by_name.return_value = "draft-folder"
    monkeypatch.setattr(account, "_should_draft_only", lambda flag: flag)
    validator = MagicMock()
    validator.validate_forward.return_value = (True, "")
    monkeypatch.setattr(
        "agy.integrations.email.email_safety.get_validator", lambda _: validator
    )
    post = MagicMock()
    post.return_value.status_code = 202
    post.return_value.json.return_value = {"id": "draft-id"}
    monkeypatch.setattr("agy.integrations.email.graph_account.requests.post", post)
    return account, post, validator


@pytest.mark.parametrize("draft", [False, True])
@pytest.mark.parametrize(
    "body_type", [EmailBodyType.HTML, EmailBodyType.TEXT, "html", "HTML", "text", ""]
)
def test_body_format_and_message_metadata(graph, draft, body_type):
    account, post, validator = graph
    body = '<p>A & B</p>\n<a href="mailto:export@example.com">Export</a>' + HTML_BODY
    email = Email.create(
        to="one@example.com,two@example.com",
        subject="Reminder",
        text=body,
        body_type=body_type,
        cc="copy@example.com",
        account=account,
    )
    email.attachments = [
        Attachment(filename="proof.txt", content=b"proof", content_type="text/plain")
    ]
    if draft:
        post.return_value.status_code = 201
        account.create_draft(email, "Review")
        payload = post.call_args.kwargs["json"]
        assert email.message_id == "draft-id"
        account.api.get_folder_id_by_name.assert_called_once_with(
            folder_name="Review", mailbox_type="personal", mailbox_upn="agv@example.com"
        )
    else:
        assert email.send() is email
        payload = post.call_args.kwargs["json"]["message"]
        validator.validate_forward.assert_called_once_with(
            "one@example.com,two@example.com"
        )
        assert payload["ccRecipients"] == [
            {"emailAddress": {"address": "copy@example.com"}}
        ]
        assert payload["attachments"][0]["contentBytes"] == "cHJvb2Y="
    assert payload["subject"] == "Reminder"
    assert payload["toRecipients"] == [
        {"emailAddress": {"address": "one@example.com"}},
        {"emailAddress": {"address": "two@example.com"}},
    ]
    assert payload["body"]["contentType"] == "HTML"
    content = payload["body"]["content"]
    if body_type.lower() == EmailBodyType.HTML:
        assert content == body
    else:
        assert "&lt;p&gt;A &amp; B&lt;/p&gt;<br/>" in content
        assert "<a " not in content
    assert email.text == body


def test_send_rejection_does_not_post_or_draft(graph):
    account, post, validator = graph
    validator.validate_forward.return_value = (False, "recipient blocked")
    email = Email(
        recipient="blocked@example.com",
        text="<p>HTML</p>",
        body_type=EmailBodyType.HTML,
        account=account,
    )
    with pytest.raises(RuntimeError, match="recipient blocked"):
        email.send()
    post.assert_not_called()
    account.api.get_folder_id_by_name.assert_not_called()


@pytest.mark.parametrize("explicit", [False, True])
def test_send_draft_redirect_keeps_html(graph, monkeypatch, explicit):
    account, post, validator = graph
    if not explicit:
        monkeypatch.setattr(account, "_should_draft_only", lambda flag: True)
    post.return_value.status_code = 201
    email = Email(
        recipient="carrier@example.com",
        text=HTML_BODY,
        body_type=EmailBodyType.HTML,
        account=account,
    )
    assert email.send(draft_only=explicit) is email
    assert post.call_count == 1
    assert "/mailFolders/draft-folder/messages" in post.call_args.args[0]
    assert post.call_args.kwargs["json"]["body"]["content"] == HTML_BODY
    assert email.message_id == "draft-id"
    validator.validate_forward.assert_not_called()


@pytest.mark.parametrize("draft", [False, True])
def test_graph_failure_propagates_without_fallback(graph, draft):
    account, post, _ = graph
    post.return_value.status_code = 500
    post.return_value.text = "unavailable"
    email = Email(
        recipient="carrier@example.com",
        text=HTML_BODY,
        body_type=EmailBodyType.HTML,
        account=account,
    )
    with pytest.raises(RuntimeError, match="HTTP 500"):
        if draft:
            account.create_draft(email, "drafts")
        else:
            email.send()
    assert post.call_count == 1
    assert email.message_id is None


def test_create_with_folder_sets_html_before_saving(graph):
    account, post, _ = graph
    post.return_value.status_code = 201
    email = Email.create(
        to="carrier@example.com",
        subject="Review",
        text=HTML_BODY,
        body_type=EmailBodyType.HTML,
        account=account,
        folder="Review",
    )
    assert email.body_type == EmailBodyType.HTML
    assert email.message_id == "draft-id"
    assert email._folder == "Review"
    assert post.call_args.kwargs["json"]["body"]["content"] == HTML_BODY


def test_create_defaults_to_escaped_plain_text(graph):
    account, post, _ = graph
    email = Email.create(
        to="carrier@example.com",
        subject="Plain",
        text="<b>A & B</b>\nNext",
        account=account,
    )
    email.send()
    assert email.body_type == EmailBodyType.TEXT
    assert post.call_args.kwargs["json"]["message"]["body"]["content"] == (
        "&lt;b&gt;A &amp; B&lt;/b&gt;<br/>Next"
    )
