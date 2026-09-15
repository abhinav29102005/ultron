"""
ui/chat_panel.py – The expanded card's contents
================================================
History bubbles, a text box, a mic button, the model-switch control and the
collapse control. Pure Qt: it emits signals and never touches the event bus,
the container or the pipeline.
"""

from __future__ import annotations

from PyQt6.QtCore import QBuffer, QEvent, QIODevice, QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

USER_BUBBLE = "#2f6feb"
FRIDAY_BUBBLE = "#2b2c33"
NOTE_COLOR = "#c9a227"

#: Shown when an image paste is swallowed. A QLineEdit cannot display the
#: picture, so without a line saying something happened, Ctrl+V on a
#: screenshot looks exactly like a broken paste.
PASTE_NOTE = "[screenshot attached]"

#: What an image submitted with no typed question is taken to mean. Without
#: it, pasting a screenshot and pressing Enter does nothing at all, because
#: the submit path refuses empty text.
PASTE_DEFAULT_QUESTION = "What's in this screenshot?"


def png_bytes(image: QImage) -> bytes:
    """A QImage as PNG bytes.

    PNG, not JPEG: the first thing done with a pasted screenshot is OCR, and
    JPEG's ringing around high-contrast edges is worst on small text, which is
    most of what these images contain. Encoded once here, at paste time,
    because everything downstream — the OCR engine, the vision model, the
    tests — wants bytes rather than a Qt object.
    """
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())

PANEL_STYLESHEET = """
QWidget#chatPanel {
    background: transparent;
    color: #e8e8ea;
    font-family: 'Segoe UI', sans-serif;
    font-size: 12px;
}
QScrollArea, QWidget#historyHost {
    background: transparent;
    border: none;
}
QScrollBar:vertical {
    background: transparent;
    width: 6px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #3a3b44;
    border-radius: 3px;
    min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QLineEdit {
    background-color: #26272e;
    border: 1px solid #34353c;
    border-radius: 14px;
    padding: 6px 10px;
    color: #e8e8ea;
}
QLineEdit:focus { border: 1px solid #4dabf7; }
QLineEdit:disabled { color: #5c5f66; }
QPushButton#send, QPushButton#mic {
    background-color: #34353c;
    color: #e8e8ea;
    border: none;
    border-radius: 14px;
    padding: 6px 10px;
    font-weight: 600;
}
QPushButton#send:hover, QPushButton#mic:hover { background-color: #43444d; }
QPushButton#send:disabled, QPushButton#mic:disabled { background-color: #26272e; color: #5c5f66; }
QPushButton#chip {
    background-color: #26272e;
    color: #9a9ba3;
    border: 1px solid #34353c;
    border-radius: 9px;
    padding: 2px 8px;
    font-size: 10px;
    font-weight: 600;
}
QPushButton#chip:hover { color: #e8e8ea; border-color: #4dabf7; }
"""


class _Bubble(QLabel):
    """One history line. A label with a rounded background."""

    def __init__(self, role: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        if role == "user":
            bg, fg = USER_BUBBLE, "#ffffff"
        elif role == "note":
            bg, fg = "transparent", NOTE_COLOR
        else:
            bg, fg = FRIDAY_BUBBLE, "#e8e8ea"
        self.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border-radius: 10px;"
            f" padding: {'2px 4px' if role == 'note' else '6px 9px'};"
            f" font-size: {'10px' if role == 'note' else '12px'};",
        )


