"""Small, reusable progress dialog for long local video tasks."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QPlainTextEdit, QProgressBar, QVBoxLayout


class TaskProgressDialog(QDialog):
    """Non-cancellable dialog that shows the latest pipeline stages and log."""

    def __init__(self, title: str, initial_message: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumSize(620, 280)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        layout = QVBoxLayout(self)
        self.message_label = QLabel(initial_message)
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        layout.addWidget(self.progress_bar)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        layout.addWidget(self.log, 1)

    def append_progress(self, message: str) -> None:
        clean = str(message).strip()
        if not clean:
            return
        self.message_label.setText(clean)
        self.log.appendPlainText(clean)
