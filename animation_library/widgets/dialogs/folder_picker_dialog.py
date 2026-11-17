# Action Library LIS Fork - new file, 2026-11-17. GPL-3.0, see LICENSE and FORK_CHANGES.md.
"""Folder picker with a filter box, for "Move to Folder" in the card context menu.

Shows full folder paths (e.g. 'Adult/Baby'), because names repeat across the
tree ('Adult/Baby' vs root 'Baby') and a name-only list can't tell them apart.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout,
)


class FolderPickerDialog(QDialog):
    def __init__(self, folders, title="Move to Folder", parent=None):
        """folders: list of (folder_id, path) tuples."""
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(420, 520)
        self._folder_id = None

        layout = QVBoxLayout(self)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter folders...")
        self._filter.setClearButtonEnabled(True)
        layout.addWidget(self._filter)

        self._list = QListWidget()
        for folder_id, path in sorted(folders, key=lambda f: f[1].lower()):
            item = QListWidgetItem(path)
            item.setData(Qt.ItemDataRole.UserRole, folder_id)
            self._list.addItem(item)
        layout.addWidget(self._list)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_current)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._filter.textChanged.connect(self._apply_filter)
        self._filter.returnPressed.connect(self._accept_current)
        self._list.itemDoubleClicked.connect(lambda _item: self._accept_current())
        self._filter.setFocus()

    def _apply_filter(self, text):
        needle = text.strip().lower()
        first_visible = None
        for i in range(self._list.count()):
            item = self._list.item(i)
            hidden = bool(needle) and needle not in item.text().lower()
            item.setHidden(hidden)
            if not hidden and first_visible is None:
                first_visible = item
        # Keep a visible row selected so Enter in the filter box just works.
        current = self._list.currentItem()
        if first_visible is not None and (current is None or current.isHidden()):
            self._list.setCurrentItem(first_visible)

    def _accept_current(self):
        item = self._list.currentItem()
        if item is None or item.isHidden():
            return
        self._folder_id = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def selected_folder_id(self):
        return self._folder_id
