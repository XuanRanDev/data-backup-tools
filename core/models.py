"""数据模型。"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class FileItem:
    path: Path
    size: int
    source_root: Path
    rel_path: str
    capture_time: Optional[str] = None
    capture_note: str = ""
    media_type: str = "other"
    device_info: str = ""
    sha256: str = ""
    video_time_source: str = ""


@dataclass
class BackupJob:
    source_paths: list
    target_drive: str
    source_type: str
    time_basis: str
    mode: str
    password: str
    rr_enabled: bool
    delete_after_encrypt: bool
    seven_zip: str
    job_id: str
    archive_name: str = ""
    readme_text: str = ""
