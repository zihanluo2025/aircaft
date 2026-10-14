from datetime import date, time
from io import BytesIO

from openpyxl import Workbook

from app.services.roster_import import (
    derive_shift_type,
    parse_date,
    parse_roster_text,
    parse_roster_xlsx,
    parse_shift,
    parse_time,
)

TODAY = date(2026, 10, 13)


def test_parse_date_day_first():
    assert parse_date("13/10/2026", TODAY) == "2026-10-13"
    assert parse_date("2026-10-13", TODAY) == "2026-10-13"
    assert parse_date("13/10", TODAY) == "2026-10-13"
    assert parse_date("1/2/26", TODAY) == "2026-02-01"


def test_parse_date_names_and_weekdays():
    assert parse_date("Mon 15 Oct", TODAY) == "2026-10-15"
    assert parse_date("15th October 2026", TODAY) == "2026-10-15"
    assert parse_date("Tue, 13/10/2026", TODAY) == "2026-10-13"


def test_parse_date_rejects_nonsense():
    assert parse_date("", TODAY) is None
    assert parse_date("Name", TODAY) is None
    assert parse_date("31/02/2026", TODAY) is None


def test_parse_shift():
    assert parse_shift("Early") == (True, "early")
    assert parse_shift("L") == (True, "late")
    assert parse_shift("All day") == (True, "all")
    assert parse_shift("Long") == (True, "all")
    assert parse_shift("Off") == (True, None)
    assert parse_shift("") == (True, None)
    assert parse_shift("banana")[0] is False


def test_parse_time():
    assert parse_time("15:50") == "15:50"
    assert parse_time("5:50") == "05:50"
    assert parse_time("1550") == "15:50"
    assert parse_time("") is None
    assert parse_time("Off") is None
    assert parse_time("banana") is None
    assert parse_time("25:00") is None


def test_derive_shift_type_within_a_normal_window():
    # 06:00-13:00 window: a near-full-window entry is "all", an early-half entry is "early", a
    # second-half entry is "late".
    window = ("06:00", "13:00")
    assert derive_shift_type("06:00", "12:50", window) == "all"
    assert derive_shift_type("06:00", "09:00", window) == "early"
    assert derive_shift_type("10:30", "13:00", window) == "late"


def test_derive_shift_type_across_midnight():
    # 13:00-06:00 window (overnight): a start soon after the window opens is "early".
    window = ("13:00", "06:00")
    assert derive_shift_type("13:00", "16:00", window) == "early"
    assert derive_shift_type("13:00", "05:50", window) == "all"


def test_wide_layout():
    text = "Name\t13/10/2026\t14/10/2026\tMon 15 Oct\nAlex K\tEarly\tAll day\tOff\nPriya S\tLate\tL\tfoo\n"
    result = parse_roster_text(text, TODAY)
    assert sorted(result.days) == ["2026-10-13", "2026-10-14", "2026-10-15"]
    assert result.days["2026-10-13"]["Alex K"] == {"shift": "early", "roles": [], "rstart": "", "rend": ""}
    assert result.days["2026-10-14"]["Alex K"]["shift"] == "all"
    assert result.days["2026-10-15"]["Alex K"]["shift"] is None
    assert result.shifts == 4
    assert result.people == {"alex k", "priya s"}
    assert result.bad == ['Priya S, Mon 15 Oct: "foo"']


def test_wide_layout_csv_with_quotes():
    text = 'Name,13/10/2026\n"Smith, Jo",Early\n'
    result = parse_roster_text(text, TODAY)
    assert result.days["2026-10-13"]["Smith, Jo"]["shift"] == "early"


def test_long_layout_with_role():
    text = "Date,Name,Shift,Role\n2026-10-13,Alex K,Early,Driver\n14/10/2026,Priya S,All day,\n"
    result = parse_roster_text(text, TODAY)
    assert result.days["2026-10-13"]["Alex K"] == {"shift": "early", "roles": ["Driver"], "rstart": "", "rend": ""}
    assert result.days["2026-10-14"]["Priya S"] == {"shift": "all", "roles": [], "rstart": "", "rend": ""}
    assert result.shifts == 2
    assert result.bad == []


