# Public Export Policy

This public `agy` repository is a curated source export from the internal
development/archive repository `agy-private`.

## Repository Roles

- `agy-private` keeps historical development context, internal notes, drafts,
  presentations and experiments.
- `agy` contains the public Python package, tests, templates, documentation and
  release workflows needed for PyPI distribution.

## Export Rules

The public repository intentionally excludes:

- private planning notes and TODO files,
- editor extension bundles and language-server artifacts,
- generated coverage output and local playground scripts,
- large internal presentation files,
- unused legacy implementation folders.

Templates, runtime code, public documentation, tests and small fixtures are kept
when they help users install, understand or validate Agy.

## Migration Guidance

For downstream projects that used the private repository directly:

1. Replace private Git dependencies with `agy` from PyPI.
2. Install with `pip install agy` or `uv add agy`.
3. Keep existing `.flowsy` files and Python imports unless they referenced
   private-only modules.
4. If a project used the former private Git URL in a template `pyproject.toml`,
   replace it with `dependencies = ["agy>=1.0.0"]`.

The Python package import path remains `agy`; the source layout changed to
`src/agy` only inside this repository.
