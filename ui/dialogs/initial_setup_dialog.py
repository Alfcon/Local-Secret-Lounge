from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QFrame, QWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from core.settings_manager import SettingsManager


class InitialSetupDialog(QDialog):
    """First-run setup dialog: collect user name and sex."""

    def __init__(self, settings_manager: SettingsManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.setWindowTitle("Welcome to The App — Setup")
        self.setMinimumWidth(480)
        self.setModal(True)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(40, 40, 40, 40)

        # Header
        header = QLabel("Welcome!")
        font = QFont()
        font.setPointSize(22)
        font.setBold(True)
        header.setFont(font)
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        subtitle = QLabel(
            "Before we begin, tell the characters a little about yourself.\n"
            "This helps them respond naturally."
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #9a9ab0; font-size: 13px;")
        layout.addWidget(subtitle)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        # Name field
        name_label = QLabel("Your name (what characters will call you):")
        name_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(name_label)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Alex")
        self.name_input.setFixedHeight(38)
        stored_name = self.settings_manager.get_user_name()
        if stored_name:
            self.name_input.setText(stored_name)
        layout.addWidget(self.name_input)

        # Sex field
        sex_label = QLabel("Your sex (used for character context):")
        sex_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(sex_label)

        self.sex_combo = QComboBox()
        self.sex_combo.addItems(["Male", "Female", "Other"])
        self.sex_combo.setFixedHeight(38)
        stored_sex = self.settings_manager.get_user_sex()
        if stored_sex:
            idx = self.sex_combo.findText(stored_sex, Qt.MatchFlag.MatchFixedString)
            if idx >= 0:
                self.sex_combo.setCurrentIndex(idx)
        layout.addWidget(self.sex_combo)

        layout.addSpacing(10)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        cancel_btn = QPushButton("Exit")
        cancel_btn.setObjectName("secondary_btn")
        cancel_btn.setFixedHeight(38)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self.start_btn = QPushButton("Start Chatting →")
        self.start_btn.setFixedHeight(38)
        self.start_btn.setDefault(True)
        self.start_btn.clicked.connect(self._on_start)
        btn_row.addWidget(self.start_btn)

        layout.addLayout(btn_row)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #e94560; font-size: 12px;")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.error_label)

        self.name_input.returnPressed.connect(self._on_start)

    def _on_start(self) -> None:
        name = self.name_input.text().strip()
        sex = self.sex_combo.currentText().strip()

        if not name:
            self.error_label.setText("Please enter your name.")
            self.name_input.setFocus()
            return

        self.settings_manager.update({
            "user_name": name,
            "user_sex": sex,
            "initial_setup_complete": True,
        })
        self.accept()
