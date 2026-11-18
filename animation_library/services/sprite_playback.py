# Modified in Action Library LIS Fork, 2026-11 (based on Action Library 1.6.2 by CGstuff). See FORK_CHANGES.md.
"""
SpritePlaybackService - animated cards in the grid.

Playback is drawing a sub-rectangle of a cached sprite sheet: no video decoding
happens while cards are on screen. Measured on a 30-card grid at 15fps this costs
about 0.3% of one core, against ~122% for decoding the webms live. See
services/preview_sprites.py for how the sheets are made and why.

The three things that keep it cheap:

  ONLY VISIBLE CARDS. The view reports which uuids are on screen; sheets are
  built for those and dropped for everything else. Scrolling through a thousand
  animations never holds more than a screenful.

  BUILT OFF-THREAD. First view of a clip costs ~72ms to decode into a sheet, so
  it happens on a worker. Requests for cards that scrolled away before their
  build started are dropped rather than wasted.

  ONE TIMER, NOT ONE PER CARD. A single tick advances every card and asks the
  view to repaint once.

Each card starts on a different frame, so a grid of walk cycles doesn't march in
lockstep - that looks like a glitch rather than a library.
"""

import logging
import os
from typing import Dict, Optional, Set, Tuple

from PyQt6.QtCore import QObject, QRect, QRunnable, QThreadPool, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap

from ..config import Config
from . import preview_sprites

logger = logging.getLogger(__name__)

DEFAULT_FPS = 15
# LIS fork: playback presets. The original pace - one sheet frame per tick at 15 fps,
# whatever the clip's length - made configurable: four "Frame Skip" presets, each
# (show every N-th sheet frame, frames per second), edited in Settings > Appearance
# and picked in the header. FS1 = the original. (A real-time mode was tried and
# dropped: with at most 24 frames per sheet it looked choppier than this.)
PREVIEW_MODE_KEY = "view/preview_mode"        # "fs1".."fs4"
DEFAULT_FS_PRESETS = [(1, 15), (1, 30), (2, 15), (2, 30)]
# Keep a little beyond the visible set so a small scroll doesn't rebuild.
# Animated previews are on out of the box. Measured at 1000 animations the
# grid costs ~0.3% of a core and holds ~75MB of sheets, both bounded by
# eviction, so there's no reason to make people find the toggle first.
DEFAULT_ANIMATED_PREVIEWS = True

EVICT_MARGIN = 12


class _BuildSignals(QObject):
    done = pyqtSignal(str, object)      # uuid, meta dict or None


class _BuildTask(QRunnable):
    """Decode one preview into a sprite sheet, off the UI thread."""

    def __init__(self, uuid: str, preview_path: str, frame_size: int):
        super().__init__()
        self.uuid = uuid
        self.preview_path = preview_path
        self.frame_size = frame_size
        self.signals = _BuildSignals()

    def run(self):
        try:
            meta = preview_sprites.get_or_build(
                self.uuid, self.preview_path, frame_size=self.frame_size)
        except Exception as e:
            logger.debug(f"Sprite build failed for {self.uuid}: {e}")
            meta = None
        self.signals.done.emit(self.uuid, meta)


