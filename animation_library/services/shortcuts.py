# Action Library LIS Fork - new file, 2026-11-17. GPL-3.0, see LICENSE and FORK_CHANGES.md.
"""Keyboard shortcuts: action list, defaults, storage and layout-independent matching.

Bindings are stored as strings in QSettings under "shortcuts/<action_id>":
    "sc:13"        - physical key by scan code (hex, PC set 1), shown as its QWERTY label
    "key:Delete"   - non-character key by Qt key name (layout-independent anyway)
    "Ctrl+sc:21"   - with modifiers (Ctrl / Shift / Alt, in that order)
    "Ctrl+wheel:Up" - mouse wheel notch up / down (with modifiers)
    ""             - unassigned

Every action has two slots: the main binding ("shortcuts/<id>") and an
alternative ("shortcuts_alt/<id>"); either one triggers the action.

Character keys are matched by the PHYSICAL key, so a shortcut sits where it would
on QWERTY whatever the active layout is (Dvorak, Russian, ...). Qt's scan codes
are PC set 1 on Windows and X11 keycodes (= set 1 + 8) on Linux; on other
platforms there is no reliable scan code and the typed letter is used instead.
"""
import sys

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QKeySequence

from ..config import Config

# (action_id, label, default binding). Order = order in Settings and in the help overlay.
ACTIONS = [
    ("delete",             "Delete / Move to Archive",   "key:Delete"),
    ("move_to_folder",     "Move to Folder",             "sc:32"),       # M
    ("add_to_folder",      "Add to Folder",              "sc:1E"),       # A
    ("remove_from_folder", "Remove from current folder", "key:Backspace"),
    ("add_tags",           "Add Tags",                   "Shift+sc:14"), # Shift+T
    ("remove_tags",        "Remove Tags",                "sc:13"),       # R
    ("gradient",           "Gradient",                   "sc:22"),       # G
    ("favorite",           "Toggle Favorite",            "sc:21"),       # F
    ("rename",             "Rename",                     "key:F2"),
    ("status_none",        "Status: None",               "sc:29"),       # ~
    ("status_wip",         "Status: WIP",                "sc:02"),       # 1
    ("status_review",      "Status: In Review",          "sc:03"),       # 2
    ("status_approved",    "Status: Approved",           "sc:04"),       # 3
    ("status_needs_work",  "Status: Needs Work",         "sc:05"),       # 4
    ("status_final",       "Status: Final",              "sc:06"),       # 5
    ("toggle_folders",     "Show/Hide folder tree",      "sc:30"),       # B
    ("toggle_info",        "Show/Hide info panel",       "sc:17"),       # I
    ("folder_jump",        "Go to folder (picker)",      "Shift+sc:30"), # Shift+B
    ("folder_next",        "Next folder (same level)",   "Alt+key:Right"),
    ("folder_prev",        "Previous folder (same level)", "Alt+key:Left"),
    ("folder_up",          "Parent folder",              "Alt+key:Up"),
    ("folder_down",        "First subfolder",            "Alt+key:Down"),
    ("previews",           "Play previews on/off",       "sc:19"),       # P
    ("view_mode",          "Grid / List view",           "sc:26"),       # L
    ("edit_mode",          "Edit mode on/off",           "sc:12"),       # E
    ("sort",               "Sort menu",                  "sc:1F"),       # S
    ("tags_filter",        "Tags filter menu",           "sc:14"),       # T
    ("size_down",          "Smaller cards",              "key:Num -"),
    ("size_up",            "Bigger cards",               "key:Num +"),
    ("reload",             "Reload library",             "Shift+sc:13"), # Shift+R
    ("search",             "Focus search",               "Ctrl+sc:21"),  # Ctrl+F
    ("clear_selection",    "Clear selection",            "key:Escape"),
    ("help",               "Toggle shortcuts help",      "sc:23"),       # H
    ("docs",               "Open documentation",         "key:F1"),
]
DEFAULTS = {a: d for a, _, d in ACTIONS}
# Second slot ("alternative") defaults; everything else starts empty.
ALT_DEFAULTS = {
    "size_down": "Ctrl+wheel:Down",
    "size_up": "Ctrl+wheel:Up",
}
LABELS = {a: l for a, l, _ in ACTIONS}

# PC set-1 scan code -> QWERTY label (character keys only)
_SC_LABELS = {
    0x29: "~", 0x02: "1", 0x03: "2", 0x04: "3", 0x05: "4", 0x06: "5", 0x07: "6",
    0x08: "7", 0x09: "8", 0x0A: "9", 0x0B: "0", 0x0C: "-", 0x0D: "=",
    0x10: "Q", 0x11: "W", 0x12: "E", 0x13: "R", 0x14: "T", 0x15: "Y", 0x16: "U",
    0x17: "I", 0x18: "O", 0x19: "P", 0x1A: "[", 0x1B: "]", 0x2B: "\\",
    0x1E: "A", 0x1F: "S", 0x20: "D", 0x21: "F", 0x22: "G", 0x23: "H", 0x24: "J",
    0x25: "K", 0x26: "L", 0x27: ";", 0x28: "'",
    0x2C: "Z", 0x2D: "X", 0x2E: "C", 0x2F: "V", 0x30: "B", 0x31: "N", 0x32: "M",
    0x33: ",", 0x34: ".", 0x35: "/",
}
_LABEL_TO_SC = {v: k for k, v in _SC_LABELS.items()}

