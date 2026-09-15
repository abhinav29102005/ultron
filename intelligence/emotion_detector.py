"""
intelligence/emotion_detector.py – Emotion Detection
=====================================================
Lightweight emotion/sentiment analysis for user input.
Uses a fast rule-based approach with optional LLM enhancement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llm.base import BaseLLM


class Emotion(Enum):
    """Primary emotion categories."""
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    FRUSTRATED = "frustrated"
    EXCITED = "excited"
    ANXIOUS = "anxious"
    CONFUSED = "confused"
    GRATEFUL = "grateful"
    APOLOGETIC = "apologetic"
    URGENT = "urgent"
    Sarcastic = "sarcastic"


@dataclass
class EmotionResult:
    """Result of emotion detection."""
    primary: Emotion
    confidence: float
    secondary: Emotion | None = None
    intensity: float = 0.5  # 0.0 to 1.0
    valence: float = 0.0    # -1.0 (negative) to 1.0 (positive)
    arousal: float = 0.5    # 0.0 (calm) to 1.0 (high energy)


# Fast rule-based emotion keywords for instant detection
EMOTION_KEYWORDS = {
    Emotion.HAPPY: {
        "keywords": ["happy", "glad", "great", "awesome", "wonderful", "amazing", "fantastic", "love", "excellent", "perfect", "joy", "delighted", "thrilled", "pleased", "satisfied"],
        "intensity": 0.7,
        "valence": 0.8,
        "arousal": 0.6,
    },
    Emotion.EXCITED: {
        "keywords": ["excited", "pumped", "thrilled", "ecstatic", "overjoyed", "can't wait", "looking forward", "hyped", "energetic"],
        "intensity": 0.8,
        "valence": 0.9,
        "arousal": 0.9,
    },
    Emotion.SAD: {
        "keywords": ["sad", "unhappy", "depressed", "down", "miserable", "heartbroken", "disappointed", "upset", "gloomy", "melancholy", "sorrow", "grief"],
        "intensity": 0.7,
        "valence": -0.7,
        "arousal": 0.3,
    },
    Emotion.ANGRY: {
        "keywords": ["angry", "furious", "mad", "livid", "outraged", "irate", "enraged", "hate", "annoyed", "irritated", "frustrated"],
        "intensity": 0.8,
        "valence": -0.8,
        "arousal": 0.8,
    },
    Emotion.FRUSTRATED: {
        "keywords": ["frustrated", "stuck", "annoying", "irritating", "doesn't work", "not working", "broken", "useless", "waste", "give up"],
        "intensity": 0.6,
        "valence": -0.6,
        "arousal": 0.6,
    },
    Emotion.ANXIOUS: {
        "keywords": ["worried", "anxious", "nervous", "stressed", "panic", "scared", "afraid", "fear", "concerned", "uneasy", "tense"],
        "intensity": 0.6,
        "valence": -0.5,
        "arousal": 0.7,
    },
    Emotion.CONFUSED: {
        "keywords": ["confused", "don't understand", "unclear", "what", "huh", "lost", "puzzled", "baffled", "perplexed", "make sense"],
        "intensity": 0.5,
        "valence": -0.2,
        "arousal": 0.4,
    },
    Emotion.GRATEFUL: {
        "keywords": ["thank you", "thanks", "grateful", "appreciate", "thankful", "much obliged"],
        "intensity": 0.6,
        "valence": 0.7,
        "arousal": 0.3,
    },
    Emotion.APOLOGETIC: {
        "keywords": ["sorry", "apologize", "my bad", "forgive", "mistake", "oops", "regret"],
        "intensity": 0.5,
        "valence": -0.1,
        "arousal": 0.3,
    },
    Emotion.URGENT: {
        "keywords": ["urgent", "asap", "immediately", "right now", "quick", "hurry", "emergency", "critical", "important"],
        "intensity": 0.8,
        "valence": 0.0,
        "arousal": 0.9,
    },
    Emotion.Sarcastic: {
        "keywords": ["yeah right", "sure", "whatever", "great job", "nice one", "obviously", "clearly", "totally", "absolutely not"],
        "intensity": 0.5,
        "valence": -0.3,
        "arousal": 0.4,
    },
}

# Punctuation/pattern boosters
URGENCY_PATTERNS = [
    r"!{2,}",           # Multiple exclamation marks
    r"\?{2,}",          # Multiple question marks
    r"(ASAP|NOW|URGENT)", # Explicit urgency words
    r"(PLEASE\s+){2,}",  # Multiple "please"
]

EMPHASIS_PATTERNS = [
    r"[A-Z]{3,}",       # ALL CAPS words
    r"[.]{3,}",         # Ellipsis
]


class EmotionDetector:
    """
    Fast emotion detection using rule-based approach with optional LLM refinement.
    """

    def __init__(
        self,
        llm: BaseLLM | None = None,
        use_llm_refinement: bool = False,
    ) -> None:
        self.llm = llm
        self.use_llm_refinement = use_llm_refinement and llm is not None

    def detect(self, text: str) -> EmotionResult:
        """
        Detect emotion from text. Returns immediately with rule-based result.
        """
        text_lower = text.lower()
        
        # Score each emotion
        scores: dict[Emotion, float] = {}
        matched_keywords: dict[Emotion, list[str]] = {}
        
        for emotion, data in EMOTION_KEYWORDS.items():
            score = 0
            matches = []
            for keyword in data["keywords"]:
                if keyword in text_lower:
                    score += 1
                    matches.append(keyword)
            if score > 0:
                scores[emotion] = score
                matched_keywords[emotion] = matches

        # Check urgency patterns
        urgency_boost = 0
        for pattern in URGENCY_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                urgency_boost += 0.5

        # Check emphasis patterns
        emphasis_boost = 0
        for pattern in EMPHASIS_PATTERNS:
            if re.search(pattern, text):
                emphasis_boost += 0.3

        # Apply boosts
        if Emotion.URGENT in scores:
            scores[Emotion.URGENT] += urgency_boost
        elif urgency_boost > 0:
            scores[Emotion.URGENT] = urgency_boost

        if Emotion.ANGRY in scores or Emotion.FRUSTRATED in scores:
            scores[Emotion.ANGRY] = scores.get(Emotion.ANGRY, 0) + emphasis_boost
            scores[Emotion.FRUSTRATED] = scores.get(Emotion.FRUSTRATED, 0) + emphasis_boost

        # Determine primary emotion
        if not scores:
            return EmotionResult(
                primary=Emotion.NEUTRAL,
                confidence=0.5,
                intensity=0.3,
                valence=0.0,
                arousal=0.3,
            )

        # Sort by score
        sorted_emotions = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        primary_emotion = sorted_emotions[0][0]
        primary_score = sorted_emotions[0][1]
        
        secondary_emotion = None
        if len(sorted_emotions) > 1:
            secondary_emotion = sorted_emotions[1][0]

        # Get base intensity/valence/arousal from primary emotion data
        base_data = EMOTION_KEYWORDS.get(primary_emotion, {})
        intensity = min(1.0, base_data.get("intensity", 0.5) + (primary_score * 0.1) + urgency_boost * 0.2 + emphasis_boost * 0.2)
        valence = base_data.get("valence", 0.0)
        arousal = min(1.0, base_data.get("arousal", 0.5) + urgency_boost * 0.3 + emphasis_boost * 0.2)

        # Confidence based on keyword match strength
        confidence = min(1.0, 0.4 + (primary_score * 0.15))

        return EmotionResult(
            primary=primary_emotion,
            confidence=confidence,
            secondary=secondary_emotion,
            intensity=intensity,
            valence=valence,
            arousal=arousal,
        )

    async def detect_with_llm(self, text: str) -> EmotionResult:
        """
        Enhanced detection using LLM for nuanced cases.
        Only used when rule-based confidence is low or explicitly requested.
        """
        if not self.use_llm_refinement or not self.llm:
            return self.detect(text)

        # Quick rule-based first
        quick_result = self.detect(text)
        if quick_result.confidence > 0.8:
            return quick_result

        try:
            messages = [
                self.llm.build_system_message("""
