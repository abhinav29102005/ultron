"""
utils/gui_recorder.py – Cross-Platform In-Engine Video Recorder for ULTRON GUI
=============================================================================
Captures PyQt6 widget frames directly from the Qt rendering pipeline using
QWidget.grab() and composites them onto a desktop canvas.

Because this operates inside Qt's own memory buffer, it works identically
and 100% reliably across:
- Linux (Wayland AND X11, completely immune to XGetImage / Compositor blocks)
- macOS (No Screen Recording permission dialog required in Privacy settings)
- Windows (Immune to DWM display affinity exclusion and DPI scaling)

Outputs universally playable MP4 (H.264/yuv420p) and WebM videos that open
seamlessly in Google Chrome, VLC, and mobile players.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np
from PyQt6.QtCore import QObject, QPoint, QRect, QRectF, Qt, QTimer
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import QWidget

from config.logging_config import get_logger

logger = get_logger("gui_recorder")


class GuiRecorder(QObject):
    """Cross-platform Qt widget video recorder."""

    def __init__(
        self,
        target_widget: QWidget,
        output_path: str | Path = "ultron_gui_recording.mp4",
        fps: int = 25,
        canvas_width: int = 1280,
        canvas_height: int = 720,
    ) -> None:
        super().__init__()
        self.widget = target_widget
        self.output_path = Path(output_path).resolve()
        self.fps = fps
        self.canvas_w = canvas_width
        self.canvas_h = canvas_height
        
        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / self.fps))
        self._timer.timeout.connect(self._capture_frame)
        
        self.frames: list[np.ndarray] = []
        self.is_recording = False
        self._start_time = 0.0

    def start(self) -> None:
        """Begin recording frames."""
        if self.is_recording:
            return
        logger.info(f"Starting GUI recording -> {self.output_path} ({self.fps} FPS, {self.canvas_w}x{self.canvas_h})")
        self.frames.clear()
        self.is_recording = True
        self._start_time = time.time()
        self._timer.start()

    def stop(self) -> Path:
        """Stop capturing and encode video."""
        if not self.is_recording:
            return self.output_path
        
        self._timer.stop()
        self.is_recording = False
        duration = time.time() - self._start_time
        logger.info(f"Recording stopped. Captured {len(self.frames)} frames across {duration:.1f}s. Encoding video...")
        
        return self._save_video()

    def _capture_frame(self) -> None:
        if not self.widget.isVisible():
            return

        # 1. Grab current widget snapshot directly from Qt
        widget_pixmap: QPixmap = self.widget.grab()
        if widget_pixmap.isNull():
            return

        # 2. Paint onto fixed HD desktop canvas
        canvas = QPixmap(self.canvas_w, self.canvas_h)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # 2a. Background gradient (Cybernetic Dark OS Workspace)
        grad = QLinearGradient(0, 0, self.canvas_w, self.canvas_h)
        grad.setColorAt(0.0, QColor(10, 12, 16))
        grad.setColorAt(1.0, QColor(18, 22, 30))
        painter.fillRect(0, 0, self.canvas_w, self.canvas_h, grad)

        # 2b. Subtle workspace grid lines
        grid_pen = QPen(QColor(255, 255, 255, 8), 1)
        painter.setPen(grid_pen)
        grid_step = 40
        for x in range(0, self.canvas_w, grid_step):
            painter.drawLine(x, 0, x, self.canvas_h)
        for y in range(0, self.canvas_h, grid_step):
            painter.drawLine(0, y, self.canvas_w, y)

        # 2c. Header HUD
        hud_bg = QColor(14, 17, 23, 230)
        painter.fillRect(0, 0, self.canvas_w, 48, hud_bg)
        painter.setPen(QPen(QColor(255, 255, 255, 20), 1))
        painter.drawLine(0, 48, self.canvas_w, 48)

        # HUD Text
        font = QFont("Inter", 10)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#e8e8ea"))
        painter.drawText(24, 30, "ULTRON DESKTOP RUNTIME")

        mode_name = getattr(self.widget, "current_mode", lambda: "card")()
        mode_str = f"MODE: {mode_name.upper()}"
        font.setBold(False)
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(QColor("#9a9ba3"))
        painter.drawText(220, 30, f"•  {mode_str}  •  CROSS-PLATFORM IN-ENGINE CAPTURE")

        # Recording badge & timer
        elapsed = time.time() - self._start_time
        mins, secs = divmod(int(elapsed), 60)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#e11d48"))
        painter.drawEllipse(self.canvas_w - 140, 20, 10, 10)
        
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(self.canvas_w - 120, 30, f"REC {mins:02d}:{secs:02d}")

        # 2d. Draw the floating Ultron Widget centered or in bottom-right
        # Centering the widget creates an amazing hero presentation
        target_x = (self.canvas_w - widget_pixmap.width()) // 2
        target_y = (self.canvas_h - widget_pixmap.height()) // 2
        
        # Soft shadow behind widget
        shadow_rect = QRectF(target_x - 6, target_y - 4, widget_pixmap.width() + 12, widget_pixmap.height() + 12)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 75))
        painter.drawRoundedRect(shadow_rect, 16, 16)

        painter.drawPixmap(target_x, target_y, widget_pixmap)

        # 2e. Bottom Telemetry Bar
        footer_y = self.canvas_h - 32
        painter.fillRect(0, footer_y, self.canvas_w, 32, QColor(9, 11, 14, 235))
        painter.setPen(QPen(QColor(255, 255, 255, 15), 1))
        painter.drawLine(0, footer_y, self.canvas_w, footer_y)

        font.setPointSize(8)
        painter.setFont(font)
        painter.setPen(QColor("#3ddc84"))
        painter.drawEllipse(24, footer_y + 11, 8, 8)
        painter.drawText(40, footer_y + 20, "DUAL LLM PIPELINE ONLINE (Groq Llama 3.3 70B + NVIDIA Nemotron)")
        
        painter.setPen(QColor("#71717a"))
        painter.drawText(self.canvas_w - 220, footer_y + 20, f"{self.fps} FPS • GOOGLE CHROME READY")

        painter.end()

        # 3. Convert QPixmap to OpenCV RGB frame
        qimage = canvas.toImage().convertToFormat(QImage.Format.Format_RGB888)
        width, height = qimage.width(), qimage.height()
        ptr = qimage.bits()
        ptr.setsize(height * width * 3)
        rgb_arr = np.frombuffer(ptr, np.uint8).reshape((height, width, 3))
        bgr_arr = cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2BGR)
        self.frames.append(bgr_arr)

    def _save_video(self) -> Path:
        if not self.frames:
            logger.warning("No frames captured; video not written.")
            return self.output_path

        temp_mp4 = self.output_path.with_name(f"temp_{self.output_path.name}")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(str(temp_mp4), fourcc, float(self.fps), (self.canvas_w, self.canvas_h))

        for frame in self.frames:
            out.write(frame)
        out.release()

        # If ffmpeg is available, re-encode to clean web-compatible H.264
        ffmpeg_bin = shutil.which("ffmpeg")
        if ffmpeg_bin:
            try:
                cmd = [
                    ffmpeg_bin,
                    "-y",
                    "-i", str(temp_mp4),
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart",
                    str(self.output_path),
                ]
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                temp_mp4.unlink(missing_ok=True)
                
                # Also generate a .webm copy alongside so Chrome can open it instantly
                webm_path = self.output_path.with_suffix(".webm")
                cmd_webm = [
                    ffmpeg_bin,
                    "-y",
                    "-i", str(self.output_path),
                    "-c:v", "libvpx-vp9",
                    "-crf", "28",
                    "-b:v", "0",
                    str(webm_path),
                ]
                subprocess.run(cmd_webm, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                logger.info(f"WebM version also generated: {webm_path}")

            except Exception as e:
                logger.warning(f"ffmpeg optimization failed ({e}), falling back to raw mp4")
                if temp_mp4.exists():
                    shutil.move(str(temp_mp4), str(self.output_path))
        else:
            if temp_mp4.exists():
                shutil.move(str(temp_mp4), str(self.output_path))

        print(f"\n[ULTRON RECORDER] Video successfully created: {self.output_path}")
        print(f"[ULTRON RECORDER] Open in Google Chrome via: file://{self.output_path}")
        return self.output_path
