"""
Migrate data from local SQLite (talkco.db) to Supabase PostgreSQL.

Usage:
    cd backend
    python scripts/migrate_data.py [--sqlite-path talkco.db]

Requires DATABASE_URL in .env.
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncpg
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from db import SCHEMA_STATEMENTS


# Tables in FK-safe insertion order
TABLES = [
    "sessions",
    "user_profiles",
    "segments",
    "ai_marks",
    "corrections",
    "session_summaries",
    "chat_summaries",
    "review_summaries",
]

# Columns per table (must match PostgreSQL schema)
TABLE_COLUMNS = {
    "sessions": ["id", "user_id", "started_at", "ended_at", "status", "mode", "topic_id"],
    "user_profiles": ["user_id", "level", "profile_data", "updated_at"],
    "segments": ["id", "session_id", "turn_index", "user_text", "ai_text", "created_at"],
    "ai_marks": ["id", "segment_id", "issue_types", "original", "suggestion", "explanation"],
    "corrections": ["id", "session_id", "segment_id", "user_message", "correction", "explanation", "created_at"],
    "session_summaries": ["session_id", "user_id", "strengths", "weaknesses", "overall", "created_at"],
    "chat_summaries": ["session_id", "topic_id", "summary", "created_at"],
    "review_summaries": ["session_id", "user_id", "practiced", "notes", "created_at"],
}


async def migrate(sqlite_path: str) -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set in environment / .env")
        sys.exit(1)

    conn_sqlite = sqlite3.connect(sqlite_path)
    conn_sqlite.row_factory = sqlite3.Row

    conn_pg = await asyncpg.connect(dsn=database_url)

    try:
        # Create tables first
        print("Creating tables...")
        for stmt in SCHEMA_STATEMENTS:
            await conn_pg.execute(stmt)
        print("Tables ready.\n")

        for table in TABLES:
            columns = TABLE_COLUMNS[table]
            col_list = ", ".join(columns)

            rows = conn_sqlite.execute(f"SELECT {col_list} FROM {table}").fetchall()
            if not rows:
                print(f"  {table}: 0 rows (skipped)")
                continue

            placeholders = ", ".join(f"${i+1}" for i in range(len(columns)))
            insert_sql = (
                f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
                f"ON CONFLICT DO NOTHING"
            )

            count = 0
            for row in rows:
                values = [row[col] for col in columns]
                await conn_pg.execute(insert_sql, *values)
                count += 1

            # Reset serial sequences for tables with SERIAL id
            if table in ("segments", "ai_marks", "corrections"):
                await conn_pg.execute(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table}), 0))"
                )

            print(f"  {table}: {count} rows migrated")

    finally:
        await conn_pg.close()
        conn_sqlite.close()

    print("\nMigration complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate SQLite → Supabase PostgreSQL")
    parser.add_argument("--sqlite-path", default="talkco.db", help="Path to SQLite DB file")
    args = parser.parse_args()

    if not os.path.exists(args.sqlite_path):
        print(f"ERROR: SQLite file not found: {args.sqlite_path}")
        sys.exit(1)

    print(f"Migrating from {args.sqlite_path} to Supabase...")
    asyncio.run(migrate(args.sqlite_path))


if __name__ == "__main__":
    main()
