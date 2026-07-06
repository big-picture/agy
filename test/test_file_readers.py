"""Tests for file_readers utility functions."""

import pytest

from agy.config import reset_cache
from agy.utils.file_readers import find_file_in_standard_dirs


def test_find_file_in_cwd(tmp_path, monkeypatch):
    """Test finding a file in the current working directory."""
    # Create test file in current directory
    test_file = tmp_path / "test_instruction.md"
    test_file.write_text("# Test instruction")

    # Change to temp directory
    monkeypatch.chdir(tmp_path)
    reset_cache()

    # Find file
    found = find_file_in_standard_dirs("test_instruction.md")
    assert found == test_file.resolve()


def test_find_file_with_subdirectory_path(tmp_path, monkeypatch):
    """Test finding a file with subdirectory path in cwd."""
    # Create test structure
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    test_file = subdir / "test.md"
    test_file.write_text("# Test")

    # Change to temp directory
    monkeypatch.chdir(tmp_path)
    reset_cache()

    # Find file with subdirectory path
    found = find_file_in_standard_dirs("subdir/test.md")
    assert found == test_file.resolve()


def test_find_file_fallback_to_project_root(tmp_path, monkeypatch):
    """Test fallback to project root when file not found in cwd."""
    # Create project structure
    project_root = tmp_path / "project"
    project_root.mkdir()
    test_file = project_root / "test_file.md"
    test_file.write_text("# Test")

    # Create pyproject.toml to mark project root
    pyproject = project_root / "pyproject.toml"
    pyproject.write_text("[project]\nname = 'test'\n")

    # Change to a subdirectory within project (not project root)
    work_dir = project_root / "work"
    work_dir.mkdir()
    monkeypatch.chdir(work_dir)
    reset_cache()

    # Find file (should fallback to project root)
    found = find_file_in_standard_dirs("test_file.md")
    assert found == test_file.resolve()


def test_find_file_prefers_cwd_over_project_root(tmp_path, monkeypatch):
    """Test that cwd is checked before project root (cwd has priority)."""
    # Create project structure
    project_root = tmp_path / "project"
    project_root.mkdir()
    project_file = project_root / "test.md"
    project_file.write_text("# Project version")

    # Create pyproject.toml to mark project root
    pyproject = project_root / "pyproject.toml"
    pyproject.write_text("[project]\nname = 'test'\n")

    # Create work directory with same file
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    work_file = work_dir / "test.md"
    work_file.write_text("# Work version")

    # Change to work directory
    monkeypatch.chdir(work_dir)
    reset_cache()

    # Find file (should prefer cwd over project root)
    found = find_file_in_standard_dirs("test.md")
    assert found == work_file.resolve()
    assert found.read_text() == "# Work version"


def test_find_file_not_found_raises_error(tmp_path, monkeypatch):
    """Test that FileNotFoundError is raised with helpful message when file not found."""
    # Change to temp directory
    monkeypatch.chdir(tmp_path)
    reset_cache()

    # Try to find non-existent file
    with pytest.raises(FileNotFoundError) as exc_info:
        find_file_in_standard_dirs("nonexistent.md")

    # Check error message contains helpful information
    error_msg = str(exc_info.value)
    assert "nonexistent.md" in error_msg
    assert str(tmp_path / "nonexistent.md") in error_msg


def test_find_file_not_found_in_both_locations(tmp_path, monkeypatch):
    """Test that error message includes both cwd and project root when file not found."""
    # Create project structure
    project_root = tmp_path / "project"
    project_root.mkdir()
    pyproject = project_root / "pyproject.toml"
    pyproject.write_text("[project]\nname = 'test'\n")

    # Create work directory within project
    work_dir = project_root / "work"
    work_dir.mkdir()

    # Change to work directory
    monkeypatch.chdir(work_dir)
    reset_cache()

    # Try to find non-existent file
    with pytest.raises(FileNotFoundError) as exc_info:
        find_file_in_standard_dirs("nonexistent.md")

    # Check error message contains both locations
    error_msg = str(exc_info.value)
    assert "nonexistent.md" in error_msg
    assert str(work_dir / "nonexistent.md") in error_msg
    assert str(project_root / "nonexistent.md") in error_msg


