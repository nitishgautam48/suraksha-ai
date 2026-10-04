"""Block until the database accepts connections (used by start scripts)."""

import sys
import time

from sqlalchemy import create_engine, text

from backend.config import settings

deadline = time.time() + 120
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
while True:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("database is ready")
        sys.exit(0)
    except Exception as exc:
        if time.time() > deadline:
            print(f"database not reachable: {exc}", file=sys.stderr)
            sys.exit(1)
        print("waiting for database...")
        time.sleep(2)
