"""通用工具函数。"""
import csv
import datetime as dt
import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ExifTags

from core.config import (
    ARCHIVE_NAME_PATTERN,
    BACKUP_ROOT_NAME,
    CHUNK_SIZE,
    CHECKSUM_DIRNAME,
    DETAIL_LOG_FILENAME,
    INDEX_DIRNAME,
    LOG_FIELDS,
    LOG_FILENAME,
    PAR2_DIRNAME,
    PAR2_EXE_NAME,
    SHA256_EXT,
    TIME_BASIS_CTIME,
    TIME_BASIS_EXIF,
    TIME_BASIS_MTIME,
)
from core.models import FileItem


def list_windows_drives():
    drives = []
    if os.name != "nt":
        return drives
    import ctypes

    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    for i in range(26):
        if bitmask & (1 << i):
            letter = chr(ord("A") + i)
            drives.append(f"{letter}:\\")
    return drives


def find_7z_exe():
    candidates = [
        r"C:\\Program Files\\7-Zip\\7z.exe",
        r"C:\\Program Files (x86)\\7-Zip\\7z.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return ""


def find_par2_exe():
    candidate = Path.cwd() / PAR2_EXE_NAME
    if candidate.exists():
        return str(candidate)
    return ""


def ensure_backup_root(target_drive: str) -> Path:
    root = Path(target_drive) / BACKUP_ROOT_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def ensure_index_dir(backup_root: Path) -> Path:
    index_dir = backup_root / INDEX_DIRNAME
    index_dir.mkdir(parents=True, exist_ok=True)
    return index_dir


def ensure_checksum_dir(base_dir: Path) -> Path:
    checksum_dir = base_dir / CHECKSUM_DIRNAME
    checksum_dir.mkdir(parents=True, exist_ok=True)
    return checksum_dir


def ensure_par2_dir(base_dir: Path) -> Path:
    par2_dir = base_dir / PAR2_DIRNAME
    par2_dir.mkdir(parents=True, exist_ok=True)
    return par2_dir


def resolve_collision(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for i in range(1, 10000):
        candidate = parent / f"{stem}({i}){suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"无法解决重名冲突: {path}")


def is_same_file(src: Path, dst: Path) -> bool:
    try:
        src_stat = src.stat()
        dst_stat = dst.stat()
    except Exception:
        return False
    return src_stat.st_size == dst_stat.st_size and int(src_stat.st_mtime) == int(dst_stat.st_mtime)


def format_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


def parse_exif_datetime(value: str):
    try:
        return dt.datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
    except Exception:
        return None


def get_exif_datetime(path: Path):
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if not exif:
                return None
            exif_map = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
            for key in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
                if key in exif_map:
                    return parse_exif_datetime(str(exif_map[key]))
    except Exception:
        return None
    return None


def get_file_datetime(path: Path, basis: str):
    note = ""
    if basis == TIME_BASIS_MTIME:
        return dt.datetime.fromtimestamp(path.stat().st_mtime), note
    if basis == TIME_BASIS_CTIME:
        return dt.datetime.fromtimestamp(path.stat().st_ctime), note
    if basis == TIME_BASIS_EXIF:
        exif_dt = get_exif_datetime(path)
        if exif_dt:
            return exif_dt, note
        note = "exif_missing_fallback_to_mtime"
        return dt.datetime.fromtimestamp(path.stat().st_mtime), note
    return dt.datetime.fromtimestamp(path.stat().st_mtime), note


def collect_source_items(source_paths):
    items = []
    for raw in source_paths:
        p = Path(raw)
        if not p.exists():
            continue
        if p.is_file():
            items.append(
                FileItem(
                    path=p,
                    size=p.stat().st_size,
                    source_root=p.parent,
                    rel_path=p.name,
                )
            )
        else:
            for root, _, files in os.walk(p):
                for name in files:
                    full = Path(root) / name
                    try:
                        rel = str(full.relative_to(p))
                    except Exception:
                        rel = full.name
                    items.append(
                        FileItem(
                            path=full,
                            size=full.stat().st_size,
                            source_root=p,
                            rel_path=rel,
                        )
                    )
    return items


def group_items_by_month(items, basis):
    groups = {}
    notes_count = {}
    for item in items:
        file_dt, note = get_file_datetime(item.path, basis)
        key = (file_dt.year, file_dt.month)
        groups.setdefault(key, []).append(item)
        if note:
            notes_count[key] = notes_count.get(key, 0) + 1
    return groups, notes_count


def append_log_row(backup_root: Path, row: dict):
    index_dir = ensure_index_dir(backup_root)
    log_path = index_dir / LOG_FILENAME
    is_new = not log_path.exists()
    with log_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)


def build_detail_log_path(backup_root: Path, job_id: str, start_dt: dt.datetime) -> Path:
    base = Path(DETAIL_LOG_FILENAME)
    stem = base.stem or "BACKUP_DETAIL"
    suffix = base.suffix or ".log"
    ts = start_dt.strftime("%Y%m%d_%H%M%S")
    name = f"{stem}_{ts}_{job_id}{suffix}"
    return backup_root / "Logs" / name


def append_detail_log(log_path: Path, line: str):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line.rstrip("\n") + "\n")


def write_detail_log_header(
    log_path: Path,
    job,
    start_dt: dt.datetime,
    total_files: int,
    total_bytes: int,
):
    start_ts = start_dt.isoformat(timespec="seconds")
    header_lines = [
        f"[{start_ts}] START",
        f"job_id={job.job_id}",
        f"source_paths={';'.join(job.source_paths)}",
        f"target_drive={job.target_drive}",
        f"source_type={job.source_type}",
        f"time_basis={job.time_basis}",
        f"mode={job.mode}",
        f"total_files={total_files}",
        f"total_bytes={total_bytes}",
        "",
    ]
    for line in header_lines:
        append_detail_log(log_path, line)


