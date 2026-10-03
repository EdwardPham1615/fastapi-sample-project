"""Architecture rules that would otherwise be comments.

These match **text**, not an import graph. They miss an alias or an
importlib call, and would false-positive on the word in a docstring. They catch the
common accident, which is what they are for; they are not a proof.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _python_files(*parts: str) -> list[Path]:
    files = sorted((ROOT.joinpath(*parts)).rglob("*.py"))
    assert files, f"no files under {'/'.join(parts)} — the check would pass vacuously"
    return files


def _imports(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip().startswith(("import ", "from "))
    ]


def test_integrations_do_not_import_the_service() -> None:
    """A third-party wrapper must stay reusable: it cannot know any domain exists."""
    for path in _python_files("integrations"):
        offending = [i for i in _imports(path) if i.startswith(("from src", "import src"))]
        assert not offending, f"{path.relative_to(ROOT)}: {offending}"


def test_only_composition_points_import_the_concrete_repository() -> None:
    """Across domains, depend on IUserRepository. The concrete class belongs to the
    places that assemble things: deps.py, the gRPC servicer, and scripts."""
    allowed = {"deps.py", "servicer.py", "sqlalchemy_repository.py"}
    for path in _python_files("src"):
        if path.name in allowed:
            continue
        offending = [i for i in _imports(path) if "sqlalchemy_repository" in i]
        assert not offending, f"{path.relative_to(ROOT)}: {offending}"


def test_policy_does_not_import_frameworks() -> None:
    """Business rules stay testable without an app or a database."""
    imports = _imports(ROOT / "src/users/policy.py")
    assert not [i for i in imports if "fastapi" in i or "sqlalchemy" in i], imports


def test_no_domain_imports_usecases() -> None:
    """usecases/ sits above the domains. One-way, so circular imports cannot happen."""
    for path in _python_files("src"):
        if "usecases" in path.parts:
            continue
        offending = [i for i in _imports(path) if "usecases" in i]
        assert not offending, f"{path.relative_to(ROOT)}: {offending}"
