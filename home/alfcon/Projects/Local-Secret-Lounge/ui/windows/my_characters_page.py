    def __init__(self, character, character_manager, parent=None):
        super().__init__(parent)
        self.character = character
        self.character_manager = character_manager
        # ... existing code ...
        self._build_ui()

    def _desc_label(self, text):
        label = QLabel(text)
        label.setWordWrap(True)
        return label

    def _build_relationship_tab(self):
        form = QFormLayout()
        self.status_label_edit = QLineEdit()
        form.addRow("Status Label:", self.status_label_edit)
        label = QLabel("")
        description_label = self._desc_label("Short label describing the relationship status with the user (e.g. 'friend').")
        form.addRow(label, description_label)
        # ... other code ...
        tabWidget.addTab(form, "Relationship")
        return tabWidget

    def _build_ui(self):
        # ... existing code ...
        tabs = QTabWidget()
        self.tabs.addTab(self._build_relationship_tab(), "Relationship")

        form = QFormLayout()
        form.addRow(QLabel(""), self._desc_label("Name: "))
        label_name = QLabel(str(self.character))
        label_name.setWordWrap(True)
        form.addRow(QLabel(""), label_name)
        form.addRow(QLabel(""), self._desc_label("Character Manager: "))
        label_manager = QLabel(str(self.character_manager))
        label_manager.setWordWrap(True)
        form.addRow(QLabel(""), label_manager)

        # ... rest of code ...

