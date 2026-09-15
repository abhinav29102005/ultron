"""
intelligence/tool_registry.py – The tools the agent may call
=============================================================
Every capability ULTRON has, described in the words the model reads when it
decides what to do.

These descriptions are load-bearing. The failure this whole subsystem exists
to fix -- "fix the bug in my code" turning into a Google search for "error" --
was a *description* problem as much as an architecture one: nothing ever told
the model that a question about the user's own screen or files is answered by
looking at them, not by searching the web. So the boundaries are stated
explicitly here, in each tool's description, rather than left to inference.

Each tool names an ``intent`` from :class:`~intelligence.router.TaskRouter`'s
routing table. Executing a tool builds an ordinary Task with that intent and
runs it through the existing router and executor, so every skill ULTRON
already has keeps working untouched.
"""

from __future__ import annotations

from llm.tools import ToolDef

#: A short string argument, reused constantly.
def _str(description: str) -> dict[str, str]:
    return {"type": "string", "description": description}


ALL_TOOLS: tuple[ToolDef, ...] = (
    # ── Looking at the machine ────────────────────────────────────────────
    ToolDef(
        name="describe_screen",
        description=(
            "Look at the user's screen and answer a question about what is on "
            "it. Use this whenever the user says 'this', 'that', or 'here' "
            "about something visible -- 'what does this mean', 'what am I "
            "looking at'. This is how you see; you cannot answer questions "
            "about the user's screen any other way."
        ),
        intent="screen_query",
        properties={"question": _str("What to find out about the screen.")},
        required=("question",),
    ),
    ToolDef(
        name="read_screen_text",
        description=(
            "Read the exact text on the user's screen using OCR. Use this "
            "instead of describe_screen whenever precision matters: error "
            "messages, stack traces, code, log output, file paths, version "
            "numbers. describe_screen paraphrases what it sees; this returns "
            "the characters verbatim, which is what you need before quoting "
            "an error or editing code."
        ),
        intent="screen_text",
        properties={},
    ),
    ToolDef(
        name="get_active_window",
        description=(
            "Return the title of the window the user is currently working in, "
            "and the program running it. Cheap. Call this first when the user "
            "refers to what they are doing ('fix this', 'what's wrong here') "
            "so you know whether they are in an editor, a browser, or a "
            "terminal before you decide how to look."
        ),
        intent="active_window",
        properties={},
    ),
    ToolDef(
        name="take_screenshot",
        description="Save a screenshot of the screen to the user's Pictures folder.",
        intent="screenshot",
        properties={},
    ),
    # ── Files and code ────────────────────────────────────────────────────
    ToolDef(
        name="read_file",
        description=(
            "Read a text or source file from disk and return its contents with "
            "line numbers. Use this to inspect the user's actual code before "
            "answering questions about it or changing it. Never guess at file "
            "contents you have not read."
        ),
        intent="read_file",
        properties={
            "path": _str("Absolute path, or a path relative to the project folder."),
        },
        required=("path",),
    ),
    ToolDef(
        name="write_file",
        description=(
            "Overwrite a file with new contents. Use this to apply a fix after "
            "you have read the file and worked out the change. Always read the "
            "file first -- this replaces it wholesale. The user is asked to "
            "confirm before anything is written."
        ),
        intent="write_file",
        properties={
            "path": _str("The file to write."),
            "content": _str("The complete new contents of the file."),
        },
        required=("path", "content"),
        confirm=True,
    ),
    ToolDef(
        name="create_document",
        description=(
            "Write a document and save it in the user's Documents folder: a "
            "study plan, a report, notes, a summary. You write the whole "
            "document yourself as markdown and pass it here; this tool only "
            "renders and saves it, so put the real content in content_md "
            "rather than a description of it. Choose the format from what the "
            "user asked for -- pdf, html, or md. For source code or a plain "
            "text file at a path the user named, use write_file instead."
        ),
        intent="create_document",
        properties={
            "filename": _str(
                "Name for the file, no folders. For example dsa-week1.pdf"
            ),
            "content_md": _str(
                "The complete document, written in markdown. Headings, lists "
                "and tables are kept."
            ),
            "format": _str("One of: md, html, pdf. Defaults to md."),
        },
        required=("filename", "content_md"),
        confirm=True,
    ),
    ToolDef(
        name="excel_read",
        description=(
            "Look inside an Excel workbook: list its sheets, describe a "
            "sheet's layout (headers, size, first few rows), or read the "
            "values in a range. Call this BEFORE excel_write, always -- it is "
            "how you learn which column is which instead of guessing letters. "
            "Leave path out to use the workbook the user currently has open "
            "in Excel."
        ),
        intent="excel_read",
        properties={
            "op": _str("One of: sheets, shape, read_range."),
            "path": _str(
                "The .xlsx file. Leave out to use the workbook open in Excel."
            ),
            "sheet": _str("Which sheet, for shape and read_range."),
            "range": _str("An A1-style range for read_range, such as A1:D20."),
        },
        required=("op",),
    ),
    ToolDef(
        name="excel_write",
        description=(
            "Change an Excel workbook: write values into a range, apply a "
            "formula across a range, add a sheet, or bold a header row. Only "
            "after excel_read has shown you the sheet's real layout. The "
            "workbook is copied to a backup before the first change, and any "
            "cell that ends up showing an Excel error is reported back to "
            "you. The user is asked to confirm before anything is written."
        ),
        intent="excel_write",
        properties={
            "op": _str("One of: set_values, set_formula, add_sheet, format_bold."),
            "path": _str(
                "The .xlsx file. Leave out to use the workbook open in Excel."
            ),
            "sheet": _str("Which sheet to change."),
            "range": _str("The A1-style range to write, such as C2:C50."),
            "values": _str(
                "For set_values: a JSON 2-D array of rows, e.g. [[1,2],[3,4]]."
            ),
            "formula": _str(
                "For set_formula: the formula as written for the range's first "
                "cell, e.g. =B2*0.18. References shift down the range."
            ),
            "name": _str("For add_sheet: the new sheet's name."),
        },
        required=("op",),
        confirm=True,
    ),
    ToolDef(
        name="edit_file",
        description=(
            "Change one exact fragment of a file, leaving everything else "
            "alone. This is how you fix code. Give the text to replace exactly "
            "as read_file showed it, including indentation, and enough of the "
            "surrounding line to be unique in the file. Prefer this over "
            "write_file for every change to an existing file."
        ),
        intent="edit_file",
        properties={
            "path": _str("The file to change."),
            "old_text": _str("The exact text to replace, copied from the file."),
            "new_text": _str("What to put in its place."),
        },
        required=("path", "old_text", "new_text"),
        confirm=True,
    ),
    ToolDef(
        name="copy_to_shadow",
        description=(
            "Make a working copy of a file and return the copy's path. Use "
            "this before trying a fix: edit and run the copy until it works, "
            "then apply the same edit to the real file. The user's own file is "
            "not touched while you experiment."
        ),
        intent="copy_to_shadow",
        properties={"path": _str("The file to copy.")},
        required=("path",),
    ),
    ToolDef(
        name="run_command",
        description=(
            "Run a program and return what it printed, including errors. Use "
            "this to check whether a fix actually works: run the file, read "
            "the output, and edit again if it is still wrong. A non-zero exit "
            "code is normal information, not a failure. Only python, py, "
            "pytest, node, npm and code can be run."
        ),
        intent="run_command",
        properties={
            "command": _str("The command, e.g. 'python C:/path/to/file.py'."),
            "cwd": _str("Optional folder to run it in."),
        },
        required=("command",),
    ),
    ToolDef(
        name="list_directory",
        description=(
            "List the files and folders at a path. Use this to find your way "
            "around a project before reading files."
        ),
        intent="list_directory",
        properties={"path": _str("The folder to list. Defaults to the project folder.")},
    ),
    ToolDef(
        name="find_file",
        description=(
            "Search the user's machine for a file or application by name when "
            "you do not know where it lives."
        ),
        intent="file_search",
        properties={"query": _str("Part of the file or application name.")},
        required=("query",),
        # FileSkill reads "target"; the tool says "query" because that is the
        # word a model reaches for. Both are sent.
        aliases={"query": "target"},
    ),
    ToolDef(
        name="open_folder",
        description="Open a folder in Windows Explorer (Documents, Downloads, Desktop, or a path).",
        intent="file_operation",
        properties={"path": _str("The folder name or path to open.")},
        required=("path",),
        aliases={"path": "folder_name"},
    ),
    # ── Running things ────────────────────────────────────────────────────
    ToolDef(
        name="open_application",
        description=(
            "Launch an installed program by name -- Chrome, VS Code, Spotify, "
            "Notepad. For a website, use open_website instead."
        ),
        intent="open_application",
        properties={"application": _str("The program name, e.g. 'chrome', 'vs code'.")},
        required=("application",),
    ),
    ToolDef(
        name="close_application",
        description="Force-close a running program by name.",
        intent="close_application",
        properties={"application": _str("The program to close.")},
        required=("application",),
        confirm=True,
    ),
    ToolDef(
        name="open_website",
        description=(
            "Open a website in the browser, optionally searching within it. "
            "Use this when the user wants to *be taken to* a site. When they "
            "want an answer instead, use research."
        ),
        intent="open_website",
        properties={
            "website": _str("The site, e.g. 'youtube', 'github', 'gmail'."),
            "query": _str("Optional: what to search for on that site."),
        },
        required=("website",),
    ),
    # ── Finding things out ────────────────────────────────────────────────
    ToolDef(
        name="research",
        description=(
            "Research a question on the web and return a cited answer. This "
            "reads the actual pages, not just search results, so it takes "
            "20-45 seconds -- use it when the user wants to KNOW something "
            "current or external: news, prices, scores, facts about the world, "
            "documentation.\n\n"
            "Do NOT use this for anything about the user's own machine, "
            "screen, files, or code. A bug in their code is not researched, it "
            "is read with read_screen_text or read_file and then fixed."
        ),
        intent="search_web",
        properties={"query": _str("The question to research.")},
        required=("query",),
    ),
    ToolDef(
        name="get_weather",
        description="Current weather and forecast for a place.",
        intent="weather",
        properties={"location": _str("City name. Defaults to the user's location.")},
    ),
    ToolDef(
        name="end_session",
        description=(
            "Say goodbye and shut ULTRON down. Use this whenever the user "
            "dismisses you -- 'bye', 'bye bye', 'goodbye', 'good night', "
            "'see you later', 'that's all', 'you can go now'. Do not simply "
            "reply with a farewell of your own: saying goodbye without "
            "calling this leaves ULTRON running, which is not what the user "
            "asked for. This tool speaks the goodbye itself."
        ),
        intent="farewell",
        properties={},
    ),
    ToolDef(
        name="get_time",
        description="The current time.",
        intent="time",
        properties={},
    ),
    ToolDef(
        name="get_date",
        description="Today's date.",
        intent="date",
        properties={},
    ),
    ToolDef(
        name="calculate",
        description="Evaluate a arithmetic or symbolic maths expression exactly.",
        intent="calculator",
        properties={"expression": _str("The expression, e.g. '15% of 240'.")},
        required=("expression",),
    ),
    # ── The machine's knobs ───────────────────────────────────────────────
    ToolDef(
        name="set_volume",
        description="Change the system volume: up, down, mute, unmute, max, min, or an exact level.",
        intent="system_control",
        properties={
            "action": {
                "type": "string",
                "enum": ["up", "down", "mute", "unmute", "max", "min", "set"],
                "description": "What to do to the volume.",
            },
            "level": {"type": "integer", "description": "0-100, only when action is 'set'."},
        },
        required=("action",),
    ),
    ToolDef(
        name="set_brightness",
        description="Change screen brightness: up, down, or an exact level.",
        intent="brightness_control",
        properties={
            "action": {
                "type": "string",
                "enum": ["up", "down", "set"],
                "description": "What to do to the brightness.",
            },
            "level": {"type": "integer", "description": "0-100, only when action is 'set'."},
        },
        required=("action",),
    ),
    ToolDef(
        name="set_microphone",
        description="Mute, unmute, or toggle the microphone.",
        intent="mic_control",
        properties={
            "action": {"type": "string", "enum": ["mute", "unmute", "toggle"]},
        },
        required=("action",),
    ),
    # ── Media ─────────────────────────────────────────────────────────────
    ToolDef(
        name="play_music",
        description="Play a song, artist, album, or playlist in Spotify.",
        intent="play_music",
        properties={"query": _str("What to play.")},
        required=("query",),
    ),
    ToolDef(
        name="control_media",
        description="Control whatever is playing: pause, resume, next, previous.",
        intent="media_control",
        properties={
            "action": {"type": "string", "enum": ["pause", "resume", "next", "previous"]},
        },
        required=("action",),
    ),
    # ── Clipboard and memory ──────────────────────────────────────────────
    ToolDef(
        name="clipboard",
        description=(
            "Read what the user has copied, or copy something for them. "
            "Reading the clipboard is often the quickest way to get an error "
            "message or a code snippet the user has already copied."
        ),
        intent="clipboard",
        properties={
            "action": {"type": "string", "enum": ["read", "write"]},
            "text": _str("The text to copy, when action is 'write'."),
        },
        required=("action",),
    ),
    # ── Notes and reminders ───────────────────────────────────────────────
    ToolDef(
        name="add_note",
        description=(
            "Save a short note for the user to look at later. Use this when "
            "they say 'make a note', 'jot this down', or 'remember that I need "
            "to...'. For something that should interrupt them at a particular "
            "time, use set_reminder instead."
        ),
        intent="notes",
        properties={"text": _str("The note to save.")},
        required=("text",),
        aliases={"text": "note"},
        fixed={"action": "add"},
    ),
    ToolDef(
        name="list_notes",
        description="Read back the user's saved notes.",
        intent="notes",
        properties={"query": _str("Optional: only notes containing this text.")},
        fixed={"action": "list"},
    ),
    ToolDef(
        name="set_reminder",
        description=(
            "Set a reminder that will be spoken at a given time. The time can "
            "be relative ('in ten minutes') or a clock time ('at 5pm', "
            "'tomorrow at 9'). Pass the user's whole sentence as `text` -- the "
            "time is parsed out of it. If they gave no time at all, ask them "
            "for one rather than choosing."
        ),
        intent="reminder",
        properties={
            "text": _str("What to be reminded about, including when."),
            "when": _str("Optional: just the time, if it was given separately."),
        },
        required=("text",),
        fixed={"action": "add"},
    ),
    ToolDef(
        name="list_reminders",
        description="Read back the reminders that have not fired yet.",
        intent="reminder",
        properties={},
        fixed={"action": "list"},
    ),
    ToolDef(
        name="cancel_reminder",
        description="Cancel a pending reminder.",
        intent="reminder",
        properties={"query": _str("Words from the reminder to cancel.")},
        required=("query",),
        fixed={"action": "cancel"},
    ),
    # ── Browser control ───────────────────────────────────────────────────
    #
    # Distinct from open_website, which just hands Chrome a URL and stops
    # there. These drive the page afterwards.
    ToolDef(
        name="browser_open",
        description=(
            "Open a URL in the controllable browser, and report the page title. "
            "Use this to START a browser task you will then click or type in. "
            "For simply putting a site in front of the user, open_website is "
            "lighter."
        ),
        intent="browser_open",
        properties={"url": _str("The URL or domain to open.")},
        required=("url",),
    ),
    ToolDef(
        name="browser_read",
        description=(
            "Read the visible text of the current browser page. Do this before "
            "clicking something you have not seen, so you know what is there."
        ),
        intent="browser_read",
        properties={},
    ),
    ToolDef(
        name="browser_click",
        description=(
            "Click something on the current page, named the way a person would "
            "say it -- a button's label, a link's text, 'Sign in'. The user is "
            "asked to confirm first."
        ),
        intent="browser_click",
        properties={"target": _str("The visible text or label of what to click.")},
        required=("target",),
        confirm=True,
    ),
    ToolDef(
        name="browser_type",
        description=(
            "Type into a field on the current page. Name the field by its "
            "label or placeholder; omit it to type wherever the cursor is. Set "
            "submit to true to press Enter afterwards. Confirmed with the user."
        ),
        intent="browser_type",
        properties={
            "text": _str("The text to type."),
            "target": _str("Optional: the field's label or placeholder."),
            "submit": {"type": "boolean", "description": "Press Enter afterwards."},
        },
        required=("text",),
        confirm=True,
    ),
    ToolDef(
        name="control_my_chrome",
        description=(
            "Take control of the user's own Chrome, with their logins and "
            "tabs. Use this when they ask you to do something in *their* "
            "browser and browser_open reports it is using a separate one. "
            "Chrome has to be restarted for this, so the user is asked first; "
            "their tabs are restored afterwards."
        ),
        intent="chrome_control",
        properties={},
        confirm=True,
    ),
    ToolDef(
        name="browser_screenshot",
        description=(
            "Save a picture of the current browser page. Use this when the "
            "question is about how the page looks rather than what it says; "
            "browser_read is cheaper for text."
        ),
        intent="browser_screenshot",
        properties={},
    ),
    # ── Desktop control ───────────────────────────────────────────────────
    ToolDef(
        name="focus_window",
        description=(
            "Bring a window to the front by part of its title. Keystrokes go "
            "to whatever has focus, so do this before press_keys to choose "
            "which application you are typing into."
        ),
        intent="focus_window",
        properties={"title": _str("Part of the window title, e.g. 'Visual Studio Code'.")},
        required=("title",),
    ),
    ToolDef(
        name="press_keys",
        description=(
            "Send a keyboard shortcut to the focused window ('ctrl+s', "
            "'alt+tab'), or type literal text into it. Applications are built "
            "to be driven by shortcuts, so this is usually more reliable than "
            "clicking. Focus the right window first. Confirmed with the user."
        ),
        intent="press_keys",
        properties={
            "keys": _str("A shortcut such as 'ctrl+s' or 'alt+tab'."),
            "text": _str("Literal text to type instead of a shortcut."),
        },
        confirm=True,
    ),
    ToolDef(
        name="recall_memory",
        description="Look up something ULTRON was told to remember about the user.",
        intent="memory_recall",
        properties={"query": _str("What to recall.")},
        required=("query",),
        aliases={"query": "target"},
    ),
)

#: Name → definition, for dispatch and confirmation lookups.
TOOLS_BY_NAME: dict[str, ToolDef] = {tool.name: tool for tool in ALL_TOOLS}


def schemas() -> list[dict]:
    """Every tool in the wire format both providers accept."""
    return [tool.to_schema() for tool in ALL_TOOLS]
