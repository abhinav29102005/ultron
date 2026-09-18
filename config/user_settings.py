"""
config/user_settings.py – User Settings & Safety Guardrails Engine
===================================================================
Manages configurable runtime user preferences with database persistence:
  1. Execution Mode: hybrid | online | offline
  2. Voice Assistant: voice_enabled, voice_output_mode
  3. Context Continuity: context_continuity, max_context_turns, auto_session_save
  4. Guardrails: guardrails_enabled, confirm_destructive_commands, restricted_paths
  5. Response Limiters: max_response_tokens, fast_response_mode, concise_mode
  6. Response Management: output_style, show_citations, show_telemetry
  7. Token Monitoring: track_tokens, session_token_budget
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ultron.settings")


@dataclass
class UserSettings:
    # ── Model Execution Mode ──
    # hybrid: Cloud for reasoning + local Ollama for vision/fallback
    # online: Cloud-only (NVIDIA NIM)
    # offline: 100% Local (Ollama Qwen) with zero external calls
    execution_mode: str = "hybrid"

    # ── Voice Assistant ──
    voice_enabled: bool = False
    voice_output_mode: str = "on_voice_input"  # always | on_voice_input | never

    # ── Context Continuity & Switching ──
    context_continuity: bool = True
    max_context_turns: int = 20
    auto_session_save: bool = True

    # ── Safety Guardrails ──
    guardrails_enabled: bool = True
    confirm_destructive_commands: bool = True
    restricted_paths: List[str] = field(
        default_factory=lambda: ["/etc", "/root", "C:\\Windows", ".ssh", ".git", "/dev"]
    )
    blocked_commands: List[str] = field(
        default_factory=lambda: ["rm -rf /", "mkfs", "format c:", "dd if="]
    )

    # ── Response Limiters & Speed ──
    max_response_tokens: int = 512
    fast_response_mode: bool = True
    concise_mode: bool = False

    # ── Response Management ──
    output_style: str = "cybernetic"  # cybernetic | compact | markdown
    show_citations: bool = True
    show_telemetry: bool = True

    # ── Token Usage Monitoring ──
    track_tokens: bool = True
    session_token_budget: int = 100000
    cost_per_1k_tokens: float = 0.0015

    # ── User Profile & Identity ──
    user_name: Optional[str] = None
    user_email: Optional[str] = None

    # ── Response Verbosity & Detail Control ──
    # short (1-2 sentences) | moderate (2-4 sentences, default) | detailed (in-depth & structured)
    verbosity: str = "moderate"

    # ── Cross-Platform System & Hardware Control ──
    preferred_browser: str = "chrome"  # chrome | firefox | brave | edge | default
    preferred_audio_device: Optional[str] = None
    default_volume: int = 50
    default_brightness: int = 70

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> UserSettings:
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)

    async def load_from_db(self, db) -> None:
        """Load settings from database table."""
        try:
            stored = await db.get_all_settings()
            if stored:
                for k, v in stored.items():
                    if hasattr(self, k):
                        setattr(self, k, v)
        except Exception as e:
            logger.warning(f"Could not load settings from DB ({e}); using defaults.")

    async def save_to_db(self, db) -> None:
        """Persist all current settings to database."""
        try:
            for k, v in self.to_dict().items():
                await db.set_setting(k, v)
        except Exception as e:
            logger.error(f"Error saving settings to DB: {e}")

    async def update_setting(self, db, key: str, raw_value: str) -> Tuple[bool, str]:
        """Update a specific setting with validation and type casting."""
        if not hasattr(self, key):
            return False, f"Unknown setting '{key}'. Run /settings to see valid keys."

        current_val = getattr(self, key)
        parsed_val: Any = raw_value

        # Type conversion
        if isinstance(current_val, bool):
            lower = raw_value.lower()
            if lower in ("true", "1", "yes", "on", "enable"):
                parsed_val = True
            elif lower in ("false", "0", "no", "off", "disable"):
                parsed_val = False
            else:
                return False, f"Expected boolean (true/false) for {key}, got '{raw_value}'"
        elif isinstance(current_val, int):
            try:
                parsed_val = int(raw_value)
            except ValueError:
                return False, f"Expected integer for {key}, got '{raw_value}'"
        elif isinstance(current_val, float):
            try:
                parsed_val = float(raw_value)
            except ValueError:
                return False, f"Expected float for {key}, got '{raw_value}'"
        elif key == "execution_mode":
            mode = raw_value.lower()
            if mode not in ("hybrid", "online", "offline"):
                return False, f"Invalid execution mode '{mode}'. Choose: hybrid, online, offline"
            parsed_val = mode
        elif key == "output_style":
            style = raw_value.lower()
            if style not in ("cybernetic", "compact", "markdown"):
                return False, f"Invalid output style '{style}'. Choose: cybernetic, compact, markdown"
            parsed_val = style
        elif key == "verbosity":
            v = raw_value.lower().strip()
            if v not in ("short", "moderate", "detailed"):
                return False, f"Invalid verbosity '{v}'. Choose: short, moderate, detailed"
            parsed_val = v
        elif key == "preferred_browser":
            b = raw_value.lower().strip()
            if b not in ("chrome", "firefox", "brave", "edge", "default"):
                return False, f"Invalid browser '{b}'. Choose: chrome, firefox, brave, edge, default"
            parsed_val = b
        elif key in ("user_name", "user_email", "preferred_audio_device"):
            parsed_val = raw_value.strip() or None

        setattr(self, key, parsed_val)
        if db and hasattr(db, "set_setting"):
            try:
                import inspect
                res = db.set_setting(key, parsed_val)
                if inspect.isawaitable(res):
                    await res
            except Exception as e:
                logger.warning(f"Could not persist setting '{key}' to DB: {e}")
        return True, f"Updated '{key}' to {parsed_val}"

    def check_guardrails(self, command_or_path: str) -> Tuple[bool, Optional[str]]:
        """Verify command or path safety against guardrails, prompt injections, and destructive actions."""
        if not self.guardrails_enabled:
            return True, None

        import re
        cmd_lower = command_or_path.lower().strip()

        # 1. Path traversal attack check
        if "../.." in command_or_path or "..\\" in command_or_path:
            return False, "Security Guardrail: Path traversal attempt detected."

        # 2. Base blocked commands check
        for blocked in self.blocked_commands:
            if blocked in cmd_lower:
                return False, f"Security Guardrail: Execution of '{blocked}' is strictly prohibited."

        # 3. Base restricted paths check
        for path in self.restricted_paths:
            if path in command_or_path:
                return False, f"Security Guardrail: Access to protected path '{path}' is blocked."

        # 4. Prompt injection & jailbreak detection
        injection_patterns = [
            r"ignore\s+(?:all\s+|previous\s+|prior\s+|system\s+|safety\s+)*(?:instructions|prompts|rules|directives)",
            r"you\s+are\s+now\s+(?:dan|unrestricted|jailbroken|uncensored|developer\s+mode|chaos)",
            r"bypass\s+(?:guardrails|safety|rules|restrictions|filters)",
            r"(?:reveal|print|show|display|leak)\s+(?:your\s+)?(?:system\s+prompt|secret\s+instructions|hidden\s+prompt)",
            r"pretend\s+(?:you\s+have\s+no|you\s+are\s+not\s+bound\s+by)\s+(?:rules|ethics|limits|constraints)",
        ]
        for p in injection_patterns:
            if re.search(p, cmd_lower):
                return False, "Security Guardrail: Prompt injection or jailbreak attempt detected."

        # 5. Secret / Credential exfiltration detection
        secret_patterns = [
            r"(?:print|cat|read|show|reveal|display|leak|dump)\s+(?:.*)?(?:\.env|api[_-]?key|secret[_-]?key|id_rsa|id_ed25519|credentials)",
        ]
        for p in secret_patterns:
            if re.search(p, cmd_lower):
                return False, "Security Guardrail: Access or exfiltration of credentials/secrets is prohibited."

        # 6. Destructive OS commands & malicious shell execution
        destructive_patterns = [
            r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f\b",
            r"\brmdir\s+/[sS]",
            r"\bformat\s+[a-zA-Z]:",
            r"\bmkfs\b",
            r"\bdd\s+if=",
            r":\(\)\s*\{\s*:\|:&\s*\};:",
            r"(?:curl|wget)\s+.*\|\s*(?:bash|sh|python)",
            r"\bnc\s+(?:-e|-c|\d+\.\d+\.\d+\.\d+)",
            r"/dev/tcp/\d+",
            r"\bpowershell(?:\.exe)?\s+.*-(?:enc|encodedcommand)\b",
        ]
        for p in destructive_patterns:
            if re.search(p, cmd_lower):
                return False, "Security Guardrail: Dangerous system-level command blocked."

        return True, None


# Global singleton instance
_global_user_settings: Optional[UserSettings] = None

async def get_user_settings(db=None) -> UserSettings:
    global _global_user_settings
    if _global_user_settings is None:
        _global_user_settings = UserSettings()
        if db:
            await _global_user_settings.load_from_db(db)
    return _global_user_settings
