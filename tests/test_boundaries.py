"""Architecture rules that would otherwise be comments.

These match **text**, not an import graph. They miss an alias or an
importlib call, and would false-positive on the word in a docstring. They catch the
common accident, which is what they are for; they are not a proof.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# The app's roots: main.py builds the app, api.py mounts every router.
COMPOSITION_FILES = ("api.py", "main.py")
# Places that assemble things on their own, like main.py does for the API.
COMPOSITION_DIRS = ("worker",)
# A domain's edges: its routes, the dependencies they ask for, and its gRPC servicer.
# They may call a usecase; the domain's logic (models, policy, repositories, services)
# may not.
TRANSPORT_DIRS = ("routers", "grpc")
TRANSPORT_FILES = ("deps.py",)


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
    places that assemble things: deps.py, the gRPC servicer, the worker, and scripts."""
    allowed = {"deps.py", "servicer.py", "sqlalchemy_repository.py"}
    for path in _python_files("src"):
        if path.name in allowed or _in_composition_dir(path):
            continue
        offending = [i for i in _imports(path) if "sqlalchemy_repository" in i]
        assert not offending, f"{path.relative_to(ROOT)}: {offending}"


def test_policy_does_not_import_frameworks() -> None:
    """Business rules stay testable without an app or a database."""
    imports = _imports(ROOT / "src/users/policy.py")
    assert not [i for i in imports if "fastapi" in i or "sqlalchemy" in i], imports


def _in_composition_dir(path: Path) -> bool:
    return any(part in COMPOSITION_DIRS for part in path.relative_to(ROOT / "src").parts)


def _is_edge(path: Path) -> bool:
    parts = path.relative_to(ROOT / "src").parts
    return (
        _in_composition_dir(path)
        or parts in [(name,) for name in COMPOSITION_FILES]
        or path.name in TRANSPORT_FILES
        or any(part in TRANSPORT_DIRS for part in parts)
    )


def test_no_domain_logic_imports_usecases() -> None:
    """usecases/ sits above the domains' logic. One-way, so circular imports cannot
    happen; only the edges that call into a domain (routes, deps, servicers, the app
    roots) may call a usecase."""
    for path in _python_files("src"):
        if "usecases" in path.parts or _is_edge(path):
            continue
        offending = [i for i in _imports(path) if "usecases" in i]
        assert not offending, f"{path.relative_to(ROOT)}: {offending}"


def test_usecases_are_logic_only() -> None:
    """usecases hold cross-domain logic only: no routes, FastAPI, deps or concrete
    repositories — a usecase receives its repositories, it does not build them."""
    files = sorted((ROOT / "src/usecases").rglob("*.py"))
    if not files:
        pytest.skip("src/usecases/ has no code yet")
    assert not [p for p in files if "routers" in p.parts], "routes do not live in usecases"
    for path in files:
        offending = [
            i
            for i in _imports(path)
            if "fastapi" in i or ".routers" in i or ".deps" in i or "sqlalchemy_repository" in i
        ]
        assert not offending, f"{path.relative_to(ROOT)}: {offending}"


def test_the_api_never_imports_the_worker_side() -> None:
    """The API may import src.worker.app to send a task. The tasks and the runtime build
    the worker's clients and would load them into every API process."""
    for path in _python_files("src"):
        if _in_composition_dir(path):
            continue
        offending = [
            i for i in _imports(path) if "src.worker.tasks" in i or "src.worker.runtime" in i
        ]
        assert not offending, f"{path.relative_to(ROOT)}: {offending}"
