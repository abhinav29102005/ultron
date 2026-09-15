"""
Tests for skills/excel_skill.py – reading and editing Excel workbooks.

Everything openpyxl does is exercised for real, headless, against workbooks
built in tmp_path: no Excel, no COM, no fixtures checked into the repo. The
backup root is redirected into tmp_path too, so a test run never writes to the
project's data/ folder.

The xlwings half needs a live Excel. It is skipped rather than failed when
there isn't one, because the machines that run this suite mostly don't have
one -- but the skip is narrow, so the test still runs where Excel exists.

What is actually being defended here:

  * the shape op stays small. It exists so a model can look before it writes,
    and a 10,000-row answer would defeat the entire point;
  * a write is backed up once per workbook, and the backups rotate;
  * the error scan finds a #DIV/0! rather than reporting a clean save;
  * an unknown op is refused with one fixed sentence;
  * a write never silently converts the workbook's formulas to values.
"""

from __future__ import annotations

import faulthandler
from datetime import datetime

import pytest
from openpyxl import Workbook, load_workbook

from intelligence.task import Task, TaskStatus
from skills.excel_skill import MAX_BACKUPS, REFUSAL, SHAPE_ROWS, ExcelSkill


def _task(intent: str, **params) -> Task:
    return Task(
        task_id="t1",
        skill_name="ExcelSkill",
        intent=intent,
        parameters=params,
        status=TaskStatus.PENDING,
        result=None,
        error=None,
        created_at=datetime.now(),
        completed_at=None,
        dependencies=[],
        metadata={},
    )



def _workbook(path):
    """A minimal workbook at an arbitrary path, for the pruning tests."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Budget"
    sheet.append(["Item", "Qty"])
    sheet.append(["a", 1])
    workbook.save(path)
    workbook.close()
    return path


@pytest.fixture
def book(tmp_path):
    """A small, realistic workbook: header row, twelve data rows, a formula."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Budget"
    sheet.append(["Item", "Qty", "Price", "Total"])
    for index in range(1, 13):
        sheet.append([f"Item {index}", index, 2.5, f"=B{index + 1}*C{index + 1}"])
    workbook.create_sheet("Summary")
    path = tmp_path / "budget.xlsx"
    workbook.save(path)
    workbook.close()
    return path


@pytest.fixture
def skill(tmp_path):
    return ExcelSkill(backup_root=tmp_path / "backups")


def _backups(tmp_path):
    root = tmp_path / "backups"
    return sorted(root.glob("*.xlsx")) if root.exists() else []


class TestReadOps:
    @pytest.mark.asyncio
    async def test_sheets_lists_every_sheet(self, skill, book):
        out = await skill.execute(_task("excel_read", op="sheets", path=str(book)))

        assert "Budget" in out
        assert "Summary" in out
        assert "2 sheets" in out

    @pytest.mark.asyncio
    async def test_shape_stops_at_five_data_rows(self, skill, book):
        """The DOM-filtering principle for spreadsheets: enough to write
        against, never the sheet itself."""
        out = await skill.execute(
            _task("excel_read", op="shape", path=str(book), sheet="Budget")
        )

        assert "Item 1" in out
        assert f"Item {SHAPE_ROWS}" in out
        # Row 7 onwards must not be in the answer at all.
        assert "Item 6" not in out
        assert "Item 12" not in out
        assert f"First {SHAPE_ROWS} of 12 data rows" in out

    @pytest.mark.asyncio
    async def test_shape_reports_headers_dimensions_and_column_types(self, skill, book):
        out = await skill.execute(
            _task("excel_read", op="shape", path=str(book), sheet="Budget")
        )

        assert "The header row is: Item, Qty, Price, Total" in out
        assert "4 columns by 13 rows" in out
        assert "Item holds text" in out
        assert "Qty holds numbers" in out
        assert "Total holds formulas" in out

    @pytest.mark.asyncio
    async def test_shape_of_a_big_sheet_stays_speakable(self, tmp_path, skill):
        """A ten-thousand-row sheet must not become the turn."""
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["A", "B"])
        for index in range(10_000):
            sheet.append([index, f"row {index}"])
        path = tmp_path / "big.xlsx"
        workbook.save(path)
        workbook.close()

        out = await skill.execute(_task("excel_read", op="shape", path=str(path)))

        assert len(out) < 1_000
        assert "10001 rows" in out
        assert "row 9999" not in out

    @pytest.mark.asyncio
    async def test_read_range_returns_the_values(self, skill, book):
        out = await skill.execute(
            _task(
                "excel_read",
                op="read_range",
                path=str(book),
                sheet="Budget",
                range="A1:B3",
            )
        )

        assert "row 1 is Item, Qty" in out
        assert "row 2 is Item 1, 1" in out
        assert "row 3 is Item 2, 2" in out

    @pytest.mark.asyncio
    async def test_read_range_needs_a_range(self, skill, book):
        out = await skill.execute(
            _task("excel_read", op="read_range", path=str(book), sheet="Budget")
        )
        assert "need a range" in out.lower()

    @pytest.mark.asyncio
    async def test_a_nonsense_range_is_explained_not_raised(self, skill, book):
        out = await skill.execute(
            _task(
                "excel_read",
                op="read_range",
                path=str(book),
                sheet="Budget",
                range="the totals column",
            )
        )
        assert "A1 style" in out

    @pytest.mark.asyncio
    async def test_a_missing_sheet_names_the_ones_that_exist(self, skill, book):
        out = await skill.execute(
            _task("excel_read", op="shape", path=str(book), sheet="Ledger")
        )

        assert "no sheet called 'Ledger'" in out
        assert "Budget" in out

    @pytest.mark.asyncio
    async def test_a_missing_workbook_is_reported_not_raised(self, skill, tmp_path):
        """The agent loop feeds this back to the model, which can then look
        for the real path. An exception would end the turn."""
        out = await skill.execute(
            _task("excel_read", op="sheets", path=str(tmp_path / "nope.xlsx"))
        )
        assert "can't find" in out.lower()

    @pytest.mark.asyncio
    async def test_a_non_workbook_is_refused(self, skill, tmp_path):
        other = tmp_path / "notes.txt"
        other.write_text("hello", encoding="utf-8")

        out = await skill.execute(_task("excel_read", op="sheets", path=str(other)))
        assert "xlsx" in out