def test_long_layout_ignores_toilet_role():
    text = "Date,Name,Shift,Role\n2026-10-13,Alex K,Early,Toilet\n"
    assert parse_roster_text(text, TODAY).days["2026-10-13"]["Alex K"]["roles"] == []


def test_long_layout_collects_bad_rows():
    text = "Date,Name,Shift\nnot a date,Alex K,Early\n13/10/2026,Priya S,banana\n13/10/2026,Tom W,Late\n"
    result = parse_roster_text(text, TODAY)
    assert len(result.bad) == 2
    assert result.days["2026-10-13"] == {"Tom W": {"shift": "late", "roles": [], "rstart": "", "rend": ""}}


def test_too_short_input():
    assert parse_roster_text("", TODAY).days == {}
    assert parse_roster_text("Name,13/10/2026", TODAY).days == {}


# ---- the real employer export: paired Start / Indicative End columns, plus licence columns ----

PAIRED_HEADER = "Name\tMon 12/10\t\tTue 13/10\t\tDriver Licence\tTruck Licence\n\tStart\tIndicative End\tStart\tIndicative End\t\t\n"


def test_paired_wide_layout_reads_times_and_derives_shift():
    text = PAIRED_HEADER + "Alex K\t15:50\t22:15\t19:50\t23:50\tYes\t\n"
    result = parse_roster_text(text, TODAY, window=("13:00", "06:00"))
    assert sorted(result.days) == ["2026-10-12", "2026-10-13"]
    entry = result.days["2026-10-12"]["Alex K"]
    assert entry["rstart"] == "15:50"
    assert entry["rend"] == "22:15"
    assert entry["roles"] == ["Driver"]
    assert entry["shift"] in ("early", "late", "all")  # derived, not asserting the exact bucket here


def test_paired_wide_layout_both_licences_from_one_row():
    text = PAIRED_HEADER + "Priya S\t15:50\t22:15\t\t\tY\tY\n"
    result = parse_roster_text(text, TODAY, window=("13:00", "06:00"))
    assert sorted(result.days["2026-10-12"]["Priya S"]["roles"]) == ["Driver", "Truck"]


def test_paired_wide_layout_off_day_still_grants_licence():
    text = PAIRED_HEADER + "Tom W\t\t\t15:50\t22:15\tYes\t\n"
    result = parse_roster_text(text, TODAY, window=("13:00", "06:00"))
    off_day = result.days["2026-10-12"]["Tom W"]
    assert off_day["shift"] is None
    assert off_day["roles"] == ["Driver"]  # the licence column still applies even on a day off


def test_paired_wide_layout_merged_date_cell_left_blank():
    # Excel's merged-cell paste often leaves the second column of a pair blank; it should still
    # count as the same date as the column to its left.
    text = PAIRED_HEADER + "Alex K\t15:50\t22:15\t15:50\t22:15\t\t\n"
    result = parse_roster_text(text, TODAY, window=("13:00", "06:00"))
    assert sorted(result.days) == ["2026-10-12", "2026-10-13"]


def test_paired_wide_layout_partial_time_is_bad_row():
    text = PAIRED_HEADER + "Alex K\t15:50\t\t\t\t\t\n"
    result = parse_roster_text(text, TODAY, window=("13:00", "06:00"))
    assert "2026-10-12" not in result.days or "Alex K" not in result.days.get("2026-10-12", {})
    assert len(result.bad) == 1


def test_plain_wide_and_long_layouts_unaffected_by_paired_detection():
    # Make sure a normal category-based wide/long paste never gets misread as the paired layout.
    assert parse_roster_text("Name,13/10/2026\nAlex K,Early\n", TODAY).days["2026-10-13"]["Alex K"]["shift"] == "early"
    assert (
        parse_roster_text("Date,Name,Shift,Role\n13/10/2026,Alex K,Early,Driver\n", TODAY)
        .days["2026-10-13"]["Alex K"]["shift"]
        == "early"
    )


# ---- the actual employer export: same paired layout, but one free-text "note" column instead of
# dedicated Driver Licence / Truck Licence columns ----

NOTE_HEADER = "Employee\tMon 12/10\t\tTue 13/10\t\tnote\n\tStart\tEnd\tStart\tEnd\t\n"


