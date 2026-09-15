"""
utils/preflight.py – Startup Health Checks
===========================================
Verifies that the things Friday needs in order to *think* are actually
present before the microphone opens.

Why this module exists
----------------------
Speech-to-text and intent detection fail in very different ways, and the
difference is invisible to the user. When Ollama is not running, the mic
still works, the transcript is still perfect, and every LLM call inside
``IntentDetector.detect`` raises — at which point the detector quietly falls
back to its regex rules. The user sees an assistant that heard them
correctly and then did something unrelated, which reads as "the AI is dumb"
rather than "a background service is down".

So the check happens here, once, at startup, where it can be reported in
plain language and — because the models are already on disk — usually fixed
automatically instead of merely complained about.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from config.settings import Settings


#: How long a single probe of the Ollama HTTP API may take. The server either
#: answers this immediately or is not listening; a generous timeout here only
#: delays the diagnosis.
PROBE_TIMEOUT_SECONDS = 2.0

#: How long to wait for a server we started ourselves to begin listening.
#:
#: This was 10s on the assumption that a local server binds its port almost
#: immediately. It does not: `ollama serve` enumerates installed models and
#: brings up its runner first, and a measured cold start on the development
#: laptop took 16.4s. At 10s the autostart always "failed", printed the
#: install instructions, and then Ollama finished starting a few seconds
#: later -- the worst of both outcomes. 45s leaves room for a slower or
#: busier machine while still ending in a message rather than a hang.
STARTUP_GRACE_SECONDS = 45.0

#: Gap between re-probes while waiting for a starting server.
STARTUP_POLL_SECONDS = 0.4


@dataclass
class PreflightResult:
    """Outcome of the startup checks.

    ``ok`` means Friday can reason. Warnings are things worth printing that
    do not stop it from running; ``problems`` are the ones that do.
    """

    ok: bool
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: True when this run started the Ollama server itself, which is worth
    #: telling the user so the new background process is not a surprise.
    started_ollama: bool = False


def _tags_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/api/tags"


def probe_ollama(base_url: str, timeout: float = PROBE_TIMEOUT_SECONDS) -> list[str] | None:
    """Return the model names Ollama is serving, or None when it is not up.

    An empty list is a meaningful answer — the server is running but has no
    models pulled — so "not running" has to be None rather than falsy.
    """
    try:
        response = httpx.get(_tags_url(base_url), timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return None

    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        return []

    return [
        str(entry.get("name", ""))
        for entry in models
        if isinstance(entry, dict) and entry.get("name")
    ]


def list_nvidia_models(settings) -> list[str] | None:
    """Model ids the NVIDIA endpoint is currently serving, or None.

    None means "could not check" -- no network, a proxy, a slow endpoint --
    which is deliberately different from "the model is wrong". Only a real
    listing is allowed to produce a complaint.
    """
    try:
        import httpx

        key = settings.nvidia_api_key
        value = key.get_secret_value() if hasattr(key, "get_secret_value") else key
        if not value:
            return None

        response = httpx.get(
            f"{settings.nvidia_base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {value}"},
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            return None

        return [entry["id"] for entry in response.json().get("data", [])]
    except Exception:
        return None


def _model_is_present(wanted: str, available: list[str]) -> bool:
    """True when the configured model matches something Ollama is serving.

    Ollama reports fully-qualified tags ("qwen2.5:3b"), but a config may name
    the model without one ("qwen2.5"), which Ollama itself resolves to
    ":latest". Matching on the bare name in that case keeps a reasonable
    config from being reported as a missing model.
    """
    wanted = (wanted or "").strip()
    if not wanted:
        return False

    if wanted in available:
        return True

    if ":" not in wanted:
        return any(name.split(":", 1)[0] == wanted for name in available)

    return False


def start_ollama_server() -> bool:
    """Launch `ollama serve` in the background.

    Returns False when the binary is not installed, which is a different
    problem with a different fix and should not be reported as a failed
    start.
    """
    binary = shutil.which("ollama")
    if binary is None:
        return False

    # Output-suppressed and given its own hidden console: this is a long-lived
    # background service, not a subprocess whose result we intend to read.
    #
    # CREATE_NO_WINDOW *alone*, deliberately. It already does what
    # DETACHED_PROCESS was added for -- the server gets its own console rather
    # than Friday's, so it cannot print into the conversation and Ctrl+C does
    # not reach it -- and the two must not be combined: Windows documents
    # CREATE_NO_WINDOW as ignored when passed with DETACHED_PROCESS. That left
    # the server with no console at all, and a console process with no console
    # allocates a fresh visible one for every console child it spawns. Ollama
    # spawns several (GPU probes, a runner per model), so starting Friday
    # sprayed black console windows across the screen.
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        subprocess.Popen(
            [binary, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
    except Exception:
        return False

    return True


def _wait_for_ollama(base_url: str, grace: float = STARTUP_GRACE_SECONDS) -> list[str] | None:
    """Poll until the server answers or the grace period runs out."""
    deadline = time.monotonic() + grace

    while time.monotonic() < deadline:
        models = probe_ollama(base_url)
        if models is not None:
            return models
        time.sleep(STARTUP_POLL_SECONDS)

    return None


def check_llm(settings: Settings, *, autostart: bool = True) -> PreflightResult:
    """Verify the configured LLM provider can actually answer.

    NVIDIA is checked for a key, and for whether the configured model still
    exists. A bad key surfaces on the first message with a clear API error and
    needs no probe; a *retired* model does not -- the previous default started
    returning 410 Gone and the cloud path was silently dead. Ollama gets the
    full treatment because its failure mode is silent in the same way.
    """
    provider = (settings.llm_provider or "").lower()

    if provider == "nvidia":
        key = settings.nvidia_api_key
        value = key.get_secret_value() if hasattr(key, "get_secret_value") else key
        if not value:
            return PreflightResult(
                ok=False,
                problems=[
                    "LLM_PROVIDER is 'nvidia' but NVIDIA_API_KEY is not set. "
                    "Set the key in .env, or switch to the local model with "
                    "LLM_PROVIDER=qwen."
                ],
            )

        # One cheap listing, and only to catch a model that no longer exists.
        # The configured default was retired upstream and started answering
        # 410 Gone; nothing said so, so every later symptom looked like FRIDAY
        # being broken. A warning rather than a failure: the listing does not
        # always include every model a key can reach, and refusing to start
        # over that would be worse than the silence it replaces.
        available = list_nvidia_models(settings)
        wanted = settings.nvidia_model

        if available and wanted not in available:
            return PreflightResult(
                ok=True,
                problems=[
                    f"NVIDIA model '{wanted}' is not available on this "
                    f"endpoint -- it may have been retired. Set NVIDIA_MODEL "
                    f"in .env to one that is, or switch to LLM_PROVIDER=qwen."
                ],
            )

        return PreflightResult(ok=True)

    if provider != "qwen":
        return PreflightResult(
            ok=True,
            warnings=[f"Unrecognised LLM_PROVIDER '{settings.llm_provider}'."],
        )

    base_url = settings.ollama_base_url
    wanted_model = settings.qwen_model

    models = probe_ollama(base_url)
    started = False

    if models is None and autostart:
        # The models are on disk and the binary is installed in the common
        # case; the only thing missing is a running server. Starting it is
        # strictly better than telling the user to open another terminal.
        if start_ollama_server():
            # Said before the wait, not after: this blocks for ~16s on a cold
            # start, and an unexplained pause at launch reads as a hang.
            print("[PRE] Starting Ollama (this takes a few seconds)...")
            sys.stdout.flush()
            models = _wait_for_ollama(base_url)
            started = models is not None

    if models is None:
        if shutil.which("ollama") is None:
            return PreflightResult(
                ok=False,
                problems=[
                    f"Ollama is not installed, but LLM_PROVIDER=qwen needs it. "
                    f"Install it from https://ollama.com/download, then run "
                    f"`ollama pull {wanted_model}`."
                ],
            )
        return PreflightResult(
            ok=False,
            problems=[
                f"Ollama is not responding at {base_url} and could not be "
                f"started automatically. Run `ollama serve` in another "
                f"terminal, then start Friday again."
            ],
        )

    result = PreflightResult(ok=True, started_ollama=started)

    if not _model_is_present(wanted_model, models):
        # Not fatal at startup: Ollama pulls a missing model on first use. But
        # that first use is an intent detection with a 15 second timeout, so
        # the pull will lose the race and the turn will silently fall back.
        result.ok = False
        result.problems.append(
            f"Ollama is running but the model '{wanted_model}' is not "
            f"installed. Run `ollama pull {wanted_model}`."
            + (f" Available: {', '.join(models)}." if models else "")
        )

    return result


def report(result: PreflightResult) -> None:
    """Print a preflight outcome in the launcher's voice."""
    if result.started_ollama:
        print("[PRE] Ollama was not running - started it in the background.")

    for warning in result.warnings:
        print(f"[PRE] Warning: {warning}")

    if result.ok:
        return

    print("\n[PRE] Friday cannot reason properly right now:\n")
    for problem in result.problems:
        print(f"  - {problem}")
    print(
        "\n  Speech recognition would still work, but every request would "
        "fall back to\n  simple keyword rules and frequently do the wrong "
        "thing. Fix the above first.\n"
    )
    sys.stdout.flush()
