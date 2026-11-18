# Action Library LIS Fork - new file, 2026-11-17. GPL-3.0, see LICENSE and FORK_CHANGES.md.
"""Small pickers / inputs that close when you click outside them.

make_dismissable(dialog) turns a dialog into a Qt popup: a click anywhere outside
closes it (= Cancel), Escape still cancels, exec() still returns the result. It
opens at the mouse cursor, kept on screen. Popups have no title bar, so the
dialogs show their purpose inside (a label / title row).
"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QApplication


def make_dismissable(dialog, at_cursor: bool = True):
    # Replace the window TYPE, don't OR it in: Dialog (0x3) | Popup (0x9) == Tool (0xB),
    # which stays an ordinary modal window (outside clicks just make it flash).
    dialog.setWindowFlags(Qt.WindowType.Popup)
    dialog.setObjectName(dialog.objectName() or "dismissablePopup")
    # A visible edge, since the window frame is gone.
    dialog.setStyleSheet(dialog.styleSheet() + "\nQDialog { border: 1px solid #555; }")
    if at_cursor:
        if not dialog.testAttribute(Qt.WidgetAttribute.WA_Resized):
            dialog.adjustSize()  # keep an explicit resize(), else size to content
        pos = QCursor.pos()
        screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        x = min(pos.x(), area.right() - dialog.width())
        y = min(pos.y(), area.bottom() - dialog.height())
        dialog.move(max(area.left(), x), max(area.top(), y))
    return dialog


__all__ = ['make_dismissable']
