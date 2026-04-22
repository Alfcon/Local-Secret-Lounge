from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class ImportModelDialog(QDialog):
    """Dialog for importing a local GGUF model into the registry."""

    def __init__(self, model_manager, parent=None) -> None:
        super().__init__(parent)
        self.model_manager = model_manager
        self.imported_model: dict | None = None

        self.setWindowTitle("Import Local Model")
        self.setModal(True)
        self.resize(680, 250)

        self.path_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.chat_format_edit = QLineEdit()
        self.copy_checkbox = QCheckBox("Copy model into Local Secret Lounge's managed models folder")
        self.copy_checkbox.setChecked(True)
        self.default_checkbox = QCheckBox("Set as default model after import")

        self.build_ui()

    def build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit, stretch=1)
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.browse_file)
        path_row.addWidget(browse_button)

        form.addRow("Model file:", path_row)
        form.addRow("Display name:", self.name_edit)
        form.addRow("Chat format:", self.chat_format_edit)
        layout.addLayout(form)
        layout.addWidget(self.copy_checkbox)
        layout.addWidget(self.default_checkbox)

        help_text = QLineEdit()
        help_text.setReadOnly(True)
        help_text.setText("Only GGUF models are supported. Duplicate models are blocked automatically.")
        layout.addWidget(help_text)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        import_button = QPushButton("Import")
        import_button.clicked.connect(self.accept_import)
        button_row.addWidget(cancel_button)
        button_row.addWidget(import_button)
        layout.addLayout(button_row)

    def browse_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select GGUF model",
            str(Path.home()),
            "GGUF Models (*.gguf)",
        )
        if not file_path:
            return
        self.path_edit.setText(file_path)
        source = Path(file_path)
        if not self.name_edit.text().strip():
            name = source.stem.replace('_', ' ').replace('-', ' ').title()
            self.name_edit.setText(name)

    def validate_inputs(self) -> tuple[str, str]:
        file_path = self.path_edit.text().strip()
        display_name = self.name_edit.text().strip()
        if not file_path:
            raise ValueError("Select a .gguf file to import.")
        path = Path(file_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")
        if path.suffix.lower() != '.gguf':
            raise ValueError("Only .gguf files are supported in version 1.")
        if not display_name:
            raise ValueError("Enter a display name for the model.")
        return str(path), display_name

    def accept_import(self) -> None:
        try:
            file_path, display_name = self.validate_inputs()
            self.imported_model = self.model_manager.import_local_model(
                source_path=file_path,
                display_name=display_name,
                copy_to_managed_storage=self.copy_checkbox.isChecked(),
                chat_format=self.chat_format_edit.text().strip() or None,
                set_default=self.default_checkbox.isChecked(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
            return
        self.accept()
