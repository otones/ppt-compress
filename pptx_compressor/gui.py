"""PySide6 GUI for pptx-compressor.

Implements US-1..US-4:
  - drag/drop or pick a .pptx, click 压缩, see "12.3 MB → 3.8 MB(节省 69%)"
  - 查看详情 dialog with per-pass breakdown
  - 设置 dialog with per-pass toggles + output naming strategy
"""

from __future__ import annotations

import os
import sys
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, QMimeData
from PySide6.QtGui import QFont, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QDialog, QCheckBox, QComboBox, QLineEdit,
    QFormLayout, QDialogButtonBox, QTextEdit, QGroupBox, QSizePolicy,
    QFrame, QMessageBox, QSpinBox,
)

from .config import Settings, PASS_DESCRIPTIONS
from .core.compressor import compress
from .core.report import CompressionReport


SETTINGS_PATH = os.path.join(
    os.path.expanduser("~"), ".pptx_compressor_settings.json"
)


def load_settings() -> Settings:
    try:
        import json
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return Settings.from_dict(json.load(f))
    except Exception:  # noqa: BLE001
        pass
    return Settings.default()


def save_settings(settings: Settings) -> None:
    try:
        import json
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings.to_dict(), f, ensure_ascii=False, indent=2)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------- worker
class CompressWorker(QThread):
    finished_report = Signal(object)  # CompressionReport
    failed = Signal(str)

    def __init__(self, file_path: str, settings: Settings):
        super().__init__()
        self.file_path = file_path
        self.settings = settings

    def run(self) -> None:
        try:
            report = compress(self.file_path, self.settings)
            self.finished_report.emit(report)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


# --------------------------------------------------------------------- dialogs
class SettingsDialog(QDialog):
    """Per-pass toggles + output naming strategy (US-3, US-4)."""

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(460)
        self.settings = settings

        layout = QVBoxLayout(self)

        # --- Pass toggles group ---
        pass_group = QGroupBox("压缩项(可单独开关)")
        pass_layout = QVBoxLayout(pass_group)
        self.pass_checks = {}
        for attr, label, desc in PASS_DESCRIPTIONS:
            cb = QCheckBox(f"{label}  —  {desc}")
            cb.setChecked(bool(getattr(settings, attr, True)))
            self.pass_checks[attr] = cb
            pass_layout.addWidget(cb)
        layout.addWidget(pass_group)

        # --- Image options ---
        img_group = QGroupBox("图片压缩参数")
        img_form = QFormLayout(img_group)
        self.max_dim_spin = QSpinBox()
        self.max_dim_spin.setRange(320, 8192)
        self.max_dim_spin.setSingleStep(160)
        self.max_dim_spin.setValue(settings.image.max_dimension)
        img_form.addRow("长边最大像素", self.max_dim_spin)

        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(10, 95)
        self.quality_spin.setSingleStep(5)
        self.quality_spin.setValue(settings.image.jpeg_quality)
        img_form.addRow("JPEG 质量", self.quality_spin)
        layout.addWidget(img_group)

        # --- Output naming ---
        name_group = QGroupBox("输出命名")
        name_form = QFormLayout(name_group)
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItem("添加后缀(name_compressed.pptx)", "suffix")
        self.strategy_combo.addItem("覆盖原文件(自动备份 .bak)", "overwrite")
        cur = settings.output_strategy
        for i in range(self.strategy_combo.count()):
            if self.strategy_combo.itemData(i) == cur:
                self.strategy_combo.setCurrentIndex(i)
                break
        name_form.addRow("策略", self.strategy_combo)

        self.suffix_edit = QLineEdit(settings.output_suffix)
        name_form.addRow("后缀", self.suffix_edit)
        layout.addWidget(name_group)

        # --- Buttons ---
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def build_settings(self) -> Settings:
        s = Settings.default()
        for attr, cb in self.pass_checks.items():
            setattr(s, attr, cb.isChecked())
        s.image.max_dimension = self.max_dim_spin.value()
        s.image.jpeg_quality = self.quality_spin.value()
        s.output_strategy = self.strategy_combo.currentData()
        s.output_suffix = self.suffix_edit.text().strip() or "_compressed"
        return s


