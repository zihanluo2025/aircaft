"""Build a blank roster .xlsx for one week that the importer reads back as-is.

Same layout as the employer's own weekly export (see roster_import.py, layout 2): a title row,
then each date merged across a Start / End pair, a Start/End sub-header row, and a trailing Note
column whose "driver" / "truck" words mark licences. The team's names are filled in, with their
current licences in Note, so the manager only types times. Both cells blank means a day off.
"""
from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

SHIFT_NAME = {"morning": "Morning", "night": "Night"}
QUAL_NOTE = {"Driver": "driver", "Truck": "truck"}


def build_roster_template(start: date, shift: str, people: list[tuple[str, list[str]]], days: int = 7) -> BytesIO:
    """people: (name, quals) for everyone on the team, in the order they should appear."""
    dates = [start + timedelta(days=i) for i in range(days)]
    note_col = 2 + 2 * days
    bold = Font(bold=True)
    head_fill = PatternFill("solid", fgColor="E8EEF4")
    thin = Side(style="thin", color="C2D1DC")
    center = Alignment(horizontal="center", vertical="center")

    wb = Workbook()
    ws = wb.active
    ws.title = "Roster"

    ws.cell(row=1, column=1, value=f"ADL - {SHIFT_NAME.get(shift, shift).upper()} SHIFT - Week {dates[0]:%d/%m/%Y} to {dates[-1]:%d/%m/%Y}").font = Font(bold=True, size=13)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=note_col)

    ws.cell(row=2, column=1, value="Name")
    ws.cell(row=3, column=1, value="")
    for i, day in enumerate(dates):
        col = 2 + 2 * i
        cell = ws.cell(row=2, column=col, value=day)
        cell.number_format = "ddd dd/mm/yyyy"
        ws.merge_cells(start_row=2, start_column=col, end_row=2, end_column=col + 1)
        ws.cell(row=3, column=col, value="Start")
        ws.cell(row=3, column=col + 1, value="End")
    ws.cell(row=2, column=note_col, value="Note")
    for row in (2, 3):
        for col in range(1, note_col + 1):
            cell = ws.cell(row=row, column=col)
            cell.font = bold
            cell.fill = head_fill
            cell.alignment = center
            cell.border = Border(bottom=thin)

    for r, (name, quals) in enumerate(people, start=4):
        ws.cell(row=r, column=1, value=name)
        for col in range(2, note_col):
            ws.cell(row=r, column=col).number_format = "hh:mm"
            ws.cell(row=r, column=col).alignment = center
        ws.cell(row=r, column=note_col, value=" ".join(QUAL_NOTE[q] for q in quals if q in QUAL_NOTE))

    ws.column_dimensions["A"].width = 34
    for col in range(2, note_col):
        ws.column_dimensions[get_column_letter(col)].width = 9
    ws.column_dimensions[get_column_letter(note_col)].width = 16
    ws.freeze_panes = "B4"

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