def compute_sha256(path: Path, progress_cb=None):
    h = hashlib.sha256()
    total = path.stat().st_size
    done = 0
    with path.open("rb") as f:
        while True:
            data = f.read(CHUNK_SIZE)
            if not data:
                break
            h.update(data)
            done += len(data)
            if progress_cb:
                progress_cb(done, total)
    return h.hexdigest()


def write_sha256_file(archive_path: Path, hash_hex: str):
    sha_path = archive_path.with_suffix(archive_path.suffix + SHA256_EXT)
    with sha_path.open("w", encoding="utf-8") as f:
        f.write(f"{hash_hex}  {archive_path.name}\n")
    return sha_path


def write_sha256_file_to_dir(archive_path: Path, hash_hex: str, checksum_dir: Path):
    checksum_dir.mkdir(parents=True, exist_ok=True)
    sha_name = archive_path.name + SHA256_EXT
    sha_path = checksum_dir / sha_name
    with sha_path.open("w", encoding="utf-8") as f:
        f.write(f"{hash_hex}  {archive_path.name}\n")
    return sha_path


def copy_file_with_progress(src: Path, dst: Path, progress_cb=None):
    dst.parent.mkdir(parents=True, exist_ok=True)
    with src.open("rb") as fsrc, dst.open("wb") as fdst:
        while True:
            buf = fsrc.read(CHUNK_SIZE)
            if not buf:
                break
            fdst.write(buf)
            if progress_cb:
                progress_cb(len(buf))
    shutil.copystat(src, dst, follow_symlinks=True)


def build_archive_name(yyyy: int, mm: int, source_type: str, job_id: str):
    safe_type = "".join(c for c in source_type if c.isalnum() or c in "-_ ").strip()
    safe_type = safe_type.replace(" ", "_") or "其他"
    return ARCHIVE_NAME_PATTERN.format(yyyy=yyyy, mm=mm, source_type=safe_type, job_id=job_id)


def sanitize_archive_name(raw_name: str):
    raw = (raw_name or "").strip()
    if not raw:
        return ""
    invalid = '<>:"/\\|?*'
    cleaned = "".join("_" if c in invalid else c for c in raw).strip()
    return cleaned


def create_7z_archive(
    seven_zip: str,
    archive_path: Path,
    items,
    password: str,
    rr_enabled: bool,
):
    if not seven_zip or not os.path.exists(seven_zip):
        raise RuntimeError("未找到 7z.exe，请选择 7z.exe 路径。")

    items_by_root = {}
    for item in items:
        items_by_root.setdefault(item.source_root, []).append(item)

    for source_root, root_items in items_by_root.items():
        list_file = None
        try:
            with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tf:
                list_file = tf.name
                for it in root_items:
                    tf.write(f"\"{it.rel_path}\"\n")

            cmd = [
                seven_zip,
                "a",
                str(archive_path),
                "-t7z",
                "-mx=9",
                "-mhe=on",
                f"-p{password}",
            ]
            # if rr_enabled:
            #     cmd.append("-rr5%")
            cmd.append(f"@{list_file}")

            result = subprocess.run(
                cmd,
                cwd=str(source_root),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "7z 执行失败")
        finally:
            if list_file and os.path.exists(list_file):
                os.remove(list_file)


def create_par2_redundancy(par2_exe: str, archive_path: Path, redundancy_percent: int = 5):
    if not par2_exe or not os.path.exists(par2_exe):
        raise RuntimeError("未找到 par2.exe，请放在程序根目录。")
    if redundancy_percent <= 0:
        return
    cmd = [
        par2_exe,
        "c",
        f"-r{redundancy_percent}",
        "-q",
        str(archive_path),
    ]
    result = subprocess.run(
        cmd,
        cwd=str(archive_path.parent),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "par2 执行失败")


def move_par2_files(archive_path: Path, par2_dir: Path):
    par2_dir.mkdir(parents=True, exist_ok=True)
    pattern = f"{archive_path.name}*.par2"
    for par2_file in archive_path.parent.glob(pattern):
        target = par2_dir / par2_file.name
        if target.exists():
            target = resolve_collision(target)
        par2_file.replace(target)


def read_sha256_file(sha_path: Path):
    try:
        content = sha_path.read_text(encoding="utf-8").strip()
        if not content:
            return ""
        return content.split()[0]
    except Exception:
        return ""


def write_readme(
    target_dir: Path,
    text: str,
    job_id: str,
    timestamp: str,
    archive_name: str,
    source_paths,
    file_names,
    source_type: str,
    mode: str,
):
    content = (text or "").strip()
    if not content:
        return
    target_dir.mkdir(parents=True, exist_ok=True)
    readme_path = target_dir / "README.txt"
    archive_part = archive_name or "-"
    header_lines = [
        "=== BACKUP ENTRY ===",
        f"timestamp: {timestamp}",
        f"job_id: {job_id}",
        f"mode: {mode}",
        f"source_paths: {';'.join(source_paths)}",
        f"file_names: {';'.join(file_names)}",
        f"source_type: {source_type}",
        f"archive: {archive_part}",
    ]
    with readme_path.open("a", encoding="utf-8") as f:
        if readme_path.stat().st_size > 0:
            f.write("\n\n")
        f.write("\n".join(header_lines) + "\n")
        f.write("--- MESSAGE ---\n")
        f.write(content + "\n")
        f.write("=== END ===\n")
