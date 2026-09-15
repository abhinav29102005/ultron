"""
tests/test_ui.py – Floating orb UI
===================================
Qt rendering is not meaningfully testable headless, so these target logic:
state -> colour, state -> mode, position clamping, message submission and the
mic staying disabled until STT arrives.

Runs under QT_QPA_PLATFORM=offscreen (set below, before PyQt6 is imported).
"""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt", reason="pytest-qt is required for the UI tests")

from PyQt6.QtCore import QRect, QSettings, Qt  # noqa: E402

from core.event_bus import (  # noqa: E402
    EventBus,
    ResponseReadyEvent,
    StateChangedEvent,
    UserInputEvent,
)
from ui.chat_panel import ChatPanel  # noqa: E402
from ui.main_window import (  # noqa: E402
    MODE_CARD,
    MODE_ORB,
    MODE_PILL,
    MODE_SIZES,
    STATE_COLORS,
    MainWindow,
    clamp_to_available,
    mode_for_state,
)
from ui.orb_widget import OrbWidget, color_for_state  # noqa: E402

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


class _FakeRecorder:
    def start(self) -> None: ...
    def listen(self):
        return b""
    def stop(self) -> None: ...


class _FakeSTT:
    def transcribe(self, audio) -> str:
        return "hello"


class _FakeLLM:
    def __init__(self) -> None:
        self.current_provider = "nvidia"

    def switch(self, provider: str) -> None:
        self.current_provider = provider


class _FakeContainer:
    def __init__(self) -> None:
        self.llm = _FakeLLM()


@pytest.fixture(autouse=True, scope="module")
def _isolated_settings(tmp_path_factory):
    """Keep QSettings("FRIDAY", "orb") out of the real user registry."""
    path = tmp_path_factory.mktemp("qsettings")
    previous = QSettings.defaultFormat()
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(path))
    yield
    QSettings.setDefaultFormat(previous)


@pytest.fixture
def window(qtbot):
    win = MainWindow(EventBus(), _FakeRecorder(), None, None, _FakeContainer())
    qtbot.addWidget(win)
    return win


# --------------------------------------------------------- state -> colour
class TestStateColours:
    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            ("IDLE", "#3ddc84"),
            ("LISTENING", "#4dabf7"),
            ("SPEAKING", "#38d9d9"),
            ("STARTING", "#c9a227"),
            ("THINKING", "#ffa94d"),
        ],
    )
    def test_known_states_map_to_their_colour(self, state, expected):
        assert color_for_state(state) == expected
        assert STATE_COLORS[state] == expected

    def test_lowercase_state_names_are_accepted(self):
        assert color_for_state("idle") == STATE_COLORS["IDLE"]

    def test_unknown_state_falls_back_to_offline_grey(self):
        assert color_for_state("BANANA") == STATE_COLORS["OFFLINE"]
        assert color_for_state("") == STATE_COLORS["OFFLINE"]

    def test_orb_widget_adopts_the_state(self, qtbot):
        orb = OrbWidget()
        qtbot.addWidget(orb)
        orb.set_state("SPEAKING")
        assert orb.state() == "SPEAKING"

    def test_window_state_change_reaches_the_orb(self, qtbot, window):
        window._apply_state("EXECUTING")
        assert window.orb.state() == "EXECUTING"


# ----------------------------------------------------------- state -> mode
class TestModeSelection:
    @pytest.mark.parametrize("state", ["IDLE", "THINKING", "EXECUTING", "OFFLINE", "STARTING"])
    def test_resting_states_give_the_orb(self, state):
        assert mode_for_state(state, expanded=False) == MODE_ORB

    @pytest.mark.parametrize("state", ["LISTENING", "SPEAKING"])
    def test_active_states_give_the_pill(self, state):
        assert mode_for_state(state, expanded=False) == MODE_PILL

    @pytest.mark.parametrize("state", ["IDLE", "LISTENING", "SPEAKING"])
    def test_expanded_always_wins(self, state):
        assert mode_for_state(state, expanded=True) == MODE_CARD

    def test_sizes_match_the_spec(self):
        assert MODE_SIZES[MODE_ORB] == (44, 44)
        assert MODE_SIZES[MODE_PILL] == (200, 48)
        assert MODE_SIZES[MODE_CARD] == (310, 340)

    def test_window_reports_pill_while_listening(self, window):
        window._apply_state("LISTENING")
        assert window.current_mode() == MODE_PILL
        window._apply_state("IDLE")
        assert window.current_mode() == MODE_ORB

    @pytest.mark.parametrize(("mode", "state"), [
        (MODE_ORB, "IDLE"),
        (MODE_PILL, "LISTENING"),
        (MODE_CARD, "IDLE"),
    ])
    def test_every_mode_paints(self, qtbot, window, mode, state):
        """
        Actually paint each mode.

        An exception inside paintEvent aborts the whole process rather than
        failing politely, so painting the card at least once is the only way to
        catch a bad QPainter call.
        """
        window._apply_state(state)
        window._expanded = mode == MODE_CARD
        window._apply_mode_layout(mode)
        window.resize(*MODE_SIZES[mode])
        window.chat.append("friday", "a reply long enough to wrap onto a second line")
        pixmap = window.grab()
        assert not pixmap.isNull()
        assert (pixmap.width(), pixmap.height()) == MODE_SIZES[mode]

    def test_expand_and_collapse_toggle_the_card(self, window):
        window.expand()
        assert window.current_mode() == MODE_CARD
        assert window.chat.isVisible() or window._pending_mode == MODE_CARD
        window.collapse()
        assert window.current_mode() == MODE_ORB


