"""
planner/router.py – Task Router
================================
Defines the task routing engine with skill mapping and LLM injection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from intelligence.task import Task
    from skills.manager import SkillManager
    from core.container import ServiceContainer
    from skills.system_skills import (
        ApplicationSkill, BrowserSkill, ClockSkill, MathSkill,
        WeatherSkill, ScreenshotSkill, VolumeSkill, DefaultSkill
    )
    from skills.System import FolderSkill, BrightnessSkill, MicSkill
    from skills.web_skill import WebSkill, WebLookupSkill
    from skills.research_skill import DeepResearchSkill
    from skills.media_skill import MediaSkill
    from skills.farewell_skill import FarewellSkill
    from skills.chat_skill import ChatSkill
    from skills.memory_skills import MemorySkill
    from skills.vision_skill import VisionSkill
    from skills.file_skill import FileSkill
    from skills.code_skill import CodeSkill
    from skills.screen_text_skill import ScreenTextSkill
    from skills.window_skill import WindowSkill
    from skills.clipboard_skill import ClipboardSkill
    from skills.notes_skill import NotesSkill
    from skills.reminder_skill import ReminderSkill
    from skills.browser_skill import BrowserControlSkill
    from skills.desktop_skill import DesktopSkill
    from skills.chrome_control_skill import ChromeControlSkill
    from skills.document_skill import DocumentSkill
    from skills.excel_skill import ExcelSkill
else:
    # Runtime imports to avoid circular dependency
    from skills.system_skills import (
        ApplicationSkill, BrowserSkill, ClockSkill, MathSkill,
        WeatherSkill, ScreenshotSkill, VolumeSkill, DefaultSkill
    )
    from skills.System import FolderSkill, BrightnessSkill, MicSkill
    from skills.web_skill import WebSkill, WebLookupSkill
    from skills.research_skill import DeepResearchSkill
    from skills.media_skill import MediaSkill
    from skills.farewell_skill import FarewellSkill
    from skills.chat_skill import ChatSkill
    from skills.memory_skills import MemorySkill
    from skills.vision_skill import VisionSkill
    from skills.file_skill import FileSkill
    from skills.code_skill import CodeSkill
    from skills.screen_text_skill import ScreenTextSkill
    from skills.window_skill import WindowSkill
    from skills.clipboard_skill import ClipboardSkill
    from skills.notes_skill import NotesSkill
    from skills.reminder_skill import ReminderSkill
    from skills.browser_skill import BrowserControlSkill
    from skills.desktop_skill import DesktopSkill
    from skills.chrome_control_skill import ChromeControlSkill
    from skills.document_skill import DocumentSkill
    from skills.excel_skill import ExcelSkill


class TaskRouter:
    """
    Routes tasks to skills.
    """

    ROUTING_TABLE = {
        "greeting": ChatSkill,
        # Another agent owns what Friday actually does on a goodbye; routing it
        # to the fallback keeps the intent detectable without claiming that
        # behaviour here.
        "farewell": FarewellSkill,
        "general_chat": ChatSkill,
        "weather": WeatherSkill,
        "news": DeepResearchSkill,
        "time": ClockSkill,
        "date": ClockSkill,
        "calculator": MathSkill,
        "open_application": ApplicationSkill,
        "close_application": ApplicationSkill,
        "system_control": VolumeSkill,
        # Both of these mean "go and find this out on the web", and what the
        # user wants back is the answer, not the search. Handing over a Chrome
        # tab left them to do the reading themselves, so these now run the
        # multi-round research loop and return a cited answer instead.
        # WebLookupSkill is still the right skill for "open a search for me"
        # and is kept for callers that ask for the tab explicitly.
        "search_web": DeepResearchSkill,
        "web_lookup": DeepResearchSkill,
        "play_music": MediaSkill,
        "media_control": MediaSkill,
        "open_website": BrowserSkill,
        "file_operation": FolderSkill,
        "brightness_control": BrightnessSkill,
        "mic_control": MicSkill,
        "screenshot": ScreenshotSkill,
        "clipboard": ClipboardSkill,
        "notes": NotesSkill,
        "reminder": ReminderSkill,
        "help": ChatSkill,
        "memory_recall": MemorySkill,
        "memory_forget": MemorySkill,
        # Looking at the screen. Nothing is captured unless an utterance
        # lands on one of these.
        #
        # Follow-ups ("what about the second one?") ride on screen_query
        # rather than an intent of their own: they route to the same skill,
        # carry the same "question" entity, and are marked by a follow_up
        # parameter the detector sets. A separate intent name would have to
        # be learned by the LLM, added to the prompt and the routing table,
        # and would still not tell VisionSkill the one thing it actually
        # needs — whether the remembered screen is fresh enough to reuse.
        "screen_query": VisionSkill,
        "screen_read": VisionSkill,
        # Files and apps by name. Folder-shaped requests stay with
        # FolderSkill, which already knows the known-folder shortcuts.
        "file_search": FileSkill,

        # ── Agent-only intents ────────────────────────────────────────────
        #
        # These are reachable through tool calls, not through the classifier:
        # they are deliberately absent from IntentDetector.VALID_INTENTS.
        #
        # The reason is the one this whole subsystem exists to fix. A 3B model
        # asked to pick one label out of thirty-odd already confuses
        # neighbouring intents; handing it "read_file" and "write_file" as
        # additional guesses would mean an utterance getting classified
        # straight into a filesystem write with entities it invented. A tool
        # call is different in kind — the model supplies typed arguments and
        # the destructive ones are confirmed with the user first.
        "screen_text": ScreenTextSkill,
        "active_window": WindowSkill,
        # Writing a document, as opposed to write_file's verbatim text: the
        # model supplies markdown and DocumentSkill renders it. Agent-only
        # for the usual reason -- it writes to disk, so it must arrive as a
        # tool call with typed arguments rather than a classifier guess.
        "create_document": DocumentSkill,
        # Spreadsheets through the real API, never keystrokes. Split in two so
        # only the writing half carries confirm=True: reading a range to answer
        # "what's the total in D" should not need permission, and a formula
        # that overwrites a column should.
        "excel_read": ExcelSkill,
        "excel_write": ExcelSkill,
        "read_file": CodeSkill,
        "write_file": CodeSkill,
        "list_directory": CodeSkill,
        "edit_file": CodeSkill,
        "copy_to_shadow": CodeSkill,
        "run_command": CodeSkill,

        # Driving a real browser and the desktop, as opposed to open_website,
        # which hands Chrome a URL and stops there.
        "browser_open": BrowserControlSkill,
        "browser_read": BrowserControlSkill,
        "browser_click": BrowserControlSkill,
        "browser_type": BrowserControlSkill,
        "browser_screenshot": BrowserControlSkill,
        "chrome_control": ChromeControlSkill,
        "focus_window": DesktopSkill,
        "press_keys": DesktopSkill,
    }

    def __init__(self, container: ServiceContainer | None = None, skill_manager: SkillManager | None = None) -> None:
        """
        Initialise TaskRouter.
        """
        self.container = container
        self.skill_manager = skill_manager

    async def route(self, tasks: list[Task]) -> list[Task]:
        """
        Populate routing information (skill_name and skill_class) for each task.
        Inject LLM and container into task metadata for skill access.
        """
        for task in tasks:
            skill_class = self.ROUTING_TABLE.get(task.intent, DefaultSkill)
            task.skill_name = skill_class.name
            task.metadata["skill_class"] = skill_class
            
            # Inject LLM for skills that need it (ChatSkill, WebSkill)
            if self.container and skill_class in (
                ChatSkill, WebSkill, WebLookupSkill, DeepResearchSkill
            ):
                task.metadata["llm"] = self.container.llm

            # Inject web skill instance for news/search/lookup/research
            if self.container and skill_class in (
                WebSkill, WebLookupSkill, DeepResearchSkill
            ):
                # Both lookup skills build their own WebSkill when the
                # container has no shared one, so a missing service is not
                # fatal here — it only costs a fresh HTTP connection pool.
                task.metadata["web_skill"] = getattr(self.container, "web_skill", None)
            
            # Inject chat skill instance for conversation continuity
            if self.container and skill_class is ChatSkill:
                task.metadata["chat_skill"] = self.container.chat_skill

        return tasks

    async def execute_task(self, task: Task) -> Any:
        """
        Do not execute tasks in Phase 2 router (moved to Executor).
        """
        pass