class SpritePlaybackService(QObject):
    """Drives animated previews for the cards currently on screen."""

    # The view connects this to viewport().update(). One repaint per tick,
    # not one per card.
    frame_advanced = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._enabled = False
        self._fps = DEFAULT_FPS
        self._frame_size = preview_sprites.DEFAULT_FRAME_SIZE

        self._sheets: Dict[str, dict] = {}        # uuid -> sheet meta
        self._pixmaps: Dict[str, QPixmap] = {}    # uuid -> loaded sheet
        self._phase: Dict[str, int] = {}          # uuid -> starting frame
        self._visible: Set[str] = set()
        self._pending: Set[str] = set()           # builds in flight

        self._tick_count = 0
        self._builds_since_prune = 0
        from PyQt6.QtCore import QSettings
        s = QSettings(Config.APP_AUTHOR, Config.APP_NAME)
        self._mode = s.value(PREVIEW_MODE_KEY, "fs1", type=str)
        if self._mode not in ("fs1", "fs2", "fs3", "fs4"):  # older values ("time", "fs")
            self._mode = "fs1"
        self._fs_presets = []
        for i, (step, fps) in enumerate(DEFAULT_FS_PRESETS, start=1):
            self._fs_presets.append((
                max(1, s.value(f"view/fs{i}_step", step, type=int)),
                max(1, s.value(f"view/fs{i}_fps", fps, type=int))))
        # A dedicated pool, deliberately not the global one. Sheet building is
        # the heaviest thing this app does (video decode per clip) and it is
        # pure nicety - it must never compete with thumbnail loading, and it
        # must never take the machine away from Blender running alongside.
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(
            max(1, min(3, (os.cpu_count() or 4) // 4)))

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # ==================== CONTROL ====================

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool):
        """Turn animated previews on or off."""
        if enabled == self._enabled:
            return
        self._enabled = enabled
        if enabled:
            # Trim the on-disk cache once per session rather than on every
            # build - scanning the directory each time would be wasteful.
            try:
                preview_sprites.prune_cache()
            except Exception as e:
                logger.debug(f"Sprite cache prune failed: {e}")
            self._timer.start(self._tick_interval())
        else:
            self._timer.stop()
            self._clear()
            self.frame_advanced.emit()      # repaint back to static thumbnails

    def pause(self):
        """Stop ticking but keep the sheets - e.g. the window lost focus."""
        if self._timer.isActive():
            self._timer.stop()

    def resume(self):
        if self._enabled and not self._timer.isActive():
            self._timer.start(self._tick_interval())

    def get_mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str):
        """Pick preset "fs1".."fs4"; saved for next start."""
        from PyQt6.QtCore import QSettings
        self._mode = mode
        QSettings(Config.APP_AUTHOR, Config.APP_NAME).setValue(PREVIEW_MODE_KEY, mode)
        self._restart_timer()

    def get_fs_presets(self):
        """[(step, fps)] for FS1..FS4."""
        return list(self._fs_presets)

    def set_fs_preset(self, index: int, step: int, fps: int):
        """Edit preset FS<index> (1-based): every `step`-th sheet frame at `fps`."""
        from PyQt6.QtCore import QSettings
        self._fs_presets[index - 1] = (max(1, int(step)), max(1, int(fps)))
        s = QSettings(Config.APP_AUTHOR, Config.APP_NAME)
        s.setValue(f"view/fs{index}_step", self._fs_presets[index - 1][0])
        s.setValue(f"view/fs{index}_fps", self._fs_presets[index - 1][1])
        self._restart_timer()

    def _active_fs(self):
        """(step, fps) of the selected preset."""
        return self._fs_presets[int(self._mode[2:]) - 1]

    def _tick_interval(self) -> int:
        return max(1, int(1000 / self._active_fs()[1]))

    def _restart_timer(self):
        if self._timer.isActive():
            self._timer.start(self._tick_interval())

    def set_frame_size(self, size: int):
        """Card size changed; sheets are size-specific so start over."""
        if size != self._frame_size:
            self._frame_size = size
            self._clear()

    # ==================== VISIBILITY ====================

    def set_visible(self, entries: Dict[str, str]):
        """Tell the service which cards are on screen: {uuid: preview_path}.

        Called on scroll and after any reload. Builds what's newly visible and
        evicts what's scrolled away.
        """
        if not self._enabled:
            return

        self._visible = set(entries)

        for uuid, preview_path in entries.items():
            if uuid in self._sheets or uuid in self._pending or not preview_path:
                continue
            self._pending.add(uuid)
            task = _BuildTask(uuid, preview_path, self._frame_size)
            task.signals.done.connect(self._on_built)
            self._pool.start(task)

        self._evict()

    def _evict(self):
        """Drop sheets for cards that are no longer on screen."""
        if len(self._sheets) <= len(self._visible) + EVICT_MARGIN:
            return
        for uuid in [u for u in self._sheets if u not in self._visible]:
            self._sheets.pop(uuid, None)
            self._pixmaps.pop(uuid, None)
            self._phase.pop(uuid, None)

    def _on_built(self, uuid: str, meta):
        self._pending.discard(uuid)
        # Scrolled away - or previews were switched off - while we were
        # building. Throw it away rather than holding a sheet nobody can see.
        # A worker that finishes after set_enabled(False) would otherwise
        # repopulate the cache we just cleared.
        if not self._enabled or not meta or uuid not in self._visible:
            return
        pixmap = QPixmap(meta['path'])
        if pixmap.isNull():
            return
        self._sheets[uuid] = meta
        self._pixmaps[uuid] = pixmap

        # Re-check the cap occasionally: a long session browsing a big library
        # can add a lot of sheets after the initial prune.
        self._builds_since_prune += 1
        if self._builds_since_prune >= 50:
            self._builds_since_prune = 0
            try:
                preview_sprites.prune_cache()
            except Exception as e:
                logger.debug(f"Sprite cache prune failed: {e}")
        # Stagger the start so identical cycles don't play in lockstep.
        self._phase[uuid] = (hash(uuid) % max(1, meta.get('count', 1)))
        self.frame_advanced.emit()

    # ==================== PLAYBACK ====================

    def _tick(self):
        self._tick_count += 1
        if self._pixmaps:
            self.frame_advanced.emit()

    def has_sheet(self, uuid: str) -> bool:
        """Is this card actually animating? Lets the view repaint only those."""
        return self._enabled and uuid in self._pixmaps

    def get_frame(self, uuid: str) -> Optional[Tuple[QPixmap, QRect]]:
        """Current (sheet, source rect) for a card, or None to use the thumbnail."""
        if not self._enabled:
            return None
        meta = self._sheets.get(uuid)
        pixmap = self._pixmaps.get(uuid)
        if not meta or pixmap is None:
            return None

        # The REAL frame count, never columns*rows. The grid has spare cells at
        # the end (24 frames tile as 5x5 = 25) and cycling over those showed a
        # blank flash at the end of every loop.
        count = meta.get('count') or 0
        if count <= 0:
            return None
        # One tick = `step` sheet frames of the selected preset (LIS fork)
        frame = (self._tick_count * self._active_fs()[0] + self._phase.get(uuid, 0)) % count
        size = meta['frame_size']
        row, col = divmod(frame, meta['columns'])
        return pixmap, QRect(col * size, row * size, size, size)

    def _clear(self):
        self._visible.clear()
        self._sheets.clear()
        self._pixmaps.clear()
        self._phase.clear()
        self._pending.clear()


_instance: Optional[SpritePlaybackService] = None


def get_sprite_playback() -> SpritePlaybackService:
    global _instance
    if _instance is None:
        _instance = SpritePlaybackService()
    return _instance


__all__ = ['SpritePlaybackService', 'get_sprite_playback']