You are an emotion analyzer. Analyze the user's text and return ONLY valid JSON:

{
  "primary": "emotion_name",
  "confidence": 0.0-1.0,
  "secondary": "emotion_name_or_null",
  "intensity": 0.0-1.0,
  "valence": -1.0 to 1.0,
  "arousal": 0.0-1.0
}

Valid emotions: neutral, happy, sad, angry, frustrated, excited, anxious, confused, grateful, apologetic, urgent, sarcastic

Be concise. No explanations.
"""),
                self.llm.build_user_message(text),
            ]

            response = await self.llm.complete(messages)
            
            import json
            data = json.loads(response.content)
            
            return EmotionResult(
                primary=Emotion(data["primary"]),
                confidence=data["confidence"],
                secondary=Emotion(data["secondary"]) if data.get("secondary") else None,
                intensity=data["intensity"],
                valence=data["valence"],
                arousal=data["arousal"],
            )
        except Exception:
            return quick_result


def get_emotion_response_style(emotion: EmotionResult) -> dict[str, str]:
    """
    Get response style parameters based on detected emotion.
    Returns dict with tone, verbosity, empathy_level, urgency.
    """
    primary = emotion.primary
    intensity = emotion.intensity

    styles = {
        Emotion.HAPPY: {"tone": "warm", "verbosity": "normal", "empathy": "match", "urgency": "normal"},
        Emotion.EXCITED: {"tone": "enthusiastic", "verbosity": "normal", "empathy": "match", "urgency": "normal"},
        Emotion.SAD: {"tone": "gentle", "verbosity": "brief", "empathy": "high", "urgency": "normal"},
        Emotion.ANGRY: {"tone": "calm", "verbosity": "brief", "empathy": "high", "urgency": "high"},
        Emotion.FRUSTRATED: {"tone": "helpful", "verbosity": "normal", "empathy": "high", "urgency": "high"},
        Emotion.ANXIOUS: {"tone": "reassuring", "verbosity": "normal", "empathy": "high", "urgency": "high"},
        Emotion.CONFUSED: {"tone": "clear", "verbosity": "detailed", "empathy": "medium", "urgency": "normal"},
        Emotion.GRATEFUL: {"tone": "warm", "verbosity": "brief", "empathy": "match", "urgency": "normal"},
        Emotion.APOLOGETIC: {"tone": "understanding", "verbosity": "brief", "empathy": "medium", "urgency": "normal"},
        Emotion.URGENT: {"tone": "direct", "verbosity": "brief", "empathy": "low", "urgency": "critical"},
        Emotion.Sarcastic: {"tone": "literal", "verbosity": "normal", "empathy": "low", "urgency": "normal"},
        Emotion.NEUTRAL: {"tone": "professional", "verbosity": "normal", "empathy": "medium", "urgency": "normal"},
    }

    base = styles.get(primary, styles[Emotion.NEUTRAL]).copy()
    
    # Adjust for intensity
    if intensity > 0.8:
        base["verbosity"] = "brief"
        base["urgency"] = "high"
    elif intensity < 0.3:
        base["verbosity"] = "normal"

    return base