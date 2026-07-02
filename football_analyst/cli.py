from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from football_analyst.config import Settings
from football_analyst.graph import graph_client
from football_analyst.ingest import (
    bootstrap,
    ingest_sample,
    ingest_statsbomb_file,
    ingest_statsbomb_open_match,
    ingest_worldcup_fixtures_from_football_data,
)
from football_analyst.sources.statsbomb_open import StatsBombOpenClient, match_includes_team, match_label
from football_analyst.visuals import generate_visuals

app = typer.Typer(help="Football analyst knowledge graph tools.")
console = Console()


@contextmanager
def open_graph(settings: Settings | None = None) -> Iterator:
    try:
        with graph_client(settings) as graph:
            yield graph
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc


@app.command()
def init_db() -> None:
    """Verify Neo4j connectivity and create constraints/indexes."""
    with open_graph() as graph:
        bootstrap(graph)
    console.print("[green]Neo4j schema is ready.[/green]")


@app.command()
def sample(path: Path = Path("data/sample/mexico-vs-argentina-sample.json")) -> None:
    """Load the bundled sample event data into Neo4j."""
    with open_graph() as graph:
        bootstrap(graph)
        count = ingest_sample(graph, path)
    console.print(f"[green]Loaded {count} sample events.[/green]")


@app.command()
def statsbomb(
    events_path: Path,
    match_id: str,
    home_team: str,
    away_team: str,
    competition: str = "FIFA World Cup",
    season: str = "2026",
) -> None:
    """Load a StatsBomb-style event JSON file into Neo4j."""
    with open_graph() as graph:
        bootstrap(graph)
        count = ingest_statsbomb_file(
            graph=graph,
            events_path=events_path,
            match_id=match_id,
            home_team=home_team,
            away_team=away_team,
            competition=competition,
            season=season,
        )
    console.print(f"[green]Loaded {count} events from {events_path}.[/green]")


@app.command("statsbomb-open-competitions")
def statsbomb_open_competitions(filter_text: str = typer.Argument("")) -> None:
    """List competitions/seasons available in StatsBomb open-data."""
    settings = Settings.from_env()
    try:
        rows = StatsBombOpenClient(settings).competitions()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    needle = filter_text.lower()
    for row in rows:
        label = (
            f"{row['competition_id']} / {row['season_id']} | "
            f"{row['competition_name']} | {row['season_name']} | "
            f"{row.get('country_name', '')}"
        )
        if not needle or needle in label.lower():
            console.print(label)


@app.command("statsbomb-open-matches")
def statsbomb_open_matches(
    competition_id: int,
    season_id: int,
    team: list[str] | None = typer.Option(None, "--team", help="Filter by team name. Can be repeated."),
) -> None:
    """List matches for a StatsBomb open-data competition/season."""
    settings = Settings.from_env()
    try:
        rows = StatsBombOpenClient(settings).matches(competition_id, season_id)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    teams = team or []
    for match in rows:
        if match_includes_team(match, teams):
            console.print(match_label(match))


@app.command("statsbomb-open")
def statsbomb_open(
    competition_id: int,
    season_id: int,
    team: list[str] | None = typer.Option(None, "--team", help="Only ingest matches involving this team. Can be repeated."),
    limit: int = typer.Option(0, help="Maximum matches to ingest. 0 means no limit."),
) -> None:
    """Download and ingest StatsBomb open-data events from GitHub."""
    settings = Settings.from_env()
    client = StatsBombOpenClient(settings)
    try:
        matches = client.matches(competition_id, season_id)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    selected = [match for match in matches if match_includes_team(match, team or [])]
    if limit > 0:
        selected = selected[:limit]
    if not selected:
        console.print("[yellow]No matches matched your filters.[/yellow]")
        raise typer.Exit(0)

    total_events = 0
    with open_graph(settings) as graph:
        bootstrap(graph)
        for match in selected:
            try:
                events = client.events(match["match_id"])
                count = ingest_statsbomb_open_match(graph, match, events)
            except RuntimeError as exc:
                console.print(f"[red]{match_label(match)} failed: {exc}[/red]")
                raise typer.Exit(1) from exc
            total_events += count
            console.print(f"[green]Loaded {count} events:[/green] {match_label(match)}")
    console.print(f"[green]Loaded {total_events} events across {len(selected)} matches.[/green]")


@app.command()
def fixtures(season: int = 2026) -> None:
    """Load World Cup fixtures/results from football-data.org."""
    settings = Settings.from_env()
    try:
        with open_graph(settings) as graph:
            bootstrap(graph)
            count = ingest_worldcup_fixtures_from_football_data(graph, settings, season=season)
        console.print(f"[green]Loaded {count} World Cup fixtures for {season}.[/green]")
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc


@app.command()
def status() -> None:
    """Show what data is currently loaded in Neo4j."""
    with open_graph() as graph:
        counts = graph.execute(
            """
MATCH (n)
RETURN labels(n)[0] AS label, count(*) AS count
ORDER BY label
""".strip()
        )
        teams = graph.execute(
            """
MATCH (t:Team)
RETURN t.name AS team
ORDER BY team
LIMIT 20
""".strip()
        )
        matches = graph.execute(
            """
MATCH (m:Match)
WITH m, properties(m) AS props
RETURN m.id AS id, props.name AS name, props.utc_date AS utc_date, props.status AS status
ORDER BY coalesce(props.utc_date, m.id)
LIMIT 20
""".strip()
        )
    console.print(Panel.fit("Graph Counts", style="cyan"))
    for row in counts:
        console.print(f"{row['label']}: {row['count']}")
    console.print(Panel.fit("Teams", style="cyan"))
    for row in teams:
        console.print(f"- {row.get('team')}")
    console.print(Panel.fit("Matches", style="cyan"))
    for row in matches:
        label = row.get("name") or row.get("id")
        suffix = f" [{row.get('status')}]" if row.get("status") else ""
        console.print(f"- {label}{suffix}")


@app.command()
def ask(
    query: str = "Find the passing sequences that most frequently lead to high-xG shots against them.",
    team: str = "Mexico",
    analysis_team: str = "England",
) -> None:
    """Ask the LangGraph analyst agent a tactical question."""
    from football_analyst.agent import build_analyst_agent

    agent = build_analyst_agent()
    final_state = agent.invoke(
        {
            "coach_query": query,
            "target_team": team,
            "opponent_team": team,
            "analysis_team": analysis_team,
        }
    )
    console.print(Panel.fit("Generated Cypher", style="cyan"))
    console.print(Syntax(final_state.get("cypher_query", ""), "cypher", word_wrap=True))
    console.print(Panel.fit("Tactical Report", style="green"))
    console.print(final_state.get("tactical_report", "No report generated"))


@app.command()
def visuals(
    output_dir: Path = Path("outputs/visuals"),
    analysis_team: str = "England",
    team: str = "Mexico",
) -> None:
    """Generate shareable HTML visuals from the graph."""
    with open_graph() as graph:
        files = generate_visuals(
            graph=graph,
            output_dir=output_dir,
            analysis_team=analysis_team,
            opponent_team=team,
        )
    console.print("[green]Visual exports created:[/green]")
    for path in files:
        console.print(f"- {path.resolve()}")


if __name__ == "__main__":
    app()
