# Action Library LIS Fork — changes

Fork of [Action Library](https://github.com/CGstuff/Action-Library) by CGstuff,
based on release **1.6.2**. Licensed under the GNU GPL v3, same as the original
(see `LICENSE`). Every modified file carries a notice in its first line.
Changes made with AI assistance (Claude, Anthropic), reviewed and tested by the maintainer — see README.

| Change | Files |
|---|---|
| Home shows only animations that are in no folder; Home is selected on startup | `models/animation_filter_proxy_model.py`, `widgets/controllers/filter_controller.py`, `widgets/main_window.py` |
| Fix: folder tree jumped to a same-named folder (`Adult/Baby` → root `Baby`) | `widgets/folder_tree.py` |
| Fix (Windows): preview videos kept open blocked delete/archive, leaving folders with only the `.webm` | `widgets/main_window.py`, `services/archive_service.py`, `widgets/controllers/archive_trash_controller.py` |
| Card context menu (archive, remove from folder, tags, favorites, delete) acts on the whole multi-selection | `widgets/main_window.py` |
| Status badge sets the status for the whole multi-selection | `widgets/metadata_panel.py`, `widgets/main_window.py` |
| **Move to Folder** in the context menu: add to the picked folder + remove from the current one; picker with full paths and a filter | `widgets/main_window.py`, `widgets/dialogs/folder_picker_dialog.py` (new) |
| Grid scrolls to the top when switching folders | `widgets/main_window.py` |
| Settings → Appearance → **Mouse Wheel Scroll** (px per notch) | `views/animation_view.py`, `widgets/settings/theme_tab.py` |
| Settings → Appearance → **Show status bar** (errors go to a dialog when hidden) | `widgets/main_window.py`, `widgets/settings/theme_tab.py` |
| New animations get status **None** instead of WIP (DB insert default; badge fallback) | `services/database/animations.py`, `widgets/metadata_panel.py` |
| Settings dialog fits the screen: pages scroll, the window opens no larger than the free screen area and can be made smaller | `widgets/settings/settings_dialog.py` |
| **Keyboard shortcuts** (Settings → Shortcuts): archive/delete, move/add to folder, remove from folder, tags, gradient, favorite, rename, statuses, previews, grid/list, edit mode, sort, tags filter, card size (Num -/+), reload, search, clear selection, help, docs. Every action has a main and an alternative binding; mouse-wheel bindings are supported (default alternative: Ctrl+Wheel = card size). Character keys work by physical position (QWERTY) under any layout; help overlay lists the current bindings | `services/shortcuts.py` (new), `widgets/settings/shortcuts_tab.py` (new), `widgets/settings/settings_dialog.py`, `widgets/main_window.py`, `widgets/help_overlay.py` |
| Card preview playback presets **FS1–FS4** (Frame Skip: every N-th preview frame at M fps), picked in the header next to Previews, each edited in Settings → Appearance; FS1 = the original pace (1 frame, 15 fps). Previews start paused on launch and, when turned on, play right away (they used to wait for the first scroll). Settings window opens taller (900×860, capped to the screen) | `services/sprite_playback.py`, `widgets/header_toolbar.py`, `widgets/settings/theme_tab.py`, `widgets/settings/settings_dialog.py`, `widgets/main_window.py`, `views/animation_view.py` |
| Settings: number boxes (folder text size, wheel step, Blender port) wide enough to show their value next to the up/down buttons | `widgets/settings/theme_tab.py`, `widgets/settings/blender_integration_tab.py` |
| Previews button shows its state: play icon while previews play, pause icon when off | `widgets/header_toolbar.py` |
| Video preview follows the info panel's splitter (grows and shrinks; it was locked to the size of the first frame) | `widgets/video_preview_widget.py` |
| Run from source on Windows: own taskbar entry with the app icon instead of Python's (explicit AppUserModelID) | `main.py` |
| Version `1.6.2-lis` when run from source (was the stale fallback `1.4.1`); the update check looks at this fork's releases, not upstream's (an upstream update would replace the fork) | `config.py`, `services/update_service.py` |
| Max card size 475 px (was 300) for the full-width grid with the panels hidden; thumbnails are loaded at that size so they stay sharp | `config.py`, `services/thumbnail_loader.py` |
| **Panel toggles**: header buttons (far left / far right) and shortcuts B / I show or hide the folder tree and the info panel; state and widths survive restarts | `widgets/header_toolbar.py`, `widgets/main_window.py`, `utils/icon_loader.py`, `icons/panel_left.svg`, `icons/panel_right.svg` (new), `services/shortcuts.py` |
| **Folder navigation from the keyboard** (works with the tree hidden): Shift+B folder picker at the cursor, Alt+←/→ previous/next folder on the same level, Alt+↑ parent, Alt+↓ first subfolder; no wrap-around. The built-in folders (Home, Actions, Poses, ...) sit one level above the user folders: Alt+←/→ moves between them, Alt+↓ goes to the first user folder, Alt+↑ from a top-level user folder goes to Home; Archive / Trash are left out | `widgets/folder_tree.py`, `widgets/main_window.py`, `services/shortcuts.py` |
| Folder picker, Add Tags and Remove Tag open at the mouse cursor and close on a click outside (= Cancel); one click in the folder picker picks the folder | `utils/popup_dialog.py` (new), `widgets/dialogs/folder_picker_dialog.py`, `widgets/dialogs/tag_input_dialog.py`, `widgets/controllers/bulk_edit_controller.py`, `widgets/main_window.py` |
| Header: **Current Library** / **Current Folder** boxes stacked on the left; the folder box shows the path being viewed and opens the folder picker on click. The header is responsive and gives way in this order: gaps and margins, search and filters, then size slider / Console / About / Docs / box labels are hidden, and only then do the library and folder boxes get narrower. Box text is cut at the edge only (library at the right, folder path at the left), never in the middle | `widgets/header_toolbar.py`, `widgets/main_window.py` |

Paths are relative to `animation_library/`. Settings keys (QSettings) and the
user data folder are unchanged, so the fork reads an existing installation's
settings and library as is.