# --------------------------------------------------------------- clamping
class TestPositionClamping:
    SMALL = [QRect(0, 0, 800, 600)]

    def test_position_beyond_a_small_screen_is_pulled_back(self):
        # Saved on a 3840x2160 monitor, restored on an 800x600 one.
        x, y = clamp_to_available(3800, 2100, 44, 44, self.SMALL)
        assert (x, y) == (800 - 44, 600 - 44)

    def test_negative_position_is_pulled_to_the_origin(self):
        assert clamp_to_available(-500, -120, 44, 44, self.SMALL) == (0, 0)

    def test_position_already_inside_is_untouched(self):
        assert clamp_to_available(120, 90, 44, 44, self.SMALL) == (120, 90)

    def test_card_sized_window_is_clamped_by_its_full_size(self):
        w, h = MODE_SIZES[MODE_CARD]
        x, y = clamp_to_available(790, 590, w, h, self.SMALL)
        assert x + w <= 800
        assert y + h <= 600

    def test_screen_offset_is_respected(self):
        # Second monitor to the right of the primary.
        rects = [QRect(0, 0, 800, 600), QRect(800, 0, 1920, 1080)]
        assert clamp_to_available(3000, 40, 44, 44, rects) == (800 + 1920 - 44, 40)

    def test_window_larger_than_screen_is_pinned_to_the_top_left(self):
        assert clamp_to_available(50, 50, 2000, 2000, self.SMALL) == (0, 0)

    def test_no_screens_leaves_the_position_alone(self):
        assert clamp_to_available(10, 20, 44, 44, []) == (10, 20)

    def test_window_restores_on_screen(self, qtbot, window):
        window._settings.setValue("pos", None)
        x, y = window._restore_position()
        rects = window._screen_rects()
        w, h = MODE_SIZES[MODE_ORB]
        assert any(r.contains(QRect(x, y, w, h)) for r in rects) or not rects


# ------------------------------------------------------------- chat panel
class TestChatPanel:
    def test_message_submitted_fires_on_enter(self, qtbot):
        panel = ChatPanel()
        qtbot.addWidget(panel)
        panel.input_box.setText("what's the weather")
        with qtbot.waitSignal(panel.message_submitted, timeout=1000) as blocker:
            qtbot.keyClick(panel.input_box, Qt.Key.Key_Return)
        assert blocker.args == ["what's the weather"]
        assert panel.input_box.text() == ""

    def test_message_submitted_fires_on_send_click(self, qtbot):
        panel = ChatPanel()
        qtbot.addWidget(panel)
        panel.input_box.setText("open spotify")
        with qtbot.waitSignal(panel.message_submitted, timeout=1000) as blocker:
            qtbot.mouseClick(panel.send_button, Qt.MouseButton.LeftButton)
        assert blocker.args == ["open spotify"]

    def test_blank_input_emits_nothing(self, qtbot):
        panel = ChatPanel()
        qtbot.addWidget(panel)
        panel.input_box.setText("   ")
        with qtbot.assertNotEmitted(panel.message_submitted):
            panel.send_button.click()

    def test_mic_click_emits(self, qtbot):
        panel = ChatPanel()
        qtbot.addWidget(panel)
        with qtbot.waitSignal(panel.mic_clicked, timeout=1000):
            panel.mic_button.click()

    def test_append_adds_history_rows(self, qtbot):
        panel = ChatPanel()
        qtbot.addWidget(panel)
        assert panel.message_count() == 0
        panel.append("user", "hi")
        panel.append("friday", "hello")
        assert panel.message_count() == 2

    @pytest.mark.asyncio
    async def test_window_publishes_user_input_on_submit(self, qtbot, window):
        published = []

        async def _capture(event: UserInputEvent) -> None:
            published.append(event)

        window._event_bus.subscribe(UserInputEvent, _capture)
        window.chat.input_box.setText("hello friday")
        window.chat.send_button.click()
        await asyncio.sleep(0.05)

        assert [e.text for e in published] == ["hello friday"]
        assert published[0].source == "text"
        assert window.chat.message_count() == 1


