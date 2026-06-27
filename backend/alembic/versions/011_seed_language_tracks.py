"""Seed default language tracks

Revision ID: 011
Revises: 010
Create Date: 2026-06-26
"""

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None

_TRACKS = [
    ("fr", "French", "A2"),
    ("ru", "Russian", "A1"),
    ("es", "Spanish", "A2"),
    ("it", "Italian", "A1"),
    ("en", "English", "B2"),
]


def upgrade() -> None:
    for code, name, level in _TRACKS:
        op.execute(
            f"""
            INSERT INTO language.tracks (code, name, level, daily_quota, review_mode, active, created_at, updated_at)
            VALUES ('{code}', '{name}', '{level}', 10, 'balanced', true, NOW(), NOW())
            ON CONFLICT (code) DO NOTHING
            """
        )


def downgrade() -> None:
    codes = ", ".join(f"'{code}'" for code, _, _ in _TRACKS)
    op.execute(f"DELETE FROM language.tracks WHERE code IN ({codes})")
