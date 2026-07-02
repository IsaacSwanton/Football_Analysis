from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests
from requests import RequestException

from football_analyst.config import Settings
from football_analyst.graph import GraphClient
from football_analyst.schema import apply_schema
from football_analyst.sources.statsbomb import load_events, normalise_events, slug


def ingest_worldcup_fixtures_from_football_data(graph: GraphClient, settings: Settings, season: int = 2026) -> int:
    if not settings.football_data_api_key:
        raise RuntimeError("Set FOOTBALL_DATA_API_KEY in .env before using football-data.org ingestion.")

    verify: bool | str = settings.football_data_verify_ssl
    if settings.football_data_ca_bundle:
        verify = settings.football_data_ca_bundle

    try:
        response = requests.get(
            f"{settings.football_data_base_url}/competitions/WC/matches",
            headers={"X-Auth-Token": settings.football_data_api_key},
            params={"season": season},
            timeout=30,
            verify=verify,
        )
        response.raise_for_status()
    except requests.exceptions.SSLError as exc:
        raise RuntimeError(
            "Football-Data.org could not be reached because SSL certificate verification failed. "
            "If you are behind a corporate proxy, set FOOTBALL_DATA_CA_BUNDLE in .env to your "
            "company root CA certificate file. For a temporary local test only, you can set "
            "FOOTBALL_DATA_VERIFY_SSL=false."
        ) from exc
    except RequestException as exc:
        raise RuntimeError(f"Football-Data.org request failed: {exc}") from exc
    payload = response.json()
    matches = payload.get("matches", [])

    graph.execute(
        """
MERGE (c:Competition {id: 'WC'})
SET c.name = 'FIFA World Cup'
MERGE (s:Season {id: $season_id})
SET s.year = $season
MERGE (c)-[:HAS_SEASON]->(s)
""",
        {"season_id": f"WC-{season}", "season": season},
    )

    for match in matches:
        match_id = f"football-data-{match['id']}"
        home = match["homeTeam"]
        away = match["awayTeam"]
        graph.execute(
            """
MATCH (s:Season {id: $season_id})
MERGE (m:Match {id: $match_id})
SET m.utc_date = $utc_date,
    m.status = $status,
    m.stage = $stage,
    m.matchday = $matchday
MERGE (s)-[:HAS_MATCH]->(m)
MERGE (home:Team {id: $home_id})
SET home.name = $home_name
MERGE (away:Team {id: $away_id})
SET away.name = $away_name
MERGE (home)-[:PLAYED_IN {side: 'home'}]->(m)
MERGE (away)-[:PLAYED_IN {side: 'away'}]->(m)
""",
            {
                "season_id": f"WC-{season}",
                "match_id": match_id,
                "utc_date": match.get("utcDate"),
                "status": match.get("status"),
                "stage": match.get("stage"),
                "matchday": match.get("matchday"),
                "home_id": f"football-data-team-{home['id']}",
                "home_name": home.get("name"),
                "away_id": f"football-data-team-{away['id']}",
                "away_name": away.get("name"),
            },
        )
    return len(matches)


def ingest_statsbomb_file(
    graph: GraphClient,
    events_path: Path,
    match_id: str,
    home_team: str,
    away_team: str,
    competition: str = "FIFA World Cup",
    season: str = "2026",
) -> int:
    raw_events = load_events(events_path)
    home_team_id = _team_id_from_events(raw_events, home_team)
    away_team_id = _team_id_from_events(raw_events, away_team)
    teams = [
        {"team_id": home_team_id, "team_name": home_team},
        {"team_id": away_team_id, "team_name": away_team},
    ]
    events = normalise_events(raw_events, match_id, teams)
    _upsert_match(
        graph,
        match_id,
        home_team,
        away_team,
        competition,
        season,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
    )
    _upsert_events(graph, events)
    return len(events)


def ingest_statsbomb_events(
    graph: GraphClient,
    raw_events: list[dict[str, Any]],
    match_id: str,
    home_team: str,
    away_team: str,
    competition: str = "FIFA World Cup",
    season: str = "2026",
) -> int:
    home_team_id = _team_id_from_events(raw_events, home_team)
    away_team_id = _team_id_from_events(raw_events, away_team)
    teams = [
        {"team_id": home_team_id, "team_name": home_team},
        {"team_id": away_team_id, "team_name": away_team},
    ]
    events = normalise_events(raw_events, match_id, teams)
    _upsert_match(
        graph,
        match_id,
        home_team,
        away_team,
        competition,
        season,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
    )
    _upsert_events(graph, events)
    return len(events)


def ingest_statsbomb_open_match(graph: GraphClient, match: dict[str, Any], raw_events: list[dict[str, Any]]) -> int:
    home_team = (match.get("home_team") or {}).get("home_team_name", "Unknown")
    away_team = (match.get("away_team") or {}).get("away_team_name", "Unknown")
    competition = (match.get("competition") or {}).get("competition_name", "StatsBomb Open Data")
    season = (match.get("season") or {}).get("season_name", "")
    return ingest_statsbomb_events(
        graph=graph,
        raw_events=raw_events,
        match_id=str(match["match_id"]),
        home_team=home_team,
        away_team=away_team,
        competition=competition,
        season=season,
    )


