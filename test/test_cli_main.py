"""Tests for CLI main entrypoint behavior."""

from __future__ import annotations

import pytest

import agy.cli as cli


def test_main_dispatches_init(monkeypatch: pytest.MonkeyPatch) -> None:
    """The init subcommand should call init_project with template."""
    called = {}

    def fake_init(template: str) -> None:
        called["template"] = template

    monkeypatch.setattr(cli, "init_project", fake_init)
    monkeypatch.setattr("sys.argv", ["agy", "init", "--template", "email_routing_mock"])

    cli.main()
    assert called["template"] == "email_routing_mock"


def test_main_without_subcommand_prints_help(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No command should print argparse help text."""
    monkeypatch.setattr("sys.argv", ["agy"])
    cli.main()
    out = capsys.readouterr().out
    assert "Available commands" in out
    assert "install-language-server" not in out