def test_note_column_grants_driver_from_the_word_driver():
    text = NOTE_HEADER + "Nhung Thi Tuyet Dang - 08212\t15:50\t22:15\t15:50\t23:55\tdriver\n"
    result = parse_roster_text(text, TODAY, window=("13:00", "06:00"))
    assert result.days["2026-10-12"]["Nhung Thi Tuyet Dang - 08212"]["roles"] == ["Driver"]


def test_note_column_grants_both_from_truck_driver():
    text = NOTE_HEADER + "Jorja Olivia Mann - 09208\t15:50\t22:15\t\t\tTruck driver\n"
    result = parse_roster_text(text, TODAY, window=("13:00", "06:00"))
    assert sorted(result.days["2026-10-12"]["Jorja Olivia Mann - 09208"]["roles"]) == ["Driver", "Truck"]


def test_note_column_blank_grants_nothing():
    text = NOTE_HEADER + "Kibreab Fente Bizuneh - 09321\t15:50\t22:15\t15:50\t23:55\t\n"
    result = parse_roster_text(text, TODAY, window=("13:00", "06:00"))
    assert result.days["2026-10-12"]["Kibreab Fente Bizuneh - 09321"]["roles"] == []


def test_paired_layout_skips_a_leading_title_banner_row():
    # A merged "ADL - PM SHIFT - Week ending..." row above the real header, like the actual export.
    text = "ADL - PM SHIFT - Week ending Sun 18 Oct 2026\n" + NOTE_HEADER + "Wei Li - 08050\t15:50\t22:15\t\t\tdriver\n"
    result = parse_roster_text(text, TODAY, window=("13:00", "06:00"))
    assert result.days["2026-10-12"]["Wei Li - 08050"]["roles"] == ["Driver"]


def test_paired_layout_gives_up_past_the_title_row_limit():
    # Four blank-ish rows before the real header is further than it looks -- should not match.
    text = "x\ny\nz\nq\n" + NOTE_HEADER + "Wei Li - 08050\t15:50\t22:15\t\t\tdriver\n"
    result = parse_roster_text(text, TODAY, window=("13:00", "06:00"))
    assert result.days == {}


# ---- an actual uploaded .xlsx workbook, not pasted text ----


def _build_sample_workbook() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "ADL - PM SHIFT - Week ending Sun 18 Oct 2026"
    ws.merge_cells("A1:F1")
    ws["A2"] = "Employee"
    ws["B2"] = date(2026, 10, 12)
    ws.merge_cells("B2:C2")
    ws["D2"] = date(2026, 10, 13)
    ws.merge_cells("D2:E2")
    ws["F2"] = "note"
    ws["B3"], ws["C3"], ws["D3"], ws["E3"] = "Start", "End", "Start", "End"
    ws["A4"] = "Jorja Olivia Mann - 09208"
    ws["B4"], ws["C4"] = time(15, 50), time(22, 15)
    ws["F4"] = "Truck driver"
    ws["A5"] = "Kibreab Fente Bizuneh - 09321"
    ws["B5"], ws["C5"], ws["D5"], ws["E5"] = time(15, 50), time(22, 15), time(15, 50), time(23, 55)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_xlsx_upload_reads_real_date_and_time_cells():
    result = parse_roster_xlsx(_build_sample_workbook(), TODAY, window=("13:00", "06:00"))
    assert sorted(result.days) == ["2026-10-12", "2026-10-13"]
    jorja = result.days["2026-10-12"]["Jorja Olivia Mann - 09208"]
    assert jorja == {"shift": "early", "roles": ["Driver", "Truck"], "rstart": "15:50", "rend": "22:15"}
    assert result.bad == []


def test_xlsx_upload_resolves_merged_date_cells():
    # B2:C2 is merged ("Mon 12/10" over its Start/End pair) -- both underlying cells should read as
    # the same date once the merge is resolved, not just the top-left one.
    result = parse_roster_xlsx(_build_sample_workbook(), TODAY, window=("13:00", "06:00"))
    kibreab = result.days["2026-10-13"]["Kibreab Fente Bizuneh - 09321"]
    assert kibreab["rstart"] == "15:50"
    assert kibreab["rend"] == "23:55"
