from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QPushButton, QFrame, QLabel, QTextEdit, QScrollArea, QLineEdit,
    QComboBox, QProgressBar, QCheckBox, QGroupBox, QFormLayout,
    QSizePolicy, QSpacerItem, QMessageBox, QDialog, QDialogButtonBox,
    QPlainTextEdit, QMenu, QApplication, QSystemTrayIcon, QStatusBar,
    QToolBar, QAction, QInputDialog,
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QUrl, QMimeData
from PySide6.QtGui import QFont, QPixmap, QPainter, QTextCursor, QDesktopServices, QIcon, QKeySequence

from core.character_manager import CharacterManager
from core.chat_engine import ChatEngine
from core.chat_storage import ChatStorage
from core.claude_client import ClaudeClient
from core.hf_downloader import HFDownloader
from core.lm_studio_client import LMStudioClient
from core.memory_store import MemoryStore
from core.model_manager import ModelManager
from core.model_validator import ModelValidator
from core.paths import get_app_root
from core.prompt_assets import PromptAssetLoader
from core.scene_state import SceneStateMachine
from core.settings_manager import SettingsManager

from ui.theme import Theme
from ui.widgets.avatar_label import AvatarLabel
from ui.widgets.character_image import CharacterImage
from ui.widgets.system_info_widget import SystemInfoWidget
from ui.windows.developer_window import DeveloperWindow

logger = logging.getLogger(__name__)

TIMESTAMP_HEADER_RE = re.compile(r'(?m)^\[([0-9]{1,2}:[0-9]{2})\]\s*([^\n]+?)\s*$')

class ChatWindow(QMainWindow):