# ------------------------------------------------------------------- STT
class TestMicAvailability:
    def test_mic_disabled_until_stt_is_set(self, window):
        assert window.chat.mic_button.isEnabled() is False
        assert window.orb.state() == "STARTING"
        assert window.chat.note_label.isVisible() is False or window.chat.note_label.text()

        window.set_stt(_FakeSTT())

        assert window.chat.mic_button.isEnabled() is True
        assert window.orb.state() == "IDLE"
        assert window.chat.note_label.text() == ""

    def test_typing_stays_available_while_stt_loads(self, window):
        assert window.chat.input_box.isEnabled() is True
        assert window.chat.send_button.isEnabled() is True

    def test_stt_failure_leaves_typing_working(self, window):
        window.set_stt(None, error="model missing")
        assert window.chat.mic_button.isEnabled() is False
        assert window.chat.input_box.isEnabled() is True
        assert window.orb.state() == "IDLE"
        assert "model missing" in window.chat.note_label.text()

    def test_mic_click_without_stt_is_a_no_op_note(self, window):
        window.chat.mic_button.setEnabled(True)  # bypass the guard the UI applies
        window._on_mic_click()
        assert window.chat.message_count() == 1

    def test_stt_provided_up_front_starts_idle(self, qtbot):
        win = MainWindow(EventBus(), _FakeRecorder(), _FakeSTT(), None, None)
        qtbot.addWidget(win)
        assert win.orb.state() == "IDLE"
        assert win.chat.mic_button.isEnabled() is True


# ------------------------------------------------------------ model switch
class TestModelSwitch:
    def test_toggle_switches_provider_and_label(self, window):
        """The chip shows a friendly label, not the raw model name.

        "qwen2.5:3b" means nothing to someone using the assistant, and the
        name now varies per machine because bootstrap picks it by hardware.
        """
        window.chat.set_model_label("nvidia")
        assert window.chat.model_button.text() == "Cloud model"

        window.chat.set_model_label("qwen")
        assert window.chat.model_button.text() == "Local model"

        # The real model name stays reachable on hover for debugging.
        window.chat.set_model_label("qwen", "qwen2.5:3b")
        assert "qwen2.5:3b" in window.chat.model_button.toolTip()

    def test_unknown_provider_falls_back_to_a_generic_label(self, window):
        window.chat.set_model_label("something-else")
        assert window.chat.model_button.text() == "Model"

    def test_toggle_without_a_container_is_harmless(self, qtbot):
        win = MainWindow(EventBus(), _FakeRecorder(), None, None, None)
        qtbot.addWidget(win)
        win._toggle_model()  # must not raise


# ------------------------------------------------------------- event wiring
class TestEventWiring:
    def test_subscribes_to_the_pipeline_events(self, window):
        assert window._event_bus.handler_count(ResponseReadyEvent) == 1
        assert window._event_bus.handler_count(StateChangedEvent) == 1

    @pytest.mark.asyncio
    async def test_response_event_appends_and_re_enables_inputs(self, window):
        window._set_inputs_enabled(False)
        await window._event_bus.publish(ResponseReadyEvent(response="done"))
        assert window.chat.message_count() == 1
        assert window.chat.input_box.isEnabled() is True

    @pytest.mark.asyncio
    async def test_state_event_drives_the_orb(self, window):
        await window._event_bus.publish(
            StateChangedEvent(old_state="IDLE", new_state="SPEAKING"),
        )
        assert window.orb.state() == "SPEAKING"
        assert window.current_mode() == MODE_PILL


# ----------------------------------------------------------------- barge-in
class TestBargeIn:
    @pytest.mark.asyncio
    async def test_mic_click_while_speaking_stops_playback_then_listens(
        self, window, monkeypatch,
    ):
        calls = []
        monkeypatch.setattr(window, "_stop_speech", lambda: calls.append("stop"))

        async def _fake_listen() -> None:
            calls.append("listen")

        monkeypatch.setattr(window, "_do_listen", _fake_listen)
        window.set_stt(_FakeSTT())
        window._apply_state("SPEAKING")

        window._on_mic_click()
        await asyncio.sleep(0.05)

        assert calls == ["stop", "listen"]  # playback is cut *before* listening
        assert window.orb.state() == "LISTENING"

    def test_mic_click_stops_playback_even_with_no_stt(self, window, monkeypatch):
        calls = []
        monkeypatch.setattr(window, "_stop_speech", lambda: calls.append("stop"))
        window._on_mic_click()
        assert calls == ["stop"]

    def test_stop_speech_never_raises(self, window):
        window._stop_speech()  # audio backend may be absent; must be swallowed