def ingest_sample(graph: GraphClient, sample_path: Path) -> int:
    with sample_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    meta = payload["match"]
    raw_events = payload["events"]
    temp_events = sample_path.parent / "_sample_events.tmp.json"
    temp_events.write_text(json.dumps(raw_events), encoding="utf-8")
    try:
        return ingest_statsbomb_file(
            graph=graph,
            events_path=temp_events,
            match_id=meta["id"],
            home_team=meta["home_team"],
            away_team=meta["away_team"],
            competition=meta.get("competition", "FIFA World Cup"),
            season=str(meta.get("season", "2026")),
        )
    finally:
        temp_events.unlink(missing_ok=True)


def bootstrap(graph: GraphClient) -> None:
    graph.verify()
    apply_schema(graph)


def _upsert_match(
    graph: GraphClient,
    match_id: str,
    home_team: str,
    away_team: str,
    competition: str,
    season: str,
    home_team_id: str | None = None,
    away_team_id: str | None = None,
) -> None:
    graph.execute(
        """
MERGE (c:Competition {id: $competition_id})
SET c.name = $competition
MERGE (s:Season {id: $season_id})
SET s.year = $season
MERGE (c)-[:HAS_SEASON]->(s)
MERGE (m:Match {id: $match_id})
SET m.name = $home_team + ' vs ' + $away_team
MERGE (s)-[:HAS_MATCH]->(m)
MERGE (home:Team {id: $home_id})
SET home.name = $home_team
MERGE (away:Team {id: $away_id})
SET away.name = $away_team
MERGE (home)-[:PLAYED_IN {side: 'home'}]->(m)
MERGE (away)-[:PLAYED_IN {side: 'away'}]->(m)
""",
        {
            "competition_id": slug(competition),
            "competition": competition,
            "season_id": f"{slug(competition)}-{season}",
            "season": season,
            "match_id": match_id,
            "home_id": home_team_id or slug(home_team),
            "home_team": home_team,
            "away_id": away_team_id or slug(away_team),
            "away_team": away_team,
        },
    )


def _team_id_from_events(events: list[dict[str, Any]], team_name: str) -> str:
    for event in events:
        team = event.get("team")
        if isinstance(team, dict) and team.get("name") == team_name:
            if team.get("id") is not None:
                return str(team["id"])
            return slug(team_name)
    return slug(team_name)


def _upsert_events(graph: GraphClient, events: list[dict[str, Any]]) -> None:
    match_ids = sorted({event["match_id"] for event in events})
    for start in range(0, len(events), 500):
        _upsert_event_batch(graph, events[start : start + 500])
    _link_next_events(graph, match_ids)


def _upsert_event_batch(graph: GraphClient, events: list[dict[str, Any]]) -> None:
    compact_events = [{key: value for key, value in event.items() if key != "raw"} for event in events]
    graph.execute(
        """
UNWIND $events AS event
MATCH (m:Match {id: event.match_id})
MATCH (team:Team {id: event.team_id})
OPTIONAL MATCH (opponent:Team {id: event.opponent_team_id})
MERGE (e:Event {id: event.event_id})
SET e.match_id = event.match_id,
    e.index = event.index,
    e.period = event.period,
    e.timestamp = event.timestamp,
    e.minute = event.minute,
    e.second = event.second,
    e.type = event.type,
    e.possession = event.possession,
    e.x = event.x,
    e.y = event.y,
    e.end_x = event.end_x,
    e.end_y = event.end_y,
    e.xg = event.xg,
    e.outcome = event.outcome
MERGE (m)-[:HAS_EVENT]->(e)
MERGE (e)-[:FOR_TEAM]->(team)
FOREACH (_ IN CASE WHEN opponent IS NULL THEN [] ELSE [1] END |
  MERGE (e)-[:AGAINST_TEAM]->(opponent)
)
FOREACH (_ IN CASE WHEN event.player_id IS NULL THEN [] ELSE [1] END |
  MERGE (player:Player {id: event.player_id})
  SET player.name = event.player_name
  MERGE (e)-[:PERFORMED_BY]->(player)
)
FOREACH (_ IN CASE WHEN event.recipient_id IS NULL THEN [] ELSE [1] END |
  MERGE (receiver:Player {id: event.recipient_id})
  SET receiver.name = event.recipient_name
  MERGE (e)-[:RECEIVED_BY]->(receiver)
)
""",
        {"events": compact_events},
    )


def _link_next_events(graph: GraphClient, match_ids: list[str]) -> None:
    graph.execute(
        """
MATCH (m:Match)-[:HAS_EVENT]->(a:Event)
MATCH (m)-[:HAS_EVENT]->(b:Event)
WHERE a.match_id IN $match_ids
  AND a.match_id = b.match_id
  AND b.index = a.index + 1
MERGE (a)-[:NEXT]->(b)
""",
        {"match_ids": match_ids},
    )
