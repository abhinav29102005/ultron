"""
ui/tray.py – System tray icon and menu
=======================================
Show / Hide / Quit. The tray is the only guaranteed way out of a frameless
Qt.Tool window, so `available` must be checked by the caller: when the platform
reports no tray, MainWindow falls back to a right-click Quit menu on the orb.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QBrush, QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from config.logging_config import get_logger
from ui.orb_widget import color_for_state

logger = get_logger("ui.tray")


def make_orb_icon(state: str = "IDLE", size: int = 32) -> QIcon:
    """Build the tray icon in code — the repo ships no icon asset."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    color = QColor(color_for_state(state))
    painter.setBrush(QBrush(color))
    painter.setPen(QPen(color.lighter(140), 1.5))
    inset = size * 0.14
    painter.drawEllipse(int(inset), int(inset), int(size - inset * 2), int(size - inset * 2))
    painter.end()
    return QIcon(pixmap)


class TrayController(QObject):
    """QSystemTrayIcon plus its menu, reduced to three signals."""

    show_requested = pyqtSignal()
    hide_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._tray: QSystemTrayIcon | None = None
        self._menu: QMenu | None = None

        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning(
                "No system tray available; MainWindow must supply a fallback quit path.",
            )
            return

        self._tray = QSystemTrayIcon(make_orb_icon("IDLE"), self)
        self._tray.setToolTip("ULTRON")

        self._menu = QMenu()
        show_action = QAction("Show", self._menu)
        show_action.triggered.connect(self.show_requested.emit)
        hide_action = QAction("Hide", self._menu)
        hide_action.triggered.connect(self.hide_requested.emit)
        quit_action = QAction("Quit", self._menu)
        quit_action.triggered.connect(self.quit_requested.emit)

        self._menu.addAction(show_action)
        self._menu.addAction(hide_action)
        self._menu.addSeparator()
        self._menu.addAction(quit_action)

        # The tray's context menu is a separate native window, so it does not
        # inherit the orb's capture exclusion. It is also the menu that
        # actually appears in practice — the orb's own fallback menu is only
        # wired up when there is no tray at all. Left alone, right-clicking
        # the tray icon mid-call puts "Show / Hide / Quit" on the shared
        # screen. The popup's handle is created lazily, so this runs each
        # time it is about to be shown.
        self._menu.aboutToShow.connect(self._hide_menu_from_capture)

        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

    @property
    def available(self) -> bool:
        """False when the platform has no tray — caller must provide a way to quit."""
        return self._tray is not None

    def _hide_menu_from_capture(self) -> None:
        """Exclude the tray popup from screen capture, best effort."""
        if self._menu is None:
            return
        try:
            from vision.screen_hider import hide_from_capture

            self._menu.winId()  # force the native handle into existence
            hide_from_capture(self._menu)
        except Exception as exc:  # pragma: no cover - platform dependent
            logger.debug("Could not hide the tray menu from capture: {}", exc)

    def set_state(self, state: str) -> None:
        if self._tray is not None:
            self._tray.setIcon(make_orb_icon(state))
            # Deliberately stateless. A tray tooltip is drawn by the shell, not
            # by a window we own, so SetWindowDisplayAffinity cannot reach it —
            # "ULTRON — Listening" would be readable on a shared screen with no
            # way to suppress it. The icon already conveys state to the user.
            self._tray.setToolTip("ULTRON")

    def hide(self) -> None:
        if self._tray is not None:
            self._tray.hide()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_requested.emit()
