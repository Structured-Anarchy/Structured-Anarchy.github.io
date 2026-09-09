"""Resolve private per-session metadata for the encrypted presentation graph."""

from __future__ import annotations

from datetime import date, datetime
import re
import tomllib
from typing import Any, Callable


def with_session_metadata(kb: dict[str, Any], read_file: Callable[[str], bytes]) -> dict[str, Any]:
    """Keep authoring content intact; the referenced TOML owns display metadata.

    Older archives without metadata references retain their existing titles.
    Missing or malformed referenced metadata is an error, never a silent fallback.
    """
    sessions = []
    for original in kb.get("sessions", []):
        session = dict(original)
        name = session.get("metadata_file")
        if name is not None:
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", session["id"]) or name != f"data/knowledge/sessions/{session['id']}.toml":
                raise ValueError("session metadata must use data/knowledge/sessions/<session-id>.toml")
            metadata = tomllib.loads(read_file(name).decode("utf-8"))
            if set(metadata) != {"date", "location"}:
                raise ValueError("session metadata requires exactly date and location")
            day = metadata["date"]
            if isinstance(day, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                day = date.fromisoformat(day)
            if not isinstance(day, date) or isinstance(day, datetime):
                raise ValueError("session date must be a YYYY-MM-DD date")
            location = metadata["location"]
            if not isinstance(location, str) or not location.strip():
                raise ValueError("session location must be a nonempty string")
            session.update(date=day.isoformat(), location=location.strip(),
                           title=f"{day.day} {day.strftime('%B %Y')} · {location.strip()}")
        sessions.append(session)
    labels = {source_id: session["title"] for session in sessions if "metadata_file" in session
              for source_id in session["source_ids"]}
    sources = [{**source, "label": labels.get(source["id"], source["label"])} for source in kb.get("sources", [])]
    return {**kb, "sessions": sessions, **({"sources": sources} if "sources" in kb else {})}
