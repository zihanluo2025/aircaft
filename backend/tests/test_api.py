from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.models import Assignment, Flight
from app.services.domain import DEFAULT_ROLES

DAY = "2026-10-13"
Q = {"date": DAY, "shift": "morning"}


def seed_team(client):
    text = "Name,2026-10-13\nAlex K,All day\nPriya S,Early\nTom W,Late\n"
    response = client.post("/api/roster/import", json={"shift": "morning", "text": text})
    assert response.status_code == 200, response.text
    staff = client.get("/api/staff", params={"team": "morning"}).json()
    return {s["name"]: s["id"] for s in staff}


def new_flight(client, number="QF 705", sched="05:50"):
    """Flights only ever come from the provider sync, so there is no create endpoint to hit here -
    go straight to the database, the same way the sync job does, and read the result back through the API."""
    with client.db_session_factory() as db:
        flight = Flight(work_date=date.fromisoformat(DAY), shift="morning", flight_no=number, sched=sched, eta=sched)
        flight.assignments = [Assignment(role=role, position=i) for i, role in enumerate(DEFAULT_ROLES)]
        db.add(flight)
        db.commit()
        flight_id = flight.id
    response = client.get(f"/api/flights/{flight_id}")
    assert response.status_code == 200, response.text
    return response.json()


def test_health_is_public(client):
    assert TestClient(app).get("/api/health").json() == {"status": "ok"}


def test_auth_required(client):
    assert TestClient(app).get("/api/staff").status_code == 401


def test_login_rejects_wrong_password(client):
    response = TestClient(app).post("/api/auth/login", json={"username": "lead", "password": "nope"})
    assert response.status_code == 401


def test_staff_crud(client):
    created = client.post("/api/staff", json={"name": "Sam R", "team": "night", "quals": ["Truck"]})
    assert created.status_code == 201
    staff_id = created.json()["id"]
    assert client.post("/api/staff", json={"name": "Sam R", "team": "night"}).status_code == 409
    assert client.patch(f"/api/staff/{staff_id}", json={"quals": ["Driver", "Truck"]}).json()["quals"] == [
        "Driver",
        "Truck",
    ]
    assert client.get("/api/staff", params={"team": "morning"}).json() == []
    assert len(client.get("/api/staff", params={"team": "night"}).json()) == 1
    assert client.delete(f"/api/staff/{staff_id}").status_code == 204
    assert client.get("/api/staff", params={"team": "night"}).json() == []


def test_import_creates_plan_and_changes_show_in_report(client):
    ids = seed_team(client)
    roster = client.get("/api/roster", params=Q).json()
    assert roster["has_plan"] is True
    assert [e["name"] for e in roster["entries"]] == ["Priya S", "Tom W", "Alex K"]  # early, late, all day

    changed = client.patch(f"/api/roster/{ids['Tom W']}", params=Q, json={"shift_type": "all"})
    assert changed.status_code == 200
    assert changed.json()["entry"]["planned_type"] == "late"

    report = client.get("/api/report", params=Q).json()
    assert report["roster_changes"] == ["Tom W (Late to All day)"]


def test_role_needs_qualification(client):
    ids = seed_team(client)
    url = f"/api/roster/{ids['Alex K']}"
    assert client.patch(url, params=Q, json={"role": "Driver"}).status_code == 400
    client.patch(f"/api/staff/{ids['Alex K']}", json={"quals": ["Driver"]})
    assert client.patch(url, params=Q, json={"role": "Driver"}).json()["entry"]["role"] == "Driver"
    assert client.patch(f"/api/roster/{ids['Priya S']}", params=Q, json={"role": "Toilet"}).status_code == 200


def test_truck_role_does_not_need_the_licence(client):
    # Truck duty also covers just helping load/unload, so unlike Driver, anyone on duty can take it.
    ids = seed_team(client)
    unqualified = client.patch(f"/api/roster/{ids['Priya S']}", params=Q, json={"role": "Truck"})
    assert unqualified.status_code == 200
    assert unqualified.json()["entry"]["role"] == "Truck"