class TestFixedOpSet:
    @pytest.mark.asyncio
    async def test_an_invented_read_op_gets_the_refusal(self, skill, book):
        out = await skill.execute(
            _task("excel_read", op="delete_rows", path=str(book))
        )
        assert out == REFUSAL

    @pytest.mark.asyncio
    async def test_an_invented_write_op_gets_the_refusal(self, skill, book):
        out = await skill.execute(
            _task("excel_write", op="pivot_table", path=str(book))
        )
        assert out == REFUSAL

    @pytest.mark.asyncio
    async def test_a_write_op_cannot_arrive_through_the_read_tool(self, skill, book):
        """excel_read is unconfirmed. A write reaching it would slip past the
        user's yes/no entirely."""
        out = await skill.execute(
            _task("excel_write".replace("write", "read"), op="set_values", path=str(book))
        )
        assert out == REFUSAL
        assert load_workbook(book).sheetnames == ["Budget", "Summary"]

    @pytest.mark.asyncio
    async def test_an_unknown_intent_is_a_wiring_bug_not_a_sentence(self, skill, book):
        with pytest.raises(ValueError):
            await skill.execute(_task("excel_dance", op="sheets", path=str(book)))


class TestWriteOps:
    @pytest.mark.asyncio
    async def test_set_values_writes_the_cells(self, skill, book):
        out = await skill.execute(
            _task(
                "excel_write",
                op="set_values",
                path=str(book),
                sheet="Budget",
                range="A2:B3",
                values=[["Bolt", 7], ["Nut", 9]],
            )
        )

        reopened = load_workbook(book, data_only=False)["Budget"]
        assert reopened["A2"].value == "Bolt"
        assert reopened["B3"].value == 9
        assert "A2:B3" in out

    @pytest.mark.asyncio
    async def test_set_values_accepts_a_json_string(self, skill, book):
        """Small models send the array as a string about as often as a list."""
        await skill.execute(
            _task(
                "excel_write",
                op="set_values",
                path=str(book),
                sheet="Budget",
                range="A2:B2",
                values='[["Bolt", 7]]',
            )
        )

        assert load_workbook(book)["Budget"]["A2"].value == "Bolt"

    @pytest.mark.asyncio
    async def test_set_values_says_where_the_values_actually_landed(self, skill, book):
        """Asked for two rows, given three: the model has to be told."""
        out = await skill.execute(
            _task(
                "excel_write",
                op="set_values",
                path=str(book),
                sheet="Budget",
                range="A2:B3",
                values=[["a", 1], ["b", 2], ["c", 3]],
            )
        )

        assert "A2:B4" in out
        assert "you asked for A2:B3" in out

    @pytest.mark.asyncio
    async def test_set_formula_fills_the_range_with_shifted_references(
        self, skill, book
    ):
        out = await skill.execute(
            _task(
                "excel_write",
                op="set_formula",
                path=str(book),
                sheet="Budget",
                range="E2:E4",
                formula="=B2*C2",
            )
        )

        sheet = load_workbook(book, data_only=False)["Budget"]
        assert sheet["E2"].value == "=B2*C2"
        assert sheet["E4"].value == "=B4*C4"
        assert "not recalculated" in out or "hasn't recalculated" in out

    @pytest.mark.asyncio
    async def test_a_formula_without_the_equals_sign_still_works(self, skill, book):
        await skill.execute(
            _task(
                "excel_write",
                op="set_formula",
                path=str(book),
                sheet="Budget",
                range="E2",
                formula="B2*C2",
            )
        )
        assert load_workbook(book, data_only=False)["Budget"]["E2"].value == "=B2*C2"

    @pytest.mark.asyncio
    async def test_add_sheet_adds_one_and_refuses_a_duplicate(self, skill, book):
        added = await skill.execute(
            _task("excel_write", op="add_sheet", path=str(book), name="Q3")
        )
        assert "Q3" in added
        assert "Q3" in load_workbook(book).sheetnames

        again = await skill.execute(
            _task("excel_write", op="add_sheet", path=str(book), name="Q3")
        )
        assert "already a sheet" in again

    @pytest.mark.asyncio
    async def test_format_bold_defaults_to_the_header_row(self, skill, book):
        await skill.execute(
            _task("excel_write", op="format_bold", path=str(book), sheet="Budget")
        )

        sheet = load_workbook(book)["Budget"]
        assert sheet["A1"].font.bold is True
        assert sheet["D1"].font.bold is True
        assert not sheet["A2"].font.bold

    @pytest.mark.asyncio
    async def test_a_write_does_not_flatten_the_workbook_s_formulas(self, skill, book):
        """The data_only trap: loading with cached values and saving replaces
        every formula in the file with a number, permanently."""
        await skill.execute(
            _task(
                "excel_write",
                op="set_values",
                path=str(book),
                sheet="Budget",
                range="F1",
                values=[["note"]],
            )
        )

        assert load_workbook(book, data_only=False)["Budget"]["D2"].value == "=B2*C2"

    @pytest.mark.asyncio
    async def test_a_macro_workbook_is_left_alone(self, skill, tmp_path):
        macro = tmp_path / "macros.xlsm"
        macro.write_bytes(b"PK\x03\x04 not really a workbook")

        out = await skill.execute(
            _task("excel_write", op="add_sheet", path=str(macro), name="Q3")
        )
        assert "macro" in out.lower()