def test_find_file_in_project_root_with_subdirectory(tmp_path, monkeypatch):
    """Test finding a file with subdirectory path in project root."""
    # Create project structure
    project_root = tmp_path / "project"
    project_root.mkdir()
    subdir = project_root / "instructions"
    subdir.mkdir()
    test_file = subdir / "test.md"
    test_file.write_text("# Test")

    # Create pyproject.toml to mark project root
    pyproject = project_root / "pyproject.toml"
    pyproject.write_text("[project]\nname = 'test'\n")

    # Change to a subdirectory within project (not project root)
    work_dir = project_root / "work"
    work_dir.mkdir()
    monkeypatch.chdir(work_dir)
    reset_cache()

    # Find file with subdirectory path (should find in project root)
    found = find_file_in_standard_dirs("instructions/test.md")
    assert found == test_file.resolve()


def test_find_file_with_absolute_path(tmp_path):
    """Test finding a file using an absolute path."""
    # Create test file
    test_file = tmp_path / "test.md"
    test_file.write_text("# Test")
    reset_cache()

    # Find file using absolute path
    found = find_file_in_standard_dirs(str(test_file))
    assert found == test_file.resolve()


def test_find_file_absolute_path_not_found(tmp_path):
    """Test that absolute path that doesn't exist raises FileNotFoundError."""
    missing_file = tmp_path / "missing.md"

    # Try to find non-existent absolute path
    with pytest.raises(FileNotFoundError) as exc_info:
        find_file_in_standard_dirs(str(missing_file))

    # Check error message
    assert "File not found" in str(exc_info.value)


def test_find_file_in_prompts_subdir(tmp_path, monkeypatch):
    """Test finding a file in prompts/ subdirectory without prefix."""
    # Create prompts directory with test file
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    test_file = prompts_dir / "instruction.md"
    test_file.write_text("# Instruction")

    monkeypatch.chdir(tmp_path)
    reset_cache()

    # Find file without specifying prompts/ prefix
    found = find_file_in_standard_dirs("instruction.md")
    assert found == test_file.resolve()


def test_find_file_in_data_subdir(tmp_path, monkeypatch):
    """Test finding a file in data/ subdirectory without prefix."""
    # Create data directory with test file
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    test_file = data_dir / "terms.md"
    test_file.write_text("# Terms")

    monkeypatch.chdir(tmp_path)
    reset_cache()

    # Find file without specifying data/ prefix
    found = find_file_in_standard_dirs("terms.md")
    assert found == test_file.resolve()


def test_find_file_in_objects_subdir(tmp_path, monkeypatch):
    """Test finding a file in objects/ subdirectory without prefix."""
    # Create objects directory with test file
    objects_dir = tmp_path / "objects"
    objects_dir.mkdir()
    test_file = objects_dir / "schema.md"
    test_file.write_text("# Schema")

    monkeypatch.chdir(tmp_path)
    reset_cache()

    # Find file without specifying objects/ prefix
    found = find_file_in_standard_dirs("schema.md")
    assert found == test_file.resolve()


def test_find_file_cwd_has_priority_over_subdirs(tmp_path, monkeypatch):
    """Test that cwd has priority over standard subdirectories."""
    # Create file in cwd
    cwd_file = tmp_path / "test.md"
    cwd_file.write_text("# CWD version")

    # Create same file in prompts/
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    prompts_file = prompts_dir / "test.md"
    prompts_file.write_text("# Prompts version")

    monkeypatch.chdir(tmp_path)
    reset_cache()

    # Find file - should prefer cwd over prompts/
    found = find_file_in_standard_dirs("test.md")
    assert found == cwd_file.resolve()
    assert found.read_text() == "# CWD version"


def test_find_file_prompts_has_priority_over_data(tmp_path, monkeypatch):
    """Test that prompts/ has priority over data/ (search order)."""
    # Create file in prompts/
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    prompts_file = prompts_dir / "test.md"
    prompts_file.write_text("# Prompts version")

    # Create same file in data/
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    data_file = data_dir / "test.md"
    data_file.write_text("# Data version")

    monkeypatch.chdir(tmp_path)
    reset_cache()

    # Find file - should prefer prompts/ over data/
    found = find_file_in_standard_dirs("test.md")
    assert found == prompts_file.resolve()
    assert found.read_text() == "# Prompts version"
