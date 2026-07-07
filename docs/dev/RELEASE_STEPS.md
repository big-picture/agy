# Release Steps

This repository builds public source distributions and wheels for Agy. PyPI
publishing can be done manually at first, or later via PyPI Trusted Publishing.

## Prerequisites

- CI is green on `main`.
- `CHANGELOG.md` has a dated section for the release version.
- `pyproject.toml` contains the same version as the release tag.
- The package builds locally and passes metadata checks.

## Local Checks

```bash
uv run ruff check src/ test/
uv run mypy src/agy src/flowsy
uv run pytest test/
uv build
uvx twine check dist/*
```

Inspect wheel contents when package data changes:

```bash
python -m zipfile -l dist/*.whl
```

## GitHub Release

Create and push a semver tag:

```bash
VERSION="1.0"
git tag "v${VERSION}"
git push origin "v${VERSION}"
```

The `release.yml` workflow validates the tag, builds the package, checks
metadata, extracts release notes from `CHANGELOG.md`, creates or updates the
GitHub Release, and uploads the built artifacts.

## PyPI Upload

Manual upload:

```bash
uv build
uvx twine check dist/*
uvx twine upload --repository testpypi dist/*
uvx twine upload dist/*
```

Before production upload, confirm that `python3 -m pip index versions agy`
does not show a conflicting package version and that the TestPyPI install works
in a clean environment.

## Post-Release Checklist

- [ ] CI passed before tagging.
- [ ] GitHub Release was created and contains `sdist` and `wheel` artifacts.
- [ ] PyPI/TestPyPI package metadata renders correctly.
- [ ] `CHANGELOG.md` has a new `[Unreleased]` section for future changes.

## Versioning

Agy follows [Semantic Versioning](https://semver.org/):

- **MAJOR**: breaking changes.
- **MINOR**: backwards-compatible features.
- **PATCH**: backwards-compatible fixes.
