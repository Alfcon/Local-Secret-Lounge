from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from core.hf_downloader import HFDownloader
from core.paths import get_models_dir


class DownloadWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, downloader: HFDownloader, repo_id: str, filename_or_pattern: str, destination: str, token: str | None) -> None:
        super().__init__()
        self.downloader = downloader
        self.repo_id = repo_id
        self.filename_or_pattern = filename_or_pattern
        self.destination = destination
        self.token = token

    @Slot()
    def run(self) -> None:
        try:
            if '*' in self.filename_or_pattern or '?' in self.filename_or_pattern:
                local_path = self.downloader.download_matching_file(
                    repo_id=self.repo_id,
                    pattern=self.filename_or_pattern,
                    local_dir=self.destination,
                    token=self.token,
                    progress_callback=self._emit_progress,
                )
            else:
                local_path = self.downloader.download_single_file(
                    repo_id=self.repo_id,
                    filename=self.filename_or_pattern,
                    local_dir=self.destination,
                    token=self.token,
                    progress_callback=self._emit_progress,
                )
        except Exception as exc:
            self.error.emit(str(exc))
            return
        self.finished.emit(local_path)

    def _emit_progress(self, downloaded: int, total: int, status: str) -> None:
        self.progress.emit(downloaded, total, status)


class DownloadModelDialog(QDialog):
    """Dialog for downloading a GGUF model from Hugging Face."""

    def __init__(self, settings_manager, model_manager, parent=None) -> None:
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.model_manager = model_manager
        self.downloader = HFDownloader(settings_manager)
        self.downloaded_model: dict | None = None
        self.worker_thread: QThread | None = None
        self.worker: DownloadWorker | None = None

        self.setWindowTitle('Download Model from Hugging Face')
        self.setModal(True)
        self.resize(760, 360)

        self.repo_id_edit = QLineEdit()
        self.filename_edit = QLineEdit()
        self.display_name_edit = QLineEdit()
        self.destination_edit = QLineEdit(str(get_models_dir()))
        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.Password)
        self.default_checkbox = QCheckBox('Set as default model after download')
        self.managed_checkbox = QCheckBox('Store inside Local Secret Lounge managed models folder')
        self.managed_checkbox.setChecked(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_label = QLabel('Idle.')
        self.progress_label.setWordWrap(True)

        self.download_button: QPushButton | None = None
        self.cancel_button: QPushButton | None = None
        self.open_button: QPushButton | None = None
        self.browse_button: QPushButton | None = None

        self.build_ui()
        self.managed_checkbox.toggled.connect(self._on_managed_toggled)
        self._on_managed_toggled(True)

    def build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.addRow('Repo ID:', self.repo_id_edit)
        form.addRow('Filename or pattern:', self.filename_edit)
        form.addRow('Display name:', self.display_name_edit)

        destination_row = QHBoxLayout()
        destination_row.addWidget(self.destination_edit, stretch=1)
        self.browse_button = QPushButton('Browse')
        self.browse_button.clicked.connect(self.browse_destination)
        destination_row.addWidget(self.browse_button)
        form.addRow('Destination:', destination_row)
        form.addRow('Access token:', self.token_edit)

        layout.addLayout(form)
        layout.addWidget(self.managed_checkbox)
        layout.addWidget(self.default_checkbox)

        layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_label)

        button_row = QHBoxLayout()
        self.open_button = QPushButton('Open Hugging Face')
        self.open_button.clicked.connect(self.open_huggingface_site)
        button_row.addWidget(self.open_button)
        button_row.addStretch(1)

        self.cancel_button = QPushButton('Cancel')
        self.cancel_button.clicked.connect(self.reject)
        self.download_button = QPushButton('Download')
        self.download_button.clicked.connect(self.start_download)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.download_button)
        layout.addLayout(button_row)

    def _on_managed_toggled(self, checked: bool) -> None:
        if checked:
            self.destination_edit.setText(str(get_models_dir()))
        self.destination_edit.setEnabled(not checked)
        if self.browse_button is not None:
            self.browse_button.setEnabled(not checked)

    def browse_destination(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            'Choose destination folder',
            self.destination_edit.text().strip() or str(get_models_dir()),
        )
        if directory:
            self.destination_edit.setText(directory)

    def open_huggingface_site(self) -> None:
        self.downloader.open_repo_in_browser(self.repo_id_edit.text().strip() or None)

    def validate_inputs(self) -> tuple[str, str, str, str | None]:
        repo_id = self.repo_id_edit.text().strip()
        filename_or_pattern = self.filename_edit.text().strip()
        destination = self.destination_edit.text().strip() or str(get_models_dir())
        token = self.token_edit.text().strip() or None
        if not repo_id:
            raise ValueError('Enter a Hugging Face repo id.')
        if not filename_or_pattern:
            raise ValueError('Enter a .gguf filename or wildcard pattern.')
        Path(destination).mkdir(parents=True, exist_ok=True)
        return repo_id, filename_or_pattern, destination, token

    def start_download(self) -> None:
        if self.worker_thread is not None:
            return
        try:
            repo_id, filename_or_pattern, destination, token = self.validate_inputs()
        except Exception as exc:
            QMessageBox.warning(self, 'Download setup error', str(exc))
            return

        self._set_downloading_state(True)
        self.progress_bar.setRange(0, 0)
        self.progress_label.setText('Starting download...')

        self.worker_thread = QThread(self)
        self.worker = DownloadWorker(self.downloader, repo_id, filename_or_pattern, destination, token)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_download_finished)
        self.worker.error.connect(self._on_download_failed)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.error.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self._cleanup_worker)
        self.worker_thread.start()

    def _set_downloading_state(self, downloading: bool) -> None:
        for widget in [
            self.repo_id_edit,
            self.filename_edit,
            self.display_name_edit,
            self.destination_edit,
            self.token_edit,
            self.default_checkbox,
            self.managed_checkbox,
            self.download_button,
            self.open_button,
            self.browse_button,
        ]:
            if widget is not None:
                widget.setEnabled(not downloading)
        if self.cancel_button is not None:
            self.cancel_button.setEnabled(not downloading)

    def _on_progress(self, downloaded: int, total: int, status: str) -> None:
        if total > 0:
            self.progress_bar.setRange(0, 100)
            percent = int((downloaded / total) * 100)
            self.progress_bar.setValue(max(0, min(100, percent)))
            self.progress_label.setText(f'{status} {percent}% ({self._format_size(downloaded)} / {self._format_size(total)})')
        else:
            self.progress_bar.setRange(0, 0)
            self.progress_label.setText(status)

    def _on_download_finished(self, local_path: str) -> None:
        try:
            display_name = self.display_name_edit.text().strip() or Path(local_path).stem.replace('_', ' ').replace('-', ' ').title()
            self.downloaded_model = self.model_manager.register_downloaded_model(
                file_path=local_path,
                display_name=display_name,
                repo_id=self.repo_id_edit.text().strip(),
                filename=Path(local_path).name,
                set_default=self.default_checkbox.isChecked(),
            )
        except Exception as exc:
            self._on_download_failed(str(exc))
            return
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_label.setText('Download complete and model registered.')
        self.accept()

    def _on_download_failed(self, error_message: str) -> None:
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_label.setText('Download failed.')
        self._set_downloading_state(False)
        QMessageBox.critical(self, 'Download failed', error_message)

    def _cleanup_worker(self) -> None:
        self._set_downloading_state(False)
        if self.worker is not None:
            self.worker.deleteLater()
        if self.worker_thread is not None:
            self.worker_thread.deleteLater()
        self.worker = None
        self.worker_thread = None

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        size = float(size_bytes or 0)
        for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
            if size < 1024 or unit == 'TB':
                return f'{size:.1f} {unit}' if unit != 'B' else f'{int(size)} B'
            size /= 1024
        return '0 B'
