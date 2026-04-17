"""
SafeSight CCTV - Violation Database
SQLite database for logging PPE violations with snapshots.
"""
import sqlite3
import os
from datetime import datetime, timedelta
from config import Config


class ViolationDB:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or Config.DB_PATH
        self.conn = None
        self._init_db()

    def _init_db(self):
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS violations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                camera_id TEXT DEFAULT '',
                camera_name TEXT DEFAULT '',
                camera_ip TEXT DEFAULT '',
                detection_type TEXT NOT NULL,
                confidence REAL NOT NULL,
                snapshot_path TEXT,
                reviewed INTEGER DEFAULT 0,
                notes TEXT DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_violations_timestamp
                ON violations(timestamp);

            CREATE INDEX IF NOT EXISTS idx_violations_camera
                ON violations(camera_id);
        """)
        self.conn.commit()
        print(f"[Database] Initialized: {self.db_path}")

    def log_violation(
        self,
        detection_type: str,
        confidence: float,
        camera_id: str = "",
        camera_name: str = "",
        camera_ip: str = "",
        snapshot_path: str = None,
    ) -> int:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor = self.conn.execute(
            """INSERT INTO violations
               (timestamp, camera_id, camera_name, camera_ip, detection_type, confidence, snapshot_path)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (now, camera_id, camera_name, camera_ip, detection_type, confidence, snapshot_path),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_violations(
        self, limit: int = 50, offset: int = 0, hours: int = 24, camera_id: str = None
    ) -> list:
        since = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")

        if camera_id:
            cursor = self.conn.execute(
                """SELECT * FROM violations
                   WHERE timestamp >= ? AND camera_id = ?
                   ORDER BY timestamp DESC LIMIT ? OFFSET ?""",
                (since, camera_id, limit, offset),
            )
        else:
            cursor = self.conn.execute(
                """SELECT * FROM violations
                   WHERE timestamp >= ?
                   ORDER BY timestamp DESC LIMIT ? OFFSET ?""",
                (since, limit, offset),
            )
        return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> dict:
        today = datetime.now().strftime("%Y-%m-%d")
        total_today = self.conn.execute(
            "SELECT COUNT(*) FROM violations WHERE DATE(timestamp) = ?", (today,)
        ).fetchone()[0]

        total_all = self.conn.execute("SELECT COUNT(*) FROM violations").fetchone()[0]

        one_hour_ago = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        last_hour = self.conn.execute(
            "SELECT COUNT(*) FROM violations WHERE timestamp >= ?", (one_hour_ago,)
        ).fetchone()[0]

        latest = self.conn.execute(
            "SELECT timestamp FROM violations ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()

        return {
            "total_today": total_today,
            "total_all": total_all,
            "last_hour": last_hour,
            "latest_violation": dict(latest)["timestamp"] if latest else None,
        }

    def clear_old_records(self, days: int = 30):
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        cursor = self.conn.execute(
            "SELECT snapshot_path FROM violations WHERE timestamp < ? AND snapshot_path IS NOT NULL",
            (cutoff,),
        )
        for row in cursor:
            path = row[0]
            if path and os.path.exists(path):
                os.remove(path)
        self.conn.execute("DELETE FROM violations WHERE timestamp < ?", (cutoff,))
        self.conn.commit()
        print(f"[Database] Cleaned records older than {days} days")

    def close(self):
        if self.conn:
            self.conn.close()