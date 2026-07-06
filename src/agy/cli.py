"""CLI module for Agy."""

import argparse
import shutil
import sys
from pathlib import Path


def init_project(template: str = "minimal") -> None:
    """
    Initialize a new Agy project from a template.
    Creates a new directory: agy_project/ or agy_<template>/

    Args:
        template: Template name to use (default: minimal)
    """
    # Templates are bundled with the agy package
    templates_dir = Path(__file__).parent / "templates"
    template_path = templates_dir / template

    # Validate template exists
    if not template_path.exists():
        print(f"❌ Template '{template}' not found")

        # List available templates
        available = [t.name for t in templates_dir.iterdir() if t.is_dir()]
        if available:
            print(f"Available templates: {', '.join(available)}")
        else:
            print("No templates found in templates/ directory")
        sys.exit(1)

    # Determine project directory name
    if template == "minimal":
        project_dir_name = "agy_project"
    else:
        project_dir_name = f"agy_{template}"

    base_path = Path.cwd() / project_dir_name

    # Check if directory already exists
    if base_path.exists():
        print(f"❌ Directory '{project_dir_name}' already exists")
        print("   Please remove it or choose a different location")
        sys.exit(1)

    # Create and copy template structure
    try:
        print(f"Initializing Agy project with template '{template}'...")
        print(f"Creating directory: {project_dir_name}/")

        base_path.mkdir(parents=True, exist_ok=False)

        for item in template_path.iterdir():
            target = base_path / item.name

            if item.is_dir():
                shutil.copytree(item, target)
                print(f"  ✓ Created directory: {item.name}/")
            else:
                shutil.copy2(item, target)
                print(f"  ✓ Created file: {item.name}")

        print(f"\n✓ Agy project initialized successfully in {base_path}")
        print(f"  Template used: {template}")

        # Print next steps
        print("\nNext steps:")
        print(f"  cd {project_dir_name}")
        print("  uv sync")
        print(
            "  # Copy .env.example to .env and add your API keys, mailbox credentials, etc."
        )
        print("  uv run python main.py")
    except Exception as e:
        print(f"❌ Error copying template: {e}")
        # Cleanup on error
        if base_path.exists():
            shutil.rmtree(base_path)
        sys.exit(1)

def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Agy - Small Agent Flow Engine CLI", prog="agy"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init command
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize a new Agy project (creates agy_project/ or agy_<template>/)",
    )
    init_parser.add_argument(
        "--template",
        default="minimal",
        help="Template name (default: minimal, options: minimal, software_support_jira, email_routing_mock, email_routing_imap_smtp, email_routing_graph, email_routing_gmail)",
    )

    args = parser.parse_args()

    if args.command == "init":
        init_project(args.template)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
