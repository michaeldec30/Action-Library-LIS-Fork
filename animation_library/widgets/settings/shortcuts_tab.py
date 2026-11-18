# Action Library LIS Fork - new file, 2026-11-17. GPL-3.0, see LICENSE and FORK_CHANGES.md.
"""ShortcutsTab - assign keyboard shortcuts to library actions.

Click a shortcut button, then press the key (with Ctrl / Shift / Alt if wanted) or
turn the mouse wheel. Escape cancels the capture; "×" unassigns. Each action
has a main and an alternative binding. Character keys are stored as the
physical key, so they stay where they are on QWERTY under any layout.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGridLayout, QScrollArea,
)

from ...events.event_bus import get_event_bus
from ...services import shortcuts as sc


class KeyCaptureButton(QPushButton):
    """Shows a binding; click, then press a key to change it."""

    def __init__(self, binding, on_captured, parent=None):
        super().__init__(parent)
        self._binding = binding
        self._on_captured = on_captured
        self._capturing = False
        self.setFixedWidth(140)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.clicked.connect(self._start)
        self._refresh()

    def binding(self):
        return self._binding

    def set_binding(self, binding):
        self._binding = binding
        self._capturing = False
        self._refresh()

    def _refresh(self):
        if self._capturing:
            self.setText("Press a key...")
        else:
            self.setText(sc.binding_label(self._binding) or "—")

    def _start(self):
        self._capturing = True
        self._refresh()
        self.setFocus()

    def focusOutEvent(self, event):
        if self._capturing:
            self._capturing = False
            self._refresh()
        super().focusOutEvent(event)

    def wheelEvent(self, event):
        if not self._capturing:
            super().wheelEvent(event)
            return
        event.accept()
        binding = sc.binding_from_wheel(event)
        if binding:
            self._capturing = False
            self._on_captured(self, binding)

    def keyPressEvent(self, event):
        if not self._capturing:
            super().keyPressEvent(event)
            return
        event.accept()
        if event.key() == Qt.Key.Key_Escape and not event.modifiers():
            self._capturing = False
            self._refresh()
            return
        binding = sc.binding_from_event(event)
        if binding is None:  # bare modifier: keep waiting for the real key
            return
        self._capturing = False
        self._on_captured(self, binding)


class ShortcutsTab(QWidget):
    def __init__(self, theme_manager, parent=None):
        super().__init__(parent)
        self._theme_manager = theme_manager
        self._buttons = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        info = QLabel(
            "Click a shortcut, then press the key or turn the mouse wheel. Escape cancels, "
            "× removes it. Main and Alternative both trigger the action.\n"
            "Letter and digit keys work by position (as on QWERTY), whatever keyboard "
            "layout is active.\nShortcuts act on the selected animations and are "
            "ignored while typing in a text field."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self._conflict_label = QLabel("")
        self._conflict_label.setStyleSheet("color: #FF9800;")
        self._conflict_label.setWordWrap(True)
        layout.addWidget(self._conflict_label)

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setColumnStretch(0, 1)
        grid.addWidget(QLabel("<b>Action</b>"), 0, 0)
        grid.addWidget(QLabel("<b>Main</b>"), 0, 1)
        grid.addWidget(QLabel("<b>Alternative</b>"), 0, 3)
        bindings = sc.load_bindings()
        for row, (action, label, _default) in enumerate(sc.ACTIONS, start=1):
            grid.addWidget(QLabel(label), row, 0)
            pair = bindings.get(action, ("", ""))
            for slot in (0, 1):
                btn = KeyCaptureButton(pair[slot], self._on_captured)
                self._buttons[(action, slot)] = btn
                grid.addWidget(btn, row, 1 + slot * 2)
                # "×" + tooltip: the word "Clear" did not fit next to two key columns
                clear = QPushButton("\u00d7")
                clear.setFixedWidth(32)
                clear.setToolTip("Clear this shortcut")
                clear.clicked.connect(lambda _=False, b=btn: b.set_binding(""))
                grid.addWidget(clear, row, 2 + slot * 2)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(grid_host)
        layout.addWidget(scroll, 1)

        row = QHBoxLayout()
        row.addStretch()
        reset = QPushButton("Reset to defaults")
        reset.clicked.connect(self._reset_defaults)
        row.addWidget(reset)
        layout.addLayout(row)

    def _on_captured(self, button, binding):
        # One key - one action: take it away from whoever had it.
        taken_from = [a for a, b in self._buttons.items() if b is not button and b.binding() == binding]
        for a in taken_from:
            self._buttons[a].set_binding("")
        button.set_binding(binding)
        if taken_from:
            names = ", ".join(sc.LABELS[a] for a, _slot in taken_from)
            self._conflict_label.setText(
                f"{sc.binding_label(binding)} was assigned to: {names}. That action is now unassigned.")
        else:
            self._conflict_label.setText("")

    def _reset_defaults(self):
        for (action, slot), btn in self._buttons.items():
            defaults = sc.DEFAULTS if slot == 0 else sc.ALT_DEFAULTS
            btn.set_binding(defaults.get(action, ""))
        self._conflict_label.setText("")

    def save_settings(self):
        sc.save_bindings({a: (self._buttons[(a, 0)].binding(), self._buttons[(a, 1)].binding())
                          for a, _, _ in sc.ACTIONS})
        get_event_bus().settings_changed.emit("shortcuts", None)


__all__ = ['ShortcutsTab']