_MODS = [("Ctrl", Qt.KeyboardModifier.ControlModifier),
         ("Shift", Qt.KeyboardModifier.ShiftModifier),
         ("Alt", Qt.KeyboardModifier.AltModifier)]

_KEYPAD_TWINS = {getattr(Qt.Key, f"Key_{d}") for d in range(10)} | {
    Qt.Key.Key_Plus, Qt.Key.Key_Minus, Qt.Key.Key_Asterisk, Qt.Key.Key_Slash,
    Qt.Key.Key_Period, Qt.Key.Key_Comma, Qt.Key.Key_Enter}

_MODIFIER_KEYS = {Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta,
                  Qt.Key.Key_AltGr, Qt.Key.Key_CapsLock}


def _physical_sc(event):
    """Set-1 scan code of a character key, or None."""
    sc = event.nativeScanCode()
    if sys.platform.startswith("win"):
        sc &= 0xFF  # drop the extended-key bit; character keys are never extended
    elif sys.platform.startswith("linux"):
        sc -= 8     # X11 keycode = evdev code + 8; evdev = set 1 for these keys
    else:
        # No portable scan code: fall back to the typed character (layout-dependent).
        text = QKeySequence(event.key()).toString().upper()
        return _LABEL_TO_SC.get(text)
    return sc if sc in _SC_LABELS else None


def binding_from_event(event):
    """Binding string for a key event, or None for a bare modifier / unknown key."""
    if event.key() in _MODIFIER_KEYS:
        return None
    mods = "".join(f"{name}+" for name, flag in _MODS if event.modifiers() & flag)
    sc = _physical_sc(event)
    if sc is not None:
        return f"{mods}sc:{sc:02X}"
    name = QKeySequence(event.key()).toString()
    if not name:
        return None
    # Keypad keys differ from the main-row ones ("Num -" vs "-"). Only for keys that
    # exist in both places: Qt on Windows also flags the plain arrow keys as keypad.
    if (event.modifiers() & Qt.KeyboardModifier.KeypadModifier
            and event.key() in _KEYPAD_TWINS):
        name = f"Num {name}"
    return f"{mods}key:{name}"


def binding_from_wheel(event):
    """Binding string for one wheel step ("Ctrl+wheel:Up"), or None for a sideways scroll."""
    dy = event.angleDelta().y()
    if dy == 0:
        return None
    mods = "".join(f"{name}+" for name, flag in _MODS if event.modifiers() & flag)
    return f"{mods}wheel:{'Up' if dy > 0 else 'Down'}"


def binding_label(binding):
    """Human-readable label ("Ctrl+F", "Delete", "~")."""
    if not binding:
        return ""
    i = next((binding.find(p) for p in ("sc:", "key:", "wheel:") if p in binding), 0)
    mods = [m for m in binding[:i].split("+") if m]
    key = binding[i:]
    if key.startswith("sc:"):
        key = _SC_LABELS.get(int(key[3:], 16), key)
    elif key.startswith("key:"):
        key = key[4:]
    elif key.startswith("wheel:"):
        key = "Wheel " + key[6:]
    return "+".join(mods + [key])


# Bump when a default changes in a way that needs migrating stored bindings.
_SCHEMA_VERSION = 2


def load_bindings():
    """{action_id: (main, alternative)} from QSettings; defaults for anything never set.

    An action / slot added in a later version gets its default only if no stored
    binding already uses that key; otherwise it starts unassigned.
    """
    s = QSettings(Config.APP_AUTHOR, Config.APP_NAME)
    if s.value("shortcuts/schema", 1, type=int) < 2:
        # v2: T became "Tags filter menu", Add Tags moved to Shift+T.
        if s.contains("shortcuts/add_tags") and s.value("shortcuts/add_tags", type=str) == "sc:14":
            s.setValue("shortcuts/add_tags", "Shift+sc:14")
        s.setValue("shortcuts/schema", _SCHEMA_VERSION)
    slots = (("shortcuts", DEFAULTS), ("shortcuts_alt", ALT_DEFAULTS))
    stored = {}
    for group, _ in slots:
        for a, _, _ in ACTIONS:
            if s.contains(f"{group}/{a}"):
                stored[(group, a)] = s.value(f"{group}/{a}", type=str)
    used = {b for b in stored.values() if b}
    result = {}
    for a, _, _ in ACTIONS:
        pair = []
        for group, defaults in slots:
            if (group, a) in stored:
                b = stored[(group, a)]
            else:
                default = defaults.get(a, "")
                b = "" if default in used else default
                if b:
                    used.add(b)
            pair.append(b)
        result[a] = tuple(pair)
    return result


def save_bindings(bindings):
    """bindings: {action_id: (main, alternative)}"""
    s = QSettings(Config.APP_AUTHOR, Config.APP_NAME)
    for a, _, _ in ACTIONS:
        main, alt = bindings.get(a, ("", ""))
        s.setValue(f"shortcuts/{a}", main)
        s.setValue(f"shortcuts_alt/{a}", alt)


__all__ = ['ACTIONS', 'DEFAULTS', 'ALT_DEFAULTS', 'LABELS', 'binding_from_event',
           'binding_from_wheel', 'binding_label',
           'load_bindings', 'save_bindings']
