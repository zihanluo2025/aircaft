"""Tiny schema upgrade for databases created before a column existed.

`create_all` makes missing tables but never adds columns to existing ones, so older databases get them here.
Switch to Alembic when the schema starts changing often.
"""
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# table -> [(column, sql type, default for existing rows)]
# default=None means "boolean-ish, use the dialect's false literal"; default="NULL" (the literal
# string) means a genuinely nullable column with no default, like a timestamp that may never happen.
_NEW_COLUMNS = {
    "flights": [
        ("origin", "VARCHAR(10)", "''"),
        ("international", "BOOLEAN", None),  # boolean default depends on the database
    ],
    "roster_entries": [
        ("rstart", "VARCHAR(5)", "''"),
        ("rend", "VARCHAR(5)", "''"),
        ("sick_at", "DATETIME", "NULL"),
        ("planned_rstart", "VARCHAR(5)", "''"),
        ("planned_rend", "VARCHAR(5)", "''"),
    ],
}

# Run once, right after the column is added: existing planned rows take today's times as their plan
# (the best guess available -- the original import isn't stored anywhere else).
_BACKFILL = {
    "roster_entries.planned_rstart": "UPDATE roster_entries SET planned_rstart = rstart WHERE planned_type IS NOT NULL",
    "roster_entries.planned_rend": "UPDATE roster_entries SET planned_rend = rend WHERE planned_type IS NOT NULL",
}


def add_missing_columns(engine: Engine) -> list[str]:
    added: list[str] = []
    inspector = inspect(engine)
    false_literal = "0" if engine.dialect.name == "sqlite" else "FALSE"
    with engine.begin() as conn:
        for table, columns in _NEW_COLUMNS.items():
            if not inspector.has_table(table):
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, sql_type, default in columns:
                if name in existing:
                    continue
                if default == "NULL":
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))
                else:
                    resolved = default if default is not None else false_literal
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type} NOT NULL DEFAULT {resolved}"))
                added.append(f"{table}.{name}")
                existing.add(name)
                backfill = _BACKFILL.get(f"{table}.{name}")
                if backfill and {"rstart", "rend", "planned_type"} <= existing:
                    conn.execute(text(backfill))
    return added
