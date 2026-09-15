"""
ui/main_window.py – FRIDAY's floating orb
==========================================
A frameless, always-on-top widget with three forms and one animated transition
between them:

    orb  (44x44)     at rest
    pill (200x48)    while LISTENING or SPEAKING, with a live waveform
    card (310x340)   when clicked: history, text input, mic, model switch

It stays a pure view over the existing event bus: UserInputEvent goes out,
StateChangedEvent and ResponseReadyEvent come in. The pipeline is untouched.
"""

from __future__ import annotations

import asyncio

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSettings,
    Qt,
    QTimer,
)
from PyQt6.QtGui import QAction, QBrush, QColor, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QMenu, QVBoxLayout, QWidget

from config.logging_config import get_logger
from core.event_bus import EventBus, ResponseReadyEvent, StateChangedEvent, UserInputEvent
from core.event_bus import ExitRequestedEvent
from ui.chat_panel import ChatPanel
from ui.orb_widget import ACTIVE_STATES, STATE_COLORS, OrbWidget, color_for_state
from ui.tray import TrayController
from intelligence.intent_detector import continues_a_screen_turn
from vision.pasted_image import PendingImage, build_image_task, route_pasted_image

logger = get_logger("ui.main_window")

__all__ = ["MainWindow", "STATE_COLORS", "clamp_to_available", "mode_for_state"]

# --- geometry -----------------------------------------------------------------
MODE_ORB = "orb"
MODE_PILL = "pill"
MODE_CARD = "card"

MODE_SIZES = {
    MODE_ORB: (44, 44),
    MODE_PILL: (200, 48),
    MODE_CARD: (310, 340),
}

ANIM_MS = 180
SCREEN_INSET = 24
HEADER_HEIGHT = 26
DRAG_THRESHOLD = 4

SHELL_BG = QColor(30, 31, 36, 244)
SHELL_BORDER = QColor(52, 53, 60)


def mode_for_state(state: str, expanded: bool) -> str:
    """Pick the visual mode. An open card wins over everything else."""
    if expanded:
        return MODE_CARD
    if (state or "").upper() in ACTIVE_STATES:
        return MODE_PILL
    return MODE_ORB


def clamp_to_available(x: int, y: int, w: int, h: int, rects) -> tuple[int, int]:
    """
    Keep a w*h window fully inside one of `rects` (screen availableGeometry()).

    Picks the screen the window overlaps most; when it overlaps none (a monitor
    was unplugged, or the resolution shrank) it picks the nearest one by centre
    distance. This is what stops a saved position from stranding the orb
    off-screen.
    """
    rects = [r for r in rects if r is not None and r.width() > 0 and r.height() > 0]
    if not rects:
        return int(x), int(y)

    target = QRect(int(x), int(y), int(w), int(h))

    def overlap(rect: QRect) -> int:
        inter = rect.intersected(target)
        return inter.width() * inter.height() if inter.isValid() else 0

    best = max(rects, key=overlap)
    if overlap(best) == 0:
        def distance(rect: QRect) -> int:
            dx = rect.center().x() - target.center().x()
            dy = rect.center().y() - target.center().y()
            return dx * dx + dy * dy

        best = min(rects, key=distance)

    max_x = best.left() + max(0, best.width() - int(w))
    max_y = best.top() + max(0, best.height() - int(h))
    return (
        int(min(max(int(x), best.left()), max_x)),
        int(min(max(int(y), best.top()), max_y)),
    )


