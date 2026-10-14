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
    assert add_missing_columns(engine) == ["roster_entries.rstart", "roster_entries.rend"]
    assert {"rstart", "rend"} <= {c["name"] for c in inspect(engine).get_columns("roster_entries")}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT rstart, rend FROM roster_entries")).one() == ("", "")
    assert add_missing_columns(engine) == []
