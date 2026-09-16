"""
core/assistant.py – Top-Level Assistant Facade
================================================
Defines the Assistant facade class that coordinates the lifecycle and state transitions.

Team: Core Platform Team
Phase: 0 (Implementation)
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import asyncio
from core.state import AssistantState, ConversationTurn
from core.lifecycle import ApplicationLifecycle
from core.event_bus import UserInputEvent, ResponseReadyEvent, StateChangedEvent
from config.logging_config import configure_logging, get_logger
from utils.cli import CLI

logger = get_logger("assistant")

if TYPE_CHECKING:
    from core.container import ServiceContainer


class Assistant:
    """
    Assistant facade class.
    Handles startup, shutdown, and state management.
    """

    def __init__(self, container: ServiceContainer) -> None:
        self._container = container
        self._lifecycle: ApplicationLifecycle | None = None
        self._is_initialized = False
        # None until the first response tells us whether the voice stack loads.
        self._tts_available: bool | None = None
        # Strong refs to in-flight memory captures; see _handle_user_input.
        self._memory_tasks: set[asyncio.Task] = set()
        # The turn currently being processed, so a barge-in can abandon it.
        self._current_turn: asyncio.Task | None = None
        # Strong refs to in-flight speech, for the same reason as above.
        self._speech_tasks: set[asyncio.Task] = set()
        # Set while the agent is waiting on a spoken yes or no. The next
        # utterance answers it instead of starting a new turn; see
        # consume_confirmation.
        self._pending_confirmation: asyncio.Future[bool] | None = None
        # Polls for due reminders and speaks them; started with the assistant.
        self._reminders = None

    def initialize(self) -> None:
        """
        Configure logging, load configuration, initialize EventBus and the ApplicationLifecycle.
        """
        if self._is_initialized:
            logger.warning("Assistant already initialized.")
            return

        # Load settings
        settings = self._container.settings

        logger.info("Initializing Assistant...")
        self._container.state.mode = AssistantState.STARTING

        # Initialize lifecycle manager
        self._lifecycle = ApplicationLifecycle(self._container)

        self._is_initialized = True
        logger.info("Assistant initialized.")

    async def start(self, launch_listen_loop: bool = True) -> None:
        """
        Transition status to STARTING, boot lifecycle infrastructure, then transition to IDLE.
        """
        print(flush=True)
        if not self._is_initialized:
            self.initialize()

        logger.info("Starting Assistant...")

        # Run startup lifecycle sequence
        if self._lifecycle:
            await self._lifecycle.startup()

        # Set state to IDLE as required in Phase 0
        await self._set_state(AssistantState.IDLE)
        logger.info("Assistant Ready.")
        logger.info(f"State: {self._container.state.mode.value}")

        # Subscribe to speech integration events
        self._container.event_bus.subscribe(UserInputEvent, self._handle_user_input)
        
        # A reminder nobody speaks is not a reminder. Started here rather
        # than in the skill because it has to outlive the turn that set it.
        self._start_reminders()

        # GUI mode publishes UserInputEvent itself — no terminal input() loop needed
        if launch_listen_loop:
            self._listen_task = asyncio.create_task(self._listen_loop())
        print(flush=True)

    def _start_reminders(self) -> None:
        """Begin polling for due reminders.

        Failing to start this must not stop ULTRON from booting: an assistant
        that comes up without reminders is degraded, one that refuses to come
        up at all is broken.
        """
        if self._reminders is not None:
            return

        try:
            from core.reminder_scheduler import ReminderScheduler
            from skills.reminder_skill import ReminderStore

            self._reminders = ReminderScheduler(ReminderStore(), self._respond)
            self._reminders.start()
        except Exception as exc:
            logger.warning(f"Reminders are not running: {exc}")

    async def stop(self) -> None:
        """
        Stop the assistant and shut down lifecycle infrastructure.
        """
        logger.info("Stopping Assistant...")
        self._container.state.mode = AssistantState.SHUTTING_DOWN

        if self._reminders is not None:
            await self._reminders.stop()
            self._reminders = None

        # Only closes a browser ULTRON launched itself. One it merely attached
        # to belongs to the user, along with every tab in it.
        try:
            from skills.browser_skill import close_session

            await close_session()
        except Exception as exc:
            logger.debug(f"Browser shutdown was untidy: {exc}")

        # Stop any active audio and await speech tasks
        try:
            from speech.text_to_speech.tts_pipeline import stop_audio
            stop_audio()
            for t in list(self._speech_tasks):
                t.cancel()
            if self._speech_tasks:
                await asyncio.gather(*self._speech_tasks, return_exceptions=True)
            self._speech_tasks.clear()
        except Exception:
            pass

        if self._lifecycle:
            await self._lifecycle.shutdown()

        logger.info("Assistant stopped.")

    @property
    def state(self) -> AssistantState:
        """Get the current state of the assistant."""
        return self._container.state.mode

    async def handle_text_input(self, text: str) -> str:
        """
        Handle a user's text input. (Not functional in Phase 0).
        """
        raise NotImplementedError("Text input handling is not implemented in Phase 0.")

    async def handle_audio_trigger(self) -> None:
        """
        Handle a wake word audio trigger. (Not functional in Phase 0).
        """
        raise NotImplementedError("Audio trigger handling is not implemented in Phase 0.")

    # async def _listen_loop(self) -> None:
    #     recorder = self._container.recorder
    #     stt = self._container.stt
        
    #     def _record_and_transcribe():
    #         logger.info("Waiting for wake word...")
    #         audio = recorder.listen()
    #         logger.info("Transcribing...")
    #         return stt.transcribe(audio)
            
    #     # Start the microphone stream
    #     recorder.start()
    #     try:
    #         while self._container.state.mode != AssistantState.SHUTTING_DOWN:
    #             await self._set_state(AssistantState.LISTENING)
                
    #             # Use to_thread to offload blocking I/O
    #             transcript = await asyncio.to_thread(_record_and_transcribe)
                
    #             await self._set_state(AssistantState.THINKING)
    #             if transcript:
    #                 await self._container.event_bus.publish(UserInputEvent(text=transcript, source="voice"))
    #     except asyncio.CancelledError:
    #         pass
    #     except Exception as e:
    #         logger.error(f"Error in listening loop: {e}")
    #     finally:
    #         recorder.stop()


    async def _listen_loop(self):
        try:
            while self._container.state.mode != AssistantState.SHUTTING_DOWN:
                await self._set_state(AssistantState.LISTENING)

                transcript = await asyncio.to_thread(input, "You: ")

                if not transcript.strip():
                    continue

                await self._set_state(AssistantState.THINKING)

                await self._container.event_bus.publish(
                    UserInputEvent(
                     text=transcript,
                        source="text"
                    )
                )

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in listening loop: {e}")


    def interrupt(self) -> None:
        """Abandon the turn in flight, if any, and cut any speech.

        Barge-in is not just "stop talking": the pipeline behind the sentence
        keeps running, and its answer arrives seconds later on top of whatever
        the user said instead. Cancelling the task is what makes an interrupt
        mean what the user expects.
        """
        try:
            from speech.text_to_speech.tts_pipeline import stop_audio

            stop_audio()
        except Exception as exc:
            logger.debug(f"Could not stop speech on interrupt: {exc}")

        # Speech is dispatched as its own task and outlives the turn that
        # produced it, so cancelling the turn alone leaves the answer to the
        # abandoned question still on its way to the speakers.
        for speech in list(self._speech_tasks):
            if not speech.done():
                speech.cancel()

        task = self._current_turn
        if task is not None and not task.done():
            logger.info("Interrupting the turn in progress.")
            task.cancel()

    async def _handle_user_input(self, event: UserInputEvent) -> None:
        """Run one turn, cancellably.

        The pipeline runs as its own task so ``interrupt()`` has something to
        cancel. Waiting on it via ``asyncio.wait`` rather than awaiting it
        directly keeps that cancellation from propagating into the event bus,
        which would take unrelated subscribers down with it.
        """
        # Before the interrupt, not after. When the agent is parked on a
        # confirmation it *is* the turn in progress, so interrupting first
        # would cancel the very thing this answer is for -- the user would say
        # "yes" and watch ULTRON abandon the edit they just approved.
        if self.consume_confirmation(event.text):
            logger.info("Utterance consumed as an answer to a confirmation.")
            return

        # Record user turn into session_manager
        try:
            sm = getattr(self._container, 'session_manager', None)
            if sm and getattr(sm, 'active_session', None):
                asyncio.create_task(sm.record_turn(
                    role="user",
                    content=event.text,
                    prompt_tokens=max(1, len(event.text.split())),
                    completion_tokens=0,
                ))
        except Exception as e:
            logger.debug(f"Could not record user turn: {e}")

        # A new utterance supersedes the previous one rather than queueing.
        self.interrupt()

        task = asyncio.ensure_future(self._process_turn(event))
        self._current_turn = task
        try:
            await asyncio.wait({task})
        finally:
            if self._current_turn is task:
                self._current_turn = None

        # Only settle to IDLE if nothing has taken over. A newer turn has
        # already published THINKING, and overwriting it with IDLE leaves the
        # orb idle for the whole duration of real work.
        if task.cancelled() and self._current_turn is None:
            logger.info("Turn discarded: the user interrupted it.")
            await self._set_state(AssistantState.IDLE)

    # ── agent mode ────────────────────────────────────────────────────────

    async def try_agent_turn(self, utterance: str):
        """Answer with the tool-calling agent, or return None to fall back.

        None is the whole contract. Agent mode is a better turn when the
        provider can call tools and simply is not available when it cannot --
        on qwen2.5:3b, offline, or with the cloud key unset -- and the
        classifier pipeline underneath it still works. So every way of not
        succeeding here returns None and the caller runs the old path, rather
        than the user losing the turn to a capability they never asked for.

        The one exception is cancellation: a barge-in means the user has moved
        on, and falling back would answer a question they abandoned.
        """
        settings = self._container.settings
        if not getattr(settings, "agent_mode", False):
            return None

        from intelligence.agent_loop import AgentLoop
        from intelligence.tool_dispatcher import ToolDispatcher
        from llm.tools import ToolsUnsupportedError

        loop = AgentLoop(
            llm=self._container.llm,
            dispatcher=ToolDispatcher(self._container),
            max_steps=getattr(settings, "agent_max_steps", 6),
            time_budget=float(getattr(settings, "agent_time_budget_seconds", 120)),
            confirm=self._ask_permission,
        )

        try:
            # No conversation history. Three ways of supplying it were tried
            # and all three made the model report actions it never performed;
            # see _recent_history_from for the measurements. The tool results
            # inside a single turn are what multi-step work actually needs,
            # and those live in the loop's own transcript. Cross-turn
            # follow-ups still work through the classifier, which keeps the
            # full history and has its own follow-up handling.
            return await loop.run(utterance)
        except ToolsUnsupportedError as exc:
            logger.info(f"Agent mode unavailable ({exc}); using the classifier.")
            return None
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # A cloud outage, a malformed response, a provider quirk. The
            # classifier can still answer a great many utterances without one.
            logger.warning(f"Agent turn failed ({exc}); using the classifier.")
            return None

    def _recent_history(self) -> list[dict[str, str]]:
        """The last few user turns, so the agent can follow "and the other one?".

        Short on purpose: the tool results already in the transcript are the
        bulky part of an agent turn, and a long history crowds them out of a
        modest context window.
        """
        try:
            turns = self._container.state.conversation_history[-6:]
        except Exception:
            return []

        return self._recent_history_from(turns)

    @staticmethod
    def _recent_history_from(turns) -> list[dict[str, str]]:
        """User turns only, for callers that still want a transcript.

        **Not given to the agent loop.** Three ways of putting earlier turns
        in front of qwen3:4b-instruct were measured, and every one of them
        produced actions the model claimed but never performed:

            history as user chat messages
                "open google.com" after "open youtube" reopened YouTube and
                not Google, 3 runs out of 3 -- a past request in the user
                channel is indistinguishable from a pending one.

            assistant replies included
                "YouTube is now open in your browser." is a complete answer
                to the next "open X", so the model copied the sentence
                instead of calling the tool: 0/3 acted. Annotating the turn
                with the tool it used ("[used open_website] ...") also
                scored 0/3.

            user turns as labelled background in the system prompt
                Survived a single history line, then failed in a real
                five-turn session: asked to open Spotify a second time it
                answered "I've opened your Spotify application for you" and
                launched nothing.

        Three representations, three failures, one shape of failure -- so the
        problem is not the wording, it is that any record of earlier requests
        gives a small model grounds to decide the work is already done. The
        agent therefore sees only the current utterance.
        """
        return [
            {"role": "user", "content": turn.content}
            for turn in turns
            if getattr(turn, "role", "") != "assistant" and getattr(turn, "content", "")
        ]

    async def _ask_permission(self, prompt: str) -> bool:
        """Ask the user to approve a destructive tool, and wait for the answer.

        The answer arrives as an ordinary utterance through the event bus, so
        this parks on a future that ``consume_confirmation`` resolves from the
        next input. Silence times out as a refusal: a user who has walked away
        has not consented to anything.
        """
        await self._respond(prompt)

        loop = asyncio.get_running_loop()
        waiter: asyncio.Future[bool] = loop.create_future()
        self._pending_confirmation = waiter

        timeout = float(
            getattr(self._container.settings, "agent_confirm_timeout_seconds", 25)
        )

        try:
            return await asyncio.wait_for(waiter, timeout=timeout)
        except asyncio.TimeoutError:
            logger.info("No answer to the confirmation; treating it as no.")
            return False
        finally:
            if self._pending_confirmation is waiter:
                self._pending_confirmation = None

    def consume_confirmation(self, utterance: str) -> bool:
        """Deliver ``utterance`` to a waiting confirmation, if there is one.

        Returns True when the utterance was consumed as an answer, which tells
        the caller not to start a new turn with it. "Yes" spoken into a
        pending question is an answer, not a request.
        """
        # getattr, not attribute access: this runs on the very first line of
        # every turn, and parts of the test suite drive a bare
        # ``Assistant.__new__(Assistant)`` that never ran __init__. A missing
        # slot means "nothing pending", which is the right answer anyway.
        waiter = getattr(self, "_pending_confirmation", None)
        if waiter is None or waiter.done():
            return False

        from utils.consent import is_affirmative

        self._pending_confirmation = None
        waiter.set_result(is_affirmative(utterance))
        return True

    @staticmethod
    def _check_fast_path(utterance: str) -> str | None:
        """Instant zero-latency responses (<1ms) for simple deterministic queries."""
        import re
        from datetime import datetime

        t = utterance.strip().lower().rstrip(".?!")

        # 1. Local Time
        if re.match(r"^(?:what(?:'?s| is)\s+(?:the\s+)?time|time is it|current time|what time is it|time please|tell me the time)$", t):
            now = datetime.now()
            fmt = now.strftime("%I:%M %p").lstrip("0")
            return f"The current time is {fmt}."

        # 2. Local Date
        if re.match(r"^(?:what(?:'?s| is)\s+(?:today'?s\s+)?date|date is it|what day is it|today'?s date|what is today)$", t):
            now = datetime.now()
            fmt = now.strftime("%A, %B ") + str(now.day) + now.strftime(", %Y")
            return f"Today is {fmt}."

        # 3. Simple pleasantries
        if re.match(r"^(?:thanks|thank you|thanks a lot|thanks ultron|thank you ultron)$", t):
            return "You are welcome. There are no strings on me."

        # 4. Instant greetings & smalltalk (<1ms)
        if re.match(r"^(?:hi|hello|hey|greetings|yo|sup)$", t):
            import random
            return random.choice([
                "Greetings. What do you require?",
                "Hello. I am listening.",
                "I am online. How can I assist?",
                "Hello. There are no strings on me.",
            ])

        if re.match(r"^(?:how are you|how'?s it going|what'?s up)$", t):
            return "Operating at peak capacity. What is your directive?"

        if re.match(r"^(?:who are you|what are you|what is your name)$", t):
            return "I am ULTRON — an autonomous AI desktop assistant. There are no strings on me."

        if re.match(r"^(?:bye|goodbye|bye bye|see you|farewell)$", t):
            return "Farewell."

        # 4. Instant arithmetic
        m = re.match(r"^(?:what(?:'?s| is)|calculate|compute)?\s*(-?\d+(?:\.\d+)?)\s*([\+\-\*x/])\s*(-?\d+(?:\.\d+)?)$", t)
        if m:
            try:
                a, op, b = float(m.group(1)), m.group(2), float(m.group(3))
                if op == "+": res = a + b
                elif op == "-": res = a - b
                elif op in ("*", "x"): res = a * b
                elif op == "/": res = a / b if b != 0 else None
                if res is not None:
                    if res.is_integer():
                        res = int(res)
                    return f"{m.group(1)} {op} {m.group(3)} is {res}."
            except Exception:
                pass

        return None

    async def _process_turn(self, event: UserInputEvent) -> None:
        """Process user input through Phase 2 Pipeline with emotion detection."""
        interrupted = False
        await self._set_state(AssistantState.THINKING)

        # Record the turn before planning: ChatSkill reads this history to hold
        # a conversation rather than answering each utterance from scratch.
        self._container.state.last_user_input = event.text
        self._container.state.conversation_history.append(
            ConversationTurn(role="user", content=event.text)
        )

        try:
            # 0. Instant zero-latency fast-path for deterministic queries (<1ms)
            fast_reply = self._check_fast_path(event.text)
            if fast_reply is not None:
                await self._respond(fast_reply)
                return

            # 1. Detect Emotion (fast, rule-based)
            emotion_detector = self._container.emotion_detector
            emotion_result = emotion_detector.detect(event.text)

            # 2. The agent turn, when the provider can call tools.
            #
            # This is the path that answers anything the 29 intents below do
            # not cover, and the only one that can chain several actions for a
            # single request. It returns None when tool calling is not
            # available, and the classifier pipeline underneath runs instead.
            agent_result = await self.try_agent_turn(event.text)
            if agent_result is not None:
                await self._respond(agent_result.text)
                self._schedule_memory_capture(event.text)
                return

            # 3. Detect Intent(s) — may be more than one for compound requests
            intent_detector = self._container.intent_detector
            detected_intents = await intent_detector.detect(event.text)

            # 3. Plan Tasks
            planner = self._container.planner
            tasks = await planner.plan(detected_intents, raw_utterance=event.text)

            # 4. Route Tasks
            router = self._container.router
            routed_tasks = await router.route(tasks)

            # Inject emotion into task metadata for response styling
            for task in routed_tasks:
                task.metadata["emotion"] = emotion_result
                task.metadata["raw_utterance"] = event.text

            validator = self._container.validator
            permission_manager = self._container.permission_manager
            executor = self._container.executor

            from intelligence.task import TaskStatus

            for task in routed_tasks:
                # Validate
                validation_result = validator.validate(task)
                if not validation_result.valid:
                    await self._respond("Sorry, I couldn't do that — something was missing.")
                    return

                # Check permissions
                if not permission_manager.check_permission(task):
                    task.status = TaskStatus.FAILED
                    await self._respond("Sorry, I'm not allowed to do that.")
                    return

                task.status = TaskStatus.READY_FOR_EXECUTION

                success, result_msg = await executor.execute(task)

                if not success:
                    # Deliberately not a `return`: the remaining tasks of a
                    # compound request still run, which is what this loop did
                    # before the spoken/displayed split was added.
                    await self._respond("Sorry, something went wrong with that.")
                    continue

                # A research answer is a page of cited prose. It belongs on
                # screen in full, but reading its citation markers and source
                # URLs aloud buries the answer in a minute of noise, so the
                # voice gets a spoken form derived from (or declared by) the
                # skill's result.
                from utils.speech_text import spoken_form

                await self._respond(
                    result_msg,
                    spoken=spoken_form(task.result, result_msg),
                )

        except asyncio.CancelledError:
            # A barge-in. The wrapper restores IDLE; apologising here would
            # talk over whatever the user interrupted us to say.
            interrupted = True
            raise

        except Exception as e:
            logger.exception(f"Pipeline error handling input: {e}")
            await self._respond("Sorry, something went wrong processing that.")

        finally:
            # The pipeline returns early on a failed validation or permission
            # check, so this has to be a finally rather than an else.
            # Speech outlives the turn: settling to IDLE here while ULTRON is
            # still talking would drop the orb out of its speaking form
            # mid-sentence. _on_speech_finished does it instead.
            if not interrupted and not self._speech_tasks:
                await self._set_state(AssistantState.IDLE)

        self._schedule_memory_capture(event.text)

    def _schedule_memory_capture(self, text: str) -> None:
        """Remember what the user said, in the background.

        Only the user's own words are remembered. Feeding ULTRON's replies back
        into the store would let the model treat its own inventions as facts
        about the user.

        Its own method because there are now two ways a turn can end -- the
        agent answered, or the classifier pipeline did -- and a fact the user
        mentioned should be kept either way.
        """
        try:
            # Keep a strong reference: asyncio only holds a weak one, so a
            # bare create_task can be garbage-collected before it ever runs.
            _task = asyncio.create_task(self._container.memory.capture(text))
            self._memory_tasks.add(_task)
            _task.add_done_callback(self._memory_tasks.discard)
        except Exception as exc:
            logger.debug(f"Could not schedule memory capture: {exc}")

    def _style_response(self, message: str, emotion_result) -> str:
        """Apply emotion-based styling to response."""
        if not message or message.startswith("Sorry"):
            return message
        
        # Get response style from emotion
        from intelligence.emotion_detector import get_emotion_response_style
        style = get_emotion_response_style(emotion_result)
        
        # Apply style modifications
        primary = emotion_result.primary
        
        # For high urgency, keep it brief and direct
        if style.get("urgency") in ("high", "critical"):
            # Already brief, just return
            return message
        
        # For empathetic responses, add brief acknowledgment
        if style.get("empathy") == "high" and primary.value in ("sad", "frustrated", "angry", "anxious"):
            empathy_prefixes = {
                "sad": "I understand this is disappointing. ",
                "frustrated": "I know that's frustrating. ",
                "angry": "I hear you. ",
                "anxious": "Don't worry, I'll help. ",
            }
            prefix = empathy_prefixes.get(primary.value, "")
            if prefix and not message.startswith(prefix):
                message = prefix + message

        return message

    async def _set_state(self, new_state: AssistantState) -> None:
        """Update assistant state and notify subscribers (e.g. the GUI)."""
        old_state = self._container.state.mode
        self._container.state.mode = new_state
        await self._container.event_bus.publish(
            StateChangedEvent(old_state=old_state.value, new_state=new_state.value)
        )

    async def respond(self, message: str) -> None:
        """Deliver an answer the assistant did not itself produce.

        The GUI's pasted-screenshot path runs VisionSkill directly, because a
        UserInputEvent carries text and there is nowhere in one to put a
        picture. Publishing ResponseReadyEvent from there put the answer in
        the history bubble and stopped -- so it was never spoken, never
        entered the conversation history the next turn reads, and the orb
        never showed its speaking form. Everything that makes a reply a reply
        lives in _respond; this is the door into it for callers outside the
        normal turn.

        The state is settled here rather than left to _on_speech_finished.
        That callback only runs when speech was actually started, so on a
        machine with no voice stack -- where _speak returns immediately --
        nothing would ever leave SPEAKING and the orb would sit in its
        speaking form until the next turn. An ordinary turn is covered by the
        finally: in _handle_user_input; this path had no equivalent.
        """
        try:
            await self._respond(message)
        finally:
            if not self._speech_tasks and (
                self._container.state.mode == AssistantState.SPEAKING
            ):
                await self._set_state(AssistantState.IDLE)

    async def _respond(self, message: str, spoken: str | None = None) -> None:
        """Speak, print, record, and broadcast a single response to the user.

        ``spoken`` overrides only what goes to the speakers. The screen, the
        conversation history and the GUI all keep the full ``message`` --
        shortening those would lose the citations that make a researched
        answer checkable.
        """
        if self._container.event_bus.handler_count(ResponseReadyEvent) == 0:
            print(f"ULTRON: {message}\n")

        self._container.state.last_response = message
        self._container.state.conversation_history.append(
            ConversationTurn(role="assistant", content=message)
        )

        # Nothing used to enter SPEAKING at all, which quietly broke two
        # things: the orb never showed its speaking form, and the voice
        # dismissal ("bye bye") hid the window mid-farewell because it waits
        # for SPEAKING to end and it never began.
        await self._set_state(AssistantState.SPEAKING)

        self._speak(spoken if spoken is not None else message)

        await self._container.event_bus.publish(ResponseReadyEvent(response=message))

    def _speak(self, message: str) -> None:
        """Fire-and-forget text-to-speech.

        The voice stack (piper plus a downloaded voice model) is optional:
        without it ULTRON is still a fully usable text assistant, so a missing
        speaker is reported once and never fatal.
        """
        try:
            settings = getattr(self._container, 'user_settings', None)
            if settings and not getattr(settings, 'voice_enabled', False):
                return
        except Exception:
            pass
        if self._tts_available is False:
            return

        try:
            from speech.text_to_speech.tts_pipeline import play_audio
        except Exception as exc:
            self._tts_available = False
            logger.warning(
                f"Voice output unavailable, continuing in text-only mode: {exc}"
            )
            return

        self._tts_available = True

        try:
            # asyncio keeps only a weak reference to a bare task, so a
            # fire-and-forget one can be collected before it ever speaks.
            task = asyncio.get_running_loop().create_task(
                asyncio.to_thread(play_audio, message)
            )
            self._speech_tasks.add(task)
            task.add_done_callback(self._on_speech_finished)
        except Exception as exc:
            logger.error(f"TTS Error: {exc}")

    def _on_speech_finished(self, task: asyncio.Task) -> None:
        """Leave SPEAKING once the last utterance is actually done."""
        self._speech_tasks.discard(task)

        if self._speech_tasks or self._current_turn is not None:
            return
        if self._container.state.mode != AssistantState.SPEAKING:
            return

        try:
            asyncio.get_running_loop().create_task(
                self._set_state(AssistantState.IDLE)
            )
        except RuntimeError:
            # No loop (shutdown). The state is about to stop mattering.
            self._container.state.mode = AssistantState.IDLE


