"""Build the plain text summary the leading hand copies at the end of a shift."""
from __future__ import annotations


def build_summary_text(
    *,
    date_str: str,
    shift_name: str,
    done: int,
    active_total: int,
    average_minutes: int,
    signed: int,
    called_in: list[str],
    changes: list[str],
    flights: list[dict],
) -> str:
    lines = [
        f"Turnaround summary {date_str}, {shift_name} shift",
        f"Flights done: {done} of {active_total}",
        f"Average time: {average_minutes} min",
        f"Signed by cabin crew: {signed}",
        f"Called in: {', '.join(called_in) if called_in else 'none'}",
        f"Roster changes: {', '.join(changes) if changes else 'none'}",
        "",
    ]
    for f in flights:
        head = f"{f['flight_no'] or 'No number'} | ETA {f['eta'] or '--'} | {f['status_label']}"
        if f.get("minutes") is not None:
            head += f" | {f['minutes']} min"
        lines.append(head)
        lines.append(f"  Crew: {', '.join(f['crew']) if f['crew'] else 'no crew recorded'}")
        lines.append(f"  {'Signed' if f.get('signed_by') else 'Not signed'}")
        if f.get("notes"):
            lines.append(f"  Notes: {f['notes']}")
    return "\n".join(lines) + "\n"
