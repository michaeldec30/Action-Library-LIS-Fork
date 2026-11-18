# Modified in Action Library LIS Fork, 2026-11 (based on Action Library 1.6.2 by CGstuff). See FORK_CHANGES.md.
"""
TagInputDialog - Dialog for adding tags to animations
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QLabel, QDialogButtonBox
)
from PyQt6.QtCore import Qt


class TagInputDialog(QDialog):
    """Dialog for entering new tags"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tags = []

        self.setWindowTitle("Add Tags")
        self.setModal(True)
        self.resize(400, 150)

        self._create_ui()

        # LIS fork: closes on a click outside (= Cancel), opens at the cursor.
        from ...utils.popup_dialog import make_dismissable
        make_dismissable(self)
        self._tag_input.setFocus()

    def _create_ui(self):
        """Create dialog UI"""
        layout = QVBoxLayout(self)

        # Instructions
        label = QLabel("Enter tags separated by commas:")
        layout.addWidget(label)

        # Tag input field
        self._tag_input = QLineEdit()
        self._tag_input.setPlaceholderText("e.g., action, combat, character")
        layout.addWidget(self._tag_input)

        # Button box
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_tags(self) -> list:
        """Get entered tags as list"""
        text = self._tag_input.text().strip()
        if not text:
            return []

        # Split by comma and clean up
        tags = [tag.strip() for tag in text.split(',') if tag.strip()]
        return tags


__all__ = ['TagInputDialog']
