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

Paths are relative to `animation_library/`. Settings keys (QSettings) and the
user data folder are unchanged, so the fork reads an existing installation's
settings and library as is.
