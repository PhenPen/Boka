"""Postgres connection pool.

One pool per process. Warm serverless instances reuse it, which keeps the
connection count low; against Neon use the pooled connection string.
"""

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import DATABASE_URL

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

pool = ConnectionPool(
    DATABASE_URL,
    min_size=0,
    max_size=20,
    timeout=10,
    open=True,
    kwargs={
        "row_factory": dict_row,
        # Neon and other pgbouncer-fronted Postgres do not survive server-side
        # prepared statements being reused across pooled backends.
        "prepare_threshold": None,
        "connect_timeout": 10,
    },
)
