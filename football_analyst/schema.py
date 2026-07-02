from __future__ import annotations

from football_analyst.graph import GraphClient


CONSTRAINTS = [
    "CREATE CONSTRAINT competition_id IF NOT EXISTS FOR (c:Competition) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT season_id IF NOT EXISTS FOR (s:Season) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT match_id IF NOT EXISTS FOR (m:Match) REQUIRE m.id IS UNIQUE",
    "CREATE CONSTRAINT team_id IF NOT EXISTS FOR (t:Team) REQUIRE t.id IS UNIQUE",
    "CREATE CONSTRAINT player_id IF NOT EXISTS FOR (p:Player) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT event_id IF NOT EXISTS FOR (e:Event) REQUIRE e.id IS UNIQUE",
    "CREATE INDEX event_type IF NOT EXISTS FOR (e:Event) ON (e.type)",
    "CREATE INDEX event_possession IF NOT EXISTS FOR (e:Event) ON (e.possession)",
    "CREATE INDEX team_name IF NOT EXISTS FOR (t:Team) ON (t.name)",
    "CREATE INDEX player_name IF NOT EXISTS FOR (p:Player) ON (p.name)",
]


def apply_schema(graph: GraphClient) -> None:
    for statement in CONSTRAINTS:
        graph.execute(statement)
