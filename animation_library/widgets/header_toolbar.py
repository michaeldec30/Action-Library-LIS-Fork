# Modified in Action Library LIS Fork, 2026-11 (based on Action Library 1.6.2 by CGstuff). See FORK_CHANGES.md.
"""
HeaderToolbar - Main toolbar with search and controls

Pattern: QWidget with horizontal layout
Inspired by: Current animation_library toolbar
"""

import os

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QGridLayout, QLineEdit, QPushButton,
    QSlider, QLabel, QSpacerItem, QSizePolicy, QComboBox,
    QFrame, QMenu, QStylePainter, QStyleOptionComboBox, QStyle
)
from PyQt6.QtCore import pyqtSignal, Qt, QSize
from PyQt6.QtGui import QIcon

from ..config import Config
from ..events.event_bus import get_event_bus
from ..services.database_service import get_database_service
from ..services.service_refs import service_ref
from ..utils import IconLoader, colorize_white_svg
from ..themes.theme_manager import get_theme_manager


class IdentityPill(QFrame):
    """
    Small always-visible widget showing the local identity.

    Layout:  [colored circle]  [display_name]

    Clicking the pill emits `clicked` so the parent can open Settings to
    the Identity tab. Subscribes to event_bus.identity_changed so the
    pill refreshes immediately when identity is edited in Settings.
    """

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click to edit your identity")
        self.setFrameShape(QFrame.Shape.NoFrame)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 10, 4)
        layout.setSpacing(8)

        self._color_dot = QLabel()
        self._color_dot.setFixedSize(14, 14)
        layout.addWidget(self._color_dot)

        self._name_label = QLabel("")
        self._name_label.setStyleSheet(
            "color: #1a1a1a; font-size: 12px; font-weight: 600;"
        )
        layout.addWidget(self._name_label)

        # Subtle pill background so it reads as a clickable chip on the
        # header gradient.
        self.setStyleSheet("""
            IdentityPill {
                background-color: rgba(255, 255, 255, 0.18);
                border-radius: 12px;
            }
            IdentityPill:hover {
                background-color: rgba(255, 255, 255, 0.28);
            }
        """)

        self._refresh()

        # Listen for identity edits — pill auto-refreshes after Apply in
        # Settings → Identity.
        get_event_bus().identity_changed.connect(self._on_identity_changed)

    def _refresh(self) -> None:
        identity = Config.load_identity()
        if identity is None:
            # Defensive fallback — wizard normally guarantees one exists.
            self._name_label.setText("(no identity)")
            self._color_dot.setStyleSheet(
                "background-color: #888; border-radius: 7px;"
            )
            return
        self._name_label.setText(identity.display_name)
        self._color_dot.setStyleSheet(
            f"background-color: {identity.color}; border-radius: 7px;"
        )

    def _on_identity_changed(self, _identity) -> None:
        # Param ignored — _refresh re-reads from disk for safety.
        self._refresh()

    def mousePressEvent(self, event):  # noqa: N802 (Qt convention)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _LocationCombo(QComboBox):
    """Combo whose text is cut only at one EDGE of the box (no ellipsis in the middle).

    ElideRight keeps the start (library name), ElideLeft keeps the end of a path
    (the folder you are in). The text is elided to exactly the field's width, so the
    style never shortens it again its own way.
    """

    def __init__(self, elide=Qt.TextElideMode.ElideRight, parent=None):
        super().__init__(parent)
        self._elide = elide

    def paintEvent(self, event):
        painter = QStylePainter(self)
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, opt)
        field = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox, opt, QStyle.SubControl.SC_ComboBoxEditField, self)
        opt.currentText = self.fontMetrics().elidedText(
            opt.currentText, self._elide, max(10, field.width() - 4))
        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, opt)


class _ClickCombo(_LocationCombo):
    """Looks like the library combo, but a click emits `clicked` instead of a dropdown."""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(Qt.TextElideMode.ElideLeft, parent)

    def showPopup(self):
        self.clicked.emit()


