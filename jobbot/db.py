"""Başvuru geçmişi (SQLite). Aynı ilana iki kez başvurulmasını önler."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, date

from .sources import Job

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    key TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    score INTEGER DEFAULT 0,
    status TEXT DEFAULT 'new',      -- new | applied | manual | skipped | failed
    apply_email TEXT,
    note TEXT,
    first_seen TEXT,
    updated TEXT
);
"""


class DB:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def upsert(self, job: Job, score: int) -> bool:
        """Yeni ilansa True döner. Var olan ilanın durumunu değiştirmez."""
        now = datetime.now().isoformat(timespec="seconds")
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO jobs (key, data, score, first_seen, updated) "
            "VALUES (?, ?, ?, ?, ?)",
            (job.key, json.dumps(asdict(job), ensure_ascii=False), score, now, now),
        )
        if cur.rowcount == 0:
            self.conn.execute("UPDATE jobs SET score=? WHERE key=?", (score, job.key))
        self.conn.commit()
        return cur.rowcount == 1

    def set_status(self, key: str, status: str, apply_email=None, note=None):
        self.conn.execute(
            "UPDATE jobs SET status=?, apply_email=COALESCE(?, apply_email), "
            "note=?, updated=? WHERE key=?",
            (status, apply_email, note, datetime.now().isoformat(timespec="seconds"), key),
        )
        self.conn.commit()

    def by_status(self, *statuses: str) -> list[tuple[Job, sqlite3.Row]]:
        q = ",".join("?" * len(statuses))
        rows = self.conn.execute(
            f"SELECT * FROM jobs WHERE status IN ({q}) ORDER BY score DESC", statuses
        ).fetchall()
        return [(Job(**json.loads(r["data"])), r) for r in rows]

    def applied_today(self) -> int:
        today = date.today().isoformat()
        return self.conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status='applied' AND updated LIKE ?",
            (today + "%",),
        ).fetchone()[0]

    def counts(self) -> dict[str, int]:
        rows = self.conn.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")
        return {r[0]: r[1] for r in rows}