def test_flight_lifecycle(client):
    ids = seed_team(client)
    client.patch(f"/api/staff/{ids['Alex K']}", json={"quals": ["Driver"]})
    client.patch(f"/api/roster/{ids['Alex K']}", params=Q, json={"role": "Driver"})
    flight = new_flight(client)
    assert flight["status"] == "sched"
    assert len(flight["assignments"]) == len(DEFAULT_ROLES)

    # the Driver fixed role counts as crew, so cleaning can start
    started = client.post(f"/api/flights/{flight['id']}/start")
    assert started.status_code == 200
    assert started.json()["status"] == "cleaning"
    assert [c["staff_name"] for c in started.json()["fixed"]] == ["Alex K"]
    assert client.post(f"/api/flights/{flight['id']}/start").status_code == 409

    finished = client.post(f"/api/flights/{flight['id']}/finish").json()
    assert finished["status"] == "done"
    assert finished["minutes"] is not None

    signed = client.put(
        f"/api/flights/{flight['id']}/signature", json={"name": flight["flight_no"], "image": "data:image/png;base64,AAAA"}
    )
    assert signed.status_code == 200
    assert signed.json()["has_signature"] is True

    report = client.get("/api/report", params=Q).json()
    assert report["done"] == 1
    assert report["signed"] == 1
    assert "  Signed\n" in report["summary_text"]


def test_can_start_before_assigning_crew(client):
    # Sometimes the clock starts as soon as people begin working the aircraft, and positions only
    # get filled in afterwards -- starting must not require anyone to already be assigned.
    flight = new_flight(client)
    started = client.post(f"/api/flights/{flight['id']}/start")
    assert started.status_code == 200
    assert started.json()["status"] == "cleaning"
    assert started.json()["fixed"] == []


def test_signature_needs_finished_flight(client):
    flight = new_flight(client)
    response = client.put(
        f"/api/flights/{flight['id']}/signature", json={"name": "Jo", "image": "data:image/png;base64,AAAA"}
    )
    assert response.status_code == 400


def test_cannot_double_book_a_cleaner(client):
    ids = seed_team(client)
    first, second = new_flight(client, "QF 705", "05:50"), new_flight(client, "VA 1252", "06:25")
    job = [{"role": "Vacuum", "staff_id": ids["Priya S"]}]
    assert client.put(f"/api/flights/{first['id']}/assignments", json=job).status_code == 200
    assert client.post(f"/api/flights/{first['id']}/start").status_code == 200
    clash = client.put(f"/api/flights/{second['id']}/assignments", json=job)
    assert clash.status_code == 409
    assert "Priya S" in clash.json()["detail"]


def test_cannot_assign_the_same_person_twice_on_one_flight(client):
    # A race between two quick "+ Add" taps (or a replayed request) should not be able to put the
    # same person in two slots on the one aircraft.
    ids = seed_team(client)
    flight = new_flight(client)
    dupe = client.put(
        f"/api/flights/{flight['id']}/assignments",
        json=[{"role": "Toilet", "staff_id": ids["Priya S"]}, {"role": "Toilet", "staff_id": ids["Priya S"]}],
    )
    assert dupe.status_code == 400
    assert "Priya S" in dupe.json()["detail"]


def test_only_people_on_duty_can_be_assigned(client):
    ids = seed_team(client)
    flight = new_flight(client)
    client.patch(f"/api/roster/{ids['Tom W']}", params=Q, json={"shift_type": None})
    response = client.put(
        f"/api/flights/{flight['id']}/assignments", json=[{"role": "Vacuum", "staff_id": ids["Tom W"]}]
    )
    assert response.status_code == 400


def test_taking_someone_off_clears_their_jobs(client):
    ids = seed_team(client)
    flight = new_flight(client)
    client.put(f"/api/flights/{flight['id']}/assignments", json=[{"role": "Vacuum", "staff_id": ids["Priya S"]}])
    off = client.patch(f"/api/roster/{ids['Priya S']}", params=Q, json={"shift_type": None}).json()
    assert off["unassigned"] == 1
    detail = client.get(f"/api/flights/{flight['id']}").json()
    assert detail["assignments"][0]["staff_id"] is None


def test_call_in_is_tagged_and_reported(client):
    ids = seed_team(client)
    client.patch(f"/api/roster/{ids['Tom W']}", params=Q, json={"shift_type": None})
    back = client.patch(f"/api/roster/{ids['Tom W']}", params=Q, json={"shift_type": "early", "called_in": True})
    assert back.json()["entry"]["called_in_at"] is not None
    assert client.get("/api/report", params=Q).json()["called_in"] == ["Tom W"]


def test_shifts_are_separate(client):
    seed_team(client)
    night = client.get("/api/roster", params={"date": DAY, "shift": "night"}).json()
    assert night["entries"] == []
    assert client.get("/api/staff", params={"team": "night"}).json() == []