class TestErrorScan:
    @pytest.mark.asyncio
    async def test_a_written_error_value_is_reported_with_its_cell(self, skill, book):
        """This is the trap the scan exists for: the save succeeds, the cell
        has content, and the column is broken."""
        out = await skill.execute(
            _task(
                "excel_write",
                op="set_values",
                path=str(book),
                sheet="Budget",
                range="A2:B2",
                values=[["#DIV/0!", 3]],
            )
        )

        assert "#DIV/0!" in out
        assert "A2" in out

    @pytest.mark.asyncio
    async def test_a_clean_write_says_the_range_is_clean(self, skill, book):
        out = await skill.execute(
            _task(
                "excel_write",
                op="set_values",
                path=str(book),
                sheet="Budget",
                range="A2:B2",
                values=[["Bolt", 3]],
            )
        )

        assert "no error values" in out
        assert not any(error in out for error in ("#REF!", "#VALUE!", "#DIV/0!"))

    @pytest.mark.asyncio
    async def test_the_openpyxl_path_admits_it_did_not_recalculate(self, skill, book):
        """openpyxl cannot make Excel calculate anything. Saying "no errors"
        without that caveat would be a claim the skill cannot support."""
        out = await skill.execute(
            _task(
                "excel_write",
                op="set_formula",
                path=str(book),
                sheet="Budget",
                range="E2:E4",
                formula="=B2/0",
            )
        )

        assert "recalculated" in out


