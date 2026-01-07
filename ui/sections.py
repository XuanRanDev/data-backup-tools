"""UI section widgets."""
from PySide6 import QtWidgets

from core.config import DEFAULT_SOURCE_TYPES
from ui.widgets import PathListWidget


class SourceSection(QtWidgets.QGroupBox):
    def __init__(self):
        super().__init__("源选择")
        layout = QtWidgets.QVBoxLayout(self)
        self.source_list = PathListWidget()
        layout.addWidget(self.source_list)

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
        layout.addLayout(btn_row)


class OptionsSection(QtWidgets.QGroupBox):
    def __init__(self):
        super().__init__("选项")
        layout = QtWidgets.QGridLayout(self)

        self.drive_combo = QtWidgets.QComboBox()
        self.btn_refresh_drives = QtWidgets.QPushButton("刷新")
        layout.addWidget(QtWidgets.QLabel("目标盘"), 0, 0)
        layout.addWidget(self.drive_combo, 0, 1)
        layout.addWidget(self.btn_refresh_drives, 0, 2)

        self.source_type_combo = QtWidgets.QComboBox()
        self.source_type_combo.setEditable(True)
        self.source_type_combo.addItems(DEFAULT_SOURCE_TYPES)
        layout.addWidget(QtWidgets.QLabel("来源类型"), 1, 0)
        layout.addWidget(self.source_type_combo, 1, 1, 1, 2)

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

        layout.addWidget(QtWidgets.QLabel("归类规则"), 2, 0)
        layout.addLayout(time_box, 2, 1, 1, 2)

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

        layout.addWidget(QtWidgets.QLabel("模式"), 3, 0)
        layout.addLayout(mode_box, 3, 1, 1, 2)


class EncryptSection(QtWidgets.QGroupBox):
    def __init__(self):
        super().__init__("加密设置")
        layout = QtWidgets.QGridLayout(self)

        self.password_input = QtWidgets.QLineEdit()
        self.password_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.chk_show_password = QtWidgets.QCheckBox("显示")
        self.archive_name_input = QtWidgets.QLineEdit()
        self.archive_name_input.setPlaceholderText("可选，例如 2025-08__素材.7z")
        self.chk_rr = QtWidgets.QCheckBox("生成 PAR2 冗余文件 (5%)")
        self.chk_rr.setChecked(True)

        self.seven_zip_edit = QtWidgets.QLineEdit()
        self.seven_zip_edit.setReadOnly(True)
        self.btn_browse_7z = QtWidgets.QPushButton("选择 7z.exe")

        layout.addWidget(QtWidgets.QLabel("密码"), 0, 0)
        layout.addWidget(self.password_input, 0, 1)
        layout.addWidget(self.chk_show_password, 0, 2)
        layout.addWidget(QtWidgets.QLabel("归档文件名"), 1, 0)
        layout.addWidget(self.archive_name_input, 1, 1, 1, 2)
        layout.addWidget(self.chk_rr, 2, 1)
        layout.addWidget(QtWidgets.QLabel("7z 路径"), 3, 0)
        layout.addWidget(self.seven_zip_edit, 3, 1)
        layout.addWidget(self.btn_browse_7z, 3, 2)

    def set_seven_zip_path(self, path: str):
        self.seven_zip_edit.setText(path or "未找到")


class ReadmeSection(QtWidgets.QGroupBox):
    def __init__(self):
        super().__init__("README")
        layout = QtWidgets.QVBoxLayout(self)
        self.readme_input = QtWidgets.QPlainTextEdit()
        self.readme_input.setPlaceholderText("可选：写入说明到目标目录的 README.txt")
        layout.addWidget(self.readme_input)


class ActionsSection(QtWidgets.QGroupBox):
    def __init__(self):
        super().__init__("操作")
        layout = QtWidgets.QHBoxLayout(self)
        self.btn_preview = QtWidgets.QPushButton("预览")
        self.btn_start = QtWidgets.QPushButton("开始执行")
        self.btn_view_log = QtWidgets.QPushButton("查看日志")
        self.btn_verify = QtWidgets.QPushButton("校验验证")
        layout.addWidget(self.btn_preview)
        layout.addWidget(self.btn_start)
        layout.addWidget(self.btn_view_log)
        layout.addWidget(self.btn_verify)
        layout.addStretch(1)


class ProgressSection(QtWidgets.QGroupBox):
    def __init__(self):
        super().__init__("进度")
        layout = QtWidgets.QVBoxLayout(self)
        self.progress_bar = QtWidgets.QProgressBar()
        self.status_label = QtWidgets.QLabel("空闲")
        self.eta_label = QtWidgets.QLabel("剩余时间: --")
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)
        layout.addWidget(self.eta_label)
