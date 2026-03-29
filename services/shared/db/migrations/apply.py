from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from services.shared.db.session import build_engine


def apply_migrations() -> None:
    engine = build_engine()
    migrations_dir = Path(__file__).resolve().parent
    sql_files = sorted(migrations_dir.glob("*.sql"))

    with engine.begin() as connection:
        for path in sql_files:
            sql = path.read_text(encoding="utf-8")
            connection.execute(text(sql))


if __name__ == "__main__":
    apply_migrations()
