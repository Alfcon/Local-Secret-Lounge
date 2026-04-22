from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QLabel, QWidget
from PySide6.QtGui import QPixmap, QPainter, QPainterPath, QColor
from PySide6.QtCore import Qt, QSize


class AvatarLabel(QLabel):
    """Avatar label — square (rounded corners) for built-in/discover characters,
    circular for user-created characters."""

    def __init__(
        self,
        size: int = 48,
        parent: QWidget | None = None,
        shape: str = "circle",  # "circle" or "square"
    ) -> None:
        super().__init__(parent)
        self._avatar_size = size
        self._name = ""
        self._color = "#e94560"
        self._shape = shape  # "circle" | "square"
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_shape(self, shape: str) -> None:
        """Set shape: 'circle' or 'square'. Call before set_character."""
        self._shape = shape

    def set_character(self, name: str, avatar_path: str = "", color: str = "") -> None:
        self._name = name
        self._color = color or "#e94560"
        self._try_load_avatar(avatar_path)

    def _try_load_avatar(self, path: str) -> None:
        if path:
            p = Path(path)
            if p.exists() and p.is_file():
                pixmap = QPixmap(str(p))
                if not pixmap.isNull():
                    scaled = pixmap.scaled(
                        self._avatar_size,
                        self._avatar_size,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    result = QPixmap(self._avatar_size, self._avatar_size)
                    result.fill(Qt.GlobalColor.transparent)
                    painter = QPainter(result)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    path_obj = QPainterPath()

                    if self._shape == "square":
                        # Rounded rectangle — 10 % corner radius
                        radius = float(self._avatar_size) * 0.10
                        path_obj.addRoundedRect(
                            0.0, 0.0,
                            float(self._avatar_size), float(self._avatar_size),
                            radius, radius,
                        )
                    else:
                        path_obj.addEllipse(0, 0, self._avatar_size, self._avatar_size)

                    painter.setClipPath(path_obj)
                    x = (self._avatar_size - scaled.width()) // 2
                    y = (self._avatar_size - scaled.height()) // 2
                    painter.drawPixmap(x, y, scaled)
                    painter.end()
                    self.setPixmap(result)
                    self.setText("")
                    return

        # Fallback: colored shape with initial
        pixmap = QPixmap(self._avatar_size, self._avatar_size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(self._color))
        painter.setPen(Qt.PenStyle.NoPen)

        if self._shape == "square":
            radius = float(self._avatar_size) * 0.10
            painter.drawRoundedRect(
                0.0, 0.0,
                float(self._avatar_size), float(self._avatar_size),
                radius, radius,
            )
        else:
            painter.drawEllipse(0, 0, self._avatar_size, self._avatar_size)

        initial = (self._name[0].upper() if self._name else "?")
        font = painter.font()
        font.setPointSize(int(self._avatar_size * 0.35))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(
            0, 0, self._avatar_size, self._avatar_size,
            Qt.AlignmentFlag.AlignCenter,
            initial,
        )
        painter.end()
        self.setPixmap(pixmap)
        self.setText("")
