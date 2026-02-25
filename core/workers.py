"""后台线程实现。"""
import datetime as dt
from pathlib import Path

from PySide6 import QtCore

from core.config import (
    BACKUP_ROOT_NAME,
    CHECKSUM_DIRNAME,
    ENCRYPTED_DIRNAME,
    MODE_ENCRYPTED,
    MODE_MOVE,
    MODE_PLAIN,
    SHA256_EXT,
)
from core.database import BackupDatabase
from core.logging_service import JobLogger, append_main_log_row
from core.models import BackupJob
from core.utils import (
    build_archive_name,
    build_db_path,
    collect_source_items,
    compute_file_sha256,
    compute_sha256,
    copy_file_with_progress,
    create_7z_archive,
    create_par2_redundancy,
    ensure_backup_root,
    ensure_checksum_dir,
    ensure_par2_dir,
    find_par2_exe,
    group_items_by_month,
    move_file_with_progress,
    move_par2_files,
    read_sha256_file,
    resolve_collision,
    sanitize_archive_name,
    write_readme,
    write_sha256_file_to_dir,
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
        db = None
        logger = None
        try:
            items = collect_source_items(job.source_paths, job.time_basis)
            if not items:
                self.finished.emit(False, "未找到有效文件。")
                return

            backup_root = ensure_backup_root(job.target_drive)
            start_dt = dt.datetime.now()
            start_ts = start_dt.isoformat(timespec="seconds")
            logger = JobLogger(backup_root, job.job_id, start_ts)
            db = BackupDatabase(build_db_path(backup_root))
            task_id = db.create_task(job, start_ts, len(items))

            par2_exe = find_par2_exe()
            groups, notes_count = group_items_by_month(items, job.time_basis)
            total_bytes = sum(i.size for i in items)
            done_bytes = 0
            session_success_hashes = set()
            stats = {
                "new_files": 0,
                "skipped_files": 0,
                "failed_files": 0,
                "retried_files": 0,
                "copied": 0,
                "moved": 0,
                "archived": 0,
            }

            logger.system(
                "TASK_START",
                job_id=job.job_id,
                source_paths=job.source_paths,
                target_drive=job.target_drive,
                source_type=job.source_type,
                time_basis=job.time_basis,
                mode=job.mode,
                total_files=len(items),
                total_bytes=total_bytes,
            )

            for (yyyy, mm), group_items in sorted(groups.items()):
                notes_parts = []
                if notes_count.get((yyyy, mm)):
                    notes_parts.append(f"metadata_fallback_count={notes_count[(yyyy, mm)]}")
                if job.mode in (MODE_PLAIN, MODE_MOVE):
                    self._process_plain_or_move_group(
                        db,
                        logger,
                        task_id,
                        job,
                        yyyy,
                        mm,
                        group_items,
                        notes_parts,
                        session_success_hashes,
                        stats,
                        total_bytes,
                        done_bytes,
                    )
                    done_bytes = self._done_bytes
                else:
                    self._process_encrypted_group(
                        db,
                        logger,
                        task_id,
                        job,
                        yyyy,
                        mm,
                        group_items,
                        notes_parts,
                        session_success_hashes,
                        stats,
                        par2_exe,
                        total_bytes,
                        done_bytes,
                    )
                    done_bytes = self._done_bytes

            end_ts = dt.datetime.now().isoformat(timespec="seconds")
            final_status = "success" if stats["failed_files"] == 0 else "partial_success"
            db.finish_task(task_id, end_ts, final_status, stats)
            logger.system(
                "TASK_END",
                status=final_status,
                copied=stats["copied"],
                moved=stats["moved"],
                archived=stats["archived"],
                skipped=stats["skipped_files"],
                failed=stats["failed_files"],
                retried=stats["retried_files"],
            )
            if stats["failed_files"]:
                self.finished.emit(
                    True,
                    f"备份完成（部分失败）。新增 {stats['new_files']}，跳过 {stats['skipped_files']}，失败 {stats['failed_files']}。",
                )
            else:
                self.finished.emit(True, "备份完成。")
        except Exception as exc:
            if logger:
                logger.error("TASK_CRASH", error_type=exc.__class__.__name__, error_message=str(exc))
            self.finished.emit(False, str(exc))
        finally:
            if db:
                db.close()

    def _register_item(self, db: BackupDatabase, task_id: int, item, yyyy: int, mm: int, stats: dict):
        item.sha256 = item.sha256 or compute_file_sha256(item.path)
        now_ts = dt.datetime.now().isoformat(timespec="seconds")
        asset_id = db.upsert_asset(
            file_hash=item.sha256,
            size_bytes=item.size,
            capture_time=item.capture_time or "",
            media_type=item.media_type,
            device_info=item.device_info,
            video_time_source=item.video_time_source,
            source_path=str(item.path),
            now_ts=now_ts,
        )
        retry_count = db.failed_retry_count(item.sha256)
        if retry_count > 0 and not db.has_successful_backup(item.sha256):
            stats["retried_files"] += 1
        record_id = db.insert_file_record(
            task_id=task_id,
            asset_id=asset_id,
            source_path=str(item.path),
            rel_path=item.rel_path,
            yyyy=yyyy,
            mm=mm,
            status="scanned",
            retry_count=retry_count,
            metadata={
                "capture_time": item.capture_time,
                "capture_note": item.capture_note,
                "media_type": item.media_type,
                "device_info": item.device_info,
                "video_time_source": item.video_time_source,
            },
        )
        return asset_id, record_id

    def _process_plain_or_move_group(
        self,
        db,
        logger,
        task_id,
        job,
        yyyy,
        mm,
        group_items,
        notes_parts,
        session_success_hashes,
        stats,
        total_bytes,
        done_bytes,
    ):
        self._done_bytes = done_bytes
        backup_root = ensure_backup_root(job.target_drive)
        target_dir = backup_root / f"{yyyy}" / f"{mm:02d}" / job.source_type
        write_readme(
            target_dir,
            job.readme_text,
            job.job_id,
            dt.datetime.now().isoformat(timespec="seconds"),
            "",
            job.source_paths,
            [it.rel_path for it in group_items],
            job.source_type,
            job.mode,
        )

        copied_bytes = 0
        copied_count = 0
        moved_count = 0

        for item in group_items:
            record_id = None
            try:
                _, record_id = self._register_item(db, task_id, item, yyyy, mm, stats)
                if item.sha256 in session_success_hashes or db.has_successful_backup(item.sha256):
                    stats["skipped_files"] += 1
                    self._done_bytes += item.size
                    db.update_file_record(record_id, "skipped_duplicate")
                    self.progress.emit(self._done_bytes, total_bytes, f"跳过重复: {item.path}")
                    logger.operation(
                        "SKIP_EXISTING",
                        source_path=str(item.path),
                        reason="duplicate_hash",
                        hash=item.sha256,
                    )
                    continue

                base_dest = target_dir / item.rel_path
                dest = resolve_collision(base_dest) if base_dest.exists() else base_dest

                def on_progress(chunk):
                    self._done_bytes += chunk
                    self.progress.emit(self._done_bytes, total_bytes, str(item.path))

                if job.mode == MODE_MOVE:
                    move_file_with_progress(item.path, dest, progress_cb=on_progress)
                    moved_count += 1
                    stats["moved"] += 1
                    status = "moved"
                    event = "MOVE"
                else:
                    copy_file_with_progress(item.path, dest, progress_cb=on_progress)
                    copied_count += 1
                    stats["copied"] += 1
                    status = "copied"
                    event = "COPY"

                copied_bytes += item.size
                stats["new_files"] += 1
                session_success_hashes.add(item.sha256)
                db.update_file_record(record_id, status, target_path=str(dest))
                logger.operation(
                    event,
                    source_path=str(item.path),
                    target_path=str(dest),
                    hash=item.sha256,
                )
            except Exception as exc:
                stats["failed_files"] += 1
                if record_id:
                    db.update_file_record(
                        record_id,
                        "failed",
                        error_type=exc.__class__.__name__,
                        error_message=str(exc),
                        is_exception=True,
                    )
                else:
                    db.insert_file_record(
                        task_id=task_id,
                        asset_id=None,
                        source_path=str(item.path),
                        rel_path=item.rel_path,
                        yyyy=yyyy,
                        mm=mm,
                        status="failed",
                        metadata={
                            "capture_time": item.capture_time,
                            "capture_note": item.capture_note,
                            "media_type": item.media_type,
                            "device_info": item.device_info,
                            "video_time_source": item.video_time_source,
                            "error_type": exc.__class__.__name__,
                            "error_message": str(exc),
                        },
                    )
                logger.error(
                    "FILE_PROCESS_FAILED",
                    source_path=str(item.path),
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                )

        if copied_count:
            notes_parts.append(f"copied_files={copied_count}")
        if moved_count:
            notes_parts.append(f"moved_files={moved_count}")
        notes = ";".join(notes_parts)
        append_main_log_row(
            backup_root,
            {
                "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
                "job_id": job.job_id,
                "source_path": ";".join(job.source_paths),
                "target_drive": job.target_drive,
                "yyyy": yyyy,
                "mm": mm,
                "source_type": job.source_type,
                "mode": job.mode,
                "archive_name": "",
                "size_bytes": copied_bytes,
                "sha256": "",
                "notes": notes,
            },
        )

    def _process_encrypted_group(
        self,
        db,
        logger,
        task_id,
        job,
        yyyy,
        mm,
        group_items,
        notes_parts,
        session_success_hashes,
        stats,
        par2_exe,
        total_bytes,
        done_bytes,
    ):
        self._done_bytes = done_bytes
        backup_root = ensure_backup_root(job.target_drive)
        enc_dir = backup_root / f"{yyyy}" / f"{mm:02d}" / ENCRYPTED_DIRNAME
        enc_dir.mkdir(parents=True, exist_ok=True)

        raw_name = sanitize_archive_name(job.archive_name)
        if raw_name:
            if not raw_name.lower().endswith(".7z"):
                raw_name += ".7z"
            archive_name = raw_name
        else:
            archive_name = build_archive_name(yyyy, mm, job.source_type, job.job_id)
        archive_path = resolve_collision(enc_dir / archive_name)

        write_readme(
            enc_dir,
            job.readme_text,
            job.job_id,
            dt.datetime.now().isoformat(timespec="seconds"),
            archive_path.name,
            job.source_paths,
            [it.rel_path for it in group_items],
            job.source_type,
            MODE_ENCRYPTED,
        )

        selected_items = []
        selected_records = []
        for item in group_items:
            record_id = None
            try:
                _, record_id = self._register_item(db, task_id, item, yyyy, mm, stats)
                if item.sha256 in session_success_hashes or db.has_successful_backup(item.sha256):
                    stats["skipped_files"] += 1
                    self._done_bytes += item.size
                    db.update_file_record(record_id, "skipped_duplicate")
                    self.progress.emit(self._done_bytes, total_bytes, f"跳过重复: {item.path}")
                    logger.operation(
                        "SKIP_EXISTING",
                        source_path=str(item.path),
                        reason="duplicate_hash",
                        hash=item.sha256,
                    )
                    continue
                selected_items.append(item)
                selected_records.append(record_id)
            except Exception as exc:
                stats["failed_files"] += 1
                if record_id:
                    db.update_file_record(
                        record_id,
                        "failed",
                        error_type=exc.__class__.__name__,
                        error_message=str(exc),
                        is_exception=True,
                    )
                else:
                    db.insert_file_record(
                        task_id=task_id,
                        asset_id=None,
                        source_path=str(item.path),
                        rel_path=item.rel_path,
                        yyyy=yyyy,
                        mm=mm,
                        status="failed",
                        metadata={
                            "capture_time": item.capture_time,
                            "capture_note": item.capture_note,
                            "media_type": item.media_type,
                            "device_info": item.device_info,
                            "video_time_source": item.video_time_source,
                            "error_type": exc.__class__.__name__,
                            "error_message": str(exc),
                        },
                    )
                logger.error(
                    "FILE_REGISTER_FAILED",
                    source_path=str(item.path),
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                )

        if not selected_items:
            return

        try:
            self.status.emit(f"正在归档 {yyyy}-{mm:02d}")
            create_7z_archive(
                job.seven_zip,
                archive_path,
                selected_items,
                job.password,
                job.rr_enabled,
            )
            self._done_bytes += sum(it.size for it in selected_items)
            self.progress.emit(self._done_bytes, total_bytes, str(archive_path))

            self.status.emit("正在计算 SHA256")
            hash_hex = compute_sha256(archive_path)
            checksum_dir = ensure_checksum_dir(enc_dir)
            write_sha256_file_to_dir(archive_path, hash_hex, checksum_dir)

            if job.rr_enabled:
                try:
                    self.status.emit("正在生成 PAR2 冗余文件")
                    create_par2_redundancy(par2_exe, archive_path, 5)
                    par2_dir = ensure_par2_dir(enc_dir)
                    move_par2_files(archive_path, par2_dir)
                    logger.operation("PAR2_CREATED", archive_name=archive_path.name)
                except Exception as exc:
                    logger.error(
                        "PAR2_FAILED",
                        archive_name=archive_path.name,
                        error_type=exc.__class__.__name__,
                        error_message=str(exc),
                    )

            deleted_count = 0
            if job.delete_after_encrypt:
                self.status.emit("正在删除源文件")
                for item in selected_items:
                    try:
                        item.path.unlink()
                        deleted_count += 1
                        logger.operation("DELETE_SOURCE", source_path=str(item.path))
                    except Exception as exc:
                        logger.error(
                            "DELETE_SOURCE_FAILED",
                            source_path=str(item.path),
                            error_type=exc.__class__.__name__,
                            error_message=str(exc),
                        )

            for item, record_id in zip(selected_items, selected_records):
                db.update_file_record(record_id, "archived", target_path=str(archive_path))
                session_success_hashes.add(item.sha256)
                stats["new_files"] += 1
                stats["archived"] += 1

            if deleted_count:
                notes_parts.append(f"deleted_files={deleted_count}")
            notes = ";".join(notes_parts)
            append_main_log_row(
                backup_root,
                {
                    "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
                    "job_id": job.job_id,
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
            logger.operation(
                "ARCHIVE_DONE",
                archive_name=archive_path.name,
                size_bytes=archive_path.stat().st_size,
                sha256=hash_hex,
                file_count=len(selected_items),
            )
        except Exception as exc:
            stats["failed_files"] += len(selected_items)
            for record_id in selected_records:
                db.update_file_record(
                    record_id,
                    "failed",
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                    is_exception=True,
                )
            logger.error(
                "ARCHIVE_FAILED",
                archive_name=archive_path.name,
                error_type=exc.__class__.__name__,
                error_message=str(exc),
                affected_items=len(selected_items),
            )


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
