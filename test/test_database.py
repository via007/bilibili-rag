import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from sqlalchemy import inspect

from app.database import SQLITE_BUSY_TIMEOUT_MS, create_database_engine, init_db


class DatabaseConfigurationTest(unittest.IsolatedAsyncioTestCase):
    async def test_sqlite_uses_wal_and_waits_for_short_write_locks(self):
        with TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "configured.db"
            engine = create_database_engine(
                f"sqlite+aiosqlite:///{database_path}",
            )

            async with engine.connect() as connection:
                journal_mode = (
                    await connection.exec_driver_sql("PRAGMA journal_mode")
                ).scalar_one()
                busy_timeout = (
                    await connection.exec_driver_sql("PRAGMA busy_timeout")
                ).scalar_one()

            await engine.dispose()

        self.assertEqual(journal_mode, "wal")
        self.assertEqual(busy_timeout, SQLITE_BUSY_TIMEOUT_MS)

    async def test_init_db_adds_transcript_metadata_to_existing_sqlite_database(self):
        with TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "legacy.db"
            engine = create_database_engine(f"sqlite+aiosqlite:///{database_path}")
            async with engine.begin() as connection:
                await connection.exec_driver_sql(
                    "CREATE TABLE video_cache (id INTEGER PRIMARY KEY, bvid VARCHAR(20), title VARCHAR(500))"
                )

            with patch("app.database.engine", engine):
                await init_db()

            async with engine.connect() as connection:
                columns = await connection.run_sync(
                    lambda sync_conn: inspect(sync_conn).get_columns("video_cache")
                )
            await engine.dispose()

        self.assertIn("transcript_segments", {column["name"] for column in columns})


if __name__ == "__main__":
    unittest.main()
