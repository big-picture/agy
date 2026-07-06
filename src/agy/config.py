# agy/config.py

"""AGY framework configuration and path resolution."""

import os
from pathlib import Path

# Constants
FILE_SEARCH_ORDER = [".", "prompts", "data", "objects"]

# FLOWSY grammar path (bundled with AGY)
FLOWSY_GRAMMAR_PATH = (
    Path(__file__).parent.parent / "flowsy" / "flowsy_grammar.v0.1.yaml"
)

# Cache
_project_root_cache: Path | None = None
_llm_config_cache: dict | None = None


def _read_pyproject_section(pyproject: Path, section_path: list[str]) -> dict | None:
    """Read a nested section from pyproject.toml, e.g., ["tool", "agy", "llm"]."""
    try:
        try:
            import tomllib  # Python 3.11+

            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except ModuleNotFoundError:
            import tomli

            with pyproject.open("rb") as f:
                data = tomli.load(f)
    except Exception:
        return None

    section: dict | None = data
    for key in section_path:
        if isinstance(section, dict):
            section = section.get(key)
        else:
            return None
    return section if isinstance(section, dict) else None


def _find_project_root() -> Path:
    """Find project root (pyproject.toml directory) using fallback chain."""
    global _project_root_cache
    if _project_root_cache:
        return _project_root_cache

    # 1. Check pyproject.toml [tool.agy] → project_root
    current = Path.cwd()
    for _ in range(10):
        pyproject = current / "pyproject.toml"
        if pyproject.exists():
            # Try to load pyproject.toml
            toml_loader = None
            try:
                import tomli

                toml_loader = tomli.load
            except ImportError:
                try:
                    import tomllib

                    toml_loader = tomllib.load
                except ImportError:
                    pass

            if toml_loader:
                try:
                    with open(pyproject, "rb") as f:
                        data = toml_loader(f)
                        if (
                            root_str := data.get("tool", {})
                            .get("agy", {})
                            .get("project_root")
                        ):
                            _project_root_cache = (current / root_str).resolve()
                            return _project_root_cache
                except Exception:
                    pass
            # 2. Auto-detect: pyproject.toml directory is project root
            _project_root_cache = current.resolve()
            return _project_root_cache
        if (current / ".git").exists():
            _project_root_cache = current.resolve()
            return _project_root_cache
        current = current.parent
        if current == current.parent:
            break

    # 3. Environment variable
    if env_root := os.getenv("AGY_PROJECT_ROOT"):
        _project_root_cache = Path(env_root).resolve()
        return _project_root_cache

    # 4. Fallback
    _project_root_cache = Path.cwd().resolve()
    return _project_root_cache


# Paths (resolved at runtime)
def get_project_root() -> Path:
    """Project root directory (where pyproject.toml is located)."""
    return _find_project_root()


def get_package_root() -> Path:
    """Installed agy package root directory."""
    return Path(__file__).parent


def reset_cache() -> None:
    """Reset the project root cache (useful for testing)."""
    global _project_root_cache
    _project_root_cache = None


def get_flowsy_grammar_path() -> Path:
    """Path to bundled FLOWSY grammar file."""
    return FLOWSY_GRAMMAR_PATH


def load_llm_config() -> dict:
    """
    Load LLM configuration from user's pyproject.toml.

    Fallback if not present:
      default_provider = "openai"
      default_model = "gpt-5-mini"
      default_params = {}
    """
    global _llm_config_cache
    if _llm_config_cache is not None:
        return _llm_config_cache

    project_root = get_project_root()
    pyproject = project_root / "pyproject.toml"

    defaults = {
        "default_provider": "openai",
        "default_model": "gpt-5-mini",
        "default_params": {},
        "providers": {},
    }

    if pyproject.exists():
        section = _read_pyproject_section(pyproject, ["tool", "agy", "llm"])
        if isinstance(section, dict):
            merged = defaults | {k: v for k, v in section.items() if v is not None}
            _llm_config_cache = merged
            return merged

    _llm_config_cache = defaults
    return defaults
