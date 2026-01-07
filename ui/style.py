"""UI styling helpers."""
from PySide6 import QtWidgets


def apply_app_style(widget: QtWidgets.QWidget):
    """Apply the app-wide stylesheet."""
    widget.setStyleSheet(
        """
        * {
            font-family: "Segoe UI Variable", "Segoe UI";
            font-size: 10.5pt;
        }
        QMainWindow {
            background: #f3f4f6;
        }
        QGroupBox {
            border: 1px solid #e5e7eb;
            border-radius: 10px;
            margin-top: 12px;
            padding: 10px;
            background: #ffffff;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 6px;
            color: #111827;
            font-weight: 600;
        }
        QLabel {
            color: #111827;
        }
        QLineEdit,
        QPlainTextEdit,
        QComboBox,
        QTableWidget {
            background: #f9fafb;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 6px;
            selection-background-color: #2563eb;
            selection-color: #ffffff;
        }
        QPlainTextEdit {
            padding: 8px;
        }
        QComboBox::drop-down {
            border-left: 1px solid #e5e7eb;
            width: 28px;
        }
        QComboBox QAbstractItemView {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            selection-background-color: #2563eb;
            selection-color: #ffffff;
        }
        QPushButton {
            background: #2563eb;
            color: #ffffff;
            border: none;
            border-radius: 8px;
            padding: 6px 14px;
        }
        QPushButton:hover {
            background: #1d4ed8;
        }
        QPushButton:pressed {
            background: #1e40af;
        }
        QPushButton:disabled {
            background: #94a3b8;
            color: #e2e8f0;
        }
        QRadioButton,
        QCheckBox {
            spacing: 6px;
        }
        QProgressBar {
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            background: #f9fafb;
            text-align: center;
            height: 16px;
        }
        QProgressBar::chunk {
            background: #10b981;
            border-radius: 8px;
        }
        QTableWidget {
            gridline-color: #e5e7eb;
        }
        QHeaderView::section {
            background: #f3f4f6;
            border: none;
            padding: 6px;
            font-weight: 600;
            color: #111827;
        }
        """.strip()
    )
