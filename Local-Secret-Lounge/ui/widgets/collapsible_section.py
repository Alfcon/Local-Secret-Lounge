"""Collapsible section widget for settings pages."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFrame, QLabel
)


class CollapsibleSection(QWidget):
    """A collapsible section with a header button and content area."""
    
    toggled = Signal(bool)  # Emitted when section is expanded/collapsed
    
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = title
        self._is_expanded = True
        self._content_widget: QWidget | None = None
        
        self._build_ui()
    
    def _build_ui(self) -> None:
        """Build the collapsible section UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header with toggle button
        header = QFrame()
        header.setObjectName("collapsibleHeader")
        header.setFixedHeight(44)
        header.setStyleSheet("""
            QFrame#collapsibleHeader {
                background-color: #252d48;
                border-bottom: 1px solid #3a3f5a;
                border-radius: 0px;
            }
        """)
        
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(8)
        
        # Toggle button with arrow
        self.toggle_button = QPushButton()
        self.toggle_button.setObjectName("collapsibleToggle")
        self.toggle_button.setFixedSize(28, 28)
        self.toggle_button.setFlat(True)
        self.toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_button.clicked.connect(self.toggle)
        self.toggle_button.setStyleSheet("""
            QPushButton#collapsibleToggle {
                background-color: transparent;
                border: none;
                color: #7a8cd1;
                font-size: 14px;
                padding: 0px;
            }
            QPushButton#collapsibleToggle:hover {
                background-color: #3a3f5a;
                border-radius: 4px;
            }
        """)
        self._update_button_arrow()
        header_layout.addWidget(self.toggle_button)
        
        # Title label
        title_label = QLabel(self.title)
        title_label.setObjectName("collapsibleTitle")
        title_label.setStyleSheet("""
            QLabel#collapsibleTitle {
                color: #e8e8ff;
                font-weight: 500;
                font-size: 13px;
            }
        """)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        layout.addWidget(header)
        
        # Content container
        self.content_container = QFrame()
        self.content_container.setObjectName("collapsibleContent")
        self.content_container.setStyleSheet("""
            QFrame#collapsibleContent {
                background-color: #1a1a2e;
                border-bottom: 1px solid #3a3f5a;
            }
        """)
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(18, 18, 18, 18)
        self.content_layout.setSpacing(14)
        
        layout.addWidget(self.content_container)
        
        self.setLayout(layout)
    
    def _update_button_arrow(self) -> None:
        """Update the toggle button arrow based on expanded state."""
        arrow = "▼" if self._is_expanded else "▶"
        self.toggle_button.setText(arrow)
    
    def set_content_widget(self, widget: QWidget) -> None:
        """Set the content widget for this section."""
        if self._content_widget is not None:
            self.content_layout.removeWidget(self._content_widget)
        
        self._content_widget = widget
        self.content_layout.insertWidget(0, widget)
    
    def toggle(self) -> None:
        """Toggle the expanded/collapsed state."""
        self.set_expanded(not self._is_expanded)
    
    def set_expanded(self, expanded: bool) -> None:
        """Set the expanded state."""
        if self._is_expanded == expanded:
            return
        
        self._is_expanded = expanded
        self._update_button_arrow()
        
        if self._content_widget is not None:
            self._content_widget.setVisible(expanded)
        
        self.content_container.setVisible(expanded)
        self.toggled.emit(expanded)
    
    def is_expanded(self) -> bool:
        """Return whether this section is expanded."""
        return self._is_expanded
