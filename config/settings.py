"""
config/settings.py – Application Settings Schema
==================================================
Loads configuration from environment variables and dotenv file using Pydantic Settings.

Team: Core Platform Team
Phase: 0 (Implementation)
"""

from __future__ import annotations

from pathlib import Path
from pydantic import SecretStr, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from utils.exceptions import ConfigurationError


class Settings(BaseSettings):
    """
    Application settings schema.
    Loads from .env and supports validation.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # ── Application Settings ──
    app_name: str = Field(default="ULTRON")
    app_version: str = Field(default="0.1.0")
    app_env: str = Field(default="development")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")
    log_dir: Path = Field(default=Path("logs"))

    # ── LLM Integration (NVIDIA NIM) ──
    nvidia_api_key: SecretStr = Field(default=SecretStr(""))
    nvidia_base_url: str = Field(default="https://integrate.api.nvidia.com/v1")
    # The previous default, meta/llama-3.1-8b-instruct, now returns HTTP 410
    # Gone -- NVIDIA retired it, and the whole cloud path had been silently
    # dead since. Of the models actually invocable on this endpoint today,
    # nemotron-3-super is both the fastest measured (~1.9s per tool-calling
    # round trip) and correct on every tool-choice probe. See the note on
    # llm/nvidia.py for how to re-check when this one is retired in turn.
    nvidia_model: str = Field(default="nvidia/nemotron-3-super-120b-a12b")
    # Fast model for quick responses (can override via env)
    nvidia_fast_model: str = Field(default="nvidia/nemotron-3-nano-30b-a3b")

    # Shared LLM settings
    llm_temperature: float = Field(default=0.1)  # Lower for faster, more deterministic
    llm_max_tokens: int = Field(default=256)      # Reduced for speed
    llm_timeout_seconds: int = Field(default=15)  # Reduced timeout

    # ── LLM Integration (Groq Cloud) ──
    groq_api_key: SecretStr = Field(default=SecretStr(""))
    groq_base_url: str = Field(default="https://api.groq.com/openai/v1")
    groq_model: str = Field(default="openai/gpt-oss-20b")
    groq_fast_model: str = Field(default="openai/gpt-oss-20b")

    # LLM Provider selection (nvidia | qwen | groq | dual)
    llm_provider: str = Field(default="groq")
    dual_llm_primary: str = Field(default="groq")
    dual_llm_secondary: str = Field(default="nvidia")
    dual_llm_strategy: str = Field(default="speculative_race")

    # Local Qwen / Ollama settings
    ollama_base_url: str = Field(default="http://localhost:11434")
    # qwen3:4b-instruct replaced qwen2.5:3b. The 2.5 model could not drive the
    # agent loop (0/2 on the fix loop, parroted "LOOKING" from its own system
    # prompt — see docs/ULTRON_PHASE2_SPEC.md).
    #
    # The "-instruct" is load-bearing, not a longer way of writing qwen3:4b.
    # Plain qwen3:4b is a hybrid reasoning model, and on Ollama 0.32.14 its
    # thinking cannot be switched off: think=False makes it emit the trace
    # into the answer anyway, think=True keeps the answer clean but still
    # spends the tokens, and /no_think does nothing. On open-ended prompts the
    # trace consumes the entire num_predict budget and the reply comes back
    # empty. Measured here: 16-30s per chat reply and 1 in 4 empty, against
    # 1.5-2.2s for the instruct release.
    qwen_model: str = Field(default="qwen3:4b-instruct")
    # Explicit context window for local calls. Ollama's default is small (4k)
    # and it TRUNCATES THE FRONT of an oversized prompt silently — system
    # prompt and tool definitions vanish first, which presents as "the model
    # ignored its instructions" rather than as an error. Agent-mode prompts
    # (system + ~40 tool schemas + transcript) do not fit in 4k.
    qwen_num_ctx: int = Field(default=8192)

    # ── Agent mode ──
    # The tool-calling turn (intelligence/agent_loop.py) that replaced one-shot
    # intent classification. On by default; it falls back to the classifier on
    # its own whenever the active provider cannot call tools, so leaving this
    # true costs nothing on a model that cannot use it.
    agent_mode: bool = Field(default=True)
    # Tool calls allowed per turn.
    #
    # Twelve, not six. Six covered "look, then act"; the verified fix loop is
    # read the error, copy to a shadow, then edit-run-check repeatedly, then
    # apply -- about ten calls when the first attempt is wrong, which it
    # usually is. A budget that cuts the loop off mid-way is worse than no
    # loop, because the user is told a fix was attempted and the file is
    # unchanged.
    agent_max_steps: int = Field(default=12)
    # Edit-run-check rounds inside one fix attempt before giving up and
    # reporting what was tried. Separate from the step budget so a model stuck
    # re-trying one wrong idea stops early instead of consuming every step.
    agent_fix_max_iterations: int = Field(default=4)
    # Programs run_command may start, as a comma-separated list. An allowlist
    # rather than a shell: the point is to run the user's own code and read
    # what it prints, not to give a language model a terminal.
    agent_run_allowlist: str = Field(default="python,py,pytest,node,npm,code")
    # Ceiling on a single run_command. Long enough for a test suite to say
    # something useful, short enough that a hung process does not eat the turn.
    agent_run_timeout_seconds: int = Field(default=45)
    # Output tokens for one tool-calling turn.
    #
    # Far larger than llm_max_tokens (256), which is tuned for a spoken
    # sentence. A tool call is structured output, and a reasoning model thinks
    # before it emits one -- at 256 tokens nemotron ran out mid-thought and the
    # loop returned the half-finished reasoning as its answer. Truncation is
    # indistinguishable from a model choosing to stop, so the loop cannot
    # detect it and the budget simply has to be right.
    agent_max_tokens: int = Field(default=2048)
    # Backstop against a wedged turn, not a latency target: one legitimate
    # tool (research) is itself a 45-second budget.
    agent_time_budget_seconds: int = Field(default=120)
    # How long to wait for a spoken yes or no before treating silence as no.
    agent_confirm_timeout_seconds: int = Field(default=25)

    # ── Browser control ──
    # False: Playwright launches its own Chromium. Nothing is logged in, so
    # the browser tools can reach public pages and none of the user's
    # accounts.
    #
    # True: attach to a Chrome the user started themselves with
    # --remote-debugging-port. Their cookies and sessions, which is what "do
    # this in *my* Gmail" requires -- and the reason browser_click and
    # browser_type are confirmed with the user before they act.
    #
    # On by default now that control_my_chrome exists to enable it. Before
    # that tool, attaching could only fail -- Chrome exposes the debug port
    # only when launched with the flag, so a normally-started browser was
    # unreachable and ULTRON silently used its own logged-out Chromium
    # instead. "Control the browser" should mean the user's browser; the
    # owned Chromium remains the fallback when they decline the restart.
    browser_attach: bool = Field(default=True)
    browser_cdp_port: int = Field(default=9222)

    # ── Deep research ──
    # The iterative web-research loop behind "look this up". Every one of
    # these is a latency dial: the assistant is spoken to, so an answer that
    # is 20% better and 60 seconds later is a worse answer.
    #
    # Two rounds is the useful minimum — one round is the old one-shot search
    # this replaced, and the second round is the one that fills the gap the
    # first round revealed. Beyond that the returns fall off faster than the
    # wait does.
    research_max_rounds: int = Field(default=2)
    # Five pages is roughly what a 3B model can hold and still write a
    # coherent answer from; more sources make it summarise the pile instead
    # of answering the question.
    research_max_sources: int = Field(default=5)
    # A ceiling on gathering, not on the whole turn: synthesis still runs on
    # whatever was collected when the clock ran out.
    research_time_budget_seconds: int = Field(default=45)
    # Per source, so one long page cannot crowd the other four out of the
    # prompt. Five of these is the synthesis context budget.
    research_chars_per_source: int = Field(default=2500)

    # Screen vision. Kept separate from qwen_model because the chat model and
    # the vision model are different jobs with different best local choices —
    # a 3B text model talks well and cannot see at all. Install with:
    #   ollama pull qwen2.5vl:3b
    vision_model: str = Field(default="qwen2.5vl:3b")

    # Vision latency. The dominant cost is not inference, it is Ollama
    # evicting the model after its default five minutes idle and reloading it
    # from disk on the next question. keep_alive holds it in RAM; preload pays
    # the first load at startup instead of on the user's first question.
    vision_keep_alive: str = Field(default="30m")
    vision_preload: bool = Field(default=True)
    # Longest edge of the screenshot. Every pixel above this is decode time on
    # a CPU-bound 3B model, not detail.
    vision_max_edge: int = Field(default=896)
    vision_jpeg_quality: int = Field(default=75)
    # Answers are spoken in one to three sentences; a bigger budget is decode
    # time the user spends waiting in silence.
    vision_num_predict: int = Field(default=128)
    # A ceiling, not a target — it exists so a stall is distinguishable from
    # a hang. A genuinely cold model can take most of a minute.
    vision_timeout_seconds: int = Field(default=90)

    # Speech performance tuning
    stt_model: str = Field(default="base")
    stt_device: str = Field(default="cpu")
    stt_compute_type: str = Field(default="int8")
    stt_beam_size: int = Field(default=3)
    tts_voice_rate: int = Field(default=175)
    tts_voice_volume: float = Field(default=1.0)
    audio_sample_rate: int = Field(default=16000)
    audio_channels: int = Field(default=1)
    audio_chunk_size: int = Field(default=1024)
    silence_timeout: float = Field(default=2.0)
    stt_rolling_buffer_blocks: int = Field(default=5)

    # Hold-to-talk / Whisperflow settings (no-wake mode)
    hold_to_talk_key: str = Field(default="right_shift")

    # ── Speech Settings ──
    stt_engine: str = Field(default="whisper")
    tts_engine: str = Field(default="pyttsx3")
    tts_voice_rate: int = Field(default=175)
    tts_voice_volume: float = Field(default=1.0)
    audio_sample_rate: int = Field(default=16000)
    audio_channels: int = Field(default=1)
    audio_chunk_size: int = Field(default=1024)

    # ── Wake Word Settings ──
    wakeword_engine: str = Field(default="porcupine")
    wakeword_keyword: str = Field(default="ultron")
    picovoice_access_key: SecretStr = Field(default=SecretStr(""))
    wakeword_sensitivity: float = Field(default=0.5)

    # ── Context Memory ──
    memory_enabled: bool = Field(default=True)
    memory_path: Path = Field(default=Path("data/memory.json"))
    memory_max_facts: int = Field(default=200)

    # ── Orchestration & Security ──
    intent_confidence_threshold: float = Field(default=0.75)
    max_plan_steps: int = Field(default=10)
    secret_key: SecretStr = Field(default=SecretStr("dev_secret_key_change_in_production"))

    # Optional Weaviate configuration for vector search
    weaviate_url: str | None = Field(default=None)
    weaviate_api_key: SecretStr | None = Field(default=None)

    # Embeddings / external API keys
    openai_api_key: SecretStr | None = Field(default=None)
    openai_embedding_model: str = Field(default="text-embedding-3-small")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v.upper()

    @field_validator("log_dir")
    @classmethod
    def validate_log_dir(cls, v: Path) -> Path:
        # Create directory if it doesn't exist
        try:
            v.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            raise ValueError(f"Could not create log directory '{v}': {exc}")
        return v

    @classmethod
    def load(cls, env_file: Path | None = None, debug: bool = False) -> Settings:
        """
        Load configuration from the environment and optional dotenv file.
        """
        try:
            if env_file:
                return cls(_env_file=env_file, debug=debug)
            return cls(debug=debug)
        except Exception as exc:
            raise ConfigurationError(f"Failed to load application settings: {exc}") from exc
