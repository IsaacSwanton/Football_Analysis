from __future__ import annotations

TACTICAL_QUERIES: dict[str, str] = {
    "matchup_winning_combos": """
CALL () {
  WITH $analysis_team AS analysis_team
  MATCH (shot:Event {type: 'Shot'})-[:FOR_TEAM]->(attacking:Team {name: analysis_team})
  WHERE coalesce(shot.xg, 0.0) >= $min_xg
  OPTIONAL MATCH (shot)-[:PERFORMED_BY]->(shooter:Player)
  MATCH (ev:Event)
  WHERE ev.match_id = shot.match_id
    AND ev.possession = shot.possession
    AND ev.index >= shot.index - 8
    AND ev.index <= shot.index
    AND ev.type IN ['Pass', 'Carry', 'Dribble', 'Ball Receipt*', 'Shot']
  WITH 'england_attacking_combo' AS category,
       attacking.name AS source_team,
       shot,
       shooter,
       ev
  OPTIONAL MATCH (ev)-[:PERFORMED_BY]->(actor:Player)
  OPTIONAL MATCH (ev)-[:RECEIVED_BY]->(receiver:Player)
  WITH category, source_team, shot, shooter, ev, actor, receiver
  ORDER BY ev.index
  WITH category, source_team, shot, shooter,
       collect({
         index: ev.index,
         type: ev.type,
         player: actor.name,
         receiver: receiver.name,
         x: ev.x,
         y: ev.y,
         end_x: ev.end_x,
         end_y: ev.end_y
       }) AS sequence
  WHERE size(sequence) > 1
  RETURN category,
         source_team,
         shot.match_id AS match_id,
         shot.minute AS shot_minute,
         shooter.name AS shooter,
         shot.xg AS xg,
         sequence

  UNION

  WITH $opponent_team AS opponent_team
  MATCH (defending:Team {name: opponent_team})<-[:AGAINST_TEAM]-(shot:Event {type: 'Shot'})
  WHERE coalesce(shot.xg, 0.0) >= $min_xg
  MATCH (shot)-[:FOR_TEAM]->(attacking:Team)
  OPTIONAL MATCH (shot)-[:PERFORMED_BY]->(shooter:Player)
  MATCH (ev:Event)
  WHERE ev.match_id = shot.match_id
    AND ev.possession = shot.possession
    AND ev.index >= shot.index - 8
    AND ev.index <= shot.index
    AND ev.type IN ['Pass', 'Carry', 'Dribble', 'Ball Receipt*', 'Shot']
  WITH 'mexico_conceded_combo' AS category,
       attacking.name AS source_team,
       shot,
       shooter,
       ev
  OPTIONAL MATCH (ev)-[:PERFORMED_BY]->(actor:Player)
  OPTIONAL MATCH (ev)-[:RECEIVED_BY]->(receiver:Player)
  WITH category, source_team, shot, shooter, ev, actor, receiver
  ORDER BY ev.index
  WITH category, source_team, shot, shooter,
       collect({
         index: ev.index,
         type: ev.type,
         player: actor.name,
         receiver: receiver.name,
         x: ev.x,
         y: ev.y,
         end_x: ev.end_x,
         end_y: ev.end_y
       }) AS sequence
  WHERE size(sequence) > 1
  RETURN category,
         source_team,
         shot.match_id AS match_id,
         shot.minute AS shot_minute,
         shooter.name AS shooter,
         shot.xg AS xg,
         sequence
}
RETURN category, source_team, match_id, shot_minute, shooter, xg, sequence
ORDER BY xg DESC
LIMIT $limit
""".strip(),
    "opponent_vulnerabilities": """
MATCH (defending:Team {name: $opponent_team})<-[:AGAINST_TEAM]-(shot:Event {type: 'Shot'})
WHERE coalesce(shot.xg, 0.0) >= $min_xg
MATCH (shot)-[:FOR_TEAM]->(attacking:Team)
OPTIONAL MATCH (shot)-[:PERFORMED_BY]->(shooter:Player)
WITH attacking,
     shooter,
     shot,
     CASE
       WHEN shot.y < 26.7 THEN 'left channel'
       WHEN shot.y > 53.3 THEN 'right channel'
       ELSE 'central lane'
     END AS lane,
     CASE
       WHEN shot.x >= 102 THEN 'box / six-yard zone'
       WHEN shot.x >= 88 THEN 'edge or inside box'
       ELSE 'outside box'
     END AS depth
RETURN lane,
       depth,
       count(*) AS shots,
       round(sum(coalesce(shot.xg, 0.0)) * 100.0) / 100.0 AS total_xg,
       round(avg(coalesce(shot.xg, 0.0)) * 100.0) / 100.0 AS avg_xg,
       collect({
         match_id: shot.match_id,
         minute: shot.minute,
         attacking_team: attacking.name,
         shooter: shooter.name,
         xg: shot.xg,
         x: shot.x,
         y: shot.y
       })[0..$examples] AS examples
ORDER BY total_xg DESC, shots DESC
LIMIT $limit
""".strip(),
    "high_xg_sequences_against_team": """
MATCH (defending:Team {name: $team})<-[:AGAINST_TEAM]-(shot:Event {type: 'Shot'})
WHERE coalesce(shot.xg, 0.0) >= $min_xg
MATCH (shot)-[:FOR_TEAM]->(attacking:Team)
MATCH (ev:Event)
WHERE ev.match_id = shot.match_id
  AND ev.possession = shot.possession
  AND ev.index >= shot.index - 8
  AND ev.index <= shot.index
  AND ev.type IN ['Pass', 'Carry', 'Dribble', 'Ball Receipt*', 'Shot']
OPTIONAL MATCH (ev)-[:PERFORMED_BY]->(actor:Player)
OPTIONAL MATCH (ev)-[:RECEIVED_BY]->(receiver:Player)
WITH attacking, shot, ev, actor, receiver
ORDER BY ev.index
WITH attacking.name AS attacking_team,
     shot.match_id AS match_id,
     shot.minute AS shot_minute,
     shot.xg AS xg,
     collect({
       index: ev.index,
       type: ev.type,
       player: actor.name,
       receiver: receiver.name,
       x: ev.x,
       y: ev.y,
       end_x: ev.end_x,
       end_y: ev.end_y
     }) AS sequence
WHERE size(sequence) > 1
RETURN attacking_team, match_id, shot_minute, xg, sequence
ORDER BY xg DESC
LIMIT $limit
""".strip(),
    "dangerous_shooters_against_team": """
MATCH (defending:Team {name: $team})<-[:AGAINST_TEAM]-(shot:Event {type: 'Shot'})-[:PERFORMED_BY]->(player:Player)
MATCH (shot)-[:FOR_TEAM]->(attacking:Team)
RETURN player.name AS player,
       attacking.name AS team,
       count(*) AS shots,
       round(sum(coalesce(shot.xg, 0.0)) * 100.0) / 100.0 AS total_xg,
       round(avg(coalesce(shot.xg, 0.0)) * 100.0) / 100.0 AS avg_xg
ORDER BY total_xg DESC, shots DESC
LIMIT $limit
""".strip(),
    "team_event_counts": """
MATCH (team:Team)<-[:FOR_TEAM]-(event:Event)
RETURN team.name AS team, event.type AS event_type, count(*) AS events
ORDER BY team, events DESC
""".strip(),
}


def get_curated_query(intent: str) -> str | None:
    return TACTICAL_QUERIES.get(intent)
