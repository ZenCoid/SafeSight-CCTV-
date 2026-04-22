"""
SafeSight CCTV - Violation Database

SQLite database for logging PPE violations with snapshots.

Improvements over original database.py:
  - WAL mode for better concurrent read performance
  - Thread-safe connection handling
  - Configurable via Settings object
  - Additional 'notes' field preserved
"""

import sqlite3
import os
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict

from app.config import Settings

logger = logging.getLogger(__name__)


class ViolationDB:
    """SQLite database for violation logging and querying."""

    def __init__(self, config: Optional[Settings] = None):
        self.config = config or Settings()
        self.db_path: str = self.config.DB_PATH
        self.conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self):
        """Create tables and indexes if they don't exist."""
        self.conn = sqlite3.connect(
            self.db_path, check_same_thread=False, timeout=10
        )
        self.conn.row_factory = sqlite3.Row

        # WAL mode for better concurrent read performance
        self.conn.execute("PRAGMA journal_mode=WAL")

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
        logger.info("Database initialized: {}", self.db_path)

    def log_violation(
        self,
        detection_type: str,
        confidence: float,
        camera_id: str = "",
        camera_name: str = "",
        camera_ip: str = "",
        snapshot_path: Optional[str] = None,
    ) -> int:
        """Log a new violation to the database.

        Returns:
            ID of the inserted violation record.
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor = self.conn.execute(
            """INSERT INTO violations
               (timestamp, camera_id, camera_name, camera_ip,
                detection_type, confidence, snapshot_path)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (now, camera_id, camera_name, camera_ip,
             detection_type, confidence, snapshot_path),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_violations(
        self,
        limit: int = 50,
        offset: int = 0,
        hours: int = 24,
        camera_id: Optional[str] = None,
    ) -> List[dict]:
        """Get violations with time and camera filtering.

        Args:
            limit: Max records to return.
            offset: Pagination offset.
            hours: Only return violations from last N hours.
            camera_id: Filter by specific camera.
        """
        since = (
            datetime.now() - timedelta(hours=hours)
        ).strftime("%Y-%m-%d %H:%M:%S")

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
        """Get violation statistics for dashboard."""
        today = datetime.now().strftime("%Y-%m-%d")
        total_today = self.conn.execute(
            "SELECT COUNT(*) FROM violations WHERE DATE(timestamp) = ?",
            (today,),
        ).fetchone()[0]

        total_all = self.conn.execute(
            "SELECT COUNT(*) FROM violations"
        ).fetchone()[0]

        one_hour_ago = (
            datetime.now() - timedelta(hours=1)
        ).strftime("%Y-%m-%d %H:%M:%S")
        last_hour = self.conn.execute(
            "SELECT COUNT(*) FROM violations WHERE timestamp >= ?",
            (one_hour_ago,),
        ).fetchone()[0]

        latest = self.conn.execute(
            "SELECT timestamp FROM violations ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()

        return {
            "total_today": total_today,
            "total_all": total_all,
            "last_hour": last_hour,
            "latest_violation": (
                dict(latest)["timestamp"] if latest else None
            ),
        }

    def clear_old_records(self, days: int = 30):
        """Remove old violations and their snapshot files."""
        cutoff = (
            datetime.now() - timedelta(days=days)
        ).strftime("%Y-%m-%d %H:%M:%S")

        # Delete snapshot files
        cursor = self.conn.execute(
            """SELECT snapshot_path FROM violations
               WHERE timestamp < ? AND snapshot_path IS NOT NULL""",
            (cutoff,),
        )
        for row in cursor:
            path = row[0]
            if path and os.path.exists(path):
                os.remove(path)

        # Delete DB records
        self.conn.execute(
            "DELETE FROM violations WHERE timestamp < ?", (cutoff,)
        )
        self.conn.commit()
        logger.info("Cleaned records older than {} days", days)

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
            logger.info("Database connection closed")