"""
ui/orb_widget.py – The orb / pill visual
=========================================
Paints ULTRON's floating presence: a small circle at rest, a wider pill with a
live waveform while listening or speaking, and a compact dot when it sits in
the expanded card's header.

Knows nothing about chat, the container or the event bus. Its whole world is a
state name and an amplitude level.
"""

from __future__ import annotations

import math
import random

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QWidget

# Reused as-is from the previous window: the canonical state -> colour vocabulary.
STATE_COLORS = {
    "OFFLINE": "#5c5f66",
    "STARTING": "#c9a227",
    "IDLE": "#3ddc84",
    "LISTENING": "#4dabf7",
    "THINKING": "#ffa94d",
    "EXECUTING": "#b794f6",
    "SPEAKING": "#38d9d9",
    "SHUTTING_DOWN": "#ff6b6b",
}

DEFAULT_COLOR = STATE_COLORS["OFFLINE"]

#: States that make the orb stretch into the waveform pill.
ACTIVE_STATES = frozenset({"LISTENING", "SPEAKING"})

#: States that get a gently pulsing halo (something is happening).
BUSY_STATES = frozenset({"LISTENING", "SPEAKING", "THINKING", "EXECUTING", "STARTING"})

SHELL_COLOR = QColor("#1e1f24")
TEXT_COLOR = QColor("#9a9ba3")

_WAVE_BARS = 13


def color_for_state(state: str) -> str:
    """Map a state name to its hex colour, falling back to the offline grey."""
    return STATE_COLORS.get((state or "").upper(), DEFAULT_COLOR)


class OrbWidget(QWidget):
    """The circle / pill / header-dot painter."""

    MODE_ORB = "orb"
    MODE_PILL = "pill"
    MODE_DOT = "dot"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._state = "STARTING"
        self._color = QColor(color_for_state(self._state))
        self._mode = self.MODE_ORB
        self._amplitude = 0.0
        self._target_amplitude = 0.0
        self._phase = 0.0
        self._pulse = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._tick)
        self._sync_timer()

    # ------------------------------------------------------------------ API
    def state(self) -> str:
        return self._state

    def set_state(self, name: str) -> None:
        """Set the state name; updates colour, halo and waveform activity."""
        self._state = (name or "").upper()
        self._color = QColor(color_for_state(self._state))
        self._sync_timer()
        self.update()

    def set_amplitude(self, level: float) -> None:
        """Feed a 0..1 loudness level for the waveform to chase."""
        self._target_amplitude = max(0.0, min(1.0, float(level)))

    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        if mode == self._mode:
            return
        self._mode = mode
        self._sync_timer()
        self.update()

    # -------------------------------------------------------------- internals
    def _is_active(self) -> bool:
        return self._state in ACTIVE_STATES

    def _sync_timer(self) -> None:
        needs_animation = self._state in BUSY_STATES or self._amplitude > 0.01
        if needs_animation and not self._timer.isActive():
            self._timer.start()
        elif not needs_animation and self._timer.isActive():
            self._timer.stop()
            self._amplitude = 0.0
            self._pulse = 0.0
            self.update()

    def _tick(self) -> None:
        self._phase += 0.36
        self._pulse = (self._pulse + 0.06) % 1.0

        if self._is_active():
            # No real level fed in? Keep it alive with a gentle random walk so
            # the pill reads as "something is happening" rather than frozen.
            drift = random.uniform(-0.25, 0.25)
            self._target_amplitude = max(0.25, min(1.0, self._target_amplitude + drift))
        else:
            self._target_amplitude = 0.0

        self._amplitude += (self._target_amplitude - self._amplitude) * 0.35
        self.update()

    # ----------------------------------------------------------------- paint
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._mode == self.MODE_PILL:
            self._paint_pill(painter)
        elif self._mode == self.MODE_DOT:
            self._paint_dot(painter)
        else:
            self._paint_orb(painter)
        painter.end()

    def _paint_orb(self, painter: QPainter) -> None:
        side = min(self.width(), self.height())
        margin = 4.0
        rect = QRectF(
            (self.width() - side) / 2 + margin,
            (self.height() - side) / 2 + margin,
            side - margin * 2,
            side - margin * 2,
        )

        # Soft halo that breathes while busy.
        if self._state in BUSY_STATES:
            glow = QColor(self._color)
            glow.setAlpha(int(40 + 45 * abs(math.sin(self._pulse * math.pi))))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(rect.adjusted(-margin, -margin, margin, margin))

        gradient = QRadialGradient(rect.center().x(), rect.top() + rect.height() * 0.3,
                                   rect.width())
        light = QColor(self._color).lighter(145)
        gradient.setColorAt(0.0, light)
        gradient.setColorAt(1.0, self._color)

        painter.setPen(QPen(QColor(255, 255, 255, 45), 1.2))
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(rect)

    def _paint_pill(self, painter: QPainter) -> None:
        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)
        radius = rect.height() / 2

        shell = QColor(SHELL_COLOR)
        shell.setAlpha(235)
        border = QColor(self._color)
        border.setAlpha(120)
        painter.setPen(QPen(border, 1.4))
        painter.setBrush(QBrush(shell))
        painter.drawRoundedRect(rect, radius, radius)

        # Leading dot in the state colour.
        dot_d = rect.height() * 0.42
        dot = QRectF(rect.left() + radius - dot_d / 2,
                     rect.center().y() - dot_d / 2, dot_d, dot_d)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._color))
        painter.drawEllipse(dot)

        self._paint_waveform(painter, QRectF(dot.right() + 10, rect.top() + 6,
                                             rect.right() - dot.right() - 20,
                                             rect.height() - 12))

    def _paint_waveform(self, painter: QPainter, area: QRectF) -> None:
        if area.width() <= 8 or area.height() <= 2:
            return
        bar_w = area.width() / (_WAVE_BARS * 1.9)
        gap = (area.width() - bar_w * _WAVE_BARS) / max(1, _WAVE_BARS - 1)
        painter.setPen(Qt.PenStyle.NoPen)

        for i in range(_WAVE_BARS):
            # Envelope tapers the ends so it reads as a waveform, not a bar chart.
            envelope = math.sin(math.pi * (i + 0.5) / _WAVE_BARS)
            wobble = abs(math.sin(self._phase + i * 0.55))
            level = max(0.08, self._amplitude * envelope * (0.35 + 0.65 * wobble))
            h = max(2.0, area.height() * level)
            x = area.left() + i * (bar_w + gap)
            bar = QRectF(x, area.center().y() - h / 2, bar_w, h)
            fill = QColor(self._color)
            fill.setAlpha(150 + int(105 * level))
            painter.setBrush(QBrush(fill))
            path = QPainterPath()
            path.addRoundedRect(bar, bar_w / 2, bar_w / 2)
            painter.drawPath(path)

    def _paint_dot(self, painter: QPainter) -> None:
        d = 12.0
        rect = QRectF(6, (self.height() - d) / 2, d, d)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._color))
        painter.drawEllipse(rect)

        font = QFont(self.font())
        font.setPointSizeF(8.5)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(TEXT_COLOR))
        text_rect = QRectF(rect.right() + 8, 0, self.width() - rect.right() - 12, self.height())
        painter.drawText(text_rect,
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                         f"ULTRON · {self._state.title().replace('_', ' ')}")