class TestBackups:
    @pytest.mark.asyncio
    async def test_the_first_write_backs_the_workbook_up(self, skill, book, tmp_path):
        await skill.execute(
            _task(
                "excel_write",
                op="set_values",
                path=str(book),
                sheet="Budget",
                range="A2",
                values=[["Bolt"]],
            )
        )

        copies = _backups(tmp_path)
        assert len(copies) == 1
        assert copies[0].name.startswith("budget_")
        # The copy is the state *before* the edit -- that is the whole point.
        assert load_workbook(copies[0])["Budget"]["A2"].value == "Item 1"

    @pytest.mark.asyncio
    async def test_later_writes_in_the_same_session_do_not_re_copy(
        self, skill, book, tmp_path
    ):
        """Backing up again on every op would rotate the original out behind
        ULTRON's own edits."""
        for column in ("A2", "A3", "A4"):
            await skill.execute(
                _task(
                    "excel_write",
                    op="set_values",
                    path=str(book),
                    sheet="Budget",
                    range=column,
                    values=[["x"]],
                )
            )

        assert len(_backups(tmp_path)) == 1

    @pytest.mark.asyncio
    async def test_backups_rotate_at_ten(self, skill, book, tmp_path):
        for _ in range(MAX_BACKUPS + 4):
            # A new session is what makes a new backup; forcing it here is
            # what the calendar would do over a fortnight of edits.
            skill._backed_up.clear()
            await skill.execute(
                _task(
                    "excel_write",
                    op="set_values",
                    path=str(book),
                    sheet="Budget",
                    range="A2",
                    values=[["x"]],
                )
            )

        assert len(_backups(tmp_path)) == MAX_BACKUPS

    @pytest.mark.asyncio
    async def test_rotation_keeps_the_newest_and_only_this_workbook(
        self, skill, book, tmp_path
    ):
        root = tmp_path / "backups"
        root.mkdir(parents=True, exist_ok=True)
        for index in range(MAX_BACKUPS + 2):
            (root / f"budget_20250101-0000{index:02d}.xlsx").write_bytes(b"old")
        (root / "payroll_20250101-000000.xlsx").write_bytes(b"other")

        await skill.execute(
            _task(
                "excel_write",
                op="set_values",
                path=str(book),
                sheet="Budget",
                range="A2",
                values=[["x"]],
            )
        )

        names = {path.name for path in _backups(tmp_path)}
        assert len(names) == MAX_BACKUPS + 1  # ten budgets plus the payroll copy
        assert "payroll_20250101-000000.xlsx" in names
        assert "budget_20250101-000000.xlsx" not in names  # oldest pruned

    @pytest.mark.asyncio
    async def test_a_write_whose_backup_fails_does_not_happen(
        self, skill, book, monkeypatch
    ):
        """Same rule as code_skill: an edit nobody can undo does not happen."""
        import skills.excel_skill as module

        def _no(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(module.shutil, "copy2", _no)

        out = await skill.execute(
            _task(
                "excel_write",
                op="set_values",
                path=str(book),
                sheet="Budget",
                range="A2",
                values=[["Bolt"]],
            )
        )

        assert "haven't changed it" in out
        assert load_workbook(book)["Budget"]["A2"].value == "Item 1"


class TestLiveExcel:
    """xlwings against a real Excel. Skipped wherever there isn't one."""

    @pytest.mark.asyncio
    async def test_the_live_path_reads_and_scans_a_real_workbook(self, book, tmp_path):
        pytest.importorskip("xlwings")
        import xlwings as xw

        try:
            running = len(xw.apps)
        except Exception as exc:
            pytest.skip(f"Excel is not available on this machine: {exc}")

        if running:
            # The no-path ops address whatever Excel calls the active
            # workbook, which is a global. If the person running the suite has
            # their own spreadsheet open, this test would write =1/0 into it.
            pytest.skip("Excel is already running; refusing to touch a live workbook")

        app = None
        try:
            app = xw.App(visible=False, add_book=False)
            workbook = app.books.open(str(book))
        except Exception as exc:  # no Excel, no COM, or Excel refused
            if app is not None:
                try:
                    app.kill()
                except Exception:
                    pass
            pytest.skip(f"Excel is not available on this machine: {exc}")

        skill = ExcelSkill(backup_root=tmp_path / "backups")
        try:
            sheets = await skill.execute(_task("excel_read", op="sheets"))
            assert "Budget" in sheets

            # Belt and braces before anything writes: the active workbook has
            # to be the throwaway one this test made.
            assert xw.books.active.name == workbook.name == "budget.xlsx"

            # The live path is the one that can really verify: Excel
            # calculates =1/0 and the scan reads the error back, which the
            # openpyxl path structurally cannot do.
            written = await skill.execute(
                _task(
                    "excel_write",
                    op="set_formula",
                    sheet="Budget",
                    range="F2",
                    formula="=1/0",
                )
            )
            assert "#DIV/0!" in written
            assert "F2" in written
            # The live write is backed up like any other.
            assert len(_backups(tmp_path)) == 1
        finally:
            # Tearing down a COM connection raises an RPC exception that
            # pywin32 handles, but pytest's faulthandler prints the SEH trace
            # anyway and it reads like a crash in an otherwise green run.
            faulthandler.disable()
            try:
                app.kill()
            except Exception:
                pass
            faulthandler.enable()

    @pytest.mark.asyncio
    async def test_no_excel_is_a_sentence_not_a_traceback(self, skill, monkeypatch):
        """The failure users actually hit -- Excel not installed -- has to
        speak, not trace."""
        import skills.excel_skill as module

        def _boom(self, path):
            raise module._ExcelUnavailable(
                "I couldn't reach Excel on this machine - it needs Excel installed."
            )

        monkeypatch.setattr(module.ExcelSkill, "_book", _boom)

        out = await skill.execute(_task("excel_read", op="sheets"))
        assert "Excel" in out
        assert "Traceback" not in out

    @pytest.mark.asyncio
    async def test_a_missing_xlwings_returns_the_install_hint(self, skill, monkeypatch):
        import skills.excel_skill as module

        def _missing(self, path):
            raise ImportError("No module named 'xlwings'")

        monkeypatch.setattr(module.ExcelSkill, "_book", _missing)

        out = await skill.execute(_task("excel_read", op="sheets"))
        assert "pip install xlwings" in out


class TestBackupPruningIsolation:
    """A prefix is not an identity.

    Pruning globbed ``{stem}_*{suffix}``, so tidying ``report.xlsx``'s backups
    also matched ``report_2025_<stamp>.xlsx`` -- the backups of a different
    workbook that merely starts with the same characters. Those sort earlier,
    so they were deleted first: ULTRON destroying the undo history of a file
    nobody asked it to touch.
    """

    @pytest.mark.asyncio
    async def test_a_similarly_named_workbook_keeps_its_backups(
        self, skill, tmp_path
    ):
        root = tmp_path / "backups"
        root.mkdir(parents=True, exist_ok=True)

        # The victim: a real backup of report_2025.xlsx, named exactly as
        # _ensure_backup would name it.
        victim = root / "report_2025_20250101-000000.xlsx"
        victim.write_bytes(b"the only copy")

        # Fill past the cap with backups of the *other* workbook.
        for index in range(MAX_BACKUPS + 3):
            (root / f"report_20260101-0000{index:02d}.xlsx").write_bytes(b"mine")

        book = _workbook(tmp_path / "report.xlsx")
        await skill.execute(
            _task(
                "excel_write",
                op="set_values",
                path=str(book),
                sheet="Budget",
                range="A2",
                values=[["x"]],
            )
        )

        assert victim.exists(), "pruning report.xlsx deleted report_2025.xlsx's backup"

    @pytest.mark.asyncio
    async def test_rotation_keeps_the_newest_by_time_not_by_name(
        self, skill, tmp_path
    ):
        """The collision suffix inverts name order against real age.

        ``-10`` sorts before ``-2`` as text, so a name-ordered rotation
        prunes whichever copy happens to carry a high counter -- regardless
        of when it was actually written. The newest copy here is deliberately
        the one that sorts *first* by name.
        """
        import os as _os

        root = tmp_path / "backups"
        root.mkdir(parents=True, exist_ok=True)

        # All in the same second, so only the counter separates the names.
        names = [f"ledger_20260101-000000-{n}.xlsx" for n in range(2, MAX_BACKUPS + 4)]
        names.sort()  # text order: -10, -11, -12, -2, -3, ...

        # Give them ages in the OPPOSITE order: the first name is the newest.
        stamp = 1_700_000_000
        for age, name in enumerate(names):
            path = root / name
            path.write_bytes(b"x")
            _os.utime(path, (stamp - age, stamp - age))

        newest = root / names[0]
        book = _workbook(tmp_path / "ledger.xlsx")
        await skill.execute(
            _task(
                "excel_write",
                op="set_values",
                path=str(book),
                sheet="Budget",
                range="A2",
                values=[["x"]],
            )
        )

        assert newest.exists(), (
            "rotation pruned the newest copy because it sorted first by name"
        )
