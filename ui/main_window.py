"""主窗口实现。"""
import os
import time
import uuid
from pathlib import Path

from PySide6 import QtCore, QtWidgets

from core.config import (
    BACKUP_ROOT_NAME,
    DEFAULT_SOURCE_TYPES,
    INDEX_DIRNAME,
    LOG_FILENAME,
    MODE_ENCRYPTED,
    MODE_PLAIN,
    TIME_BASIS_CTIME,
    TIME_BASIS_EXIF,
    TIME_BASIS_MTIME,
)
from core.models import BackupJob
from core.utils import (
    collect_source_items,
    find_7z_exe,
    format_size,
    group_items_by_month,
    list_windows_drives,
)
from core.workers import BackupWorker, VerifyWorker
from ui.widgets import PathListWidget


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("离线备份助手")
        self.resize(1000, 700)

        self.seven_zip_path = find_7z_exe()
        self.worker_thread = None

        self._build_ui()
        self._refresh_drives()
        self._apply_mode_visibility()

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        # 源选择
        source_group = QtWidgets.QGroupBox("源选择")
        source_layout = QtWidgets.QVBoxLayout(source_group)
        self.source_list = PathListWidget()
        self.source_list.paths_dropped.connect(self.add_source_paths)
        source_layout.addWidget(self.source_list)

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_add_files = QtWidgets.QPushButton("添加文件")
        self.btn_add_folders = QtWidgets.QPushButton("添加文件夹")
        self.btn_remove_selected = QtWidgets.QPushButton("移除选中")
        self.btn_clear = QtWidgets.QPushButton("清空")
        btn_row.addWidget(self.btn_add_files)
        btn_row.addWidget(self.btn_add_folders)
        btn_row.addWidget(self.btn_remove_selected)
        btn_row.addWidget(self.btn_clear)
        btn_row.addStretch(1)
        source_layout.addLayout(btn_row)

        # 目标与选项
        options_group = QtWidgets.QGroupBox("选项")
        options_layout = QtWidgets.QGridLayout(options_group)

        self.drive_combo = QtWidgets.QComboBox()
        self.btn_refresh_drives = QtWidgets.QPushButton("刷新")
        options_layout.addWidget(QtWidgets.QLabel("目标盘"), 0, 0)
        options_layout.addWidget(self.drive_combo, 0, 1)
        options_layout.addWidget(self.btn_refresh_drives, 0, 2)

        self.source_type_combo = QtWidgets.QComboBox()
        self.source_type_combo.setEditable(True)
        self.source_type_combo.addItems(DEFAULT_SOURCE_TYPES)
        options_layout.addWidget(QtWidgets.QLabel("来源类型"), 1, 0)
        options_layout.addWidget(self.source_type_combo, 1, 1, 1, 2)

        self.time_group = QtWidgets.QButtonGroup(self)
        self.rb_mtime = QtWidgets.QRadioButton("按修改时间")
        self.rb_ctime = QtWidgets.QRadioButton("按创建时间")
        self.rb_exif = QtWidgets.QRadioButton("按 EXIF（缺失则用修改时间）")
        self.rb_mtime.setChecked(True)
        self.time_group.addButton(self.rb_mtime)
        self.time_group.addButton(self.rb_ctime)
        self.time_group.addButton(self.rb_exif)

        time_box = QtWidgets.QHBoxLayout()
        time_box.addWidget(self.rb_mtime)
        time_box.addWidget(self.rb_ctime)
        time_box.addWidget(self.rb_exif)
        time_box.addStretch(1)

        options_layout.addWidget(QtWidgets.QLabel("归类规则"), 2, 0)
        options_layout.addLayout(time_box, 2, 1, 1, 2)

        self.mode_group = QtWidgets.QButtonGroup(self)
        self.rb_plain = QtWidgets.QRadioButton("明文复制")
        self.rb_encrypted = QtWidgets.QRadioButton("加密归档")
        self.rb_plain.setChecked(True)
        self.mode_group.addButton(self.rb_plain)
        self.mode_group.addButton(self.rb_encrypted)

        mode_box = QtWidgets.QHBoxLayout()
        mode_box.addWidget(self.rb_plain)
        mode_box.addWidget(self.rb_encrypted)
        mode_box.addStretch(1)

        options_layout.addWidget(QtWidgets.QLabel("模式"), 3, 0)
        options_layout.addLayout(mode_box, 3, 1, 1, 2)

        # 加密设置
        self.encrypt_group = QtWidgets.QGroupBox("加密设置")
        encrypt_layout = QtWidgets.QGridLayout(self.encrypt_group)

        self.password_input = QtWidgets.QLineEdit()
        self.password_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.chk_show_password = QtWidgets.QCheckBox("显示")
        self.archive_name_input = QtWidgets.QLineEdit()
        self.archive_name_input.setPlaceholderText("可选，例如 2025-08__素材.7z")
        self.chk_rr = QtWidgets.QCheckBox("生成 PAR2 冗余文件 (5%)")
        self.chk_rr.setChecked(True)

        self.seven_zip_edit = QtWidgets.QLineEdit()
        self.seven_zip_edit.setReadOnly(True)
        self.seven_zip_edit.setText(self.seven_zip_path or "未找到")
        self.btn_browse_7z = QtWidgets.QPushButton("选择 7z.exe")

        encrypt_layout.addWidget(QtWidgets.QLabel("密码"), 0, 0)
        encrypt_layout.addWidget(self.password_input, 0, 1)
        encrypt_layout.addWidget(self.chk_show_password, 0, 2)
        encrypt_layout.addWidget(QtWidgets.QLabel("归档文件名"), 1, 0)
        encrypt_layout.addWidget(self.archive_name_input, 1, 1, 1, 2)
        encrypt_layout.addWidget(self.chk_rr, 2, 1)
        encrypt_layout.addWidget(QtWidgets.QLabel("7z 路径"), 3, 0)
        encrypt_layout.addWidget(self.seven_zip_edit, 3, 1)
        encrypt_layout.addWidget(self.btn_browse_7z, 3, 2)

        # README
        self.readme_group = QtWidgets.QGroupBox("README")
        readme_layout = QtWidgets.QVBoxLayout(self.readme_group)
        self.readme_input = QtWidgets.QPlainTextEdit()
        self.readme_input.setPlaceholderText("可选：写入说明到目标目录的 README.txt")
        readme_layout.addWidget(self.readme_input)

        # 操作
        actions_group = QtWidgets.QGroupBox("操作")
        actions_layout = QtWidgets.QHBoxLayout(actions_group)
        self.btn_preview = QtWidgets.QPushButton("预览")
        self.btn_start = QtWidgets.QPushButton("开始执行")
        self.btn_view_log = QtWidgets.QPushButton("查看日志")
        self.btn_verify = QtWidgets.QPushButton("校验验证")
        actions_layout.addWidget(self.btn_preview)
        actions_layout.addWidget(self.btn_start)
        actions_layout.addWidget(self.btn_view_log)
        actions_layout.addWidget(self.btn_verify)
        actions_layout.addStretch(1)

        # 进度
        progress_group = QtWidgets.QGroupBox("进度")
        progress_layout = QtWidgets.QVBoxLayout(progress_group)
        self.progress_bar = QtWidgets.QProgressBar()
        self.status_label = QtWidgets.QLabel("空闲")
        self.eta_label = QtWidgets.QLabel("剩余时间: --")
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.status_label)
        progress_layout.addWidget(self.eta_label)

        layout.addWidget(source_group)
        layout.addWidget(options_group)
        layout.addWidget(self.encrypt_group)
        layout.addWidget(self.readme_group)
        layout.addWidget(actions_group)
        layout.addWidget(progress_group)

        # 信号
        self.btn_add_files.clicked.connect(self._on_add_files)
        self.btn_add_folders.clicked.connect(self._on_add_folder)
        self.btn_remove_selected.clicked.connect(self._on_remove_selected)
        self.btn_clear.clicked.connect(self.source_list.clear)
        self.btn_refresh_drives.clicked.connect(self._refresh_drives)
        self.btn_browse_7z.clicked.connect(self._on_browse_7z)
        self.chk_show_password.toggled.connect(self._toggle_password)
        self.rb_plain.toggled.connect(self._apply_mode_visibility)
        self.rb_encrypted.toggled.connect(self._apply_mode_visibility)
        self.btn_preview.clicked.connect(self._on_preview)
        self.btn_start.clicked.connect(self._on_start)
        self.btn_view_log.clicked.connect(self._on_view_log)
        self.btn_verify.clicked.connect(self._on_verify)

    def _toggle_password(self, checked):
        self.password_input.setEchoMode(
            QtWidgets.QLineEdit.Normal if checked else QtWidgets.QLineEdit.Password
        )

    def _apply_mode_visibility(self):
        self.encrypt_group.setVisible(self.rb_encrypted.isChecked())

    def add_source_paths(self, paths):
        existing = set(self.get_source_paths())
        for p in paths:
            if p and p not in existing:
                self.source_list.addItem(p)
                existing.add(p)

    def get_source_paths(self):
        return [self.source_list.item(i).text() for i in range(self.source_list.count())]

    def _on_add_files(self):
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "选择文件")
        if files:
            self.add_source_paths(files)

    def _on_add_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            self.add_source_paths([folder])

    def _on_remove_selected(self):
        for item in self.source_list.selectedItems():
            self.source_list.takeItem(self.source_list.row(item))

    def _refresh_drives(self):
        self.drive_combo.clear()
        for d in list_windows_drives():
            self.drive_combo.addItem(d)

    def _on_browse_7z(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择 7z.exe", filter="7z.exe (7z.exe)")
        if path:
            self.seven_zip_path = path
            self.seven_zip_edit.setText(path)

    def _collect_job(self):
        source_paths = self.get_source_paths()
        if not source_paths:
            raise RuntimeError("请添加源文件或文件夹。")

        target_drive = self.drive_combo.currentText()
        if not target_drive:
            raise RuntimeError("请选择目标盘。")

        source_type = self.source_type_combo.currentText().strip() or "其他"

        if self.rb_mtime.isChecked():
            time_basis = TIME_BASIS_MTIME
        elif self.rb_ctime.isChecked():
            time_basis = TIME_BASIS_CTIME
        else:
            time_basis = TIME_BASIS_EXIF

        mode = MODE_PLAIN if self.rb_plain.isChecked() else MODE_ENCRYPTED
        password = self.password_input.text()
        rr_enabled = self.chk_rr.isChecked()
        archive_name = self.archive_name_input.text().strip()
        readme_text = self.readme_input.toPlainText()

        if mode == MODE_ENCRYPTED:
            if not password:
                raise RuntimeError("加密模式需要密码。")
            if not self.seven_zip_path or not os.path.exists(self.seven_zip_path):
                raise RuntimeError("未找到 7z.exe，请手动选择。")

        job_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]

        return BackupJob(
            source_paths=source_paths,
            target_drive=target_drive,
            source_type=source_type,
            time_basis=time_basis,
            mode=mode,
            password=password,
            rr_enabled=rr_enabled,
            seven_zip=self.seven_zip_path,
            job_id=job_id,
            archive_name=archive_name,
            readme_text=readme_text,
        )

    def _on_preview(self):
        try:
            job = self._collect_job()
            items = collect_source_items(job.source_paths)
            if not items:
                QtWidgets.QMessageBox.warning(self, "预览", "未找到有效文件。")
                return

            groups, notes = group_items_by_month(items, job.time_basis)
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle("预览")
            vbox = QtWidgets.QVBoxLayout(dialog)

            table = QtWidgets.QTableWidget(0, 4)
            table.setHorizontalHeaderLabels(["年", "月", "文件数", "大小"])
            for (yyyy, mm), group_items in sorted(groups.items()):
                row = table.rowCount()
                table.insertRow(row)
                table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(yyyy)))
                table.setItem(row, 1, QtWidgets.QTableWidgetItem(f"{mm:02d}"))
                table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(len(group_items))))
                table.setItem(
                    row,
                    3,
                    QtWidgets.QTableWidgetItem(format_size(sum(i.size for i in group_items))),
                )
            table.resizeColumnsToContents()
            vbox.addWidget(table)

            note_lines = []
            for key, cnt in notes.items():
                note_lines.append(f"{key[0]}-{key[1]:02d}: EXIF 缺失回退 {cnt} 个文件")
            if note_lines:
                note_label = QtWidgets.QLabel("\n".join(note_lines))
                vbox.addWidget(note_label)

            btn = QtWidgets.QPushButton("关闭")
            btn.clicked.connect(dialog.accept)
            vbox.addWidget(btn)

            dialog.exec()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "预览", str(exc))

    def _on_start(self):
        try:
            job = self._collect_job()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "开始执行", str(exc))
            return

        self._set_busy(True)
        self.status_label.setText("执行中...")
        self.progress_bar.setValue(0)
        self.eta_label.setText("剩余时间: --")

        self.worker = BackupWorker(job)
        self.worker_thread = QtCore.QThread()
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.status.connect(self._on_status)
        self.worker.finished.connect(self._on_finished)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self._start_time = time.time()
        self._total_bytes = 1
        self.worker_thread.start()

    def _on_progress(self, done_bytes, total_bytes, message):
        self._total_bytes = max(total_bytes, 1)
        pct = int((done_bytes / self._total_bytes) * 100)
        self.progress_bar.setValue(pct)
        self.status_label.setText(message)

        elapsed = time.time() - self._start_time
        if done_bytes > 0:
            speed = done_bytes / max(elapsed, 1)
            remaining = (self._total_bytes - done_bytes) / max(speed, 1)
            self.eta_label.setText(f"剩余时间: {int(remaining)} 秒")

    def _on_status(self, message):
        self.status_label.setText(message)

    def _on_finished(self, ok, message):
        self._set_busy(False)
        if ok:
            self.progress_bar.setValue(100)
            self.status_label.setText(message)
            QtWidgets.QMessageBox.information(self, "完成", message)
        else:
            self.status_label.setText("失败")
            QtWidgets.QMessageBox.critical(self, "错误", message)

    def _set_busy(self, busy: bool):
        self.btn_start.setEnabled(not busy)
        self.btn_preview.setEnabled(not busy)
        self.btn_verify.setEnabled(not busy)
        self.btn_view_log.setEnabled(not busy)

    def _on_view_log(self):
        try:
            drive = self.drive_combo.currentText()
            if not drive:
                raise RuntimeError("请选择目标盘。")
            log_path = Path(drive) / BACKUP_ROOT_NAME / INDEX_DIRNAME / LOG_FILENAME
            if not log_path.exists():
                raise RuntimeError("未找到日志文件。")
            os.startfile(str(log_path))
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "查看日志", str(exc))

    def _on_verify(self):
        drive = self.drive_combo.currentText()
        if not drive:
            QtWidgets.QMessageBox.warning(self, "校验验证", "请选择目标盘。")
            return

        self._set_busy(True)
        self.status_label.setText("正在校验...")
        self.progress_bar.setValue(0)

        self.verify_worker = VerifyWorker(drive)
        self.verify_thread = QtCore.QThread()
        self.verify_worker.moveToThread(self.verify_thread)
        self.verify_thread.started.connect(self.verify_worker.run)
        self.verify_worker.progress.connect(self._on_verify_progress)
        self.verify_worker.finished.connect(self._on_verify_finished)
        self.verify_worker.finished.connect(self.verify_thread.quit)
        self.verify_thread.finished.connect(self.verify_worker.deleteLater)
        self.verify_thread.finished.connect(self.verify_thread.deleteLater)
        self.verify_thread.start()

    def _on_verify_progress(self, current, total, message):
        pct = int((current / max(total, 1)) * 100)
        self.progress_bar.setValue(pct)
        self.status_label.setText(message)

    def _on_verify_finished(self, ok, message):
        self._set_busy(False)
        if ok:
            self.status_label.setText(message)
            QtWidgets.QMessageBox.information(self, "校验验证", message)
        else:
            self.status_label.setText("校验失败")
            QtWidgets.QMessageBox.warning(self, "校验验证", message)