class ChatPanel(QWidget):
    """History + input + mic + model switch + collapse."""

    message_submitted = pyqtSignal(str)
    #: PNG bytes, not a QImage: the panel is the only place that should have to
    #: know about Qt image types, and the receivers all want an encoded file.
    image_pasted = pyqtSignal(bytes)
    mic_clicked = pyqtSignal()
    model_toggle_requested = pyqtSignal()
    collapse_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("chatPanel")
        self.setStyleSheet(PANEL_STYLESHEET)

        # Whether the message being typed has a screenshot behind it. The
        # panel tracks only enough to let Enter mean something on an empty
        # box; the image itself lives in MainWindow.
        self._image_pending = False

        # --- header controls (placed into the card header by MainWindow) ---
        self.model_button = QPushButton("Local model", self)
        self.model_button.setObjectName("chip")
        self.model_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.model_button.setToolTip("Switch LLM provider")
        self.model_button.clicked.connect(self.model_toggle_requested.emit)

        self.collapse_button = QPushButton("▾", self)
        self.collapse_button.setObjectName("chip")
        self.collapse_button.setFixedWidth(24)
        self.collapse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.collapse_button.setToolTip("Collapse to orb")
        self.collapse_button.clicked.connect(self.collapse_requested.emit)

        # --- history ---
        self._history_host = QWidget()
        self._history_host.setObjectName("historyHost")
        self._history_layout = QVBoxLayout(self._history_host)
        self._history_layout.setContentsMargins(2, 2, 2, 2)
        self._history_layout.setSpacing(6)
        self._history_layout.addStretch(1)

        self._scroll = QScrollArea(self)
        self._scroll.setWidget(self._history_host)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # --- note line (STT unavailable, etc.) ---
        self.note_label = QLabel("", self)
        self.note_label.setWordWrap(True)
        self.note_label.setStyleSheet(f"color: {NOTE_COLOR}; font-size: 10px;")
        self.note_label.hide()

        # --- input row ---
        self.input_box = QLineEdit(self)
        self.input_box.setPlaceholderText("Ask FRIDAY…")
        self.input_box.returnPressed.connect(self._submit)
        # The paste is caught as an event rather than by polling the clipboard
        # (the obvious PIL.ImageGrab loop): in a Qt app the paste keystroke is
        # already delivered here, and polling would also pick up images the
        # user copied for some entirely unrelated reason.
        self.input_box.installEventFilter(self)

        self.send_button = QPushButton("Send", self)
        self.send_button.setObjectName("send")
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.clicked.connect(self._submit)

        self.mic_button = QPushButton("🎤", self)
        self.mic_button.setObjectName("mic")
        self.mic_button.setFixedWidth(34)
        self.mic_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mic_button.clicked.connect(self.mic_clicked.emit)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(5)
        input_row.addWidget(self.input_box, 1)
        input_row.addWidget(self.send_button)
        input_row.addWidget(self.mic_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 10)
        layout.setSpacing(6)
        layout.addWidget(self._scroll, 1)
        layout.addWidget(self.note_label)
        layout.addLayout(input_row)

    # ------------------------------------------------------------------ API
    def append(self, role: str, text: str) -> None:
        """Add a history bubble. `role` is 'user', 'friday' or 'note'."""
        bubble = _Bubble(role, text, self._history_host)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        if role == "user":
            row.addStretch(1)
            row.addWidget(bubble, 4)
        elif role == "note":
            row.addWidget(bubble, 1)
        else:
            row.addWidget(bubble, 4)
            row.addStretch(1)
        # Keep the trailing stretch last so bubbles stack from the top.
        self._history_layout.insertLayout(self._history_layout.count() - 1, row)
        QTimer.singleShot(0, self._scroll_to_bottom)

    def message_count(self) -> int:
        """Number of history rows currently shown (excludes the trailing stretch)."""
        return self._history_layout.count() - 1

    def set_note(self, text: str) -> None:
        self.note_label.setText(text)
        self.note_label.setVisible(bool(text))

    #: What the user sees. The underlying model name is an implementation
    #: detail -- "qwen2.5:3b" means nothing to someone using the assistant,
    #: and it changes per machine now that bootstrap picks by hardware.
    PROVIDER_LABELS = {"qwen": "Local model", "nvidia": "Cloud model"}

    def set_model_label(self, provider: str, detail: str = "") -> None:
        key = (provider or "").lower()
        self.model_button.setText(self.PROVIDER_LABELS.get(key, "Model"))
        # The real name stays reachable on hover, for debugging.
        self.model_button.setToolTip(
            f"{detail} - click to switch" if detail else "Switch LLM provider"
        )

    def set_inputs_enabled(self, enabled: bool) -> None:
        """Enable/disable the text path. The mic is controlled separately."""
        self.input_box.setEnabled(enabled)
        self.send_button.setEnabled(enabled)

    def set_mic_enabled(self, enabled: bool) -> None:
        self.mic_button.setEnabled(enabled)
        self.mic_button.setToolTip(
            "Speak to FRIDAY" if enabled else "Speech recognition is still loading…",
        )

    def focus_input(self) -> None:
        self.input_box.setFocus(Qt.FocusReason.OtherFocusReason)

    # ----------------------------------------------------------- paste hook
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt)
        """Turn an image paste into a signal; leave every other paste alone.

        Returning True swallows the keystroke, which matters: a QLineEdit
        handed a clipboard holding only an image inserts nothing at all, so
        the user would see a paste that did nothing while the image quietly
        went somewhere else.
        """
        if (
            obj is self.input_box
            and event.type() == QEvent.Type.KeyPress
            and event.matches(QKeySequence.StandardKey.Paste)
        ):
            png = self._clipboard_png()
            if png:
                self._image_pending = True
                self.image_pasted.emit(png)
                self.append("note", PASTE_NOTE)
                return True
        return super().eventFilter(obj, event)

    @staticmethod
    def _clipboard_png() -> bytes | None:
        """The clipboard's image as PNG, or None when it holds anything else.

        Never raises: a clipboard owned by another process can disappear
        between the check and the read, and a failed paste must not take the
        keystroke — or the window — down with it.
        """
        try:
            clipboard = QApplication.clipboard()
            if clipboard is None:
                return None
            mime = clipboard.mimeData()
            if mime is None or not mime.hasImage():
                return None
            image = clipboard.image()
            if image.isNull():
                return None
            return png_bytes(image) or None
        except Exception:
            return None

    # ------------------------------------------------------------- internals
    def _submit(self) -> None:
        text = self.input_box.text().strip()
        if not text:
            if not self._image_pending:
                return
            text = PASTE_DEFAULT_QUESTION
        self._image_pending = False
        self.input_box.clear()
        self.message_submitted.emit(text)

    def _scroll_to_bottom(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
