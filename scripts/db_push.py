"""Apply db/schema.sql to whatever DATABASE_URL points at.

Used for the local container and for Neon before deploying.
"""

import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import DATABASE_URL  # noqa: E402


def main() -> int:
    if not DATABASE_URL:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 1

    sql = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    statements = [part.strip() for part in sql.split(";") if part.strip()]

    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        for statement in statements:
            conn.execute(statement)

    target = DATABASE_URL.rsplit("@", 1)[-1]
    print(f"applied {len(statements)} statements to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
