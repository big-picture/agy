"""Tests for config path resolution functions."""

from agy.config import get_project_root, reset_cache


def test_get_project_root_from_pyproject_toml(tmp_path, monkeypatch):
    """Test that project root is read from pyproject.toml [tool.agy] config."""
    # Create project structure
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create pyproject.toml with [tool.agy] config
    pyproject = project_root / "pyproject.toml"
    pyproject.write_text(
        """[project]
name = "test"

[tool.agy]
project_root = "."
"""
    )

    # Change to project root
    monkeypatch.chdir(project_root)
    reset_cache()

    # Get project root
    root = get_project_root()
    assert root == project_root.resolve()


def test_get_project_root_from_pyproject_toml_relative_path(tmp_path, monkeypatch):
    """Test that project_root can be a relative path in pyproject.toml."""
    # Create project structure
    actual_root = tmp_path / "actual_root"
    actual_root.mkdir()

    config_dir = tmp_path / "config_dir"
    config_dir.mkdir()

    # Create pyproject.toml in config_dir with relative path to actual_root
    pyproject = config_dir / "pyproject.toml"
    pyproject.write_text(
        """[project]
name = "test"

[tool.agy]
project_root = "../actual_root"
"""
    )

    # Change to config_dir
    monkeypatch.chdir(config_dir)
    reset_cache()

    # Get project root
    root = get_project_root()
    assert root == actual_root.resolve()


def test_get_project_root_auto_detect_pyproject_toml(tmp_path, monkeypatch):
    """Test auto-detection of project root via pyproject.toml."""
    # Create project structure
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create pyproject.toml (without [tool.agy] config)
    pyproject = project_root / "pyproject.toml"
    pyproject.write_text("[project]\nname = 'test'\n")

    # Create subdirectory
    subdir = project_root / "subdir"
    subdir.mkdir()

    # Change to subdirectory
    monkeypatch.chdir(subdir)
    reset_cache()

    # Get project root (should auto-detect)
    root = get_project_root()
    assert root == project_root.resolve()


def test_get_project_root_auto_detect_git(tmp_path, monkeypatch):
    """Test auto-detection of project root via .git directory."""
    # Create project structure
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create .git directory
    git_dir = project_root / ".git"
    git_dir.mkdir()

    # Create subdirectory
    subdir = project_root / "subdir"
    subdir.mkdir()

    # Change to subdirectory
    monkeypatch.chdir(subdir)
    reset_cache()

    # Get project root (should auto-detect via .git)
    root = get_project_root()
    assert root == project_root.resolve()


def test_get_project_root_from_env(tmp_path, monkeypatch):
    """Test that project root can be set via environment variable."""
    # Create project structure
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Set environment variable
    monkeypatch.setenv("AGY_PROJECT_ROOT", str(project_root))

    # Change to different directory
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    monkeypatch.chdir(work_dir)
    reset_cache()

    # Get project root
    root = get_project_root()
    assert root == project_root.resolve()

    # Cleanup
    monkeypatch.delenv("AGY_PROJECT_ROOT", raising=False)


def test_get_project_root_fallback_to_cwd(tmp_path, monkeypatch):
    """Test that project root falls back to cwd() when no markers found."""
    # Create work directory (no pyproject.toml or .git)
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    # Change to work directory
    monkeypatch.chdir(work_dir)
    reset_cache()

    # Get project root (should fallback to cwd)
    root = get_project_root()
    assert root == work_dir.resolve()


def test_get_project_root_caching(tmp_path, monkeypatch):
    """Test that project root is cached after first lookup."""
    # Create project structure
    project_root = tmp_path / "project"
    project_root.mkdir()
    pyproject = project_root / "pyproject.toml"
    pyproject.write_text("[project]\nname = 'test'\n")

    monkeypatch.chdir(project_root)
    reset_cache()

    # First call
    root1 = get_project_root()

    # Remove pyproject.toml (should still use cached value)
    pyproject.unlink()

    # Second call (should use cache)
    root2 = get_project_root()

    assert root1 == root2 == project_root.resolve()


def test_reset_cache(tmp_path, monkeypatch):
    """Test that reset_cache() clears the cache."""
    # Create project structure
    project_root = tmp_path / "project"
    project_root.mkdir()
    pyproject = project_root / "pyproject.toml"
    pyproject.write_text("[project]\nname = 'test'\n")

    monkeypatch.chdir(project_root)
    reset_cache()

    # First call
    root1 = get_project_root()
    assert root1 == project_root.resolve()

    # Remove pyproject.toml
    pyproject.unlink()

    # Reset cache
    reset_cache()

    # Now should fallback to cwd (since pyproject.toml is gone)
    root2 = get_project_root()
    assert root2 == project_root.resolve()  # Still same because cwd is project_root


def test_get_project_root_walks_up_directory_tree(tmp_path, monkeypatch):
    """Test that project root detection walks up the directory tree."""
    # Create nested structure
    project_root = tmp_path / "project"
    project_root.mkdir()
    pyproject = project_root / "pyproject.toml"
    pyproject.write_text("[project]\nname = 'test'\n")

    # Create nested subdirectories
    level1 = project_root / "level1"
    level1.mkdir()
    level2 = level1 / "level2"
    level2.mkdir()
    level3 = level2 / "level3"
    level3.mkdir()

    # Change to deepest level
    monkeypatch.chdir(level3)
    reset_cache()

    # Get project root (should find it by walking up)
    root = get_project_root()
    assert root == project_root.resolve()