def test_roster_import_from_xlsx_file(client):
    from datetime import date as _date, time as _time
    from io import BytesIO

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws["A1"] = "ADL - PM SHIFT - Week ending Sun 18 Oct 2026"
    ws.merge_cells("A1:D1")
    ws["A2"] = "Employee"
    ws["B2"] = _date(2026, 10, 13)
    ws.merge_cells("B2:C2")
    ws["D2"] = "note"
    ws["B3"], ws["C3"] = "Start", "End"
    ws["A4"] = "Alex K"
    ws["B4"], ws["C4"] = _time(15, 50), _time(22, 15)
    ws["D4"] = "Truck driver"
    buf = BytesIO()
    wb.save(buf)

    files = {"file": ("roster.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    preview = client.post("/api/roster/import/preview/file", data={"shift": "morning"}, files=files)
    assert preview.status_code == 200, preview.text
    assert preview.json() == {"days": 1, "people": 1, "new_people": 1, "shifts": 1, "bad": []}

    buf.seek(0)
    files = {"file": ("roster.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    applied = client.post("/api/roster/import/file", data={"shift": "morning"}, files=files)
    assert applied.status_code == 200, applied.text
    assert applied.json() == {"days": 1, "created_staff": 1, "shifts": 1}

    roster = client.get("/api/roster", params={"date": DAY, "shift": "morning"}).json()
    entry = roster["entries"][0]
    assert entry["name"] == "Alex K"
    assert entry["rstart"] == "15:50"
    assert entry["rend"] == "22:15"
    assert sorted(entry["quals"]) == ["Driver", "Truck"]


def test_roster_import_file_rejects_non_xlsx(client):
    files = {"file": ("roster.csv", b"Name,13/10/2026\nAlex K,Early\n", "text/csv")}
    response = client.post("/api/roster/import/preview/file", data={"shift": "morning"}, files=files)
    assert response.status_code == 400


def test_calling_someone_sick_clears_their_jobs_and_tags_them(client):
    ids = seed_team(client)
    flight = new_flight(client)
    client.put(f"/api/flights/{flight['id']}/assignments", json=[{"role": "Vacuum", "staff_id": ids["Priya S"]}])

    sick = client.patch(f"/api/roster/{ids['Priya S']}", params=Q, json={"sick": True})
    assert sick.status_code == 200, sick.text
    body = sick.json()
    assert body["unassigned"] == 1
    assert body["entry"]["sick_at"] is not None
    assert body["entry"]["shift_type"] is None
    detail = client.get(f"/api/flights/{flight['id']}").json()
    assert detail["assignments"][0]["staff_id"] is None

    # giving them a shift again implicitly undoes the sick call
    back = client.patch(f"/api/roster/{ids['Priya S']}", params=Q, json={"shift_type": "early"}).json()
    assert back["entry"]["sick_at"] is None
    assert back["entry"]["shift_type"] == "early"


def test_undo_sick(client):
    ids = seed_team(client)
    client.patch(f"/api/roster/{ids['Priya S']}", params=Q, json={"sick": True})
    undo = client.patch(f"/api/roster/{ids['Priya S']}", params=Q, json={"sick": False}).json()
    assert undo["entry"]["sick_at"] is None


def test_report_only_shows_people_on_this_aircraft_grouped_by_role(client):
    # Driver/Toilet/Truck are day-wide, not per-flight -- the report lists only the "On this
    # aircraft" assignments, one row per role, even after the fixed-role snapshot is taken.
    ids = seed_team(client)
    client.patch(f"/api/staff/{ids['Alex K']}", json={"quals": ["Driver"]})
    client.patch(f"/api/roster/{ids['Alex K']}", params=Q, json={"role": "Driver"})
    flight = new_flight(client)
    with client.db_session_factory() as db:
        db.add_all(
            [
                Assignment(flight_id=flight["id"], role="Toilet", staff_id=ids["Priya S"], position=10),
                Assignment(flight_id=flight["id"], role="Toilet", staff_id=ids["Tom W"], position=11),
            ]
        )
        db.commit()

    client.post(f"/api/flights/{flight['id']}/start")
    row = client.get("/api/report", params=Q).json()["flights"][0]
    assert row["crew_count"] == 2
    assert row["roles"] == [{"role": "Toilet", "names": ["Priya S", "Tom W"]}]


def test_names_are_shown_in_title_case(client):
    # Imported rosters come through in ALL CAPS; the API should hand back names the way a person
    # would write them, without changing what is actually stored.
    text = "Name,2026-10-13\nJOHN O'CONNOR,All day\n"
    client.post("/api/roster/import", json={"shift": "morning", "text": text})
    roster = client.get("/api/roster", params=Q).json()
    assert roster["entries"][0]["name"] == "John O'connor"
    staff = client.get("/api/staff", params={"team": "morning"}).json()
    assert staff[0]["name"] == "John O'connor"


def test_flight_photos_crud(client):
    flight = new_flight(client)

    added = client.post(
        f"/api/flights/{flight['id']}/photos",
        json={"name": "Stain row 12", "image": "data:image/jpeg;base64,AAAA"},
    )
    assert added.status_code == 201, added.text
    photo = added.json()
    assert photo["name"] == "Stain row 12"

    listed = client.get(f"/api/flights/{flight['id']}/photos").json()
    assert len(listed) == 1
    assert listed[0]["id"] == photo["id"]

    renamed = client.patch(f"/api/flights/{flight['id']}/photos/{photo['id']}", json={"name": "Seat 12A stain"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Seat 12A stain"

    bad = client.post(f"/api/flights/{flight['id']}/photos", json={"name": "x", "image": "not-an-image"})
    assert bad.status_code == 400

    removed = client.delete(f"/api/flights/{flight['id']}/photos/{photo['id']}")
    assert removed.status_code == 204
    assert client.get(f"/api/flights/{flight['id']}/photos").json() == []


def test_flight_photos_are_deleted_with_the_flight(client):
    flight = new_flight(client)
    client.post(f"/api/flights/{flight['id']}/photos", json={"name": "", "image": "data:image/jpeg;base64,AAAA"})
    assert client.delete(f"/api/flights/{flight['id']}").status_code == 204
    # the flight is gone, so its photo endpoint 404s rather than returning orphaned rows
    assert client.get(f"/api/flights/{flight['id']}/photos").status_code == 404


def test_report_export_is_a_real_xlsx(client):
    from openpyxl import load_workbook
    from io import BytesIO

    ids = seed_team(client)
    client.patch(f"/api/staff/{ids['Alex K']}", json={"quals": ["Driver"]})
    client.patch(f"/api/roster/{ids['Alex K']}", params=Q, json={"role": "Driver"})
    flight = new_flight(client)
    client.post(f"/api/flights/{flight['id']}/start")
    client.post(f"/api/flights/{flight['id']}/finish")

    response = client.get("/api/report/export", params=Q)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "turnaround-2026-10-13-morning.xlsx" in response.headers["content-disposition"]

    wb = load_workbook(BytesIO(response.content))
    assert wb.sheetnames == ["Summary", "Flights", "Per person"]
    flights_rows = list(wb["Flights"].iter_rows(values_only=True))
    assert flights_rows[0] == ("Flight", "ETA", "Status", "Minutes", "Staff", "Signed", "Crew")
    assert flights_rows[1][0] == "QF 705"
    assert flights_rows[1][2] == "done"


def test_reimport_replaces_previous_roster(client):
    old = "Name,2026-10-13,2026-10-14\nAlex K,All day,Early\nPriya S,Early,Late\n"
    client.post("/api/roster/import", json={"shift": "morning", "text": old})
    flight = new_flight(client)
    priya = next(s["id"] for s in client.get("/api/staff", params={"team": "morning"}).json() if s["name"] == "Priya S")
    with client.db_session_factory() as db:
        db.query(Assignment).filter_by(flight_id=flight["id"], position=0).one().staff_id = priya
        db.commit()

    new = "Name,2026-10-13\nAlex K,Late\nTom W,Early\n"
    assert client.post("/api/roster/import", json={"shift": "morning", "text": new}).status_code == 200

    roster = client.get("/api/roster", params=Q).json()
    assert {(e["name"], e["shift_type"]) for e in roster["entries"]} == {("Alex K", "late"), ("Tom W", "early")}
    # 新文件不再包含的日期也被清空
    assert client.get("/api/roster", params={"date": "2026-10-14", "shift": "morning"}).json()["entries"] == []
    # 不在新名单里的人不再出现在员工列表里，也从未开始的航班上撤下
    assert {s["name"] for s in client.get("/api/staff", params={"team": "morning"}).json()} == {"Alex K", "Tom W"}
    assert client.get(f"/api/flights/{flight['id']}").json()["assignments"][0]["staff_id"] is None
