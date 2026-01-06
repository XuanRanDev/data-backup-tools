"""数据模型。"""
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FileItem:
    path: Path
    size: int
    source_root: Path
    rel_path: str


@dataclass
class BackupJob:
    source_paths: list
    target_drive: str
    source_type: str
    time_basis: str
    mode: str
    password: str
    rr_enabled: bool
    seven_zip: str
    job_id: str
    archive_name: str = ""
    readme_text: str = ""
