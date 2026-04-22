from __future__ import annotations

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt


DARK_BG = "#1a1a2e"
DARK_SURFACE = "#16213e"
DARK_PANEL = "#0f3460"
ACCENT = "#e94560"
ACCENT_HOVER = "#ff5a75"
ACCENT_PRESSED = "#c73652"

# ── Brighter, more visible text palette ──────────────────────────────────
TEXT_PRIMARY = "#ffffff"       # was #eaeaea — pure white for max visibility
TEXT_SECONDARY = "#c8c8e0"     # was #9a9ab0 — noticeably brighter
TEXT_MUTED = "#a8a8c8"         # for caption-level text
TEXT_HIGHLIGHT = "#ffe98a"     # bright yellow for description emphasis

BORDER = "#3a3a5a"             # slightly lighter so borders are visible
BORDER_LIGHT = "#5a5a7a"       # bevel highlights (top / left edges)
BORDER_DARK = "#0a0a1a"        # bevel shadows (bottom / right edges)
INPUT_BG = "#12122a"
CHAT_USER_BG = "#1e3a5f"
CHAT_CHAR_BG = "#1a1a3a"

# Beveled button gradients
BTN_GRAD_TOP = "#ff5a75"
BTN_GRAD_BOT = "#c73652"
BTN_GRAD_TOP_HOVER = "#ff7088"
BTN_GRAD_BOT_HOVER = "#d74662"

SECONDARY_GRAD_TOP = "#1a4a7a"
SECONDARY_GRAD_BOT = "#0a2a4a"
SECONDARY_GRAD_TOP_HOVER = "#2560a0"
SECONDARY_GRAD_BOT_HOVER = "#0f3460"

DANGER_GRAD_TOP = "#c02020"
DANGER_GRAD_BOT = "#6a0000"
DANGER_GRAD_TOP_HOVER = "#d03030"
DANGER_GRAD_BOT_HOVER = "#800000"


DEFAULT_FONT_SIZE = 13


def build_stylesheet(font_size: int = DEFAULT_FONT_SIZE) -> str:
    """Return the full application stylesheet with the requested base font size.

    Only the ``QMainWindow / QWidget`` base font-size is driven by the parameter;
    all widget-specific font sizes are expressed as offsets (px) from the
    13 px baseline so the relative scale (headings larger, captions smaller)
    is preserved when the user changes the global size.
    """
    try:
        base = int(font_size)
    except (TypeError, ValueError):
        base = DEFAULT_FONT_SIZE
    if base < 9:
        base = 9
    elif base > 28:
        base = 28

    delta = base - DEFAULT_FONT_SIZE

    def sz(px: int) -> int:
        scaled = px + delta
        return scaled if scaled >= 8 else 8

    return STYLESHEET_TEMPLATE.format(
        DARK_BG=DARK_BG,
        DARK_SURFACE=DARK_SURFACE,
        DARK_PANEL=DARK_PANEL,
        ACCENT=ACCENT,
        TEXT_PRIMARY=TEXT_PRIMARY,
        TEXT_SECONDARY=TEXT_SECONDARY,
        TEXT_MUTED=TEXT_MUTED,
        BORDER=BORDER,
        BORDER_LIGHT=BORDER_LIGHT,
        BORDER_DARK=BORDER_DARK,
        INPUT_BG=INPUT_BG,
        BTN_GRAD_TOP=BTN_GRAD_TOP,
        BTN_GRAD_BOT=BTN_GRAD_BOT,
        BTN_GRAD_TOP_HOVER=BTN_GRAD_TOP_HOVER,
        BTN_GRAD_BOT_HOVER=BTN_GRAD_BOT_HOVER,
        SECONDARY_GRAD_TOP=SECONDARY_GRAD_TOP,
        SECONDARY_GRAD_BOT=SECONDARY_GRAD_BOT,
        SECONDARY_GRAD_TOP_HOVER=SECONDARY_GRAD_TOP_HOVER,
        SECONDARY_GRAD_BOT_HOVER=SECONDARY_GRAD_BOT_HOVER,
        DANGER_GRAD_TOP=DANGER_GRAD_TOP,
        DANGER_GRAD_BOT=DANGER_GRAD_BOT,
        DANGER_GRAD_TOP_HOVER=DANGER_GRAD_TOP_HOVER,
        DANGER_GRAD_BOT_HOVER=DANGER_GRAD_BOT_HOVER,
        FS_BASE=base,
        FS_NAV=sz(13),
        FS_HEADING=sz(18),
        FS_SUBHEADING=sz(14),
        FS_SECTION=sz(11),
        FS_GROUP=sz(12),
    )


