"""Parse a pasted, uploaded, or .xlsx roster. No database access.

Three layouts are understood:

1. Wide, one row per person and one column per date, each cell a shift word
       Name,13/10/2026,14/10/2026
       Alex K,Early,All day

2. Wide, one row per person with a paired Start / End column per date -- what the employer's own
   weekly export looks like -- plus an optional trailing licence column, either a dedicated Driver
   Licence / Truck Licence column each, or (as in the real export) a single free-text "note" column
   scanned for those words:
       Name,Mon 12/10,,Tue 13/10,,note
       ,Start,End,Start,End,
       Alex K,15:50,22:15,19:50,23:50,Truck driver
   The date is only needed on the first column of a pair; Excel's merged-cell paste often leaves the
   second blank, which is treated as "same date as the column to its left".

3. Long, one row per shift
       Date,Name,Shift,Role
       13/10/2026,Alex K,Early,Driver

Dates are read day first. Shifts are Early, Late, All day (also E, L, A). Off or blank means not
working. Times are HH:MM (also H:MM or HHMM, e.g. 1550). A dedicated Driver/Truck licence column
counts as held unless the cell is blank or an "off"-style word (no, n, 0, -, ...); a note column
grants it when the cell's text contains "driver" and/or "truck". In the paired layout, the actual
Start/Indicative End is kept and Early/Late/All day is a best-effort label derived from it, against the
shift's configured window -- the times are the source of truth, the label only exists so the existing
chip filters and sort order keep working.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from io import BytesIO
from typing import Optional

from openpyxl import load_workbook

from .domain import to_minutes

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
QUAL_ROLES = ("Driver", "Truck")
_OFF = {"", "off", "rdo", "leave", "al", "sl", "-", "x", "n/a", "na", "no", "n", "0"}
_WEEKDAY = re.compile(r"^(mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?[,\s]*", re.IGNORECASE)
_TIME = re.compile(r"^(\d{1,2}):?([0-5]\d)$")


def _iso(year: int, month: int, day: int) -> Optional[str]:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def parse_date(value: str, today: Optional[date] = None) -> Optional[str]:
    """Return an ISO date string or None. Day first: 13/10/2026 is 13 October."""
    today = today or date.today()
    text = _WEEKDAY.sub("", (value or "").strip())
    if not text:
        return None
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    if m:
        return _iso(int(m[1]), int(m[2]), int(m[3]))
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})(?:[-/.](\d{2,4}))?", text)
    if m:
        year = int(m[3]) if m[3] else today.year
        if year < 100:
            year += 2000
        return _iso(year, int(m[2]), int(m[1]))
    m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?[\s-]+([A-Za-z]{3,9})\.?(?:[\s,-]+(\d{4}))?", text)
    if m:
        name = m[2].lower()
        for index, month in enumerate(MONTHS):
            if name.startswith(month):
                return _iso(int(m[3]) if m[3] else today.year, index + 1, int(m[1]))
    return None


def parse_shift(value: str) -> tuple[bool, Optional[str]]:
    """Return (recognised, shift). shift is early, late, all or None for not working."""
    text = (value or "").strip().lower()
    if text in _OFF:
        return True, None
    if "early" in text or text in ("e", "am"):
        return True, "early"
    if "late" in text or text in ("l", "pm"):
        return True, "late"
    if any(word in text for word in ("all", "long", "full")) or text in ("a", "ad"):
        return True, "all"
    return False, None


def parse_time(value: str) -> Optional[str]:
    """Return a normalised HH:MM, or None if blank/off/unreadable. Accepts 15:50, 5:50, 1550."""
    text = (value or "").strip()
    if text.lower() in _OFF:
        return None
    m = _TIME.fullmatch(text)
    if not m:
        return None
    hour = int(m[1])
    if not (0 <= hour <= 23):
        return None
    return f"{hour:02d}:{m[2]}"


def derive_shift_type(rstart: str, rend: str, window: tuple[str, str]) -> str:
    """Best-effort Early/Late/All day label for an actual Start/Indicative End, relative to the
    shift's configured window. Calibrated against this employer's two real shift patterns within a
    13:00-06:00 (17h) window -- Early 15:50-22:15 (starts ~17% in, runs ~38%), Late 19:50-23:55
    (starts ~40% in, runs ~24%), All day 15:50-23:55 (runs ~48%) -- rather than splitting the window
    down the literal middle, which puts both real start times in the first half and mislabels Late
    as Early. Handles the entry and/or the window crossing midnight."""
    start, end = to_minutes(rstart), to_minutes(rend)
    w_start, w_end = to_minutes(window[0]), to_minutes(window[1])
    duration = (end - start) % 1440
    window_len = (w_end - w_start) % 1440 or 1440
    if duration >= window_len * 0.45:
        return "all"
    offset = (start - w_start) % 1440
    return "early" if offset <= window_len * 0.28 else "late"


def _split_row(line: str) -> list[str]:
    if "\t" in line:
        cells = line.split("\t")
    else:
        cells = next(csv.reader([line]))
    return [cell.strip() for cell in cells]


def _cell(row: list[str], index: int) -> str:
    return row[index] if 0 <= index < len(row) else ""


@dataclass
class ParsedRoster:
    days: dict[str, dict[str, dict]] = field(default_factory=dict)  # date -> name -> cell
    bad: list[str] = field(default_factory=list)
    people: set[str] = field(default_factory=set)  # lower-case names
    shifts: int = 0

    def put(
        self,
        day: str,
        name: str,
        shift: Optional[str],
        roles: Optional[list[str]] = None,
        rstart: str = "",
        rend: str = "",
    ) -> None:
        self.days.setdefault(day, {})[name] = {"shift": shift, "roles": roles or [], "rstart": rstart, "rend": rend}
        self.people.add(name.lower())
        if shift:
            self.shifts += 1


def _is_startish(text: str) -> bool:
    return "start" in text.strip().lower()


def _is_endish(text: str) -> bool:
    text = text.strip().lower()
    return "end" in text or "finish" in text


_TRAILING_START = re.compile(r"\s*start\s*$", re.IGNORECASE)


def _find_single_row_pairs(head: list[str], today: Optional[date]) -> list[tuple[str, int, int]]:
    """The employer's actual .xlsx has one header row, each date and "Start" combined into one cell
    ("Mon 12/10 Start") immediately followed by a plain "End" cell -- no separate sub-header row."""
    pairs: list[tuple[str, int, int]] = []
    i = 1
    while i + 1 < len(head):
        cell = head[i].strip()
        if _is_startish(cell):
            day = parse_date(_TRAILING_START.sub("", cell), today)
            if day and _is_endish(_cell(head, i + 1)):
                pairs.append((day, i, i + 1))
                i += 2
                continue
        break
    return pairs


def _find_two_row_pairs(head: list[str], sub: list[str], today: Optional[date]) -> list[tuple[str, int, int]]:
    """A date row (the date only needed on the first column of a pair -- a merged cell's paste often
    leaves the second blank) over a separate Start/Indicative End sub-header row."""
    pairs: list[tuple[str, int, int]] = []
    last_date_cell = ""
    i = 1
    while i < len(head):
        if head[i].strip():
            last_date_cell = head[i]
        day = parse_date(last_date_cell, today)
        if day and _is_startish(_cell(sub, i)) and _is_endish(_cell(sub, i + 1)):
            pairs.append((day, i, i + 1))
            i += 2
            continue
        break
    return pairs


def _licence_columns(head: list[str], start: int) -> tuple[list[tuple[int, str]], list[int]]:
    """Either a dedicated Driver Licence / Truck Licence column each (a non-blank cell means held),
    or a single free-text note column (e.g. "driver", "Truck driver") scanned for those words -- the
    real export from this employer uses the latter."""
    lic_cols: list[tuple[int, str]] = []
    note_cols: list[int] = []
    for j in range(start, len(head)):
        name = head[j].strip().lower()
        if "note" in name:
            note_cols.append(j)
        elif re.search(r"driver", name):
            lic_cols.append((j, "Driver"))
        elif re.search(r"truck", name):
            lic_cols.append((j, "Truck"))
    return lic_cols, note_cols


_MAX_TITLE_ROWS = 3  # how many leading rows (e.g. a merged "ADL - PM SHIFT - Week ending..." banner) to skip


def _detect_paired_header(rows: list[list[str]], today: Optional[date]):
    """Scan the first few rows for a paired Start/End header, skipping past an optional title banner
    above it. Tries the single-header-row style first (see _find_single_row_pairs), then the
    two-header-row style (see _find_two_row_pairs). Returns the date pairs (date, start_col, end_col),
    any trailing Driver/Truck licence columns, any note columns, and the row index the person data
    starts at -- or None if nothing matches."""
    for header_row in range(0, min(_MAX_TITLE_ROWS, len(rows) - 1) + 1):
        head = rows[header_row]
        pairs = _find_single_row_pairs(head, today)
        data_start = header_row + 1
        if not pairs and header_row + 1 < len(rows):
            pairs = _find_two_row_pairs(head, rows[header_row + 1], today)
            data_start = header_row + 2
        if not pairs:
            continue
        end_col = pairs[-1][2]
        lic_cols, note_cols = _licence_columns(head, end_col + 1)
        return pairs, lic_cols, note_cols, data_start
    return None


def _roles_for_row(row: list[str], lic_cols: list[tuple[int, str]], note_cols: list[int]) -> list[str]:
    roles = [role for col, role in lic_cols if _cell(row, col).strip().lower() not in _OFF]
    for col in note_cols:
        text = _cell(row, col).strip().lower()
        if "driver" in text and "Driver" not in roles:
            roles.append("Driver")
        if "truck" in text and "Truck" not in roles:
            roles.append("Truck")
    return roles


def _parse_paired_wide(
    rows: list[list[str]],
    pairs: list[tuple[str, int, int]],
    lic_cols: list[tuple[int, str]],
    note_cols: list[int],
    data_start: int,
    window: tuple[str, str],
) -> ParsedRoster:
    result = ParsedRoster()
    header = rows[data_start - 2]  # the date row, for the column label in a bad-row message
    for row in rows[data_start:]:
        name = _cell(row, 0).strip()
        if not name:
            continue
        roles = _roles_for_row(row, lic_cols, note_cols)
        for day, start_col, end_col in pairs:
            raw_start, raw_end = _cell(row, start_col), _cell(row, end_col)
            if raw_start.strip().lower() in _OFF and raw_end.strip().lower() in _OFF:
                result.put(day, name, None, roles=roles)
                continue
            rstart, rend = parse_time(raw_start), parse_time(raw_end)
            if not rstart or not rend:
                result.bad.append(f'{name}, {_cell(header, start_col) or "that day"}: "{raw_start}"/"{raw_end}"')
                continue
            result.put(day, name, derive_shift_type(rstart, rend, window), roles=roles, rstart=rstart, rend=rend)
    return result


def parse_roster_text(text: str, today: Optional[date] = None, window: Optional[tuple[str, str]] = None) -> ParsedRoster:
    rows = [_split_row(line) for line in (text or "").splitlines() if line.strip()]
    return parse_roster_rows(rows, today, window)


def parse_roster_rows(
    rows: list[list[str]], today: Optional[date] = None, window: Optional[tuple[str, str]] = None
) -> ParsedRoster:
    """Same as parse_roster_text, but already split into a grid of cells -- the common core for both
    the pasted/CSV text path and an uploaded .xlsx workbook (see parse_roster_xlsx)."""
    if len(rows) < 2:
        return ParsedRoster()

    paired = _detect_paired_header(rows, today)
    if paired:
        pairs, lic_cols, note_cols, data_start = paired
        return _parse_paired_wide(rows, pairs, lic_cols, note_cols, data_start, window or ("00:00", "23:59"))

    result = ParsedRoster()
    head = rows[0]
    date_cols = [parse_date(cell, today) if i > 0 else None for i, cell in enumerate(head)]

    if any(date_cols):  # wide layout
        for row in rows[1:]:
            name = row[0] if row else ""
            if not name:
                continue
            for index, day in enumerate(date_cols):
                if not day:
                    continue
                raw = row[index] if index < len(row) else ""
                ok, shift = parse_shift(raw)
                if not ok:
                    result.bad.append(f'{name}, {head[index]}: "{raw}"')
                    continue
                result.put(day, name, shift)
        return result

    # long layout
    lowered = [cell.lower() for cell in head]

    def find(pattern: str) -> int:
        for i, cell in enumerate(lowered):
            if re.search(pattern, cell):
                return i
        return -1

    col_date, col_name, col_shift, col_role = find("date"), find("name|staff|employee"), find("shift"), find("role")
    start = 1
    if min(col_date, col_name, col_shift) < 0:
        col_date, col_name, col_shift = 0, 1, 2
        col_role = 3 if len(head) > 3 else -1
        start = 0

    for row in rows[start:]:
        day = parse_date(_cell(row, col_date), today)
        name = _cell(row, col_name).strip()
        ok, shift = parse_shift(_cell(row, col_shift))
        if not day or not name or not ok:
            result.bad.append(", ".join(row))
            continue
        role = None
        if col_role >= 0:
            wanted = _cell(row, col_role).strip().lower()
            role = next((r for r in QUAL_ROLES if r.lower() == wanted), None)
        result.put(day, name, shift, roles=[role] if role else [])
    return result


def _xlsx_cell_text(value) -> str:
    """Render one openpyxl cell value the same way a pasted/CSV cell would read as text."""
    if value is None:
        return ""
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, datetime):
        # Excel stores a time-only value as a datetime on its epoch day (1899-12-30) plus the time.
        if value.year <= 1900 and (value.hour or value.minute):
            return value.strftime("%H:%M")
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def parse_roster_xlsx(data: bytes, today: Optional[date] = None, window: Optional[tuple[str, str]] = None) -> ParsedRoster:
    """Same as parse_roster_text, but for an uploaded .xlsx workbook: reads the first sheet and
    resolves merged cells (e.g. a date merged across its Start/End columns) by filling the merged
    value into every cell of the range -- more reliable than the paste-text path, which can only
    guess that a blank cell means "same as the column to its left"."""
    workbook = load_workbook(BytesIO(data), data_only=True)
    sheet = workbook.active
    grid: list[list[str]] = [[_xlsx_cell_text(cell.value) for cell in row] for row in sheet.iter_rows()]
    for merged in sheet.merged_cells.ranges:
        value = grid[merged.min_row - 1][merged.min_col - 1]
        for r in range(merged.min_row, merged.max_row + 1):
            for c in range(merged.min_col, merged.max_col + 1):
                grid[r - 1][c - 1] = value
    rows = [row for row in grid if any(cell.strip() for cell in row)]
    return parse_roster_rows(rows, today, window)
