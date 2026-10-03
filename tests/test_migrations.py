"""Migration numbering: 000001, 000002, ... in one straight line. No database needed."""

from __future__ import annotations

from alembic.config import Config
from alembic.script import ScriptDirectory

SCRIPTS = ScriptDirectory.from_config(Config("alembic.ini"))


def test_single_head() -> None:
    # Two branches that both created the next number collide loudly on merge; a
    # second head would mean someone resolved it wrongly.
    assert len(SCRIPTS.get_heads()) == 1


def test_every_revision_is_a_six_digit_number() -> None:
    # A non-numeric id means a revision was made without the env.py hook — most
    # likely because revision_environment was removed from alembic.ini.
    for rev in SCRIPTS.walk_revisions():
        assert rev.revision.isdigit() and len(rev.revision) == 6, rev.revision


def test_numbers_follow_the_chain() -> None:
    # The number is for humans; down_revision is the truth. Keep them in agreement.
    for rev in SCRIPTS.walk_revisions():
        expected = None if rev.revision == "000001" else f"{int(rev.revision) - 1:06d}"
        assert rev.down_revision == expected, rev.revision