class DetailDialog(QDialog):
    """Per-pass breakdown (US-2)."""

    def __init__(self, report: CompressionReport, parent=None):
        super().__init__(parent)
        self.setWindowTitle("压缩详情")
        self.resize(640, 520)

        layout = QVBoxLayout(self)
        summary = QLabel(
            f"<div style='font-size:16px;font-weight:600;'>"
            f"{report.summary_line()}</div>"
            f"<div style='color:#666;'>{report.input_path}</div>"
            f"<div style='color:#666;'>→ {report.output_path}</div>"
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        edit = QTextEdit()
        edit.setReadOnly(True)
        body = []
        for p in report.passes:
            if not p.ran:
                continue
            head = f"<b>{p.name}</b>  —  影响 {p.items_affected} 项"
            body.append(f"<p>{head}</p><ul>")
            for d in p.details:
                body.append(f"<li>{d}</li>")
            if not p.details:
                body.append("<li>无变化</li>")
            body.append("</ul>")
        edit.setHtml("".join(body))
        layout.addWidget(edit, 1)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


# --------------------------------------------------------------------- dropzone
class DropZone(QFrame):
    """Drag & drop area; also click to pick a file."""

    file_selected = Signal(str)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setMinimumHeight(160)
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(
            "DropZone { border:2px dashed #9aa; border-radius:12px; "
            "background:#fafbfc; }"
        )
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        hint = QLabel("拖拽 .pptx 到这里\n或点击选择文件")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color:#555; font-size:15px;")
        lay.addWidget(hint)

    def mousePressEvent(self, e):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 PowerPoint 文件", "", "PowerPoint (*.pptx)"
        )
        if path:
            self.file_selected.emit(path)

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            urls = e.mimeData().urls()
            if any(u.toLocalFile().lower().endswith(".pptx") for u in urls):
                e.acceptProposedEvent()

    def dropEvent(self, e: QDropEvent):
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if p.lower().endswith(".pptx"):
                self.file_selected.emit(p)
                break


# --------------------------------------------------------------------- main win
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PPTX 压缩器")
        self.resize(560, 460)
        self.settings = load_settings()
        self.worker: Optional[CompressWorker] = None
        self.last_report: Optional[CompressionReport] = None

        central = QWidget()
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(14)

        title = QLabel("PPTX 压缩器")
        title.setStyleSheet("font-size:22px; font-weight:600;")
        v.addWidget(title)

        self.drop_zone = DropZone()
        self.drop_zone.file_selected.connect(self.set_file)
        v.addWidget(self.drop_zone)

        self.file_label = QLabel("未选择文件")
        self.file_label.setStyleSheet("color:#444;")
        self.file_label.setWordWrap(True)
        v.addWidget(self.file_label)

        row = QHBoxLayout()
        self.compress_btn = QPushButton("压缩")
        self.compress_btn.setEnabled(False)
        self.compress_btn.setMinimumHeight(40)
        self.compress_btn.setStyleSheet(
            "QPushButton { background:#0a84ff; color:white; "
            "font-size:16px; border-radius:8px; }"
            "QPushButton:disabled { background:#b8c4d0; }"
        )
        self.compress_btn.clicked.connect(self.run_compress)
        row.addWidget(self.compress_btn, 1)

        self.settings_btn = QPushButton("设置")
        self.settings_btn.clicked.connect(self.open_settings)
        row.addWidget(self.settings_btn)
        v.addLayout(row)

        self.result_label = QLabel("")
        self.result_label.setStyleSheet("font-size:15px;")
        self.result_label.setWordWrap(True)
        v.addWidget(self.result_label)

        self.detail_btn = QPushButton("查看详情")
        self.detail_btn.setEnabled(False)
        self.detail_btn.clicked.connect(self.show_detail)
        v.addWidget(self.detail_btn)

        v.addStretch(1)

        self.reveal_btn = QPushButton("在 Finder 中显示")
        self.reveal_btn.setEnabled(False)
        self.reveal_btn.clicked.connect(self.reveal_output)
        v.addWidget(self.reveal_btn)

    # ------------------------------------------------------------- helpers
    def set_file(self, path: str) -> None:
        self.current_file = path
        self.file_label.setText(path)
        self.compress_btn.setEnabled(True)
        self.result_label.setText("")
        self.detail_btn.setEnabled(False)
        self.reveal_btn.setEnabled(False)

    def run_compress(self) -> None:
        if not getattr(self, "current_file", None):
            return
        self.compress_btn.setEnabled(False)
        self.settings_btn.setEnabled(False)
        self.result_label.setText("压缩中…")
        self.detail_btn.setEnabled(False)
        self.reveal_btn.setEnabled(False)
        self.worker = CompressWorker(self.current_file, self.settings)
        self.worker.finished_report.connect(self.on_done)
        self.worker.failed.connect(self.on_failed)
        self.worker.start()

    def on_done(self, report: CompressionReport) -> None:
        self.last_report = report
        self.result_label.setText(
            f"<b style='color:#0a84ff;'>{report.summary_line()}</b>"
        )
        self.compress_btn.setEnabled(True)
        self.settings_btn.setEnabled(True)
        self.detail_btn.setEnabled(True)
        self.reveal_btn.setEnabled(True)
        self.worker = None

    def on_failed(self, msg: str) -> None:
        self.result_label.setText(f"<span style='color:#d00;'>压缩失败:{msg}</span>")
        self.compress_btn.setEnabled(True)
        self.settings_btn.setEnabled(True)
        self.worker = None

    def show_detail(self) -> None:
        if self.last_report:
            DetailDialog(self.last_report, self).exec()

    def open_settings(self) -> None:
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec() == QDialog.Accepted:
            self.settings = dlg.build_settings()
            save_settings(self.settings)

    def reveal_output(self) -> None:
        if self.last_report and os.path.exists(self.last_report.output_path):
            import subprocess
            subprocess.Popen(
                ["open", "-R", self.last_report.output_path]
            )


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PPTX 压缩器")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
