"""后台线程实现。"""
import datetime as dt
from pathlib import Path

from PySide6 import QtCore

from core.config import (
    BACKUP_ROOT_NAME,
    CHECKSUM_DIRNAME,
    ENCRYPTED_DIRNAME,
    MODE_ENCRYPTED,
    MODE_PLAIN,
    PAR2_DIRNAME,
    SHA256_EXT,
)
from core.models import BackupJob
from core.utils import (
    append_log_row,
    compute_sha256,
    create_7z_archive,
    create_par2_redundancy,
    ensure_checksum_dir,
    ensure_backup_root,
    ensure_par2_dir,
    find_par2_exe,
    group_items_by_month,
    collect_source_items,
    read_sha256_file,
    resolve_collision,
    sanitize_archive_name,
    write_sha256_file_to_dir,
    build_archive_name,
    copy_file_with_progress,
    move_par2_files,
    write_readme,
)


class BackupWorker(QtCore.QObject):
    progress = QtCore.Signal(int, int, str)
    status = QtCore.Signal(str)
    finished = QtCore.Signal(bool, str)

    def __init__(self, job: BackupJob):
        super().__init__()
        self.job = job

    def run(self):
        job = self.job
        try:
            items = collect_source_items(job.source_paths)
            if not items:
                self.finished.emit(False, "未找到有效文件。")
                return

            par2_exe = find_par2_exe()

            groups, notes_count = group_items_by_month(items, job.time_basis)
            total_bytes = sum(i.size for i in items)
            done_bytes = 0

            backup_root = ensure_backup_root(job.target_drive)
            job_id = job.job_id
            start_ts = dt.datetime.now().isoformat(timespec="seconds")

            for (yyyy, mm), group_items in sorted(groups.items()):
                notes = ""
                if notes_count.get((yyyy, mm)):
                    notes = f"exif_fallback_count={notes_count[(yyyy, mm)]}"

                if job.mode == MODE_PLAIN:
                    target_dir = backup_root / f"{yyyy}" / f"{mm:02d}" / job.source_type
                    write_readme(
                        target_dir,
                        job.readme_text,
                        job_id,
                        start_ts,
                        "",
                        job.source_type,
                        MODE_PLAIN,
                    )
                    for it in group_items:
                        dest = target_dir / it.rel_path
                        dest = resolve_collision(dest)

                        def on_progress(chunk):
                            nonlocal done_bytes
                            done_bytes += chunk
                            self.progress.emit(done_bytes, total_bytes, str(it.path))

                        copy_file_with_progress(it.path, dest, progress_cb=on_progress)

                    size_bytes = sum(it.size for it in group_items)
                    append_log_row(
                        backup_root,
                        {
                            "timestamp": start_ts,
                            "job_id": job_id,
                            "source_path": ";".join(job.source_paths),
                            "target_drive": job.target_drive,
                            "yyyy": yyyy,
                            "mm": mm,
                            "source_type": job.source_type,
                            "mode": MODE_PLAIN,
                            "archive_name": "",
                            "size_bytes": size_bytes,
                            "sha256": "",
                            "notes": notes,
                        },
                    )
                else:
                    enc_dir = backup_root / f"{yyyy}" / f"{mm:02d}" / ENCRYPTED_DIRNAME
                    enc_dir.mkdir(parents=True, exist_ok=True)
                    raw_name = sanitize_archive_name(job.archive_name)
                    if raw_name:
                        if not raw_name.lower().endswith(".7z"):
                            raw_name += ".7z"
                        archive_name = raw_name
                    else:
                        archive_name = build_archive_name(yyyy, mm, job.source_type, job_id)
                    archive_path = resolve_collision(enc_dir / archive_name)
                    write_readme(
                        enc_dir,
                        job.readme_text,
                        job_id,
                        start_ts,
                        archive_path.name,
                        job.source_type,
                        MODE_ENCRYPTED,
                    )

                    self.status.emit(f"正在归档 {yyyy}-{mm:02d}")
                    create_7z_archive(
                        job.seven_zip,
                        archive_path,
                        group_items,
                        job.password,
                        job.rr_enabled,
                    )

                    done_bytes += sum(it.size for it in group_items)
                    self.progress.emit(done_bytes, total_bytes, str(archive_path))

                    self.status.emit("正在计算 SHA256")
                    hash_hex = compute_sha256(archive_path)
                    checksum_dir = ensure_checksum_dir(enc_dir)
                    write_sha256_file_to_dir(archive_path, hash_hex, checksum_dir)

                    if job.rr_enabled:
                        self.status.emit("正在生成 PAR2 冗余文件")
                        create_par2_redundancy(par2_exe, archive_path, 5)
                        par2_dir = ensure_par2_dir(enc_dir)
                        move_par2_files(archive_path, par2_dir)

                    append_log_row(
                        backup_root,
                        {
                            "timestamp": start_ts,
                            "job_id": job_id,
                            "source_path": ";".join(job.source_paths),
                            "target_drive": job.target_drive,
                            "yyyy": yyyy,
                            "mm": mm,
                            "source_type": job.source_type,
                            "mode": MODE_ENCRYPTED,
                            "archive_name": archive_path.name,
                            "size_bytes": archive_path.stat().st_size,
                            "sha256": hash_hex,
                            "notes": notes,
                        },
                    )

            self.finished.emit(True, "备份完成。")
        except Exception as exc:
            self.finished.emit(False, str(exc))


class VerifyWorker(QtCore.QObject):
    progress = QtCore.Signal(int, int, str)
    finished = QtCore.Signal(bool, str)

    def __init__(self, target_drive: str):
        super().__init__()
        self.target_drive = target_drive

    def run(self):
        try:
            backup_root = Path(self.target_drive) / BACKUP_ROOT_NAME
            if not backup_root.exists():
                self.finished.emit(False, "未找到 BACKUP 目录。")
                return

            archives = list(backup_root.rglob("*.7z"))
            total = len(archives)
            if not archives:
                self.finished.emit(False, "未找到 .7z 归档。")
                return

            ok_count = 0
            for idx, arch in enumerate(archives, start=1):
                checksum_dir = arch.parent / CHECKSUM_DIRNAME
                sha_path = checksum_dir / (arch.name + SHA256_EXT)
                if not sha_path.exists():
                    sha_path = arch.with_suffix(arch.suffix + SHA256_EXT)
                expected = read_sha256_file(sha_path) if sha_path.exists() else ""
                if not expected:
                    self.progress.emit(idx, total, f"缺少 sha256: {arch.name}")
                    continue

                actual = compute_sha256(arch)
                if actual.lower() == expected.lower():
                    ok_count += 1
                    msg = f"通过: {arch.name}"
                else:
                    msg = f"失败: {arch.name}"
                self.progress.emit(idx, total, msg)

            self.finished.emit(True, f"校验完成: {ok_count}/{total}")
        except Exception as exc:
            self.finished.emit(False, str(exc))
