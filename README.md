

# Data Backup Tools

An offline backup organizer for Windows 10/11. It helps archive camera/phone/screen-recording materials to external drives by year and month. It supports plain copy or encrypted 7z archives with verification and logs for long-term offline storage.

## What it does
- Auto groups files into `YYYY/MM` by file time (mtime/ctime/EXIF, EXIF falls back to mtime)
- Plain copy or encrypted 7z archive (AES-256, `-mhe=on`, `-mx=9`)
- One archive per month with SHA256 checksum generation
- Optional PAR2 redundancy files (default 5%)
- Preview grouping stats, progress, and ETA
- Unified log `BACKUP/_INDEX/BACKUP_LOG.csv` plus detailed logs
- Skips already-backed-up identical files in plain mode

Typical uses:
- Offline archiving for photo/video materials
- External drive organization and long-term preservation
- Encrypted offline backups with integrity verification

## Directory structure
The target drive will contain:

```
<TargetDrive>\BACKUP\
  └─<YYYY>\
     └─<MM>\
        ├─<SourceType>\
        └─ENCRYPTED\
```

- Plain mode: files are copied into `<SourceType>`
- Encrypted mode: archives go into `ENCRYPTED`

## Requirements
- Python 3.10+ (3.12 recommended)
- Dependencies: PySide6, Pillow
- Encrypted mode requires 7-Zip (`7z.exe`), auto-detected if installed
- PAR2 uses the bundled `par2.exe`

Install dependencies:
```bash
pip install PySide6 Pillow
```

## Run
```bash
python main.py
```

## Usage
1. Add files or folders (drag & drop supported)
2. Choose target drive and source type (editable)
3. Choose time basis (mtime/ctime/EXIF)
4. Choose mode: plain copy or encrypted archive
5. In encrypted mode, enter password and confirm 7z.exe path
6. Preview grouping stats, then start

After completion, use “Verify” to recompute SHA256 and compare results.

## Logs
- Main log: `<TargetDrive>\BACKUP\_INDEX\BACKUP_LOG.csv`
- Detail logs: `<TargetDrive>\BACKUP\Logs\BACKUP_DETAIL_*.log`

Fields include timestamp, job ID, source path, target drive, year/month, source type, mode, archive name, size, SHA256, and notes.

## Configuration
Edit `core/config.py` to change:
- Directory and archive naming rules
- Default source types
- Log field definitions
- Mode and time-basis constants

## Notes
- PAR2 is optional and only available in encrypted mode (5%) to improve archive resilience
- 7-Zip is provided by the system; if not found, select `7z.exe` manually
