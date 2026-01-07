"""配置常量。"""

BACKUP_ROOT_NAME = "BACKUP"
ENCRYPTED_DIRNAME = "ENCRYPTED"
INDEX_DIRNAME = "_INDEX"
LOG_FILENAME = "BACKUP_LOG.csv"
DETAIL_LOG_FILENAME = "BACKUP_DETAIL.log"
CHECKSUM_DIRNAME = "_CHECKSUM"
PAR2_DIRNAME = "_PAR2"

ARCHIVE_NAME_PATTERN = "{yyyy}-{mm:02d}__{source_type}__{job_id}.7z"

DEFAULT_SOURCE_TYPES = ["相机", "屏幕录制", "手机", "下载", "Insta360", "其他"]

LOG_FIELDS = [
    "timestamp",
    "job_id",
    "source_path",
    "target_drive",
    "yyyy",
    "mm",
    "source_type",
    "mode",
    "archive_name",
    "size_bytes",
    "sha256",
    "notes",
]

TIME_BASIS_MTIME = "mtime"
TIME_BASIS_CTIME = "ctime"
TIME_BASIS_EXIF = "exif"

MODE_PLAIN = "plain"
MODE_ENCRYPTED = "encrypted"

SHA256_EXT = ".sha256"

CHUNK_SIZE = 1024 * 1024

PAR2_EXE_NAME = "par2.exe"
