from app.services.summary import build_summary_text


def test_summary_text():
    text = build_summary_text(
        date_str="2026-10-13",
        shift_name="Morning",
        done=1,
        active_total=2,
        average_minutes=38,
        signed=1,
        called_in=["Ben T"],
        changes=["Tom W (Early to All day)"],
        flights=[
            {
                "flight_no": "QF 705",
                "eta": "05:50",
                "status_label": "Done",
                "minutes": 38,
                "crew": ["Alex K (Driver)", "Mei L (Business)"],
                "signed_by": "Jo",
                "notes": "Spill row 12",
            },
            {"flight_no": "VA 1252", "eta": "06:40", "status_label": "Scheduled", "minutes": None, "crew": [], "signed_by": "", "notes": ""},
        ],
    )
    lines = text.splitlines()
    assert lines[0] == "Turnaround summary 2026-10-13, Morning shift"
    assert "Flights done: 1 of 2" in lines
    assert "Called in: Ben T" in lines
    assert "Roster changes: Tom W (Early to All day)" in lines
    assert "QF 705 | ETA 05:50 | Done | 38 min" in lines
    assert "  Crew: Alex K (Driver), Mei L (Business)" in lines
    assert "  Signed" in lines
    assert "  Notes: Spill row 12" in lines
    assert "VA 1252 | ETA 06:40 | Scheduled" in lines
    assert "  Crew: no crew recorded" in lines
    assert "  Not signed" in lines


def test_summary_none_values():
    text = build_summary_text(
        date_str="2026-10-13", shift_name="Night", done=0, active_total=0, average_minutes=0,
        signed=0, called_in=[], changes=[], flights=[],
    )
    assert "Called in: none" in text
    assert "Roster changes: none" in text
