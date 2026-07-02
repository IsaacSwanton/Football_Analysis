from __future__ import annotations

import html
import json
import math
from pathlib import Path
from typing import Any

from football_analyst.graph import GraphClient
from football_analyst.queries import get_curated_query


def generate_visuals(
    graph: GraphClient,
    output_dir: Path,
    analysis_team: str = "England",
    opponent_team: str = "Mexico",
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    combos = graph.execute(
        get_curated_query("matchup_winning_combos") or "",
        {
            "analysis_team": analysis_team,
            "opponent_team": opponent_team,
            "min_xg": 0.05,
            "limit": 24,
        },
    )
    vulnerabilities = graph.execute(
        get_curated_query("opponent_vulnerabilities") or "",
        {
            "opponent_team": opponent_team,
            "min_xg": 0.01,
            "examples": 8,
            "limit": 12,
        },
    )
    shots = graph.execute(
        """
MATCH (shot:Event {type: 'Shot'})-[:FOR_TEAM]->(team:Team)
WHERE team.name IN [$analysis_team, $opponent_team]
OPTIONAL MATCH (shot)-[:PERFORMED_BY]->(player:Player)
RETURN team.name AS team,
       shot.match_id AS match_id,
       shot.minute AS minute,
       player.name AS player,
       shot.xg AS xg,
       shot.x AS x,
       shot.y AS y,
       shot.outcome AS outcome
ORDER BY team, shot.match_id, shot.minute
LIMIT 600
""".strip(),
        {"analysis_team": analysis_team, "opponent_team": opponent_team},
    )
    heat = graph.execute(
        """
MATCH (defending:Team {name: $opponent_team})<-[:AGAINST_TEAM]-(shot:Event {type: 'Shot'})
MATCH (shot)-[:FOR_TEAM]->(attacking:Team)
OPTIONAL MATCH (shot)-[:PERFORMED_BY]->(player:Player)
WITH floor(coalesce(shot.x, 0) / 10) AS x_bin,
     floor(coalesce(shot.y, 0) / 10) AS y_bin,
     count(*) AS shots,
     sum(coalesce(shot.xg, 0.0)) AS total_xg,
     collect({
       attacking_team: attacking.name,
       player: player.name,
       minute: shot.minute,
       xg: shot.xg
     })[0..4] AS examples
RETURN x_bin, y_bin, shots, round(total_xg * 100.0) / 100.0 AS total_xg, examples
ORDER BY total_xg DESC
""".strip(),
        {"opponent_team": opponent_team},
    )
    event_patterns = _build_event_patterns(combos, vulnerabilities)
    overview = {
        "counts": graph.execute(
            """
MATCH (n)
RETURN labels(n)[0] AS label, count(*) AS count
ORDER BY label
""".strip()
        ),
        "relationships": graph.execute(
            """
MATCH (a)-[r]->(b)
RETURN labels(a)[0] AS source, type(r) AS relationship, labels(b)[0] AS target, count(*) AS count
ORDER BY source, relationship, target
""".strip()
        ),
    }

    files = [
        _write_json(output_dir / "matchup-data.json", combos, vulnerabilities, overview, shots, heat, event_patterns),
        _write_pitch_map(output_dir / "pitch-map.html", combos, analysis_team, opponent_team),
        _write_event_patterns(output_dir / "event-patterns.html", event_patterns, analysis_team, opponent_team),
        _write_shot_map(output_dir / "shot-map.html", shots, analysis_team, opponent_team),
        _write_heat_map(output_dir / "mexico-vulnerability-heatmap.html", heat, opponent_team),
        _write_chance_network(output_dir / "england-chance-network.html", combos, analysis_team),
        _write_player_combinations(output_dir / "player-combinations.html", combos, analysis_team, opponent_team),
        _write_vulnerabilities(output_dir / "vulnerabilities.html", vulnerabilities, opponent_team),
        _write_graph_overview(output_dir / "graph-overview.html", overview),
    ]
    return files


def _write_json(
    path: Path,
    combos: list[dict[str, Any]],
    vulnerabilities: list[dict[str, Any]],
    overview: dict[str, Any],
    shots: list[dict[str, Any]] | None = None,
    heat: list[dict[str, Any]] | None = None,
    event_patterns: list[dict[str, Any]] | None = None,
) -> Path:
    path.write_text(
        json.dumps(
            {
                "combos": combos,
                "vulnerabilities": vulnerabilities,
                "overview": overview,
                "shots": shots or [],
                "heat": heat or [],
                "event_patterns": event_patterns or [],
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return path


def _write_pitch_map(path: Path, rows: list[dict[str, Any]], analysis_team: str, opponent_team: str) -> Path:
    sequences = [_sequence_svg(row, idx) for idx, row in enumerate(rows[:12])]
    cards = "\n".join(_combo_card(row) for row in rows[:12]) or "<p>No high-value sequences found yet.</p>"
    body = f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_e(analysis_team)} vs {_e(opponent_team)} Pitch Map</title>
  <style>{CSS}</style>
</head>
<body>
  <main class="page">
    <header>
      <p class="eyebrow">Matchup Evidence</p>
      <h1>{_e(analysis_team)} attacking combos and {_e(opponent_team)} conceded patterns</h1>
    </header>
    <section class="layout">
      <div>
        <svg class="pitch" viewBox="0 0 1200 800" role="img" aria-label="Pitch map">
          <rect x="0" y="0" width="1200" height="800" rx="14" class="grass" />
          <line x1="600" y1="0" x2="600" y2="800" class="line" />
          <circle cx="600" cy="400" r="92" class="line-fill" />
          <rect x="0" y="176" width="180" height="448" class="box" />
          <rect x="1020" y="176" width="180" height="448" class="box" />
          <rect x="0" y="296" width="60" height="208" class="box" />
          <rect x="1140" y="296" width="60" height="208" class="box" />
          {''.join(sequences)}
        </svg>
      </div>
      <aside class="panel">
        <h2>Sequence Evidence</h2>
        {cards}
      </aside>
    </section>
  </main>
</body>
</html>
"""
    path.write_text(body, encoding="utf-8")
    return path


def _write_event_patterns(path: Path, rows: list[dict[str, Any]], analysis_team: str, opponent_team: str) -> Path:
    cards = "\n".join(
        f"""
        <article class="card">
          <p class="tag">{_e(row['category'])}</p>
          <h3>{_e(row['pattern'])}</h3>
          <p>{row['count']} sequences | total xG {_fmt(row['total_xg'])} | avg xG {_fmt(row['avg_xg'])}</p>
          <small>{_e(row['detail'])}</small>
        </article>
        """
        for row in rows
    ) or "<p>No event patterns found.</p>"
    body = f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Event Pattern Analysis</title>
  <style>{CSS}</style>
</head>
<body>
  <main class="page">
    <header>
      <p class="eyebrow">Event Driven Analysis</p>
      <h1>{_e(analysis_team)} routes and {_e(opponent_team)} vulnerabilities by event archetype</h1>
    </header>
    <section class="panel pattern-grid">
      {cards}
    </section>
  </main>
</body>
</html>
"""
    path.write_text(body, encoding="utf-8")
    return path


def _write_shot_map(path: Path, rows: list[dict[str, Any]], analysis_team: str, opponent_team: str) -> Path:
    dots = "\n".join(_shot_dot(row, analysis_team, opponent_team) for row in rows if row.get("x") is not None and row.get("y") is not None)
    table_rows = "\n".join(
        f"""
        <tr>
          <td>{_e(row.get("team"))}</td>
          <td>{_e(row.get("player"))}</td>
          <td>{row.get("minute", "?")}</td>
          <td>{_fmt(row.get("xg"))}</td>
          <td>{_e(row.get("outcome"))}</td>
        </tr>
        """
        for row in sorted(rows, key=lambda item: float(item.get("xg") or 0), reverse=True)[:20]
    ) or '<tr><td colspan="5">No shots found.</td></tr>'
    body = f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Shot Map</title>
  <style>{CSS}</style>
</head>
<body>
  <main class="page">
    <header>
      <p class="eyebrow">Shot Map</p>
      <h1>{_e(analysis_team)} and {_e(opponent_team)} shot locations</h1>
    </header>
    <section class="layout">
      <div>
        {_pitch_svg(dots)}
        <div class="legend">
          <span><i class="key england"></i>{_e(analysis_team)}</span>
          <span><i class="key mexico"></i>{_e(opponent_team)}</span>
        </div>
      </div>
      <aside class="panel">
        <h2>Highest xG shots</h2>
        <table>
          <thead><tr><th>Team</th><th>Player</th><th>Min</th><th>xG</th><th>Outcome</th></tr></thead>
          <tbody>{table_rows}</tbody>
        </table>
      </aside>
    </section>
  </main>
</body>
</html>
"""
    path.write_text(body, encoding="utf-8")
    return path


def _write_heat_map(path: Path, rows: list[dict[str, Any]], opponent_team: str) -> Path:
    max_xg = max([float(row.get("total_xg") or 0) for row in rows] or [1.0])
    cells = "\n".join(_heat_cell(row, max_xg) for row in rows)
    top_rows = "\n".join(
        f"""
        <tr>
          <td>{int(row.get("x_bin", 0) or 0) * 10}-{int(row.get("x_bin", 0) or 0) * 10 + 10}</td>
          <td>{int(row.get("y_bin", 0) or 0) * 10}-{int(row.get("y_bin", 0) or 0) * 10 + 10}</td>
          <td>{row.get("shots", 0)}</td>
          <td>{_fmt(row.get("total_xg"))}</td>
          <td>{_examples(row.get("examples", []))}</td>
        </tr>
        """
        for row in rows[:12]
    ) or '<tr><td colspan="5">No conceded shots found.</td></tr>'
    body = f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_e(opponent_team)} Vulnerability Heat Map</title>
  <style>{CSS}</style>
</head>
<body>
  <main class="page">
    <header>
      <p class="eyebrow">Vulnerability Heat Map</p>
      <h1>Shot value conceded by {_e(opponent_team)}</h1>
    </header>
    <section class="layout">
      <div>{_pitch_svg(cells)}</div>
      <aside class="panel">
        <h2>Highest value zones</h2>
        <table>
          <thead><tr><th>X</th><th>Y</th><th>Shots</th><th>xG</th><th>Examples</th></tr></thead>
          <tbody>{top_rows}</tbody>
        </table>
      </aside>
    </section>
  </main>
</body>
</html>
"""
    path.write_text(body, encoding="utf-8")
    return path


def _write_chance_network(path: Path, rows: list[dict[str, Any]], analysis_team: str) -> Path:
    england_rows = [row for row in rows if row.get("category") == "england_attacking_combo"]
    edges = _combination_edges(england_rows)
    nodes = _network_nodes(edges)
    svg = _network_svg(nodes, edges)
    table_rows = "\n".join(
        f"""
        <tr>
          <td>{_e(edge['source'])}</td>
          <td>{_e(edge['target'])}</td>
          <td>{edge['count']}</td>
          <td>{_fmt(edge['total_xg'])}</td>
        </tr>
        """
        for edge in sorted(edges.values(), key=lambda item: (item["total_xg"], item["count"]), reverse=True)[:20]
    ) or '<tr><td colspan="4">No player links found.</td></tr>'
    body = f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_e(analysis_team)} Chance Network</title>
  <style>{CSS}</style>
</head>
<body>
  <main class="page">
    <header>
      <p class="eyebrow">Chance Creation Network</p>
      <h1>{_e(analysis_team)} player links before high-xG shots</h1>
    </header>
    <section class="layout">
      <div class="panel network-panel">{svg}</div>
      <aside class="panel">
        <h2>Top links</h2>
        <table>
          <thead><tr><th>From</th><th>To</th><th>Count</th><th>Total xG</th></tr></thead>
          <tbody>{table_rows}</tbody>
        </table>
      </aside>
    </section>
  </main>
</body>
</html>
"""
    path.write_text(body, encoding="utf-8")
    return path


def _write_player_combinations(path: Path, rows: list[dict[str, Any]], analysis_team: str, opponent_team: str) -> Path:
    combo_rows = []
    for row in rows:
        chain = _chain_names(row.get("sequence", []))
        combo_rows.append(
            {
                "category": "England attack" if row.get("category") == "england_attacking_combo" else "Mexico conceded",
                "source_team": row.get("source_team"),
                "chain": " -> ".join(chain),
                "xg": row.get("xg") or 0,
                "shooter": row.get("shooter"),
                "minute": row.get("shot_minute"),
                "match_id": row.get("match_id"),
            }
        )
    table_rows = "\n".join(
        f"""
        <tr>
          <td>{_e(row['category'])}</td>
          <td>{_e(row['source_team'])}</td>
          <td>{_e(row['chain'])}</td>
          <td>{_e(row['shooter'])}</td>
          <td>{_fmt(row['xg'])}</td>
          <td>{row['minute']}</td>
        </tr>
        """
        for row in sorted(combo_rows, key=lambda item: float(item["xg"] or 0), reverse=True)
    ) or '<tr><td colspan="6">No combinations found.</td></tr>'
    body = f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Player Combination Map</title>
  <style>{CSS}</style>
</head>
<body>
  <main class="page">
    <header>
      <p class="eyebrow">Player Combination Map</p>
      <h1>{_e(analysis_team)} chance chains and {_e(opponent_team)} conceded chains</h1>
    </header>
    <section class="panel">
      <table>
        <thead>
          <tr><th>Type</th><th>Team</th><th>Chain</th><th>Shooter</th><th>xG</th><th>Min</th></tr>
        </thead>
        <tbody>{table_rows}</tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""
    path.write_text(body, encoding="utf-8")
    return path


def _write_vulnerabilities(path: Path, rows: list[dict[str, Any]], opponent_team: str) -> Path:
    table_rows = "\n".join(
        f"""
        <tr>
          <td>{_e(row.get("lane"))}</td>
          <td>{_e(row.get("depth"))}</td>
          <td>{row.get("shots", 0)}</td>
          <td>{row.get("total_xg", 0)}</td>
          <td>{row.get("avg_xg", 0)}</td>
          <td>{_examples(row.get("examples", []))}</td>
        </tr>
        """
        for row in rows
    ) or '<tr><td colspan="6">No vulnerability rows found yet.</td></tr>'
    body = f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_e(opponent_team)} Vulnerability Summary</title>
  <style>{CSS}</style>
</head>
<body>
  <main class="page">
    <header>
      <p class="eyebrow">Opponent Vulnerabilities</p>
      <h1>Where opponents create value against {_e(opponent_team)}</h1>
    </header>
    <section class="panel">
      <table>
        <thead>
          <tr>
            <th>Lane</th>
            <th>Depth</th>
            <th>Shots</th>
            <th>Total xG</th>
            <th>Avg xG</th>
            <th>Examples</th>
          </tr>
        </thead>
        <tbody>{table_rows}</tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""
    path.write_text(body, encoding="utf-8")
    return path


def _write_graph_overview(path: Path, overview: dict[str, Any]) -> Path:
    count_cards = "\n".join(
        f'<div class="metric"><span>{_e(row.get("label"))}</span><strong>{row.get("count", 0)}</strong></div>'
        for row in overview.get("counts", [])
    ) or "<p>No graph counts found yet.</p>"
    rel_rows = "\n".join(
        f"""
        <tr>
          <td>{_e(row.get("source"))}</td>
          <td>{_e(row.get("relationship"))}</td>
          <td>{_e(row.get("target"))}</td>
          <td>{row.get("count", 0)}</td>
        </tr>
        """
        for row in overview.get("relationships", [])
    ) or '<tr><td colspan="4">No relationships found yet.</td></tr>'
    body = f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Knowledge Graph Overview</title>
  <style>{CSS}</style>
</head>
<body>
  <main class="page">
    <header>
      <p class="eyebrow">Neo4j Knowledge Graph</p>
      <h1>Loaded football graph overview</h1>
    </header>
    <section class="metrics">{count_cards}</section>
    <section class="panel">
      <h2>Relationship Inventory</h2>
      <table>
        <thead>
          <tr><th>From</th><th>Relationship</th><th>To</th><th>Count</th></tr>
        </thead>
        <tbody>{rel_rows}</tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""
    path.write_text(body, encoding="utf-8")
    return path


def _build_event_patterns(combos: list[dict[str, Any]], vulnerabilities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for row in combos:
        category = "England attacking route" if row.get("category") == "england_attacking_combo" else "Mexico conceded route"
        pattern = _event_pattern(row.get("sequence", []), row)
        key = (category, pattern)
        bucket = buckets.setdefault(
            key,
            {
                "category": category,
                "pattern": pattern,
                "count": 0,
                "total_xg": 0.0,
                "examples": [],
            },
        )
        bucket["count"] += 1
        bucket["total_xg"] += float(row.get("xg") or 0)
        if len(bucket["examples"]) < 3:
            bucket["examples"].append(
                f"minute {row.get('shot_minute', '?')} xG {_fmt(row.get('xg'))}"
            )
    for row in vulnerabilities:
        pattern = f"{row.get('lane')} / {row.get('depth')}"
        key = ("Mexico shot-zone vulnerability", pattern)
        buckets[key] = {
            "category": "Mexico shot-zone vulnerability",
            "pattern": pattern,
            "count": int(row.get("shots") or 0),
            "total_xg": float(row.get("total_xg") or 0),
            "examples": [f"avg xG {_fmt(row.get('avg_xg'))}"],
        }
    patterns = []
    for bucket in buckets.values():
        count = max(int(bucket["count"]), 1)
        patterns.append(
            {
                **bucket,
                "avg_xg": bucket["total_xg"] / count,
                "detail": "; ".join(bucket["examples"]),
            }
        )
    return sorted(patterns, key=lambda item: (item["total_xg"], item["count"]), reverse=True)


def _event_pattern(sequence: list[dict[str, Any]], row: dict[str, Any]) -> str:
    clean = _clean_sequence(sequence)
    types = [item.get("type") for item in clean if item.get("type") != "Ball Receipt*"]
    shot = clean[-1] if clean else {}
    zone = _zone_label(shot.get("x"), shot.get("y"))
    has_carry = "Carry" in types
    pass_count = types.count("Pass")
    if pass_count >= 2 and has_carry:
        prefix = "multi-pass plus carry"
    elif pass_count >= 2:
        prefix = "multi-pass combination"
    elif pass_count == 1 and has_carry:
        prefix = "carry then final pass"
    elif has_carry:
        prefix = "carry into shot zone"
    elif pass_count == 1:
        prefix = "single final pass"
    else:
        prefix = "second phase or loose-ball shot"
    return f"{prefix} ending in {zone}"


def _zone_label(x: Any, y: Any) -> str:
    if x is None or y is None:
        return "unknown shot zone"
    x_value = float(x)
    y_value = float(y)
    lane = "left channel" if y_value < 26.7 else "right channel" if y_value > 53.3 else "central lane"
    depth = "six-yard/central box" if x_value >= 102 else "box edge" if x_value >= 88 else "outside box"
    return f"{lane}, {depth}"


def _pitch_svg(content: str) -> str:
    return f"""
        <svg class="pitch" viewBox="0 0 1200 800" role="img" aria-label="Football pitch">
          <rect x="0" y="0" width="1200" height="800" rx="14" class="grass" />
          <line x1="600" y1="0" x2="600" y2="800" class="line" />
          <circle cx="600" cy="400" r="92" class="line-fill" />
          <rect x="0" y="176" width="180" height="448" class="box" />
          <rect x="1020" y="176" width="180" height="448" class="box" />
          <rect x="0" y="296" width="60" height="208" class="box" />
          <rect x="1140" y="296" width="60" height="208" class="box" />
          {content}
        </svg>
    """


def _shot_dot(row: dict[str, Any], analysis_team: str, opponent_team: str) -> str:
    x = _scale_x(row.get("x"))
    y = _scale_y(row.get("y"))
    if x is None or y is None:
        return ""
    team = row.get("team")
    color = "#00a676" if team == analysis_team else "#e84a5f" if team == opponent_team else "#456990"
    radius = max(6, min(28, 6 + float(row.get("xg") or 0) * 34))
    return (
        f'<circle cx="{x}" cy="{y}" r="{radius:.1f}" fill="{color}" fill-opacity="0.62">'
        f'<title>{_e(team)} | {_e(row.get("player"))} | xG {_fmt(row.get("xg"))}</title>'
        "</circle>"
    )


def _heat_cell(row: dict[str, Any], max_xg: float) -> str:
    x_bin = int(row.get("x_bin") or 0)
    y_bin = int(row.get("y_bin") or 0)
    total_xg = float(row.get("total_xg") or 0)
    opacity = 0.18 + (0.72 * total_xg / max(max_xg, 0.01))
    return (
        f'<rect x="{x_bin * 100}" y="{y_bin * 100}" width="100" height="100" '
        f'fill="#e84a5f" fill-opacity="{opacity:.2f}" stroke="rgba(20,33,61,0.18)">'
        f'<title>xG {_fmt(total_xg)} | shots {row.get("shots", 0)}</title>'
        "</rect>"
    )


def _sequence_svg(row: dict[str, Any], idx: int) -> str:
    color = "#00a676" if row.get("category") == "england_attacking_combo" else "#e84a5f"
    parts = []
    for event in _clean_sequence(row.get("sequence", [])):
        x = _scale_x(event.get("x"))
        y = _scale_y(event.get("y"))
        ex = _scale_x(event.get("end_x"))
        ey = _scale_y(event.get("end_y"))
        if x is None or y is None:
            continue
        opacity = max(0.25, 1 - idx * 0.055)
        if ex is not None and ey is not None:
            parts.append(
                f'<line x1="{x}" y1="{y}" x2="{ex}" y2="{ey}" stroke="{color}" '
                f'stroke-width="6" stroke-opacity="{opacity:.2f}" stroke-linecap="round" />'
            )
        parts.append(f'<circle cx="{x}" cy="{y}" r="8" fill="{color}" fill-opacity="{opacity:.2f}" />')
    return "\n".join(parts)


def _combo_card(row: dict[str, Any]) -> str:
    category = "England chance pattern" if row.get("category") == "england_attacking_combo" else "Mexico concession pattern"
    chain = " -> ".join(_chain_names(row.get("sequence", [])))
    return f"""
    <article class="card">
      <p class="tag">{_e(category)}</p>
      <h3>{_e(row.get("source_team"))} | xG {row.get("xg", 0)}</h3>
      <p>{_e(chain or "No player chain available")}</p>
      <small>Match { _e(row.get("match_id")) }, minute {row.get("shot_minute", "?")}, shooter { _e(row.get("shooter")) }</small>
    </article>
    """


def _clean_sequence(sequence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_index: dict[Any, dict[str, Any]] = {}
    for item in sequence:
        index = item.get("index")
        if index is None:
            continue
        by_index[index] = item
    return [by_index[index] for index in sorted(by_index)]


def _chain_names(sequence: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for item in _clean_sequence(sequence):
        player = item.get("player")
        if player and (not names or names[-1] != player):
            names.append(player)
    return names


def _combination_edges(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    edges: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        names = _chain_names(row.get("sequence", []))
        for source, target in zip(names, names[1:]):
            if source == target:
                continue
            key = (source, target)
            edge = edges.setdefault(
                key,
                {"source": source, "target": target, "count": 0, "total_xg": 0.0},
            )
            edge["count"] += 1
            edge["total_xg"] += float(row.get("xg") or 0)
    return edges


def _network_nodes(edges: dict[tuple[str, str], dict[str, Any]]) -> dict[str, dict[str, Any]]:
    names = sorted({name for edge in edges for name in edge})
    if not names:
        return {}
    center_x, center_y = 480, 330
    radius = 240
    nodes = {}
    for idx, name in enumerate(names):
        angle = 2 * 3.141592653589793 * idx / len(names)
        nodes[name] = {
            "name": name,
            "x": center_x + radius * math.cos(angle),
            "y": center_y + radius * math.sin(angle),
        }
    return nodes


def _network_svg(nodes: dict[str, dict[str, Any]], edges: dict[tuple[str, str], dict[str, Any]]) -> str:
    if not nodes:
        return '<p>No player network found.</p>'
    max_xg = max([edge["total_xg"] for edge in edges.values()] or [1.0])
    edge_svg = []
    for edge in edges.values():
        source = nodes[edge["source"]]
        target = nodes[edge["target"]]
        width = 1.5 + 7 * edge["total_xg"] / max(max_xg, 0.01)
        edge_svg.append(
            f'<line x1="{source["x"]:.1f}" y1="{source["y"]:.1f}" x2="{target["x"]:.1f}" y2="{target["y"]:.1f}" '
            f'stroke="#456990" stroke-width="{width:.1f}" stroke-opacity="0.42" />'
        )
    node_svg = []
    for node in nodes.values():
        node_svg.append(
            f'<g><circle cx="{node["x"]:.1f}" cy="{node["y"]:.1f}" r="24" fill="#00a676" fill-opacity="0.86" />'
            f'<text x="{node["x"]:.1f}" y="{node["y"] + 42:.1f}" text-anchor="middle" class="node-label">{_e(node["name"])}</text></g>'
        )
    return f'<svg class="network" viewBox="0 0 960 660" role="img" aria-label="Player combination network">{"".join(edge_svg)}{"".join(node_svg)}</svg>'


def _examples(examples: list[dict[str, Any]]) -> str:
    items = [
        f"{_e(item.get('attacking_team'))}: {_e(item.get('shooter') or item.get('player'))} min {item.get('minute', '?')} xG {_fmt(item.get('xg'))}"
        for item in examples
    ]
    return "<br>".join(items)


def _scale_x(value: Any) -> int | None:
    if value is None:
        return None
    return round(float(value) * 10)


def _scale_y(value: Any) -> int | None:
    if value is None:
        return None
    return round(float(value) * 10)


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _fmt(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "0.00"


CSS = """
:root {
  color-scheme: light;
  --ink: #14213d;
  --muted: #667085;
  --border: #d8dee8;
  --panel: #ffffff;
  --bg: #f5f7fb;
  --accent: #00a676;
  --danger: #e84a5f;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: Inter, Arial, sans-serif;
  color: var(--ink);
  background: var(--bg);
}
.page {
  width: min(1320px, calc(100vw - 48px));
  margin: 32px auto;
}
header { margin-bottom: 24px; }
.eyebrow {
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
h1 { margin: 0; font-size: 32px; line-height: 1.15; }
h2 { margin-top: 0; font-size: 18px; }
.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 380px;
  gap: 20px;
  align-items: start;
}
.pitch {
  width: 100%;
  aspect-ratio: 3 / 2;
  display: block;
  border-radius: 8px;
  border: 1px solid #a7c5b8;
  background: #dff3e7;
}
.grass { fill: #dff3e7; }
.line, .box, .line-fill {
  fill: none;
  stroke: rgba(20, 33, 61, 0.32);
  stroke-width: 4;
}
.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 18px;
  box-shadow: 0 10px 30px rgba(20, 33, 61, 0.06);
}
.card {
  border-top: 1px solid var(--border);
  padding: 14px 0;
}
.card:first-of-type { border-top: 0; }
.tag {
  margin: 0 0 6px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
}
.card h3 { margin: 0 0 8px; font-size: 16px; }
.card p { margin: 0 0 8px; color: #344054; }
small { color: var(--muted); }
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
th, td {
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid var(--border);
  padding: 12px;
}
th {
  color: var(--muted);
  font-size: 12px;
  text-transform: uppercase;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}
.metric {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
}
.metric span { display: block; color: var(--muted); margin-bottom: 8px; }
.metric strong { font-size: 28px; }
.legend {
  display: flex;
  gap: 16px;
  margin-top: 12px;
  color: var(--muted);
  font-size: 14px;
}
.key {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  margin-right: 6px;
}
.key.england { background: var(--accent); }
.key.mexico { background: var(--danger); }
.network-panel { min-height: 520px; }
.pattern-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px 22px;
}
.pattern-grid .card {
  border-top: 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px;
}
.network {
  width: 100%;
  aspect-ratio: 16 / 11;
  display: block;
}
.node-label {
  font-size: 13px;
  fill: var(--ink);
  paint-order: stroke;
  stroke: #fff;
  stroke-width: 4px;
  stroke-linejoin: round;
}
@media (max-width: 980px) {
  .layout { grid-template-columns: 1fr; }
  .page { width: min(100vw - 28px, 1320px); margin: 20px auto; }
  h1 { font-size: 24px; }
}
"""
