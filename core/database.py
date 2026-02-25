"""SQLite 持久化层。"""
import json
import sqlite3
from pathlib import Path


class BackupDatabase:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self):
        self.conn.close()

    def _init_schema(self):
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS backup_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL UNIQUE,
                start_time TEXT NOT NULL,
                end_time TEXT,
                status TEXT NOT NULL,
                source_paths TEXT NOT NULL,
                target_drive TEXT NOT NULL,
                source_type TEXT NOT NULL,
                time_basis TEXT NOT NULL,
                mode TEXT NOT NULL,
                scanned_files INTEGER NOT NULL DEFAULT 0,
                new_files INTEGER NOT NULL DEFAULT 0,
                skipped_files INTEGER NOT NULL DEFAULT 0,
                failed_files INTEGER NOT NULL DEFAULT 0,
                retried_files INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS file_assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hash_type TEXT NOT NULL,
                file_hash TEXT NOT NULL UNIQUE,
                size_bytes INTEGER NOT NULL,
                capture_time TEXT,
                media_type TEXT NOT NULL,
                device_info TEXT,
                video_time_source TEXT,
                first_source_path TEXT,
                last_source_path TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS task_file_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                asset_id INTEGER,
                source_path TEXT NOT NULL,
                rel_path TEXT NOT NULL,
                target_path TEXT,
                yyyy INTEGER,
                mm INTEGER,
                status TEXT NOT NULL,
                error_type TEXT,
                error_message TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0,
                is_exception INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES backup_tasks(id),
                FOREIGN KEY(asset_id) REFERENCES file_assets(id)
            );

            CREATE INDEX IF NOT EXISTS idx_task_file_records_task_id
                ON task_file_records(task_id);
            CREATE INDEX IF NOT EXISTS idx_task_file_records_status
                ON task_file_records(status);
            CREATE INDEX IF NOT EXISTS idx_task_file_records_asset_id
                ON task_file_records(asset_id);

            CREATE TABLE IF NOT EXISTS schema_comments (
                table_name TEXT NOT NULL,
                column_name TEXT NOT NULL,
                comment TEXT NOT NULL,
                PRIMARY KEY (table_name, column_name)
            );
            """
        )
        self._init_schema_comments()
        self.conn.commit()

    def _init_schema_comments(self):
        comments = [
            ("backup_tasks", "id", "备份任务主键"),
            ("backup_tasks", "job_id", "任务唯一标识，来自程序运行实例"),
            ("backup_tasks", "start_time", "任务开始时间（ISO8601）"),
            ("backup_tasks", "end_time", "任务结束时间（ISO8601）"),
            ("backup_tasks", "status", "任务状态：running/success/partial_success/failed"),
            ("backup_tasks", "source_paths", "本次任务来源路径列表，分号分隔"),
            ("backup_tasks", "target_drive", "目标盘符"),
            ("backup_tasks", "source_type", "来源类型，如相机/手机"),
            ("backup_tasks", "time_basis", "归类时间依据：mtime/ctime/exif"),
            ("backup_tasks", "mode", "备份模式：plain/move/encrypted"),
            ("backup_tasks", "scanned_files", "扫描到的文件总数"),
            ("backup_tasks", "new_files", "新增入备份的文件数"),
            ("backup_tasks", "skipped_files", "因去重跳过的文件数"),
            ("backup_tasks", "failed_files", "失败文件数"),
            ("backup_tasks", "retried_files", "命中失败重试逻辑的文件数"),
            ("file_assets", "id", "文件资产主键"),
            ("file_assets", "hash_type", "哈希算法类型（当前为 sha256）"),
            ("file_assets", "file_hash", "文件内容哈希，资产唯一键"),
            ("file_assets", "size_bytes", "文件大小（字节）"),
            ("file_assets", "capture_time", "拍摄/创建时间（ISO8601）"),
            ("file_assets", "media_type", "媒体类型：image/video/other"),
            ("file_assets", "device_info", "设备信息（如相机厂商/型号）"),
            ("file_assets", "video_time_source", "视频时间来源（ffprobe解析结果）"),
            ("file_assets", "first_source_path", "首次扫描到该资产的源路径"),
            ("file_assets", "last_source_path", "最近一次扫描到该资产的源路径"),
            ("file_assets", "first_seen_at", "资产首次入库时间（ISO8601）"),
            ("file_assets", "last_seen_at", "资产最近一次更新入库时间（ISO8601）"),
            ("task_file_records", "id", "任务文件记录主键"),
            ("task_file_records", "task_id", "所属备份任务ID"),
            ("task_file_records", "asset_id", "关联文件资产ID，可为空"),
            ("task_file_records", "source_path", "文件源路径"),
            ("task_file_records", "rel_path", "相对来源路径"),
            ("task_file_records", "target_path", "目标路径（明文目标或归档路径）"),
            ("task_file_records", "yyyy", "归档年份"),
            ("task_file_records", "mm", "归档月份"),
            ("task_file_records", "status", "文件状态：scanned/copied/moved/archived/skipped_duplicate/failed"),
            ("task_file_records", "error_type", "异常类型"),
            ("task_file_records", "error_message", "异常信息"),
            ("task_file_records", "retry_count", "该文件历史失败后重试次数"),
            ("task_file_records", "is_exception", "是否标记为异常记录（0/1）"),
            ("task_file_records", "metadata_json", "扩展元数据JSON"),
            ("task_file_records", "created_at", "记录创建时间（ISO8601）"),
            ("task_file_records", "updated_at", "记录更新时间（ISO8601）"),
        ]
        self.conn.executemany(
            """
            INSERT INTO schema_comments (table_name, column_name, comment)
            VALUES (?, ?, ?)
            ON CONFLICT(table_name, column_name) DO UPDATE SET comment = excluded.comment
            """,
            comments,
        )

    def create_task(self, job, start_ts: str, scanned_files: int) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO backup_tasks (
                job_id, start_time, status, source_paths, target_drive, source_type,
                time_basis, mode, scanned_files
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.job_id,
                start_ts,
                "running",
                ";".join(job.source_paths),
                job.target_drive,
                job.source_type,
                job.time_basis,
                job.mode,
                scanned_files,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_task(self, task_id: int, end_ts: str, status: str, stats: dict):
        self.conn.execute(
            """
            UPDATE backup_tasks
            SET end_time = ?,
                status = ?,
                new_files = ?,
                skipped_files = ?,
                failed_files = ?,
                retried_files = ?
            WHERE id = ?
            """,
            (
                end_ts,
                status,
                int(stats.get("new_files", 0)),
                int(stats.get("skipped_files", 0)),
                int(stats.get("failed_files", 0)),
                int(stats.get("retried_files", 0)),
                task_id,
            ),
        )
        self.conn.commit()

    def upsert_asset(
        self,
        file_hash: str,
        size_bytes: int,
        capture_time: str,
        media_type: str,
        device_info: str,
        video_time_source: str,
        source_path: str,
        now_ts: str,
    ) -> int:
        self.conn.execute(
            """
            INSERT INTO file_assets (
                hash_type, file_hash, size_bytes, capture_time, media_type, device_info,
                video_time_source, first_source_path, last_source_path, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_hash) DO UPDATE SET
                size_bytes = excluded.size_bytes,
                capture_time = COALESCE(excluded.capture_time, capture_time),
                media_type = excluded.media_type,
                device_info = COALESCE(excluded.device_info, device_info),
                video_time_source = COALESCE(excluded.video_time_source, video_time_source),
                last_source_path = excluded.last_source_path,
                last_seen_at = excluded.last_seen_at
            """,
            (
                "sha256",
                file_hash,
                size_bytes,
                capture_time or None,
                media_type or "other",
                device_info or None,
                video_time_source or None,
                source_path,
                source_path,
                now_ts,
                now_ts,
            ),
        )
        cur = self.conn.execute(
            "SELECT id FROM file_assets WHERE file_hash = ?",
            (file_hash,),
        )
        row = cur.fetchone()
        self.conn.commit()
        return int(row["id"])

    def has_successful_backup(self, file_hash: str) -> bool:
        cur = self.conn.execute(
            """
            SELECT 1
            FROM task_file_records r
            JOIN file_assets a ON a.id = r.asset_id
            WHERE a.file_hash = ?
              AND r.status IN ('copied', 'moved', 'archived')
            LIMIT 1
            """,
            (file_hash,),
        )
        return cur.fetchone() is not None

    def failed_retry_count(self, file_hash: str) -> int:
        cur = self.conn.execute(
            """
            SELECT COUNT(1) AS cnt
            FROM task_file_records r
            JOIN file_assets a ON a.id = r.asset_id
            WHERE a.file_hash = ?
              AND r.status = 'failed'
            """,
            (file_hash,),
        )
        row = cur.fetchone()
        return int(row["cnt"] if row else 0)

    def insert_file_record(
        self,
        task_id: int,
        asset_id: int | None,
        source_path: str,
        rel_path: str,
        yyyy: int,
        mm: int,
        status: str,
        retry_count: int = 0,
        metadata: dict | None = None,
    ) -> int:
        now_ts = self._now_ts()
        payload = json.dumps(metadata or {}, ensure_ascii=False)
        cur = self.conn.execute(
            """
            INSERT INTO task_file_records (
                task_id, asset_id, source_path, rel_path, yyyy, mm, status,
                retry_count, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                asset_id,
                source_path,
                rel_path,
                yyyy,
                mm,
                status,
                retry_count,
                payload,
                now_ts,
                now_ts,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update_file_record(
        self,
        record_id: int,
        status: str,
        target_path: str = "",
        error_type: str = "",
        error_message: str = "",
        is_exception: bool = False,
    ):
        self.conn.execute(
            """
            UPDATE task_file_records
            SET status = ?,
                target_path = ?,
                error_type = ?,
                error_message = ?,
                is_exception = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                target_path or None,
                error_type or None,
                error_message or None,
                1 if is_exception else 0,
                self._now_ts(),
                record_id,
            ),
        )
        self.conn.commit()

    @staticmethod
    def _now_ts() -> str:
        from datetime import datetime

        return datetime.now().isoformat(timespec="seconds")
