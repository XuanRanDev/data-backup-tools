import os
import datetime as dt
from pathlib import Path

import pytest

from core.config import MODE_ENCRYPTED, MODE_MOVE, MODE_PLAIN, TIME_BASIS_MTIME
from core.models import BackupJob
from core.utils import copy_file_with_progress, move_file_with_progress
import core.workers as workers


def _write_file(path: Path, content: str, mtime: dt.datetime):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    ts = mtime.timestamp()
    os.utime(path, (ts, ts))


def _make_job(
    source_paths,
    target_drive,
    mode,
    job_id="job-1",
    source_type="Camera",
    readme_text="note",
    delete_after_encrypt=False,
):
    return BackupJob(
        source_paths=source_paths,
        target_drive=str(target_drive),
        source_type=source_type,
        time_basis=TIME_BASIS_MTIME,
        mode=mode,
        password="pass",
        rr_enabled=False,
        delete_after_encrypt=delete_after_encrypt,
        seven_zip="fake-7z.exe",
        job_id=job_id,
        archive_name="",
        readme_text=readme_text,
    )


def test_copy_and_move_file_with_progress(tmp_path: Path):
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("hello", encoding="utf-8")

    copy_file_with_progress(src, dst)
    assert dst.exists()
    assert dst.read_text(encoding="utf-8") == "hello"
    assert src.exists()

    moved = tmp_path / "moved.txt"
    move_file_with_progress(dst, moved)
    assert moved.exists()
    assert moved.read_text(encoding="utf-8") == "hello"
    assert not dst.exists()


def test_backup_worker_plain_copy(tmp_path: Path):
    source_dir = tmp_path / "source"
    mtime = dt.datetime(2024, 3, 5, 10, 0, 0)
    _write_file(source_dir / "a.txt", "a", mtime)
    _write_file(source_dir / "sub" / "b.txt", "b", mtime)

    target_drive = tmp_path / "target"
    job = _make_job([str(source_dir)], target_drive, MODE_PLAIN, job_id="job-plain")

    worker = workers.BackupWorker(job)
    worker.run()

    base = target_drive / "BACKUP" / "2024" / "03" / "Camera"
    assert (base / "a.txt").exists()
    assert (base / "sub" / "b.txt").exists()
    assert (source_dir / "a.txt").exists()
    assert (source_dir / "sub" / "b.txt").exists()

    readme = (base / "README.txt").read_text(encoding="utf-8")
    assert "source_paths:" in readme
    assert "file_names:" in readme
    assert "a.txt" in readme
    assert "sub/b.txt" in readme


def test_skip_existing_file_plain(tmp_path: Path):
    source_dir = tmp_path / "source"
    target_drive = tmp_path / "target"
    mtime = dt.datetime(2024, 6, 1, 12, 0, 0)
    _write_file(source_dir / "a.txt", "a", mtime)

    job = _make_job([str(source_dir)], target_drive, MODE_PLAIN, job_id="job-skip")
    worker = workers.BackupWorker(job)
    worker.run()

    base = target_drive / "BACKUP" / "2024" / "06" / "Camera"
    assert (base / "a.txt").exists()

    # run again with same file; should skip existing
    worker = workers.BackupWorker(job)
    worker.run()

    detail_logs = list((target_drive / "BACKUP" / "Logs").glob("BACKUP_DETAIL_*.log"))
    assert detail_logs
    content = detail_logs[-1].read_text(encoding="utf-8")
    assert "SKIP_EXISTING" in content


def test_log_csv_written(tmp_path: Path):
    source_dir = tmp_path / "source"
    mtime = dt.datetime(2024, 7, 1, 10, 0, 0)
    _write_file(source_dir / "a.txt", "a", mtime)

    target_drive = tmp_path / "target"
    job = _make_job([str(source_dir)], target_drive, MODE_PLAIN, job_id="job-log")
    worker = workers.BackupWorker(job)
    worker.run()

    log_path = target_drive / "BACKUP" / "_INDEX" / "BACKUP_LOG.csv"
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "job-log" in content
    assert "mode" in content


def test_backup_worker_move(tmp_path: Path):
    source_dir = tmp_path / "source"
    mtime = dt.datetime(2024, 4, 1, 9, 0, 0)
    _write_file(source_dir / "a.txt", "a", mtime)
    _write_file(source_dir / "b.txt", "b", mtime)

    target_drive = tmp_path / "target"
    job = _make_job([str(source_dir)], target_drive, MODE_MOVE, job_id="job-move")

    worker = workers.BackupWorker(job)
    worker.run()

    base = target_drive / "BACKUP" / "2024" / "04" / "Camera"
    assert (base / "a.txt").exists()
    assert (base / "b.txt").exists()
    assert not (source_dir / "a.txt").exists()
    assert not (source_dir / "b.txt").exists()


def test_backup_worker_encrypted_delete_after(tmp_path: Path, monkeypatch):
    source_dir = tmp_path / "source"
    mtime = dt.datetime(2024, 5, 2, 8, 0, 0)
    _write_file(source_dir / "a.txt", "a", mtime)
    _write_file(source_dir / "b.txt", "b", mtime)

    def fake_create_7z_archive(seven_zip, archive_path, items, password, rr_enabled):
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.write_text("archive", encoding="utf-8")

    monkeypatch.setattr(workers, "create_7z_archive", fake_create_7z_archive)

    target_drive = tmp_path / "target"
    job = _make_job(
        [str(source_dir)],
        target_drive,
        MODE_ENCRYPTED,
        job_id="job-enc",
        delete_after_encrypt=True,
    )

    worker = workers.BackupWorker(job)
    worker.run()

    enc_dir = target_drive / "BACKUP" / "2024" / "05" / "ENCRYPTED"
    archives = list(enc_dir.glob("*.7z"))
    assert archives
    checksum_dir = enc_dir / "_CHECKSUM"
    assert checksum_dir.exists()
    assert any(p.name.endswith(".sha256") for p in checksum_dir.iterdir())

    assert not (source_dir / "a.txt").exists()
    assert not (source_dir / "b.txt").exists()


def test_encrypted_archive_failure_reports_error(tmp_path: Path, monkeypatch):
    source_dir = tmp_path / "source"
    mtime = dt.datetime(2024, 8, 1, 9, 0, 0)
    _write_file(source_dir / "a.txt", "a", mtime)

    def fake_create_7z_archive(seven_zip, archive_path, items, password, rr_enabled):
        raise RuntimeError("7z fail")

    monkeypatch.setattr(workers, "create_7z_archive", fake_create_7z_archive)

    target_drive = tmp_path / "target"
    job = _make_job([str(source_dir)], target_drive, MODE_ENCRYPTED, job_id="job-fail")
    worker = workers.BackupWorker(job)
    worker.run()

    detail_logs = list((target_drive / "BACKUP" / "Logs").glob("BACKUP_DETAIL_*.log"))
    assert detail_logs
    content = detail_logs[-1].read_text(encoding="utf-8")
    assert "status=failed" in content
