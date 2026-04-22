from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from PySide6.QtWidgets import QApplication, QDialog

from core.character_manager import CharacterManager
from core.chat_storage import ChatStorage
from core.model_manager import ModelManager
from core.paths import ensure_app_directories, get_app_root
from core.settings_manager import SettingsManager
from ui.dialogs.initial_setup_dialog import InitialSetupDialog
from ui.main_window import MainWindow
from ui.theme import apply_theme


def configure_logging() -> None:
    log_file = get_app_root() / 'run_app.log'
    log_file.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    formatter = logging.Formatter('%(asctime)s %(levelname)s [%(name)s] %(message)s')
    file_handler = RotatingFileHandler(log_file, maxBytes=1_048_576, backupCount=3, encoding='utf-8')
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)


def main() -> int:
    ensure_app_directories()
    configure_logging()

    app = QApplication(sys.argv)
    app.setApplicationName("The_App")
    app.setOrganizationName("The_App Local")

    logging.getLogger(__name__).info('Starting The_App.')

    settings_manager = SettingsManager()
    model_manager = ModelManager(settings_manager)
    character_manager = CharacterManager()
    chat_storage = ChatStorage()

    try:
        _font_size = int(settings_manager.get("ui_font_size", 13) or 13)
    except (TypeError, ValueError):
        _font_size = 13
    apply_theme(app, font_size=_font_size)

    if settings_manager.needs_initial_setup():
        setup_dialog = InitialSetupDialog(settings_manager)
        if setup_dialog.exec() != QDialog.DialogCode.Accepted:
            logging.getLogger(__name__).info('Initial setup cancelled. Exiting application before main window opens.')
            return 0

    window = MainWindow(
        settings_manager=settings_manager,
        model_manager=model_manager,
        character_manager=character_manager,
        chat_storage=chat_storage,
    )
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
