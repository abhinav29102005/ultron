"""
Tests for utils/preflight.py.

Bug this covers: with Ollama stopped, Friday started normally, transcribed
speech correctly, and then silently fell back to regex intent rules for every
single request -- so it reliably did the wrong thing while looking healthy.
Nothing anywhere checked that the LLM backend was reachable.

No test here touches the network or a real Ollama; the HTTP probe is stubbed.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from config.settings import Settings
from utils import preflight
from utils.preflight import (
    PreflightResult,
    check_llm,
    start_ollama_server,
    _model_is_present,
)


def _settings(provider: str = "qwen", model: str = "qwen2.5:3b", key: str = "") -> Settings:
    s = Settings()
    s.llm_provider = provider
    s.qwen_model = model
    s.nvidia_api_key = SecretStr(key)
    return s


@pytest.fixture
def probe(monkeypatch):
    """Control what the Ollama probe reports, without any HTTP."""

    state = {"models": ["qwen2.5:3b", "qwen2.5vl:3b"], "calls": 0}

    def fake_probe(base_url, timeout=None):
        state["calls"] += 1
        return state["models"]

    monkeypatch.setattr(preflight, "probe_ollama", fake_probe)
    return state


@pytest.fixture(autouse=True)
def no_real_server(monkeypatch):
    """Never actually spawn `ollama serve` from a test."""
    monkeypatch.setattr(preflight, "start_ollama_server", lambda: False)


class TestOllamaReachability:
    def test_running_with_the_model_present_passes(self, probe):
        result = check_llm(_settings())
        assert result.ok is True
        assert result.problems == []

    def test_server_down_is_a_hard_problem(self, probe, monkeypatch):
        probe["models"] = None
        monkeypatch.setattr(preflight.shutil, "which", lambda name: r"C:\ollama.exe")

        result = check_llm(_settings(), autostart=False)

        assert result.ok is False
        assert any("not responding" in p for p in result.problems)

    def test_missing_binary_is_reported_as_an_install_problem(self, probe, monkeypatch):
        probe["models"] = None
        monkeypatch.setattr(preflight.shutil, "which", lambda name: None)

        result = check_llm(_settings(), autostart=False)

        assert result.ok is False
        assert any("not installed" in p for p in result.problems)

    def test_running_but_model_not_pulled_is_a_problem(self, probe):
        probe["models"] = ["llama3:8b"]

        result = check_llm(_settings(model="qwen2.5:3b"))

        assert result.ok is False
        assert any("ollama pull qwen2.5:3b" in p for p in result.problems)

    def test_server_with_no_models_is_not_mistaken_for_a_dead_server(self, probe):
        """An empty model list is a running server, not a missing one -- the
        two need different advice, so probe_ollama distinguishes [] from None."""
        probe["models"] = []

        result = check_llm(_settings(), autostart=False)

        assert result.ok is False
        assert any("not installed" in p and "model" in p for p in result.problems)
        assert not any("not responding" in p for p in result.problems)


class TestAutostart:
    def test_a_successful_autostart_is_reported(self, monkeypatch):
        attempts = {"n": 0}

        def fake_probe(base_url, timeout=None):
            # Down on the first look, up once the server has been started.
            attempts["n"] += 1
            return None if attempts["n"] == 1 else ["qwen2.5:3b"]

        monkeypatch.setattr(preflight, "probe_ollama", fake_probe)
        monkeypatch.setattr(preflight, "start_ollama_server", lambda: True)

        result = check_llm(_settings(), autostart=True)

        assert result.ok is True
        assert result.started_ollama is True

    def test_autostart_is_skipped_when_disabled(self, probe, monkeypatch):
        probe["models"] = None
        monkeypatch.setattr(preflight.shutil, "which", lambda name: r"C:\ollama.exe")
        started = {"called": False}

        def spy():
            started["called"] = True
            return True

        monkeypatch.setattr(preflight, "start_ollama_server", spy)

        check_llm(_settings(), autostart=False)

        assert started["called"] is False


class TestNvidiaProvider:
    def test_missing_key_is_caught_at_startup(self):
        result = check_llm(_settings(provider="nvidia", key=""))
        assert result.ok is False
        assert any("NVIDIA_API_KEY" in p for p in result.problems)

    def test_a_key_is_enough_to_pass(self):
        assert check_llm(_settings(provider="nvidia", key="sk-test")).ok is True

    def test_nvidia_does_not_probe_ollama(self, probe):
        check_llm(_settings(provider="nvidia", key="sk-test"))
        assert probe["calls"] == 0


class TestModelMatching:
    def test_exact_tag_matches(self):
        assert _model_is_present("qwen2.5:3b", ["qwen2.5:3b"]) is True

    def test_untagged_name_matches_a_tagged_install(self):
        """Ollama resolves a bare name to ':latest', so a config that omits
        the tag is valid and must not be reported as a missing model."""
        assert _model_is_present("qwen2.5", ["qwen2.5:latest"]) is True

    def test_a_different_tag_does_not_match(self):
        assert _model_is_present("qwen2.5:7b", ["qwen2.5:3b"]) is False

    def test_empty_name_never_matches(self):
        assert _model_is_present("", ["qwen2.5:3b"]) is False


class TestReporting:
    def test_report_is_quiet_on_success(self, capsys):
        preflight.report(PreflightResult(ok=True))
        assert capsys.readouterr().out == ""

    def test_report_names_the_problem_and_the_consequence(self, capsys):
        preflight.report(PreflightResult(ok=False, problems=["Ollama is not responding."]))
        out = capsys.readouterr().out
        assert "Ollama is not responding." in out
        # The point of the message: explain why a working mic is not proof
        # that the assistant is working.
        assert "keyword rules" in out


class TestServerLaunchFlags:
    """The Windows creation flags `ollama serve` is launched with.

    Bug this covers: the server was started with
    ``DETACHED_PROCESS | CREATE_NO_WINDOW``. Windows documents CREATE_NO_WINDOW
    as *ignored* when combined with DETACHED_PROCESS, so the server came up
    with no console at all -- and every console subprocess Ollama then spawns
    (GPU probes, model runners) had to allocate its own console, which is
    visible. Starting Friday sprayed black console windows across the screen.

    CREATE_NO_WINDOW on its own gives the server a real but windowless console
    that its children inherit, which is what keeps the whole tree invisible.
    It also still gives the server its *own* console rather than Friday's, so
    the server cannot print into the conversation and Ctrl+C does not reach it
    -- the two things DETACHED_PROCESS was there for.
    """

    @pytest.fixture
    def spawn(self, monkeypatch):
        calls: list[dict] = []

        monkeypatch.setattr(preflight.shutil, "which", lambda _: r"C:\ollama.exe")
        monkeypatch.setattr(
            preflight.subprocess, "Popen", lambda *a, **kw: calls.append(kw)
        )
        monkeypatch.setattr(preflight.sys, "platform", "win32")
        return calls

    def test_no_window_flag_is_set(self, spawn):
        assert start_ollama_server() is True
        assert spawn[0]["creationflags"] & preflight.subprocess.CREATE_NO_WINDOW

    def test_detached_process_is_not_combined_with_it(self, spawn):
        start_ollama_server()
        flags = spawn[0]["creationflags"]
        assert not flags & preflight.subprocess.DETACHED_PROCESS, (
            "DETACHED_PROCESS makes Windows ignore CREATE_NO_WINDOW, which is "
            "what let Ollama's child processes open visible console windows."
        )

    def test_other_platforms_pass_no_flags(self, spawn, monkeypatch):
        monkeypatch.setattr(preflight.sys, "platform", "linux")
        start_ollama_server()
        assert spawn[0]["creationflags"] == 0


class TestNvidiaModelProbe:
    """A retired cloud model is caught at boot, not on the first question.

    check_llm deliberately skips a network probe for NVIDIA -- a bad key
    surfaces on the first message with a clear error, and a round trip at
    startup costs more than it tells you. A *retired model* is different: the
    configured default (meta/llama-3.1-8b-instruct) started returning HTTP 410
    Gone, and nothing said so. The cloud path was silently dead, and every
    symptom looked like FRIDAY misbehaving rather than a model that no longer
    exists.

    So the model list is checked, and only that. It is one cheap call, it
    cannot be confused with a key problem, and it is a warning rather than a
    failure -- an unreachable API at boot must not stop FRIDAY starting.
    """

    def test_a_live_model_passes_quietly(self, monkeypatch):
        monkeypatch.setattr(
            preflight, "list_nvidia_models", lambda s: ["nvidia/nemotron-3-super-120b-a12b"]
        )
        result = check_llm(_settings(provider="nvidia", key="sk-test"))

        assert result.ok is True
        assert result.problems == []

    def test_a_retired_model_is_named_in_the_problems(self, monkeypatch):
        monkeypatch.setattr(preflight, "list_nvidia_models", lambda s: ["some/other-model"])

        result = check_llm(_settings(provider="nvidia", key="sk-test"))

        joined = " ".join(result.problems)
        assert "qwen2.5:3b" not in joined
        assert "not available" in joined.lower() or "retired" in joined.lower()

    def test_a_retired_model_does_not_stop_startup(self, monkeypatch):
        """Degraded, not dead: the user may have set a model the listing does
        not report, and refusing to boot over that would be worse."""
        monkeypatch.setattr(preflight, "list_nvidia_models", lambda s: ["some/other-model"])

        assert check_llm(_settings(provider="nvidia", key="sk-test")).ok is True

    def test_an_unreachable_api_is_not_reported_as_a_bad_model(self, monkeypatch):
        """None means "could not check", which is not the same as "wrong"."""
        monkeypatch.setattr(preflight, "list_nvidia_models", lambda s: None)

        result = check_llm(_settings(provider="nvidia", key="sk-test"))

        assert result.ok is True
        assert result.problems == []

    def test_a_missing_key_still_short_circuits_before_any_probe(self, monkeypatch):
        """No key means nothing to probe with."""
        called = []
        monkeypatch.setattr(preflight, "list_nvidia_models", lambda s: called.append(1))

        result = check_llm(_settings(provider="nvidia", key=""))

        assert result.ok is False
        assert called == []