class HeaderToolbar(QWidget):
    """
    Header toolbar with search and view controls

    Features:
    - Search box with live filtering
    - View mode toggle (grid/list)
    - Card size slider (grid mode)
    - Edit mode toggle
    - Delete button
    - Event bus integration

    Layout:
        [Library] [Search] [Grid/List] [Size: ----] [Edit Mode] [Delete]
    """

    # Resolved on every access, never cached - the library can change at runtime.
    # See services/service_refs.py.
    _db_service = service_ref(get_database_service, '_injected_db_service')

    # Sentinel for the picker's "Browse..." entry, so it can't collide with a path.
    BROWSE_LIBRARY = "__browse__"

    # Signals
    library_switch_requested = pyqtSignal(str)  # user picked a known library (path)
    library_browse_requested = pyqtSignal()     # user picked "Browse for another folder..."
    library_forget_requested = pyqtSignal(str)  # user asked to drop a library from the list
    docs_clicked = pyqtSignal()                 # open the local documentation
    search_text_changed = pyqtSignal(str)
    view_mode_changed = pyqtSignal(str)  # "grid" or "list"
    card_size_changed = pyqtSignal(int)
    edit_mode_changed = pyqtSignal(bool)
    animated_previews_toggled = pyqtSignal(bool)  # play previews on the cards
    delete_clicked = pyqtSignal()
    refresh_library_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()  # New: settings button
    new_folder_clicked = pyqtSignal()  # New: create folder button
    about_clicked = pyqtSignal()  # New: about button
    console_clicked = pyqtSignal()  # New: console button
    rig_type_filter_changed = pyqtSignal(list)  # List of selected rig types
    tags_filter_changed = pyqtSignal(list)  # List of selected tags
    sort_changed = pyqtSignal(str, str)  # (sort_by, sort_order)
    help_clicked = pyqtSignal()  # Help button clicked
    identity_pill_clicked = pyqtSignal()  # Identity pill clicked → open Settings → Identity
    folder_picker_requested = pyqtSignal()    # LIS fork: click on "Current Folder"
    folders_panel_toggled = pyqtSignal(bool)  # LIS fork: show/hide folder tree
    info_panel_toggled = pyqtSignal(bool)     # LIS fork: show/hide info (metadata + apply) panel

    def __init__(self, parent=None, db_service=None, event_bus=None, theme_manager=None):
        super().__init__(parent)

        # LIS fork: library / folder boxes stacked in the 50px header
        self.LOCATION_WIDTH = 340        # max width of the library / folder boxes
        self.LOCATION_MIN_WIDE = 230     # kept until everything else has given way
        self.LOCATION_MIN_TIGHT = 120
        self.LOCATION_HEIGHT = 21
        self.LOCATION_QSS = "QComboBox { padding: 1px 6px; font-size: 8pt; }"

        # Set header property for theme-based styling (orange gradient)
        self.setProperty("header", "true")
        # Enable styled background for gradient to work with property selector
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # Fixed height like old repo
        self.setFixedHeight(50)

        # Services (injectable for testing)
        self._event_bus = event_bus or get_event_bus()
        self._injected_db_service = db_service  # None in production
        self._theme_manager = theme_manager or get_theme_manager()

        # State
        self._view_mode = Config.DEFAULT_VIEW_MODE
        self._card_size = Config.DEFAULT_CARD_SIZE
        self._edit_mode = False

        # Setup UI
        self._create_widgets()
        self._create_layout()
        self._connect_signals()

        # Load filter data
        self._refresh_filter_data()
        self.refresh_libraries()

        # Force Qt to reapply stylesheet for dynamic property AFTER widgets are created
        self.style().unpolish(self)
        self.style().polish(self)

    def _create_widgets(self):
        """Create toolbar widgets"""

        # Get theme for icon colorization
        theme = self._theme_manager.get_current_theme()
        icon_color = theme.palette.header_icon_color if theme else "#1a1a1a"

        # Library picker - which library everything else in this bar applies to
        self._library_combo = _LocationCombo(Qt.TextElideMode.ElideRight)
        self._flex(self._library_combo, self.LOCATION_MIN_WIDE, self.LOCATION_WIDTH)
        self._library_combo.setFixedHeight(self.LOCATION_HEIGHT)
        self._library_combo.setStyleSheet(self.LOCATION_QSS)

        # LIS fork: "Current Folder" under the library picker - same look, shows the
        # path of the folder being viewed; clicking it opens the folder picker.
        self._folder_combo = _ClickCombo()
        self._flex(self._folder_combo, self.LOCATION_MIN_WIDE, self.LOCATION_WIDTH)
        self._folder_combo.setFixedHeight(self.LOCATION_HEIGHT)
        self._folder_combo.setStyleSheet(self.LOCATION_QSS)
        self._folder_combo.setToolTip("Go to folder (Shift+B)")
        # Never takes keyboard focus: a focused combo opens on Alt+Down, which here
        # would pop the folder picker instead of the Alt+arrow folder navigation.
        self._folder_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._folder_combo.clicked.connect(self.folder_picker_requested.emit)
        self._folder_path = ""
        self._library_label = QLabel("Current Library:")
        self._folder_label = QLabel("Current Folder:")
        for lbl in (self._library_label, self._folder_label):
            lbl.setStyleSheet(f"color: {icon_color}; font-size: 8pt;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            # Fixed: the label column must not soak up spare width (it opened a big
            # gap between the folder-tree button and the labels).
            lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self._library_combo.setToolTip(
            "Switch animation library\nRight-click to forget a library"
        )
        self._library_combo.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )

        # Search box (match old repo: 200px wide)
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search...")
        self._search_box.setClearButtonEnabled(True)
        self._search_box.setMinimumWidth(100)  # LIS fork: flexible, was fixed 200
        self._search_box.setMaximumWidth(260)

        # Refresh library button (icon-only)
        self._refresh_btn = QPushButton()
        refresh_icon_path = IconLoader.get("refresh")
        refresh_icon = colorize_white_svg(refresh_icon_path, icon_color)
        self._refresh_btn.setIcon(refresh_icon)
        self._refresh_btn.setIconSize(QSize(24, 24))
        self._refresh_btn.setFixedSize(40, 40)
        self._refresh_btn.setToolTip("Refresh Library (F5)")

        # New folder button (40x40, icon-only)
        self._new_folder_btn = QPushButton()
        add_icon_path = IconLoader.get("add")
        add_icon = colorize_white_svg(add_icon_path, icon_color)
        self._new_folder_btn.setIcon(add_icon)
        self._new_folder_btn.setIconSize(QSize(24, 24))
        self._new_folder_btn.setFixedSize(40, 40)
        self._new_folder_btn.setToolTip("Create New Folder (Ctrl+N)")

        # View mode toggle button (icon-only, smaller like old repo: 32x32)
        self._view_mode_btn = QPushButton()
        view_mode_icon_path = IconLoader.get("view_mode")
        view_mode_icon = colorize_white_svg(view_mode_icon_path, icon_color)
        self._view_mode_btn.setIcon(view_mode_icon)
        self._view_mode_btn.setIconSize(QSize(20, 20))  # Smaller icon
        self._view_mode_btn.setFixedSize(32, 32)  # Match old repo: 32x32
        self._view_mode_btn.setCheckable(True)
        self._view_mode_btn.setChecked(self._view_mode == "grid")
        self._view_mode_btn.setToolTip("Toggle Grid/List View")

        # Panel toggles (LIS fork): folder tree on the left, info panel on the right
        self._folders_btn = QPushButton()
        self._folders_btn.setIcon(colorize_white_svg(IconLoader.get("panel_left"), icon_color))
        self._folders_btn.setIconSize(QSize(20, 20))
        self._folders_btn.setFixedSize(32, 32)
        self._folders_btn.setCheckable(True)
        self._folders_btn.setChecked(True)
        self._folders_btn.setToolTip("Show/Hide Folder Tree (B)")
        self._info_btn = QPushButton()
        self._info_btn.setIcon(colorize_white_svg(IconLoader.get("panel_right"), icon_color))
        self._info_btn.setIconSize(QSize(20, 20))
        self._info_btn.setFixedSize(32, 32)
        self._info_btn.setCheckable(True)
        self._info_btn.setChecked(True)
        self._info_btn.setToolTip("Show/Hide Info Panel (I)")

        # Card size slider with grid icon
        self._grid_icon_label = QLabel()
        grid_icon_path = IconLoader.get("resize_grid")
        grid_icon = colorize_white_svg(grid_icon_path, icon_color)
        self._grid_icon_label.setPixmap(grid_icon.pixmap(20, 20))
        self._grid_icon_label.setToolTip("Card Size")

        self._size_slider = QSlider(Qt.Orientation.Horizontal)
        self._size_slider.setProperty("cardsize", "true")  # Property for CSS selector
        self._size_slider.setMinimum(Config.MIN_CARD_SIZE)
        self._size_slider.setMaximum(Config.MAX_CARD_SIZE)
        self._size_slider.setValue(self._card_size)
        self._size_slider.setSingleStep(Config.CARD_SIZE_STEP)
        self._size_slider.setPageStep(Config.CARD_SIZE_STEP * 2)
        self._size_slider.setFixedWidth(120)
        self._size_slider.setToolTip(f"Card size ({Config.MIN_CARD_SIZE}-{Config.MAX_CARD_SIZE}px)")

        # Animated previews toggle. LABELLED, not a bare glyph: as a 32px "play"
        # icon squeezed between the view controls it was effectively invisible.
        # LIS fork: preview playback preset FS1-FS4, left of the Previews button.
        from ..services.sprite_playback import get_sprite_playback
        self._preview_speed_combo = QComboBox()
        self._preview_speed_combo.setToolTip(
            "Preview playback preset FS1-FS4 (Frame Skip), edited in Settings > Appearance")
        mode = get_sprite_playback().get_mode()
        for i in range(1, 5):
            self._preview_speed_combo.addItem(f"FS{i}", f"fs{i}")
            if mode == f"fs{i}":
                self._preview_speed_combo.setCurrentIndex(i - 1)
        # Small, like the library / folder boxes (the header font made it a big button)
        # 31 px (half the first version): no drop-down arrow, the text alone ("FS1")
        self._preview_speed_combo.setStyleSheet(
            "QComboBox { padding: 1px 2px; font-size: 8pt; }"
            "QComboBox::drop-down { width: 0px; border: none; }"
            "QComboBox::down-arrow { image: none; width: 0px; }"
            # List items the same size as the box (the theme's 4px 8px item padding
            # left no room for the text in a 31 px wide list)
            "QComboBox QAbstractItemView { font-size: 8pt; padding: 0px; }"
            "QComboBox QAbstractItemView::item { padding: 0px 2px; min-height: 22px;"
            " max-height: 22px; border: none; }")
        self._preview_speed_combo.setFixedSize(31, 22)
        _view = self._preview_speed_combo.view()
        _view.setFixedWidth(31)
        # Never "FS…": no elision, no frame / scrollbar eating the few pixels there are
        _view.setTextElideMode(Qt.TextElideMode.ElideNone)
        _view.setFrameShape(QFrame.Shape.NoFrame)
        _view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        _view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._preview_speed_combo.currentIndexChanged.connect(
            lambda _i: get_sprite_playback().set_mode(self._preview_speed_combo.currentData()))

        # LIS fork: play / pause icon instead of a "▶" glyph, so the state is visible
        self._animated_btn = QPushButton(" Previews")
        self._animated_btn.setIconSize(QSize(14, 14))
        self._previews_icon_color = icon_color
        self._animated_btn.setFixedHeight(32)
        self._animated_btn.setMinimumWidth(96)
        self._animated_btn.setCheckable(True)
        # Left off at construction on purpose: MainWindow applies the stored
        # (or default) value once the service exists, so nothing starts
        # building sheets before then.
        self._animated_btn.setChecked(False)
        self._animated_btn.setToolTip(
            "Play each card's preview in the grid. "
            "Previews are prepared the first time you view them."
        )

        # Edit mode toggle (icon-only)
        self._edit_mode_btn = QPushButton()
        edit_icon_path = IconLoader.get("edit")
        edit_icon = colorize_white_svg(edit_icon_path, icon_color)
        self._edit_mode_btn.setIcon(edit_icon)
        self._edit_mode_btn.setIconSize(QSize(24, 24))
        self._edit_mode_btn.setFixedSize(40, 40)
        self._edit_mode_btn.setCheckable(True)
        self._edit_mode_btn.setChecked(False)
        self._edit_mode_btn.setToolTip("Toggle Edit Mode")

        # Delete/Archive button (icon-only)
        # Solo mode: instant delete (trash icon)
        # Studio/Pipeline mode: soft delete to archive (archive icon)
        self._delete_btn = QPushButton()
        self._delete_btn.setIconSize(QSize(24, 24))
        self._delete_btn.setFixedSize(40, 40)
        self._delete_btn.setEnabled(False)
        self._update_delete_button_mode(icon_color)

        # About button (icon-only)
        self._about_btn = QPushButton()
        about_icon_path = IconLoader.get("al_icon")  # App logo icon
        about_icon = colorize_white_svg(about_icon_path, icon_color)
        self._about_btn.setIcon(about_icon)
        self._about_btn.setIconSize(QSize(24, 24))
        self._about_btn.setFixedSize(40, 40)
        self._about_btn.setToolTip("About Animation Library")

        # Console button (icon-only)
        self._console_btn = QPushButton()
        console_icon_path = IconLoader.get("console")
        console_icon = colorize_white_svg(console_icon_path, icon_color)
        self._console_btn.setIcon(console_icon)
        self._console_btn.setIconSize(QSize(24, 24))
        self._console_btn.setFixedSize(40, 40)
        self._console_btn.setToolTip("Console & Logs")

        # Settings button (icon-only, new)
        self._settings_btn = QPushButton()
        settings_icon_path = IconLoader.get("settings")
        settings_icon = colorize_white_svg(settings_icon_path, icon_color)
        self._settings_btn.setIcon(settings_icon)
        self._settings_btn.setIconSize(QSize(24, 24))
        self._settings_btn.setFixedSize(40, 40)
        self._settings_btn.setToolTip("Settings (Ctrl+,)")

        # Identity pill (Option B Phase 5) — colored circle + display name.
        # Always visible, click opens Settings → Identity.
        self._identity_pill = IdentityPill(self)

        # Help button (shows keyboard shortcuts)
        self._help_btn = QPushButton("?")
        self._help_btn.setFixedSize(40, 40)
        self._help_btn.setToolTip("Keyboard Shortcuts (H)")
        self._help_btn.setStyleSheet("""
            QPushButton {
                font-size: 18px;
                font-weight: bold;
            }
        """)

        # Documentation button. Text rather than an icon for now - there's no
        # book/doc glyph in the icon set; drop one in animation_library/icons/
        # and swap this for an IconLoader icon like its neighbours.
        self._docs_btn = QPushButton("Docs")
        self._docs_btn.setFixedSize(52, 40)
        self._docs_btn.setToolTip("Documentation (F1)")

        # Rig type filter dropdown
        self._rig_type_combo = QComboBox()
        self._rig_type_combo.addItem("All Rig Types")
        self._flex(self._rig_type_combo, 80, 140)
        self._rig_type_combo.setToolTip("Filter by Rig Type")

        # Tags filter dropdown (shows all tags, multiple can be selected via dialog)
        self._tags_combo = QComboBox()
        self._tags_combo.addItem("All Tags")
        self._flex(self._tags_combo, 80, 140)
        self._tags_combo.setToolTip("Filter by Tags")

        # Sort dropdown
        self._sort_combo = QComboBox()
        self._sort_combo.addItem("Sort: Name ↑", ("name", "ASC"))
        self._sort_combo.addItem("Sort: Name ↓", ("name", "DESC"))
        self._sort_combo.addItem("Sort: Date ↑", ("created_date", "ASC"))
        self._sort_combo.addItem("Sort: Date ↓", ("created_date", "DESC"))
        self._sort_combo.addItem("Sort: Duration ↑", ("duration_seconds", "ASC"))
        self._sort_combo.addItem("Sort: Duration ↓", ("duration_seconds", "DESC"))
        self._sort_combo.addItem("Sort: Recent", ("last_viewed_date", "DESC"))
        self._flex(self._sort_combo, 80, 150)
        self._sort_combo.setToolTip("Sort Animations")

    def _create_layout(self):
        """Create toolbar layout with filters and sorting.

        LIS fork: every gap is a named spacer (self._gaps) so a narrow window can
        squeeze the gaps first, see _fit_to_width().
        """

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 15, 0)  # Match old repo: 15px left/right
        layout.setSpacing(0)  # all spacing comes from the gaps below
        self._gaps = []

        def gap(width):
            item = QSpacerItem(width, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
            layout.addSpacerItem(item)
            self._gaps.append((item, width))

        # ===== SECTION 0: FAR LEFT - Folder tree toggle, which library =====
        layout.addWidget(self._folders_btn)
        gap(8)
        location = QGridLayout()
        location.setContentsMargins(0, 0, 0, 0)
        location.setHorizontalSpacing(6)
        location.setVerticalSpacing(2)
        location.setColumnStretch(0, 0)
        location.setColumnStretch(1, 1)
        location.addWidget(self._library_label, 0, 0)
        location.addWidget(self._library_combo, 0, 1)
        location.addWidget(self._folder_label, 1, 0)
        location.addWidget(self._folder_combo, 1, 1)
        layout.addLayout(location, 3)
        gap(16)

        # ===== SECTION 1: LEFT - Creation =====
        layout.addWidget(self._new_folder_btn)
        gap(16)  # Space after New Folder

        # ===== SECTION 2: MIDDLE-LEFT - Search & Filters =====
        layout.addWidget(self._search_box, 2)
        gap(8)
        layout.addWidget(self._rig_type_combo, 1)
        gap(8)
        layout.addWidget(self._tags_combo, 1)
        gap(8)
        layout.addWidget(self._sort_combo, 1)
        gap(24)  # Space after filters

        # ===== SECTION 3: MIDDLE-RIGHT - View & Edit Controls (grouped) =====
        layout.addWidget(self._view_mode_btn)
        gap(4)
        layout.addWidget(self._preview_speed_combo)
        gap(2)
        layout.addWidget(self._animated_btn)
        gap(4)
        layout.addWidget(self._grid_icon_label)
        gap(8)
        layout.addWidget(self._size_slider)
        gap(4)
        layout.addWidget(self._edit_mode_btn)
        gap(4)
        layout.addWidget(self._refresh_btn)

        # Stretch spacer to push right buttons to far right
        layout.addStretch()

        # ===== SECTION 4: RIGHT - Archive, Identity & System Buttons =====
        # Archive button separated from refresh to prevent accidental clicks
        layout.addWidget(self._delete_btn)
        gap(16)  # Extra spacing before identity pill
        layout.addWidget(self._identity_pill)
        gap(12)  # Space between pill and system buttons
        layout.addWidget(self._docs_btn)
        gap(4)
        layout.addWidget(self._about_btn)
        gap(4)
        layout.addWidget(self._console_btn)
        gap(4)
        layout.addWidget(self._help_btn)
        gap(4)
        layout.addWidget(self._settings_btn)
        gap(8)
        layout.addWidget(self._info_btn)  # far right, next to the panel it toggles

    def _connect_signals(self):
        """Connect internal signals"""

        # Library picker. `activated` fires only on a real user pick;
        # currentIndexChanged would also fire while arrowing through the list
        # with the keyboard, i.e. a library switch per keystroke.
        self._library_combo.activated.connect(self._on_library_activated)
        self._library_combo.customContextMenuRequested.connect(
            self._on_library_context_menu
        )

        # Search box
        self._search_box.textChanged.connect(self._on_search_text_changed)

        # Panel toggles (LIS fork)
        self._folders_btn.toggled.connect(self.folders_panel_toggled.emit)
        self._info_btn.toggled.connect(self.info_panel_toggled.emit)

        # Refresh button
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)

        # New folder button
        self._new_folder_btn.clicked.connect(self._on_new_folder_clicked)

        # View mode button
        self._view_mode_btn.clicked.connect(self._on_view_mode_clicked)

        # Card size slider
        self._size_slider.valueChanged.connect(self._on_card_size_changed)

        # Edit mode button
        self._edit_mode_btn.clicked.connect(self._on_edit_mode_clicked)
        self._animated_btn.toggled.connect(self.animated_previews_toggled.emit)
        self._animated_btn.toggled.connect(lambda _on: self._update_previews_icon())
        self._update_previews_icon()

        # Delete button
        self._delete_btn.clicked.connect(self._on_delete_clicked)

        # Settings button
        self._settings_btn.clicked.connect(self.settings_clicked.emit)

        # Identity pill — re-emits as identity_pill_clicked for the parent
        # to open Settings → Identity tab.
        self._identity_pill.clicked.connect(self.identity_pill_clicked.emit)

        # Help button
        self._help_btn.clicked.connect(self.help_clicked.emit)

        # About button
        self._about_btn.clicked.connect(self._on_about_clicked)
        self._docs_btn.clicked.connect(self._on_docs_clicked)

        # Console button
        self._console_btn.clicked.connect(self._on_console_clicked)

        # Filter and sort dropdowns
        self._rig_type_combo.currentIndexChanged.connect(self._on_rig_type_filter_changed)
        self._tags_combo.currentIndexChanged.connect(self._on_tags_filter_changed)
        self._sort_combo.currentIndexChanged.connect(self._on_sort_changed)

        # Event bus - button states
        self._event_bus.delete_button_enabled.connect(self._delete_btn.setEnabled)

        # Theme changes - reload icons with new color
        self._theme_manager.theme_changed.connect(self._on_theme_changed)

    def _update_delete_button_mode(self, icon_color: str = None):
        """
        Update delete button icon and tooltip based on operation mode.
        
        Solo mode: trash icon, "Delete Selected"
        Studio/Pipeline mode: archive icon, "Archive Selected"
        """
        if icon_color is None:
            theme = self._theme_manager.get_current_theme()
            icon_color = theme.palette.header_icon_color if theme else "#1a1a1a"
        
        if Config.is_solo_mode():
            # Solo mode - instant delete
            delete_icon_path = IconLoader.get("delete")
            delete_icon = colorize_white_svg(delete_icon_path, icon_color)
            self._delete_btn.setIcon(delete_icon)
            self._delete_btn.setToolTip("Delete Selected (Del)")
        else:
            # Studio/Pipeline mode - archive (soft delete)
            archive_icon_path = IconLoader.get("archive_icon")
            archive_icon = colorize_white_svg(archive_icon_path, icon_color)
            self._delete_btn.setIcon(archive_icon)
            self._delete_btn.setToolTip("Archive Selected (Del)")

    def _on_theme_changed(self, theme_name: str):
        """Reload all icons when theme changes"""
        theme = self._theme_manager.get_current_theme()
        if not theme:
            return

        icon_color = theme.palette.header_icon_color

        # Reload all icons with new color
        add_icon = colorize_white_svg(IconLoader.get("add"), icon_color)
        self._new_folder_btn.setIcon(add_icon)

        refresh_icon = colorize_white_svg(IconLoader.get("refresh"), icon_color)
        self._refresh_btn.setIcon(refresh_icon)

        view_mode_icon = colorize_white_svg(IconLoader.get("view_mode"), icon_color)
        self._view_mode_btn.setIcon(view_mode_icon)
        self._folders_btn.setIcon(colorize_white_svg(IconLoader.get("panel_left"), icon_color))
        self._info_btn.setIcon(colorize_white_svg(IconLoader.get("panel_right"), icon_color))
        for lbl in (self._library_label, self._folder_label):
            lbl.setStyleSheet(f"color: {icon_color}; font-size: 8pt;")
        self._previews_icon_color = icon_color
        self._update_previews_icon()

        grid_icon = colorize_white_svg(IconLoader.get("resize_grid"), icon_color)
        self._grid_icon_label.setPixmap(grid_icon.pixmap(20, 20))

        edit_icon = colorize_white_svg(IconLoader.get("edit"), icon_color)
        self._edit_mode_btn.setIcon(edit_icon)

        # Update delete button based on mode
        self._update_delete_button_mode(icon_color)

        about_icon = colorize_white_svg(IconLoader.get("al_icon"), icon_color)
        self._about_btn.setIcon(about_icon)

        console_icon = colorize_white_svg(IconLoader.get("console"), icon_color)
        self._console_btn.setIcon(console_icon)

        settings_icon = colorize_white_svg(IconLoader.get("settings"), icon_color)
        self._settings_btn.setIcon(settings_icon)

        # Force style refresh for gradient background
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    # ---- Responsive header (LIS fork) ---------------------------------------------
    # Text boxes stretch between a minimum and their old width; when even the
    # minimums don't fit, the least important items are hidden one by one (and come
    # back as the window grows), so nothing overlaps any more.

    @staticmethod
    def _flex(combo, min_w, max_w):
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(4)
        combo.setMinimumWidth(min_w)
        combo.setMaximumWidth(max_w)
        combo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def _optional_groups(self):
        """Hidden first -> last when the header is too narrow (after the gaps are gone)."""
        return [
            [self._grid_icon_label, self._size_slider],   # Num -/+ still work
            [self._console_btn],
            [self._about_btn],
            [self._docs_btn],                             # F1 still works
            [self._library_label, self._folder_label],
        ]

    def _fits(self):
        layout = self.layout()
        layout.invalidate()
        return layout.minimumSize().width() <= self.width()

    def _fit_to_width(self):
        """Squeeze in priority order until the header fits:
        1. gaps and side margins, 2. search / filters (they shrink to their minimum
        on their own), 3. hide optional items one group at a time, 4. last of all
        let the library / folder boxes go below their comfortable width."""
        layout = self.layout()
        # Start from the roomy layout
        layout.setContentsMargins(15, 0, 15, 0)
        for item, width in self._gaps:
            item.changeSize(width, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        for combo in (self._library_combo, self._folder_combo):
            combo.setMinimumWidth(self.LOCATION_MIN_WIDE)
        groups = self._optional_groups()
        for group in groups:
            for w in group:
                w.setVisible(True)

        if not self._fits():
            layout.setContentsMargins(4, 0, 4, 0)
            for item, width in self._gaps:
                item.changeSize(min(width, 2), 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        for group in groups:
            if self._fits():
                break
            for w in group:
                w.setVisible(False)
        if not self._fits():
            for combo in (self._library_combo, self._folder_combo):
                combo.setMinimumWidth(self.LOCATION_MIN_TIGHT)
        self._elide_folder()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_to_width()

    def _elide_folder(self):
        # Full path; _LocationCombo cuts it at the left edge when painting.
        if self._folder_combo.count() == 0:
            self._folder_combo.addItem(self._folder_path)
        else:
            self._folder_combo.setItemText(0, self._folder_path)

    def _update_previews_icon(self):
        """Icon shows the current STATE: play triangle while previews play, pause bars while off."""
        name = "play" if self._animated_btn.isChecked() else "pause"
        self._animated_btn.setIcon(colorize_white_svg(IconLoader.get(name), self._previews_icon_color))
        self._animated_btn.setToolTip(
            ("Previews are playing - click to stop. " if self._animated_btn.isChecked()
             else "Play each card's preview in the grid. ")
            + "Previews are prepared the first time you view them. (P)")

    def set_current_folder(self, path: str):
        """Show the folder being viewed (full path in the tooltip, left-elided in the box)."""
        self._folder_path = path or ""
        self._elide_folder()
        self._folder_combo.setToolTip(f"{self._folder_path}\nClick or Shift+B: go to folder")

    def set_panel_buttons(self, folders_visible: bool, info_visible: bool):
        """Restore the saved panel visibility; emits the toggled signals only if a state changes."""
        self._folders_btn.setChecked(bool(folders_visible))
        self._info_btn.setChecked(bool(info_visible))

    def refresh_mode(self):
        """Refresh button appearance when operation mode changes."""
        self._update_delete_button_mode()

    def _on_search_text_changed(self, text: str):
        """Handle search text change"""
        self.search_text_changed.emit(text)
        self._event_bus.set_search_text(text)

    def _on_refresh_clicked(self):
        """Handle refresh library button click"""
        self.refresh_library_clicked.emit()

    def _on_new_folder_clicked(self):
        """Handle new folder button click"""
        self.new_folder_clicked.emit()

    def _on_view_mode_clicked(self):
        """Handle view mode button click"""

        # Toggle mode
        if self._view_mode == "grid":
            self._view_mode = "list"
            self._size_slider.setEnabled(False)  # Size only for grid
        else:
            self._view_mode = "grid"
            self._size_slider.setEnabled(True)

        # Update button checked state (stays icon-only)
        self._view_mode_btn.setChecked(self._view_mode == "grid")

        # Emit signals
        self.view_mode_changed.emit(self._view_mode)
        self._event_bus.set_view_mode(self._view_mode)

    def _on_card_size_changed(self, size: int):
        """Handle card size slider change"""

        self._card_size = size

        # Emit signals
        self.card_size_changed.emit(size)
        self._event_bus.set_card_size(size)

    def is_animated_previews_on(self) -> bool:
        return self._animated_btn.isChecked()

    def set_animated_previews(self, enabled: bool):
        """Restore the saved state without re-emitting during startup."""
        self._animated_btn.blockSignals(True)
        self._animated_btn.setChecked(bool(enabled))
        self._animated_btn.blockSignals(False)
        self._update_previews_icon()

    def get_card_size(self) -> int:
        """Current card size - for persisting across sessions."""
        return self._card_size

    def set_card_size(self, size: int):
        """Restore a saved card size. Moving the slider drives the view through
        the normal change signal, so this both updates the control and resizes
        the cards."""
        size = max(Config.MIN_CARD_SIZE, min(Config.MAX_CARD_SIZE, int(size)))
        self._size_slider.setValue(size)

    def _on_edit_mode_clicked(self):
        """Handle edit mode button click"""

        self._edit_mode = self._edit_mode_btn.isChecked()

        # Emit signals
        self.edit_mode_changed.emit(self._edit_mode)
        self._event_bus.set_edit_mode(self._edit_mode)

    def _on_delete_clicked(self):
        """Handle delete button click"""
        self.delete_clicked.emit()

    def _on_docs_clicked(self):
        """Docs button pressed.

        A plain method rather than connecting clicked -> docs_clicked.emit:
        QPushButton.clicked carries a `checked` bool, and emit() of a no-argument
        signal would choke on it.
        """
        self.docs_clicked.emit()

    def _on_about_clicked(self):
        """Handle about button click"""
        self.about_clicked.emit()

        # Show About dialog
        from .dialogs.about_dialog import AboutDialog

        dialog = AboutDialog(self, self._theme_manager)
        dialog.exec()

    def _on_console_clicked(self):
        """Handle console button click"""
        self.console_clicked.emit()

        # Show Console/Logs dialog
        from .dialogs.log_console_dialog import LogConsoleDialog

        dialog = LogConsoleDialog(self, self._theme_manager)
        dialog.exec()

    def _on_rig_type_filter_changed(self, index: int):
        """Handle rig type filter change"""
        if index == 0:
            # "All Rig Types" selected
            self.rig_type_filter_changed.emit([])
        else:
            # Specific rig type selected
            rig_type = self._rig_type_combo.currentText()
            self.rig_type_filter_changed.emit([rig_type])

    def _on_tags_filter_changed(self, index: int):
        """Handle tags filter change"""
        if index == 0:
            # "All Tags" selected
            self.tags_filter_changed.emit([])
        else:
            # Specific tag selected
            tag = self._tags_combo.currentText()
            self.tags_filter_changed.emit([tag])

    def _on_sort_changed(self, index: int):
        """Handle sort option change"""
        # Get sort data from combobox item
        sort_data = self._sort_combo.itemData(index)
        if sort_data:
            sort_by, sort_order = sort_data
            self.sort_changed.emit(sort_by, sort_order)

    def _refresh_filter_data(self):
        """Refresh filter dropdown data from database"""
        # Get all unique rig types
        rig_types = self._db_service.get_all_rig_types()

        # Update rig type combo
        self._rig_type_combo.blockSignals(True)  # Prevent triggering filter change
        self._rig_type_combo.clear()
        self._rig_type_combo.addItem("All Rig Types")
        for rig_type in rig_types:
            self._rig_type_combo.addItem(rig_type)
        self._rig_type_combo.blockSignals(False)

        # Get all unique tags
        tags = self._db_service.get_all_tags()

        # Update tags combo
        self._tags_combo.blockSignals(True)  # Prevent triggering filter change
        self._tags_combo.clear()
        self._tags_combo.addItem("All Tags")
        for tag in tags:
            self._tags_combo.addItem(tag)
        self._tags_combo.blockSignals(False)

    # ==================== LIBRARY PICKER ====================

    def refresh_libraries(self):
        """Rebuild the library picker from the known-libraries list.

        Also the revert path: call this after a switch is cancelled or fails and
        the combo snaps back to the real current library, with no index
        bookkeeping to get wrong.
        """
        from ..services.known_libraries import get_known_libraries_store

        libraries = get_known_libraries_store().list_libraries()

        # Repopulating fires currentIndexChanged; block it so rebuilding the list
        # can never be mistaken for the user choosing something.
        self._library_combo.blockSignals(True)
        try:
            self._library_combo.clear()

            current_index = 0
            for i, lib in enumerate(libraries):
                label = lib['label']
                if not lib['exists']:
                    # Unavailable, NOT gone: an offline network path must stay
                    # listed, or the list silently empties itself whenever you're
                    # off the VPN.
                    label = f"{label}  (unavailable)"
                self._library_combo.addItem(label, lib['path'])
                self._library_combo.setItemData(
                    i, lib['path'], Qt.ItemDataRole.ToolTipRole
                )
                if not lib['exists']:
                    item = self._library_combo.model().item(i)
                    if item is not None:
                        item.setEnabled(False)
                if lib['is_current']:
                    current_index = i

            if libraries:
                self._library_combo.insertSeparator(self._library_combo.count())
            self._library_combo.addItem("Browse for another folder...", self.BROWSE_LIBRARY)

            self._library_combo.setCurrentIndex(current_index)
        finally:
            self._library_combo.blockSignals(False)

    def _on_library_context_menu(self, pos):
        """Right-click on the picker: forget a library.

        The CURRENT library is deliberately not offered - forgetting it would be
        meaningless, since the list re-seeds itself with whatever library is in
        use and it would reappear immediately.
        """
        from ..services.known_libraries import get_known_libraries_store

        removable = [
            lib for lib in get_known_libraries_store().list_libraries()
            if not lib['is_current']
        ]

        menu = QMenu(self)

        if not removable:
            empty = menu.addAction("No other libraries to forget")
            empty.setEnabled(False)
        else:
            forget_menu = menu.addMenu("Forget")
            for lib in removable:
                label = lib['label']
                if not lib['exists']:
                    label = f"{label}  (unavailable)"
                action = forget_menu.addAction(label)
                action.setData(lib['path'])
                action.setToolTip(lib['path'])
            forget_menu.triggered.connect(
                lambda action: self.library_forget_requested.emit(action.data())
            )

        menu.exec(self._library_combo.mapToGlobal(pos))

    def _on_library_activated(self, index: int):
        """Handle a user picking a library.

        Wired to `activated`, NOT `currentIndexChanged`: the latter also fires
        while arrowing through a combo with the keyboard, which would try to
        switch library on every keystroke.
        """
        path = self._library_combo.itemData(index)
        if not path:
            return

        if path == self.BROWSE_LIBRARY:
            self.library_browse_requested.emit()
            return

        # Ignore re-picking the library we're already on. Normalize BOTH sides:
        # stored paths keep their original casing (so labels read correctly), so
        # a raw string compare would miss on Windows.
        current = Config.load_library_path()
        if current:
            def key(p):
                return os.path.normcase(os.path.normpath(str(p)))
            if key(path) == key(current):
                return

        self.library_switch_requested.emit(str(path))

    def refresh_filters(self):
        """Public method to refresh filter data (e.g., after library refresh)"""
        self._refresh_filter_data()


__all__ = ['HeaderToolbar']