class MainWindow(QWidget):
    """The orb itself: mode switching, dragging, persistence and event wiring."""

    def __init__(
        self,
        event_bus: EventBus,
        recorder,
        stt=None,
        wake_detector=None,
        container=None,
    ) -> None:
        super().__init__()
        self._event_bus = event_bus
        self._recorder = recorder
        self._stt = stt
        self._wake_detector = wake_detector
        self.container = container

        self._inputs_enabled = True
        self._wake_paused = False
        self._wake_stopped = False
        self._pending_exit = False
        self._expanded = False
        self._state = "STARTING" if stt is None else "IDLE"
        # One slot for a pasted screenshot; see vision/pasted_image.py for why
        # it outlives the message that consumed it.
        self._pending_image = PendingImage()
        self._drag_origin: QPoint | None = None
        self._drag_start_pos: QPoint | None = None
        self._dragging = False
        self._settings = QSettings("FRIDAY", "orb")

        self.setWindowTitle("FRIDAY")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

        # --- children -------------------------------------------------------
        self.orb = OrbWidget(self)
        self.chat = ChatPanel(self)

        self._header = QHBoxLayout()
        # Match the chat body's 10px horizontal inset. At 0 the model chip ran
        # into the card's rounded corner and looked clipped.
        self._header.setContentsMargins(10, 8, 10, 4)
        self._header.setSpacing(4)
        self._header.addWidget(self.orb, 1)
        self._header.addWidget(self.chat.model_button)
        self._header.addWidget(self.chat.collapse_button)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addLayout(self._header)
        root.addWidget(self.chat, 1)

        self.chat.message_submitted.connect(self._on_message_submitted)
        self.chat.image_pasted.connect(self._on_image_pasted)
        self.chat.mic_clicked.connect(self._on_mic_click)
        self.chat.model_toggle_requested.connect(self._toggle_model)
        self.chat.collapse_requested.connect(self.collapse)

        self._apply_mode_layout(MODE_ORB)
        self.orb.set_state(self._state)
        self._sync_model_label()
        self._set_inputs_enabled(True)

        # --- tray ------------------------------------------------------------
        self.tray = TrayController(self)
        self.tray.show_requested.connect(self._on_tray_show)
        self.tray.hide_requested.connect(self.hide)
        self.tray.quit_requested.connect(self._quit)
        if not self.tray.available:
            # Without this the frameless Qt.Tool window would be unquittable.
            logger.warning("System tray unavailable — using right-click Quit on the orb.")
            self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.customContextMenuRequested.connect(self._show_fallback_menu)

        # --- geometry --------------------------------------------------------
        self._anim = QPropertyAnimation(self, b"geometry", self)
        self._anim.setDuration(ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._on_anim_finished)
        self._pending_mode: str | None = None

        x, y = self._restore_position()
        self.setGeometry(x, y, *MODE_SIZES[MODE_ORB])

        # --- screen-share privacy ---------------------------------------------
        # The orb sits on top of everything, including whatever the user is
        # presenting. Excluding it from capture at the OS level keeps it on the
        # physical display and out of Meet, Zoom, Teams and OBS alike.
        self._apply_capture_exclusion()

        # --- pipeline wiring --------------------------------------------------
        self._event_bus.subscribe(ResponseReadyEvent, self._on_response)
        self._event_bus.subscribe(StateChangedEvent, self._on_state_changed)
        self._event_bus.subscribe(ExitRequestedEvent, self._on_exit_requested)

        self._wake_word_task = None
        if self._wake_detector is not None:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                logger.debug("No running event loop; wake-word loop not started.")
            else:
                self._wake_word_task = asyncio.ensure_future(self._wake_word_loop())

        if self._stt is None:
            self.chat.set_note("Speech recognition is still loading — you can type meanwhile.")

    # ====================================================== screen-share privacy
    def _apply_capture_exclusion(self) -> None:
        """Mark this window as excluded from screen capture.

        Reapplied on every show: Qt destroys and recreates the native handle
        when window flags change, and the affinity belongs to the handle.
        """
        try:
            from vision.screen_hider import hide_from_capture

            self._hidden_from_capture = hide_from_capture(self)
        except Exception as exc:  # pragma: no cover - platform dependent
            self._hidden_from_capture = False
            logger.debug("Capture exclusion unavailable: {}", exc)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_capture_exclusion()

    @property
    def hidden_from_capture(self) -> bool:
        """Whether a screen share currently sees straight through the orb."""
        return getattr(self, "_hidden_from_capture", False)

    # ================================================================= public
    def set_stt(self, stt, error: str | None = None) -> None:
        """
        Hand the window its transcriber once the worker thread has built it.

        Called with `stt=None, error=...` when STT fails: typing must keep
        working, so only the mic goes dark.
        """
        self._stt = stt
        if stt is None:
            note = f"Speech recognition unavailable ({error})." if error else \
                "Speech recognition unavailable — typing still works."
            self.chat.set_note(note)
            logger.warning("STT unavailable: {}", error)
        else:
            self.chat.set_note("")
        self._set_inputs_enabled(self._inputs_enabled)
        self._apply_state("IDLE")

    def set_wake_detector(self, detector, error: str | None = None) -> None:
        """Hand the window its wake-word detector once a worker thread built it.

        Built off the boot path on purpose: importing openWakeWord drags in
        scipy and sklearn, measured at 66-114s on this machine, and paying
        that before the first paint is indistinguishable from a hung app --
        no window, and nothing on stdout to say why. Typing and the mic
        button work without it, so a failure here costs only the wake word.
        """
        self._wake_detector = detector

        if detector is None:
            logger.warning("Wake word unavailable: {}", error)
            return

        # Closed before the import finished: don't start a loop for a window
        # that is already shutting down.
        if self._wake_stopped or self._wake_word_task is not None:
            return

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("No running event loop; wake-word loop not started.")
            return

        self._wake_word_task = asyncio.ensure_future(self._wake_word_loop())
        logger.info("Wake word ready")

    def expand(self) -> None:
        """Grow the orb into the card."""
        if self._expanded:
            return
        self._expanded = True
        self._sync_model_label()
        self._animate_to(MODE_CARD)

    def collapse(self) -> None:
        """Return the card to the orb (or pill, if FRIDAY is mid-utterance)."""
        if not self._expanded:
            return
        self._expanded = False
        self._animate_to(mode_for_state(self._state, False))

    def toggle_expanded(self) -> None:
        self.collapse() if self._expanded else self.expand()

    def current_mode(self) -> str:
        return mode_for_state(self._state, self._expanded)

    async def shutdown(self) -> None:
        """Stop the wake-word background thread/task cleanly."""
        self._wake_stopped = True
        self._wake_paused = False
        if self._wake_detector is not None:
            self._wake_detector.stop()
        if self._wake_word_task is not None:
            # Bounded: the loop can be parked inside a blocking detect() that
            # never returns, and an unbounded await there hangs shutdown.
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._wake_word_task), timeout=3.0
                )
            except (asyncio.TimeoutError, asyncio.CancelledError):
                logger.warning("Wake-word loop did not stop in time; abandoning it.")
            except Exception as exc:
                logger.debug("Wake-word loop ended with: {}", exc)

    # ============================================================ input paths
    def _on_message_submitted(self, text: str) -> None:
        self.chat.append("user", text)
        self._set_inputs_enabled(False)

        png = self._pending_image.take()
        if png is not None:
            asyncio.ensure_future(self._submit_with_image(text, png))
            return

        # "Is that aligned?" straight after a screenshot answer means the
        # screenshot, not the screen -- which has moved on. The retained copy
        # is what saves the user from pasting the same picture twice.
        #
        # continues_a_screen_turn rather than a pronoun check of our own: it
        # already carries the veto that keeps "play the next one" with the
        # music, and a deictic sentence is only a follow-up when the previous
        # turn was actually about a picture.
        followed_up = self._pending_image.last
        if followed_up is not None and continues_a_screen_turn(
            text, after_screen_turn=True
        ):
            asyncio.ensure_future(self._ask_vision_about(text, followed_up))
            return

        # A turn with no image ends the screenshot's life: keeping it any
        # longer would attach a picture to a question that has moved on.
        self._pending_image.clear()
        asyncio.ensure_future(
            self._event_bus.publish(UserInputEvent(text=text, source="text")),
        )

    def _on_image_pasted(self, png: bytes) -> None:
        """Hold a pasted screenshot for the message the user is about to send.

        Nothing runs here — not OCR, not the vision model. The user is still
        typing, and the question they type decides what the image is for.
        """
        self._pending_image.set(png)
        logger.debug("Screenshot pasted into the chat ({} KB).", len(png) // 1024)

    async def _submit_with_image(self, text: str, png: bytes) -> None:
        """Send a message that has a screenshot attached.

        OCR decides which way this goes (vision/pasted_image.py explains the
        threshold). It runs in a thread because it is a second or two of CPU
        on the loop that also drives speech and the orb animation.
        """
        try:
            route = await asyncio.to_thread(route_pasted_image, text, png)
        except Exception as exc:
            # route_pasted_image already absorbs OCR failure; anything left is
            # a bug, and a swallowed one would leave the inputs disabled.
            logger.exception("Routing a pasted screenshot failed: {}", exc)
            await self._event_bus.publish(
                ResponseReadyEvent(response=f"I couldn't read that screenshot: {exc}"),
            )
            return

        if route.kind == "text":
            # The common case: local OCR, no VLM, no model swap. Only the
            # extracted text travels onward, which is what makes this safe
            # when the active provider is the (text-only) cloud one.
            logger.debug("Pasted screenshot read as text ({} chars).", route.ocr_chars)
            await self._event_bus.publish(
                UserInputEvent(text=route.text, source="text"),
            )
            return

        logger.debug("Pasted screenshot routed to vision ({} chars).", route.ocr_chars)
        await self._ask_vision_about(route.text or text, png)

    async def _ask_vision_about(self, question: str, png: bytes) -> None:
        """Run VisionSkill against a pasted image and show what it says.

        The skill is driven directly rather than through the bus because the
        pipeline carries text only — there is nowhere in a UserInputEvent to
        put a picture.

        The answer goes back through ``Assistant.respond`` rather than
        straight onto the bus. Publishing ResponseReadyEvent here was enough
        to fill the history bubble, and that was the trap: it skipped the
        speaking, the conversation history the next turn reads, and the orb's
        speaking form. A screenshot answer is a reply like any other and has
        to leave by the same door.
        """
        from skills.vision_skill import VisionSkill

        try:
            answer = await VisionSkill(self.container).execute(
                build_image_task(question, png),
            )
        except Exception as exc:
            logger.exception("Vision on a pasted screenshot failed: {}", exc)
            answer = f"I couldn't look at that screenshot: {exc}"

        assistant = getattr(self.container, "assistant", None)
        if assistant is not None and hasattr(assistant, "respond"):
            await assistant.respond(answer)
        else:
            # No container in the widget tests; the bubble still has to appear.
            await self._event_bus.publish(ResponseReadyEvent(response=answer))

    def _on_mic_click(self) -> None:
        # Barge-in: a mic click cuts whatever FRIDAY is saying, and abandons
        # the turn behind it. Without the second half, an interrupted question
        # still delivers its answer some seconds later, over the new one.
        self._stop_speech()
        self._cancel_current_turn()
        if self._stt is None:
            self.chat.append("note", "(mic unavailable — speech recognition not loaded)")
            return
        self._set_inputs_enabled(False)
        self._apply_state("LISTENING")
        # Set synchronously, before the capture is scheduled: the wake-word
        # loop runs on this thread too, and would otherwise re-enter detect()
        # and grab the microphone before _do_listen ever starts.
        self._wake_paused = True
        asyncio.ensure_future(self._do_listen())

    def _stop_speech(self) -> None:
        """Cut any in-progress TTS playback. Best effort; never fatal."""
        try:
            from speech.text_to_speech.tts_pipeline import stop_audio

            stop_audio()
        except Exception as exc:  # pragma: no cover - depends on audio backend
            logger.debug("stop_audio failed during barge-in: {}", exc)

    def _cancel_current_turn(self) -> None:
        """Abandon the in-flight pipeline run, if there is one."""
        assistant = getattr(self.container, "assistant", None) if self.container else None
        if assistant is None:
            return
        try:
            assistant.interrupt()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Could not cancel current turn: {}", exc)

    async def _wake_word_loop(self) -> None:
        """Listen for the wake word, except while we are recording a command.

        The detector holds its own microphone stream open. Opening the
        recorder's stream on the same device at the same time makes PortAudio
        report an input overflow and kills the app, so the loop stands down
        for the duration of a capture and resumes afterwards.
        """
        while not self._wake_stopped:
            if self._wake_paused:
                await asyncio.sleep(0.1)
                continue

            try:
                heard = await asyncio.to_thread(self._wake_detector.detect)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Nothing awaits this task, so an escaping exception used to
                # kill the wake word with no log line and no sign in the UI.
                logger.exception("Wake-word detection failed: {}", exc)
                await asyncio.sleep(1.0)
                continue

            if self._wake_stopped:
                return
            if self._wake_paused:
                # detect() returned because we asked it to stand down, not
                # because it heard anything.
                continue
            if heard and self._inputs_enabled:
                self.chat.append("note", "(wake word heard)")
                self._on_mic_click()

    def _pause_wake_word(self) -> None:
        """Release the wake-word microphone stream before we record.

        stop() only asks the detect loop to finish; its stream is closed
        afterwards on the detector's own thread. Returning here without
        waiting is what left two input streams open on one device.
        """
        if self._wake_detector is None:
            return
        self._wake_paused = True
        try:
            self._wake_detector.stop()
            if not self._wake_detector.wait_closed(timeout=2.0):
                logger.warning("Wake-word stream did not close in time.")
        except Exception as exc:
            logger.debug("Could not pause wake word: {}", exc)

    def _resume_wake_word(self) -> None:
        """Hand the microphone back to the wake-word detector.

        The stop is sticky, so it must be lifted explicitly — otherwise
        detect() returns immediately for ever and the wake word goes deaf.
        """
        if self._wake_detector is not None:
            try:
                self._wake_detector.resume()
            except Exception as exc:
                logger.debug("Could not resume wake word: {}", exc)
        self._wake_paused = False

    async def _do_listen(self) -> None:
        try:
            # The mic hears the speakers, so anything we are playing has to go
            # quiet first or the VAD just records the music back at us.
            from speech.mic_guard import listening_quiet

            # Only one microphone stream may be open at a time. The wake-word
            # detector owns one continuously, so it stands down before the
            # recorder opens its own. The handover waits for the detector's
            # stream to actually close, which is why it runs on the worker
            # thread — blocking the Qt loop for that would freeze the orb.
            def _capture():
                self._pause_wake_word()
                with listening_quiet():
                    self._recorder.start()
                    try:
                        return self._recorder.listen()
                    finally:
                        self._recorder.stop()

            try:
                audio = await asyncio.to_thread(_capture)
            finally:
                self._resume_wake_word()

            if audio is None:
                # Nobody spoke. Common after a wake-word false positive, and
                # the inputs must come back on or the orb is stuck listening.
                self.chat.append("note", "(didn't catch that)")
                self._set_inputs_enabled(True)
                self._apply_state("IDLE")
                return

            self._apply_state("THINKING")
            text = await asyncio.to_thread(self._stt.transcribe, audio)

            if not text.strip():
                self.chat.append("note", "(didn't catch that)")
                self._set_inputs_enabled(True)
                self._apply_state("IDLE")
                return

            self.chat.append("user", text)
            await self._event_bus.publish(UserInputEvent(text=text, source="voice"))
        except Exception as exc:
            self.chat.append("note", f"(mic error: {exc})")
            self._set_inputs_enabled(True)
            self._apply_state("IDLE")

    # =========================================================== bus handlers
    async def _on_response(self, event: ResponseReadyEvent) -> None:
        self.chat.append("friday", event.response)
        self._set_inputs_enabled(True)

    async def _on_exit_requested(self, event: ExitRequestedEvent) -> None:
        """Dismissed by voice ("bye bye"). Quit once the goodbye has been said.

        Quitting immediately would cut the farewell off mid-word, so we wait
        for the assistant to leave SPEAKING. The timer is a backstop for the
        case where no further state change arrives.
        """
        self._pending_exit = True
        if self._state != "SPEAKING":
            QTimer.singleShot(2500, self._exit_if_pending)

    def _exit_if_pending(self) -> None:
        """Actually shut down.

        This used to hide to the tray and leave the wake word listening, so
        an assistant the user had said goodbye to was still running and still
        holding the microphone. A goodbye now ends the process; the tray menu
        and the orb are how you keep it around.
        """
        if not self._pending_exit:
            return
        self._pending_exit = False
        self._quit()

    async def _on_state_changed(self, event: StateChangedEvent) -> None:
        self._apply_state(event.new_state)

    # ================================================================== state
    def _apply_state(self, state: str) -> None:
        previous = getattr(self, "_state", "")
        self._state = (state or "").upper()
        if getattr(self, "_pending_exit", False) and previous == "SPEAKING" and self._state != "SPEAKING":
            QTimer.singleShot(400, self._exit_if_pending)
        self.orb.set_state(self._state)
        self.tray.set_state(self._state)
        # A tooltip renders in its own native window, which does not inherit
        # this window's capture exclusion — so on a shared screen the orb
        # itself is invisible but "FRIDAY — Listening" hovers over it. When we
        # are hidden from capture, the tooltip says nothing.
        self.setToolTip(
            ""
            if self.hidden_from_capture
            else f"FRIDAY — {self._state.title().replace('_', ' ')}"
        )
        if not self._expanded:
            self._animate_to(mode_for_state(self._state, False))
        self.update()

    def _set_inputs_enabled(self, enabled: bool) -> None:
        self._inputs_enabled = enabled
        self.chat.set_inputs_enabled(enabled)
        self.chat.set_mic_enabled(enabled and self._stt is not None)

    def _sync_model_label(self) -> None:
        """
        Refresh the provider chip.

        `container.llm` is a lazy property that builds the LLM client — roughly
        2.7s on this machine — so it is only read once something else has
        already built it. Until then the chip shows the container's default.
        """
        # Default to the configured provider, not a hardcoded one: the chip
        # used to read "NVIDIA" on a machine running purely locally.
        provider = "qwen"
        detail = ""
        container = self.container
        if container is not None:
            settings = getattr(container, "settings", None)
            if settings is not None:
                provider = getattr(settings, "llm_provider", provider)
            registry = getattr(container, "_registry", None)
            if isinstance(registry, dict) and "llm" in registry:
                provider = getattr(container.llm, "current_provider", provider)
            if settings is not None:
                detail = (
                    getattr(settings, "qwen_model", "")
                    if provider == "qwen"
                    else getattr(settings, "nvidia_model", "")
                )
        self.chat.set_model_label(provider, detail)

    def _toggle_model(self) -> None:
        """Preserved from the previous window: NVIDIA <-> Qwen switch."""
        if not self.container:
            return
        llm = self.container.llm
        try:
            current = getattr(llm, "current_provider", "qwen")

            # Only offer providers that are actually configured. Switching to
            # an unconfigured one used to succeed here and then crash every
            # later message inside intent detection.
            options = None
            if hasattr(llm, "available_providers"):
                options = [p for p in llm.available_providers()]
            if not options:
                options = ["qwen", "nvidia"]

            if len(options) < 2:
                only = options[0].upper()
                self.chat.append(
                    "note",
                    f"({only} is the only configured provider — "
                    f"set NVIDIA_API_KEY in .env to enable switching)",
                )
                self._sync_model_label()
                return

            idx = options.index(current) if current in options else 0
            new_provider = options[(idx + 1) % len(options)]
            llm.switch(new_provider)
            self.chat.set_model_label(new_provider)
            self._sync_model_label()
            self.chat.append("note", f"(switched LLM to {new_provider.upper()})")
        except Exception as exc:
            self.chat.append("note", f"(model switch error: {exc})")
            self._sync_model_label()

    # =============================================================== geometry
    def _apply_mode_layout(self, mode: str) -> None:
        """Show/hide the card chrome for a mode. Called around the animation."""
        card = mode == MODE_CARD
        self.chat.setVisible(card)
        self.chat.model_button.setVisible(card)
        self.chat.collapse_button.setVisible(card)
        self._header.setContentsMargins(*((8, 6, 8, 2) if card else (0, 0, 0, 0)))
        if card:
            self.orb.setFixedHeight(HEADER_HEIGHT)
            self.orb.set_mode(OrbWidget.MODE_DOT)
        else:
            self.orb.setMinimumHeight(0)
            self.orb.setMaximumHeight(16777215)
            self.orb.set_mode(
                OrbWidget.MODE_PILL if mode == MODE_PILL else OrbWidget.MODE_ORB,
            )

    def _screen_rects(self) -> list[QRect]:
        app = QApplication.instance()
        if app is None:
            return []
        return [s.availableGeometry() for s in app.screens()]

    def _target_geometry(self, mode: str) -> QRect:
        w, h = MODE_SIZES[mode]
        current = self.geometry()
        # Keep the orb's centre where the user put it, then pull it on-screen.
        x = current.center().x() - w // 2
        y = current.y()
        x, y = clamp_to_available(x, y, w, h, self._screen_rects())
        return QRect(x, y, w, h)

    def _animate_to(self, mode: str) -> None:
        if mode == self._applied_mode() and not self._anim.state():
            return
        target = self._target_geometry(mode)
        if self.geometry() == target and mode == self._applied_mode():
            return

        self._anim.stop()
        if mode == MODE_CARD:
            # Grow first, then fill: showing the card contents up front would
            # raise the layout's minimum size and block the animation.
            self._pending_mode = MODE_CARD
        else:
            self._apply_mode_layout(mode)
            self._pending_mode = None
        self._applied = mode
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(target)
        self._anim.start()

    def _applied_mode(self) -> str:
        return getattr(self, "_applied", MODE_ORB)

    def _on_anim_finished(self) -> None:
        if self._pending_mode is not None:
            self._apply_mode_layout(self._pending_mode)
            self._pending_mode = None
            self.chat.focus_input()

    # ---------------------------------------------------------- persistence
    def _restore_position(self) -> tuple[int, int]:
        w, h = MODE_SIZES[MODE_ORB]
        saved = self._settings.value("pos")
        rects = self._screen_rects()
        if saved is not None:
            try:
                x, y = int(saved.x()), int(saved.y())
            except AttributeError:
                try:
                    x, y = int(saved[0]), int(saved[1])
                except (TypeError, ValueError, IndexError):
                    saved = None
        if saved is None:
            base = rects[0] if rects else QRect(0, 0, 1280, 720)
            x = base.right() - w - SCREEN_INSET
            y = base.bottom() - h - SCREEN_INSET
        return clamp_to_available(x, y, w, h, rects)

    def _save_position(self) -> None:
        self._settings.setValue("pos", QPoint(self.x(), self.y()))

    # ------------------------------------------------------------- mouse/drag
    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().toPoint()
            self._drag_start_pos = self.pos()
            self._dragging = False
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self._drag_origin is None or self._drag_start_pos is None:
            return
        delta = event.globalPosition().toPoint() - self._drag_origin
        if not self._dragging and delta.manhattanLength() < DRAG_THRESHOLD:
            return
        self._dragging = True
        x, y = clamp_to_available(
            self._drag_start_pos.x() + delta.x(),
            self._drag_start_pos.y() + delta.y(),
            self.width(),
            self.height(),
            self._screen_rects(),
        )
        self.move(x, y)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() != Qt.MouseButton.LeftButton:
            return
        was_drag = self._dragging
        self._drag_origin = None
        self._drag_start_pos = None
        self._dragging = False
        if was_drag:
            self._save_position()
        elif not self._expanded:
            self.expand()
        event.accept()

    def moveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().moveEvent(event)

    # ----------------------------------------------------------------- paint
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Only the card needs a shell; the orb and pill paint themselves."""
        if not self._expanded and self._pending_mode is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QBrush(SHELL_BG))
        pen = QPen(QColor(color_for_state(self._state)))
        pen.setWidthF(1.2)
        painter.setPen(pen)
        # QRectF, not loose floats: the float overload does not exist and the
        # resulting TypeError inside paintEvent aborts the process.
        painter.drawRoundedRect(
            QRectF(0.6, 0.6, self.width() - 1.2, self.height() - 1.2), 16.0, 16.0,
        )
        painter.end()

    # ------------------------------------------------------------------ tray
    def _on_tray_show(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def _show_fallback_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        hide_action = QAction("Hide", menu)
        hide_action.triggered.connect(self.hide)
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(hide_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        # A popup is its own native window, so it does not inherit the orb's
        # capture exclusion. Without this the menu is the one part of FRIDAY
        # a screen share would still show.
        menu.winId()
        try:
            from vision.screen_hider import hide_from_capture

            hide_from_capture(menu)
        except Exception as exc:  # pragma: no cover - platform dependent
            logger.debug("Could not hide the context menu from capture: {}", exc)

        menu.exec(self.mapToGlobal(pos))

    def _quit(self) -> None:
        self._save_position()
        self.tray.hide()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._save_position()
        super().closeEvent(event)
