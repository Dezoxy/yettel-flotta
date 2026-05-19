from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import UsageResult, UsageRow


class UsageHistoryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS usage_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    name TEXT NOT NULL,
                    limit_value TEXT NOT NULL,
                    available TEXT NOT NULL,
                    valid_until TEXT NOT NULL
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_usage_history_phone ON usage_history(phone)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_usage_history_fetched_at ON usage_history(fetched_at)")

    def save_result(self, result: UsageResult) -> int:
        self.initialize()
        rows = [
            (
                result.phone,
                result.fetched_at.isoformat(timespec="seconds"),
                row.name,
                row.limit,
                row.available,
                row.valid_until,
            )
            for row in result.rows
        ]
        with sqlite3.connect(self.db_path) as connection:
            connection.executemany(
                """
                INSERT INTO usage_history (phone, fetched_at, name, limit_value, available, valid_until)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def save_results(self, results: list[UsageResult]) -> int:
        return sum(self.save_result(result) for result in results)

    def latest_result(self, phone: str) -> UsageResult | None:
        self.initialize()
        with sqlite3.connect(self.db_path) as connection:
            fetched_row = connection.execute(
                "SELECT MAX(fetched_at) FROM usage_history WHERE phone = ?",
                (phone,),
            ).fetchone()
            fetched_at = fetched_row[0] if fetched_row else None
            if not fetched_at:
                return None

            rows = connection.execute(
                """
                SELECT name, limit_value, available, valid_until
                FROM usage_history
                WHERE phone = ? AND fetched_at = ?
                ORDER BY id
                """,
                (phone, fetched_at),
            ).fetchall()

        return UsageResult(
            phone=phone,
            rows=[
                UsageRow(name=name, limit=limit_value, available=available, valid_until=valid_until)
                for name, limit_value, available, valid_until in rows
            ],
            fetched_at=UsageResult.parse_fetched_at(fetched_at),
        )

    def latest_results(self, phones: list[str]) -> dict[str, UsageResult]:
        return {phone: result for phone in phones if (result := self.latest_result(phone)) is not None}
