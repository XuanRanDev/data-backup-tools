"""主窗口实现。"""
import os
import time
import uuid
from pathlib import Path

from PySide6 import QtCore, QtWidgets

from core.config import (
    BACKUP_ROOT_NAME,
    INDEX_DIRNAME,
    LOG_FILENAME,
    MODE_ENCRYPTED,
    MODE_MOVE,
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
from ui.sections import (
    ActionsSection,
    EncryptSection,
    OptionsSection,
    ProgressSection,
    ReadmeSection,
    SourceSection,
)
from ui.style import apply_app_style


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("离线备份助手")
        self.resize(1000, 700)
        apply_app_style(self)

        self.seven_zip_path = find_7z_exe()
        self.worker_thread = None

        self._build_ui()
        self._refresh_drives()
        self._apply_mode_visibility()

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        self.source_section = SourceSection()
        self.options_section = OptionsSection()
        self.encrypt_section = EncryptSection()
        self.readme_section = ReadmeSection()
        self.actions_section = ActionsSection()
        self.progress_section = ProgressSection()

        self.source_list = self.source_section.source_list
        self.btn_add_files = self.source_section.btn_add_files
        self.btn_add_folders = self.source_section.btn_add_folders
        self.btn_remove_selected = self.source_section.btn_remove_selected
        self.btn_clear = self.source_section.btn_clear

        self.drive_combo = self.options_section.drive_combo
        self.btn_refresh_drives = self.options_section.btn_refresh_drives
        self.source_type_combo = self.options_section.source_type_combo
        self.time_group = self.options_section.time_group
        self.rb_mtime = self.options_section.rb_mtime
        self.rb_ctime = self.options_section.rb_ctime
        self.rb_exif = self.options_section.rb_exif
        self.mode_group = self.options_section.mode_group
        self.rb_plain = self.options_section.rb_plain
        self.rb_move = self.options_section.rb_move
        self.rb_encrypted = self.options_section.rb_encrypted

        self.encrypt_group = self.encrypt_section
        self.password_input = self.encrypt_section.password_input
        self.chk_show_password = self.encrypt_section.chk_show_password
        self.archive_name_input = self.encrypt_section.archive_name_input
        self.chk_rr = self.encrypt_section.chk_rr
        self.chk_delete_after = self.encrypt_section.chk_delete_after
        self.seven_zip_edit = self.encrypt_section.seven_zip_edit
        self.btn_browse_7z = self.encrypt_section.btn_browse_7z

        self.readme_group = self.readme_section
        self.readme_input = self.readme_section.readme_input

        self.btn_preview = self.actions_section.btn_preview
        self.btn_start = self.actions_section.btn_start
        self.btn_view_log = self.actions_section.btn_view_log
        self.btn_verify = self.actions_section.btn_verify

        self.progress_bar = self.progress_section.progress_bar
        self.status_label = self.progress_section.status_label
        self.eta_label = self.progress_section.eta_label

        self.source_list.paths_dropped.connect(self.add_source_paths)
        self.encrypt_section.set_seven_zip_path(self.seven_zip_path)

        body = QtWidgets.QHBoxLayout()
        left_col = QtWidgets.QVBoxLayout()
        right_col = QtWidgets.QVBoxLayout()

        left_col.addWidget(self.source_section)
        left_col.addWidget(self.readme_section)
        left_col.addStretch(1)

        right_col.addWidget(self.options_section)
        right_col.addWidget(self.encrypt_section)
        right_col.addWidget(self.actions_section)
        right_col.addWidget(self.progress_section)
        right_col.addStretch(1)

        body.addLayout(left_col, 3)
        body.addLayout(right_col, 2)
        layout.addLayout(body)

        # 信号
        self.btn_add_files.clicked.connect(self._on_add_files)
        self.btn_add_folders.clicked.connect(self._on_add_folder)
        self.btn_remove_selected.clicked.connect(self._on_remove_selected)
        self.btn_clear.clicked.connect(self.source_list.clear)
        self.btn_refresh_drives.clicked.connect(self._refresh_drives)
        self.btn_browse_7z.clicked.connect(self._on_browse_7z)
        self.chk_show_password.toggled.connect(self._toggle_password)
        self.rb_plain.toggled.connect(self._apply_mode_visibility)
        self.rb_move.toggled.connect(self._apply_mode_visibility)
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
            self.encrypt_section.set_seven_zip_path(path)

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

        if self.rb_plain.isChecked():
            mode = MODE_PLAIN
        elif self.rb_move.isChecked():
            mode = MODE_MOVE
        else:
            mode = MODE_ENCRYPTED
        password = self.password_input.text()
        rr_enabled = self.chk_rr.isChecked()
        delete_after_encrypt = self.chk_delete_after.isChecked()
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
            delete_after_encrypt=delete_after_encrypt,
            seven_zip=self.seven_zip_path,
            job_id=job_id,
            archive_name=archive_name,
            readme_text=readme_text,
        )

    def _on_preview(self):
        try:
            job = self._collect_job()
            items = collect_source_items(job.source_paths, job.time_basis)
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
