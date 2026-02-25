"""结构化日志服务。"""
import csv
import json
from pathlib import Path

from core.config import INDEX_DIRNAME, LOG_FIELDS, LOG_FILENAME


class JobLogger:
    def __init__(self, backup_root: Path, job_id: str, start_ts: str):
        safe_ts = start_ts.replace(":", "").replace("-", "").replace("T", "_")
        logs_root = backup_root / "Logs"
        self.system_log = logs_root / "system" / f"BACKUP_SYSTEM_{safe_ts}_{job_id}.log"
        self.operation_log = logs_root / "operation" / f"BACKUP_DETAIL_{safe_ts}_{job_id}.log"
        self.error_log = logs_root / "error" / f"BACKUP_ERROR_{safe_ts}_{job_id}.log"
        for p in (self.system_log, self.operation_log, self.error_log):
            p.parent.mkdir(parents=True, exist_ok=True)

    def system(self, event: str, **fields):
        self._write(self.system_log, event, fields)

    def operation(self, event: str, **fields):
        self._write(self.operation_log, event, fields)

    def error(self, event: str, **fields):
        self._write(self.error_log, event, fields)

    def _write(self, path: Path, event: str, fields: dict):
        row = {"event": event, **fields}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_main_log_row(backup_root: Path, row: dict):
    index_dir = backup_root / INDEX_DIRNAME
    index_dir.mkdir(parents=True, exist_ok=True)
    log_path = index_dir / LOG_FILENAME
    is_new = not log_path.exists()
    with log_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)
