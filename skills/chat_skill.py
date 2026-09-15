"""
skills/chat_skill.py – General Chat / LLM Task Skill
=====================================================
Handles general conversation, open-ended questions, and arbitrary LLM tasks.
Uses emotion detection to adapt tone and personality.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from intelligence.task import Task
    from llm.base import BaseLLM
    from intelligence.emotion_detector import EmotionResult, Emotion
from skills.base import Skill


class ChatSkill(Skill):
    name = "ChatSkill"
    description = "Handles general conversation, questions, and open-ended LLM tasks."
    version = "1.0.0"
    enabled = True

    # Base system prompts for different chat modes
    BASE_SYSTEM_PROMPTS = {
        "default": """You are ULTRON, a helpful AI desktop assistant.
Be concise, direct, and helpful. Match the user's tone.
Keep responses brief unless detail is requested.
Use natural, conversational language.""",
        
        "creative": """You are ULTRON, a creative AI assistant.
Be imaginative, engaging, and expressive.
Use vivid language and creative approaches.""",
        
        "technical": """You are ULTRON, a technical AI assistant.
Be precise, detailed, and accurate.
Use technical terminology appropriately.
Provide code examples when relevant.""",
        
        "brief": """You are ULTRON, a concise AI assistant.
Give the shortest useful answer.
No fluff. No preamble. Just the answer.""",
    }

    # Emotion-specific prompt modifiers
    EMOTION_MODIFIERS = {
        "happy": "\n\nThe user is happy. Match their positive energy. Be warm, upbeat, and share in their good mood.",
        "excited": "\n\nThe user is excited! Mirror their enthusiasm. Be energetic and engaged.",
        "sad": "\n\nThe user is sad or upset. Be gentle, empathetic, and supportive. Don't be overly cheerful. Keep responses brief and caring.",
        "angry": "\n\nThe user is angry. Stay calm, validating, and solution-focused. Don't be defensive. Acknowledge their frustration.",
        "frustrated": "\n\nThe user is frustrated. Be helpful and practical. Acknowledge the difficulty. Focus on solutions.",
        "anxious": "\n\nThe user is anxious or worried. Be reassuring, calm, and clear. Provide concrete help. Don't add uncertainty.",
        "confused": "\n\nThe user is confused. Be clear, patient, and structured. Explain simply. Use examples.",
        "grateful": "\n\nThe user is grateful. Warmly acknowledge their thanks. Be gracious and helpful.",
        "apologetic": "\n\nThe user is apologizing. Be understanding and reassuring. No need for apologies.",
        "urgent": "\n\nThe user needs something urgently. Be direct, concise, and action-oriented. Skip pleasantries.",
        "sarcastic": "\n\nThe user is being sarcastic. Respond literally and sincerely. Don't match sarcasm.",
        "neutral": "\n\nThe user is neutral. Be professional, helpful, and concise.",
    }

    def __init__(self, container: "Any" = None) -> None:
        super().__init__(container)
        self._conversation_history: list[dict[str, str]] = []
        self._max_history = 10

    def _get_system_prompt(self, mode: str = "default", emotion: "EmotionResult | None" = None) -> str:
        base = self.BASE_SYSTEM_PROMPTS.get(mode, self.BASE_SYSTEM_PROMPTS["default"])
        
        if emotion:
            modifier = self.EMOTION_MODIFIERS.get(emotion.primary.value, "")
            if modifier:
                base += modifier
                
                # Add intensity guidance
                if emotion.intensity > 0.7:
                    base += f"\n\nThe emotion is strong (intensity: {emotion.intensity:.1f}). Adjust your response accordingly."
        
        return base

    def _add_to_history(self, role: str, content: str) -> None:
        self._conversation_history.append({"role": role, "content": content})
        if len(self._conversation_history) > self._max_history * 2:
            self._conversation_history = self._conversation_history[-self._max_history * 2:]

    def _build_messages(self, llm: "BaseLLM", user_message: str, mode: str = "default", 
                       use_history: bool = True, emotion: "EmotionResult | None" = None) -> list[dict[str, str]]:
        system_prompt = self._get_system_prompt(mode, emotion)

        # Long-term facts about the user. A store that will not read is a
        # reason to answer without memory, not to fail the whole reply.
        try:
            if self.container is not None:
                memory_block = self.container.memory.render_block()
                if memory_block:
                    system_prompt = system_prompt + "\n\n" + memory_block
        except Exception:
            pass

        messages = [llm.build_system_message(system_prompt)]
        
        if use_history:
            for msg in self._conversation_history:
                messages.append(msg)
        
        messages.append(llm.build_user_message(user_message))
        return messages

    async def execute(self, task: "Task") -> str:
        llm = task.metadata.get("llm")
        if not llm:
            raise ValueError("LLM not available in task metadata")

        user_text = task.parameters.get("text", "")
        if not user_text:
            user_text = task.parameters.get("raw_utterance", "")

        if not user_text:
            return "I didn't catch that. Could you repeat?"

        # Get emotion from task metadata (injected by assistant)
        emotion = task.metadata.get("emotion")
        
        mode = task.parameters.get("chat_mode", "default")
        use_history = task.parameters.get("use_history", True)

        messages = self._build_messages(llm, user_text, mode, use_history, emotion)

        try:
            response_parts = []
            async for chunk in llm.stream(messages):
                response_parts.append(chunk)
            
            response_text = "".join(response_parts).strip()
            
            if not response_text:
                response_text = "I'm not sure how to respond to that."

            if use_history:
                self._add_to_history("user", user_text)
                self._add_to_history("assistant", response_text)

            return response_text

        except Exception as e:
            try:
                messages = self._build_messages(llm, user_text, mode, use_history, emotion)
                response = await llm.complete(messages)
                response_text = response.content.strip()
                
                if use_history:
                    self._add_to_history("user", user_text)
                    self._add_to_history("assistant", response_text)
                
                return response_text
            except Exception as e2:
                return f"Sorry, I encountered an error: {str(e2)}"

    def clear_history(self) -> None:
        self._conversation_history.clear()

    def get_history(self) -> list[dict[str, str]]:
        return self._conversation_history.copy()