STYLESHEET_TEMPLATE = """
QMainWindow, QWidget {{
    background-color: {DARK_BG};
    color: {TEXT_PRIMARY};
    font-family: "Segoe UI", "Ubuntu", "Helvetica Neue", sans-serif;
    font-size: {FS_BASE}px;
}}

QStackedWidget {{
    background-color: {DARK_BG};
}}

/* Sidebar */
QFrame#sidebar {{
    background-color: {DARK_SURFACE};
    border-right: 1px solid {BORDER};
}}

/* Standard buttons — beveled with indent on press */
QPushButton {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {BTN_GRAD_TOP},
        stop:1 {BTN_GRAD_BOT}
    );
    color: white;
    border-top: 1px solid #ff8aa0;
    border-left: 1px solid #ff8aa0;
    border-right: 1px solid #8a1a2a;
    border-bottom: 2px solid #8a1a2a;
    border-radius: 6px;
    padding: 7px 18px 9px 18px;
    font-size: {FS_NAV}px;
    font-weight: bold;
}}
QPushButton:hover {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {BTN_GRAD_TOP_HOVER},
        stop:1 {BTN_GRAD_BOT_HOVER}
    );
    border-top: 1px solid #ffa0b5;
    border-left: 1px solid #ffa0b5;
}}
QPushButton:pressed {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {BTN_GRAD_BOT},
        stop:1 {BTN_GRAD_TOP}
    );
    border-top: 2px solid #8a1a2a;
    border-left: 2px solid #8a1a2a;
    border-right: 1px solid #ff8aa0;
    border-bottom: 1px solid #ff8aa0;
    padding: 9px 17px 7px 19px;
    color: #ffe0e8;
}}
QPushButton:disabled {{
    background-color: #3a3a5a;
    color: {TEXT_MUTED};
    border-top: 1px solid #4a4a6a;
    border-left: 1px solid #4a4a6a;
    border-right: 1px solid #1a1a2a;
    border-bottom: 2px solid #1a1a2a;
}}

/* Nav buttons — transparent sidebar nav, overrides generic QPushButton */
QPushButton#nav_btn {{
    background-color: transparent;
    color: {TEXT_SECONDARY};
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 10px 16px;
    text-align: left;
    font-size: {FS_NAV}px;
    font-weight: normal;
}}
QPushButton#nav_btn:hover {{
    background-color: {DARK_PANEL};
    color: {TEXT_PRIMARY};
    border-top: 1px solid {BORDER_LIGHT};
    border-left: 1px solid {BORDER_LIGHT};
    border-right: 1px solid {BORDER_DARK};
    border-bottom: 1px solid {BORDER_DARK};
}}
QPushButton#nav_btn:pressed {{
    background-color: #0a2550;
    color: {TEXT_PRIMARY};
    border-top: 1px solid {BORDER_DARK};
    border-left: 1px solid {BORDER_DARK};
    border-right: 1px solid {BORDER_LIGHT};
    border-bottom: 1px solid {BORDER_LIGHT};
    padding-top: 12px;
    padding-left: 18px;
    padding-bottom: 8px;
    padding-right: 14px;
}}
QPushButton#nav_btn:checked {{
    background-color: {ACCENT};
    color: white;
    font-weight: bold;
    border-top: 1px solid #ff8aa0;
    border-left: 1px solid #ff8aa0;
    border-right: 1px solid #8a1a2a;
    border-bottom: 1px solid #8a1a2a;
}}

/* Secondary buttons — blue bevel */
QPushButton#secondary_btn {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {SECONDARY_GRAD_TOP},
        stop:1 {SECONDARY_GRAD_BOT}
    );
    color: {TEXT_PRIMARY};
    border-top: 1px solid #3a7ac0;
    border-left: 1px solid #3a7ac0;
    border-right: 1px solid #061530;
    border-bottom: 2px solid #061530;
}}
QPushButton#secondary_btn:hover {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {SECONDARY_GRAD_TOP_HOVER},
        stop:1 {SECONDARY_GRAD_BOT_HOVER}
    );
    border-top: 1px solid #5090d0;
    border-left: 1px solid #5090d0;
}}
QPushButton#secondary_btn:pressed {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {SECONDARY_GRAD_BOT},
        stop:1 {SECONDARY_GRAD_TOP}
    );
    border-top: 2px solid #061530;
    border-left: 2px solid #061530;
    border-right: 1px solid #3a7ac0;
    border-bottom: 1px solid #3a7ac0;
    padding: 9px 17px 7px 19px;
    color: #d0e0f8;
}}

/* Danger buttons — red bevel */
QPushButton#danger_btn {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {DANGER_GRAD_TOP},
        stop:1 {DANGER_GRAD_BOT}
    );
    color: white;
    border-top: 1px solid #e05050;
    border-left: 1px solid #e05050;
    border-right: 1px solid #300000;
    border-bottom: 2px solid #300000;
}}
QPushButton#danger_btn:hover {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {DANGER_GRAD_TOP_HOVER},
        stop:1 {DANGER_GRAD_BOT_HOVER}
    );
    border-top: 1px solid #f07070;
    border-left: 1px solid #f07070;
}}
QPushButton#danger_btn:pressed {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {DANGER_GRAD_BOT},
        stop:1 {DANGER_GRAD_TOP}
    );
    border-top: 2px solid #300000;
    border-left: 2px solid #300000;
    border-right: 1px solid #e05050;
    border-bottom: 1px solid #e05050;
    padding: 9px 17px 7px 19px;
    color: #ffd0d0;
}}

/* Inputs */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {INPUT_BG};
    color: {TEXT_PRIMARY};
    border-top: 1px solid {BORDER_DARK};
    border-left: 1px solid {BORDER_DARK};
    border-right: 1px solid {BORDER_LIGHT};
    border-bottom: 1px solid {BORDER_LIGHT};
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: {DARK_PANEL};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {ACCENT};
}}

/* ComboBox */
QComboBox {{
    background-color: {INPUT_BG};
    color: {TEXT_PRIMARY};
    border-top: 1px solid {BORDER_DARK};
    border-left: 1px solid {BORDER_DARK};
    border-right: 1px solid {BORDER_LIGHT};
    border-bottom: 1px solid {BORDER_LIGHT};
    border-radius: 6px;
    padding: 6px 10px;
}}
QComboBox:hover {{
    border: 1px solid {ACCENT};
}}
QComboBox QAbstractItemView {{
    background-color: {DARK_SURFACE};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    selection-background-color: {DARK_PANEL};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

/* SpinBox */
QSpinBox {{
    background-color: {INPUT_BG};
    color: {TEXT_PRIMARY};
    border-top: 1px solid {BORDER_DARK};
    border-left: 1px solid {BORDER_DARK};
    border-right: 1px solid {BORDER_LIGHT};
    border-bottom: 1px solid {BORDER_LIGHT};
    border-radius: 6px;
    padding: 5px 8px;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background-color: {DARK_PANEL};
    border: none;
    width: 16px;
}}

/* Labels */
QLabel {{
    color: {TEXT_PRIMARY};
}}
QLabel#heading {{
    font-size: {FS_HEADING}px;
    font-weight: bold;
    color: {TEXT_PRIMARY};
}}
QLabel#subheading {{
    font-size: {FS_SUBHEADING}px;
    font-weight: bold;
    color: {TEXT_SECONDARY};
}}
QLabel#section_label {{
    font-size: {FS_SECTION}px;
    font-weight: bold;
    color: {TEXT_SECONDARY};
    text-transform: uppercase;
    letter-spacing: 1px;
}}

/* ScrollBars */
QScrollBar:vertical {{
    background: {DARK_SURFACE};
    width: 10px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical {{
    background: {DARK_PANEL};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {ACCENT};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: {DARK_SURFACE};
    height: 10px;
    border-radius: 5px;
}}
QScrollBar::handle:horizontal {{
    background: {DARK_PANEL};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {ACCENT};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* ListWidget */
QListWidget {{
    background-color: {DARK_SURFACE};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    outline: none;
}}
QListWidget::item {{
    padding: 8px 10px;
    border-radius: 4px;
    color: {TEXT_PRIMARY};
}}
QListWidget::item:selected {{
    background-color: {DARK_PANEL};
    color: {TEXT_PRIMARY};
}}
QListWidget::item:hover {{
    background-color: #1e1e40;
}}

/* GroupBox */
QGroupBox {{
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 6px;
    font-size: {FS_GROUP}px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {TEXT_SECONDARY};
}}

/* Tabs */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    background-color: {DARK_BG};
    border-radius: 0 6px 6px 6px;
}}
QTabBar::tab {{
    background-color: {DARK_SURFACE};
    color: {TEXT_SECONDARY};
    padding: 8px 16px;
    border: 1px solid {BORDER};
    border-bottom: none;
    border-radius: 6px 6px 0 0;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background-color: {DARK_BG};
    color: {TEXT_PRIMARY};
    border-bottom: 1px solid {DARK_BG};
}}
QTabBar::tab:hover {{
    color: {TEXT_PRIMARY};
}}

/* Splitter */
QSplitter::handle {{
    background-color: {BORDER};
}}
QSplitter::handle:horizontal {{
    width: 2px;
}}
QSplitter::handle:vertical {{
    height: 2px;
}}

/* CheckBox */
QCheckBox {{
    color: {TEXT_PRIMARY};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {BORDER_LIGHT};
    background-color: {INPUT_BG};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

/* Dialog */
QDialog {{
    background-color: {DARK_BG};
    color: {TEXT_PRIMARY};
}}

/* Slider */
QSlider::groove:horizontal {{
    height: 4px;
    background: {DARK_PANEL};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT};
    border: none;
    width: 14px;
    height: 14px;
    border-radius: 7px;
    margin: -5px 0;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}

/* Progress */
QProgressBar {{
    background-color: {DARK_PANEL};
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 4px;
}}

/* Separator */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {BORDER};
}}

/* Tooltip */
QToolTip {{
    background-color: {DARK_SURFACE};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    padding: 4px 8px;
    border-radius: 4px;
}}

/* MessageBox */
QMessageBox {{
    background-color: {DARK_BG};
    color: {TEXT_PRIMARY};
}}
QMessageBox QLabel {{
    color: {TEXT_PRIMARY};
}}
"""


def apply_theme(app: QApplication, font_size: int | None = None) -> None:
    """Install the dark stylesheet and colour palette.

    ``font_size`` sets the application-wide base font size (px). If omitted,
    the stylesheet ``DEFAULT_FONT_SIZE`` (13) is used. Callers can re-invoke
    this function after the user changes the setting — Qt will re-polish
    every widget automatically.
    """
    from PySide6.QtGui import QFont

    try:
        base = int(font_size) if font_size is not None else DEFAULT_FONT_SIZE
    except (TypeError, ValueError):
        base = DEFAULT_FONT_SIZE

    app.setStyleSheet(build_stylesheet(base))

    # Also set the application default font so widgets that don't inherit
    # a font-size from the stylesheet (e.g. dynamically-created tooltips,
    # QMessageBox native labels) still scale with the user's preference.
    app_font = QFont(app.font())
    app_font.setPointSize(max(7, base - 3))  # pt ≈ px * 0.75, rounded down
    app.setFont(app_font)

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(DARK_BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Base, QColor(INPUT_BG))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(DARK_SURFACE))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(DARK_SURFACE))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Button, QColor(DARK_PANEL))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Link, QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(DARK_PANEL))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)
