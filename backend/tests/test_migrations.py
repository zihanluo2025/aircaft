from sqlalchemy import create_engine, inspect, text

from app.migrations import add_missing_columns


def test_adds_new_flight_columns_to_an_old_database():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE flights (id INTEGER PRIMARY KEY, flight_no VARCHAR(20))"))
        conn.execute(text("INSERT INTO flights (flight_no) VALUES ('QF 1')"))
    assert add_missing_columns(engine) == ["flights.origin", "flights.international"]
    assert {"origin", "international"} <= {c["name"] for c in inspect(engine).get_columns("flights")}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT origin, international FROM flights")).one() == ("", 0)
    assert add_missing_columns(engine) == []  # running again changes nothing


def test_does_nothing_on_a_fresh_database():
    engine = create_engine("sqlite://")
    assert add_missing_columns(engine) == []


def test_adds_new_roster_entry_columns_to_an_old_database():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE roster_entries (id INTEGER PRIMARY KEY, staff_id INTEGER)"))
        conn.execute(text("INSERT INTO roster_entries (staff_id) VALUES (1)"))
    assert add_missing_columns(engine) == [
        "roster_entries.rstart",
        "roster_entries.rend",
        "roster_entries.sick_at",
        "roster_entries.planned_rstart",
        "roster_entries.planned_rend",
    ]
    assert {"rstart", "rend", "sick_at"} <= {c["name"] for c in inspect(engine).get_columns("roster_entries")}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT rstart, rend, sick_at FROM roster_entries")).one() == ("", "", None)
    assert add_missing_columns(engine) == []


def test_nullable_column_gets_no_forced_default():
    # sick_at uses the "NULL" sentinel: nullable, no default, unlike the NOT NULL DEFAULT '' columns.
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE roster_entries (id INTEGER PRIMARY KEY, staff_id INTEGER)"))
    add_missing_columns(engine)
    sick_at = next(c for c in inspect(engine).get_columns("roster_entries") if c["name"] == "sick_at")
    assert sick_at["nullable"] is True
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO roster_entries (staff_id) VALUES (1)"))
        assert conn.execute(text("SELECT sick_at FROM roster_entries")).one() == (None,)


def test_planned_times_are_backfilled_from_todays_times():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE roster_entries (id INTEGER PRIMARY KEY, staff_id INTEGER, planned_type VARCHAR(10),"
                " rstart VARCHAR(5) NOT NULL DEFAULT '', rend VARCHAR(5) NOT NULL DEFAULT '')"
            )
        )
        conn.execute(text("INSERT INTO roster_entries (staff_id, planned_type, rstart, rend) VALUES (1, 'early', '15:45', '22:15')"))
        conn.execute(text("INSERT INTO roster_entries (staff_id, planned_type, rstart, rend) VALUES (2, NULL, '17:10', '23:55')"))
    add_missing_columns(engine)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT planned_rstart, planned_rend FROM roster_entries ORDER BY staff_id")).all()
    assert rows == [("15:45", "22:15"), ("", "")]  # a call-in (no plan) gets no planned times
