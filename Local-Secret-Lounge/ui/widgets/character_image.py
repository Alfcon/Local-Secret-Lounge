from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPainterPath, QPixmap, QColor
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget


class CharacterImage(QLabel):
    """Scalable character image with a rounded-rectangle frame.

    The widget shows the entire character image (no cropping) and rescales
    to fit the available space while preserving the image's aspect ratio.
    It is used for every character portrait in the app — Discover cards,
    My-Characters detail pane, and the chat window image pane — so image
    presentation stays uniform across the UI.
    """

    _CORNER_RADIUS_RATIO = 0.06  # radius relative to the shorter side

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        minimum_size: tuple[int, int] = (128, 128),
    ) -> None:
        super().__init__(parent)
        self._pixmap_original = QPixmap()
        self._fallback_text = ""
        self._fallback_color = "#e94560"
        self._fallback_initial = "?"

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setMinimumSize(*minimum_size)
        # Expanding in both directions so the image grows with the card.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Let the layout control our size — the image aspect ratio must not
        # drive the widget's width, otherwise cards with landscape pictures
        # become wider than cards with portrait ones.
        self.setScaledContents(False)
        self.setStyleSheet(
            "border: 1px solid #3a4163; border-radius: 12px; "
            "color: #b8b0d7; background-color: #171a26; padding: 4px;"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_character(
        self,
        name: str,
        avatar_path: str = "",
        color: str = "",
    ) -> None:
        """Set the character to display. If the avatar file is missing or
        invalid, a coloured tile with the first initial is shown instead.
        """
        self._fallback_initial = (name[:1].upper() if name else "?")
        self._fallback_color = color or "#e94560"
        self._fallback_text = name or ""

        if avatar_path:
            p = Path(avatar_path).expanduser()
            if p.exists() and p.is_file():
                pm = QPixmap(str(p))
                if not pm.isNull():
                    self._pixmap_original = pm
                    self._apply_pixmap()
                    return

        # Fallback: clear pixmap cache; _apply_pixmap will paint the initial.
        self._pixmap_original = QPixmap()
        self._apply_pixmap()

    def clear_character(self) -> None:
        self._pixmap_original = QPixmap()
        self._fallback_text = ""
        self._fallback_initial = "?"
        self.setPixmap(QPixmap())
        self.setText("")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def hasHeightForWidth(self) -> bool:  # noqa: N802 (Qt naming)
        # Tell the layout we don't want aspect-ratio-driven widths — we
        # simply fill whatever rectangle the layout gives us.
        return False

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self._apply_pixmap()

    def _apply_pixmap(self) -> None:
        rect = self.contentsRect()
        w = rect.width()
        h = rect.height()
        if w <= 8 or h <= 8:
            return

        # Paint on a canvas that matches the widget's available area so the
        # image can fill the full card — no forced square, no cropping.
        canvas = QPixmap(w, h)
        canvas.fill(Qt.GlobalColor.transparent)

        painter = QPainter(canvas)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

            radius = float(min(w, h)) * self._CORNER_RADIUS_RATIO
            clip = QPainterPath()
            clip.addRoundedRect(0.0, 0.0, float(w), float(h), radius, radius)
            painter.setClipPath(clip)

            if not self._pixmap_original.isNull():
                # KeepAspectRatio (not ByExpanding) so the entire image is
                # visible — no top/bottom crop on portraits, no side crop
                # on landscape photos.
                scaled = self._pixmap_original.scaled(
                    w,
                    h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                # Fill the area behind the image so letterboxed edges match
                # the widget background instead of showing transparency.
                painter.fillRect(0, 0, w, h, QColor("#171a26"))
                x = (w - scaled.width()) // 2
                y = (h - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)
            else:
                # Coloured tile + initial
                painter.setBrush(QColor(self._fallback_color))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(0.0, 0.0, float(w), float(h), radius, radius)
                font = painter.font()
                font.setPointSize(max(12, int(min(w, h) * 0.35)))
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QColor("#ffffff"))
                painter.drawText(
                    0, 0, w, h,
                    Qt.AlignmentFlag.AlignCenter,
                    self._fallback_initial,
                )
        finally:
            painter.end()

        self.setPixmap(canvas)
        self.setText("")
