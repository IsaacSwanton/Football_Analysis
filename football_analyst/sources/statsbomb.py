from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def load_events(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON list of event objects")
    return data


def xy(location: list[float] | None) -> tuple[float | None, float | None]:
    if not location:
        return None, None
    return float(location[0]), float(location[1])


def event_type(event: dict[str, Any]) -> str:
    value = event.get("type")
    if isinstance(value, dict):
        return str(value.get("name", "Unknown"))
    return str(value or "Unknown")


def nested_name(event: dict[str, Any], key: str) -> str | None:
    value = event.get(key)
    if isinstance(value, dict):
        return value.get("name")
    return None


def nested_id(event: dict[str, Any], key: str, fallback: str) -> str:
    value = event.get(key)
    if isinstance(value, dict) and value.get("id") is not None:
        return str(value["id"])
    if isinstance(value, dict) and value.get("name"):
        return slug(value["name"])
    return fallback


def slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")


def normalise_event(raw: dict[str, Any], match_id: str, opponent_by_team: dict[str, str]) -> dict[str, Any]:
    kind = event_type(raw)
    team_name = nested_name(raw, "team") or "Unknown"
    team_id = nested_id(raw, "team", slug(team_name))
    player_name = nested_name(raw, "player")
    player_id = nested_id(raw, "player", slug(player_name or f"unknown-{raw.get('id', '')}"))
    x, y = xy(raw.get("location"))

    pass_data = raw.get("pass") if isinstance(raw.get("pass"), dict) else {}
    shot_data = raw.get("shot") if isinstance(raw.get("shot"), dict) else {}
    carry_data = raw.get("carry") if isinstance(raw.get("carry"), dict) else {}

    end_location = pass_data.get("end_location") or carry_data.get("end_location")
    end_x, end_y = xy(end_location)

    recipient = pass_data.get("recipient") if isinstance(pass_data.get("recipient"), dict) else None
    outcome = (
        (pass_data.get("outcome") or {}).get("name")
        or (shot_data.get("outcome") or {}).get("name")
        or raw.get("outcome")
    )

    return {
        "event_id": str(raw.get("id")),
        "match_id": str(match_id),
        "index": int(raw.get("index", 0)),
        "period": int(raw.get("period", 0)),
        "timestamp": raw.get("timestamp"),
        "minute": int(raw.get("minute", 0)),
        "second": int(raw.get("second", 0)),
        "type": kind,
        "possession": int(raw.get("possession", 0)),
        "team_id": team_id,
        "team_name": team_name,
        "opponent_team_id": opponent_by_team.get(team_id),
        "player_id": player_id if player_name else None,
        "player_name": player_name,
        "recipient_id": str(recipient.get("id")) if recipient and recipient.get("id") is not None else None,
        "recipient_name": recipient.get("name") if recipient else None,
        "x": x,
        "y": y,
        "end_x": end_x,
        "end_y": end_y,
        "xg": float(shot_data.get("statsbomb_xg", 0.0)) if kind == "Shot" else None,
        "outcome": outcome,
        "raw": raw,
    }


def normalise_events(
    raw_events: Iterable[dict[str, Any]],
    match_id: str,
    teams: list[dict[str, str]],
) -> list[dict[str, Any]]:
    ids = [team["team_id"] for team in teams]
    opponent_by_team = {ids[0]: ids[1], ids[1]: ids[0]} if len(ids) == 2 else {}
    events = [normalise_event(event, match_id, opponent_by_team) for event in raw_events]
    return sorted(events, key=lambda item: item["index"])
