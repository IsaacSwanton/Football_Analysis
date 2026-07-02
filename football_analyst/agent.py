from __future__ import annotations

import re
from typing import Any, TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from football_analyst.config import Settings
from football_analyst.graph import graph_client
from football_analyst.queries import get_curated_query


class AnalystState(TypedDict, total=False):
    coach_query: str
    target_team: str
    analysis_team: str
    opponent_team: str
    intent: str
    cypher_query: str
    parameters: dict[str, Any]
    graph_data: list[dict[str, Any]]
    tactical_report: str
    errors: str | None


READ_ONLY_PATTERN = re.compile(r"^\s*(MATCH|WITH|RETURN|CALL\s*(\(|\{|db\.))", re.IGNORECASE)
WRITE_PATTERN = re.compile(
    r"\b(CREATE|MERGE|SET|DELETE|DETACH|DROP|REMOVE|LOAD CSV|CALL apoc)\b",
    re.IGNORECASE,
)


def is_read_only_query(cypher: str) -> bool:
    return bool(READ_ONLY_PATTERN.search(cypher)) and not WRITE_PATTERN.search(cypher)


def draft_fallback_report(state: AnalystState, reason: str | None = None) -> str:
    rows = state.get("graph_data", [])
    analysis_team = state.get("analysis_team", "England")
    opponent_team = state.get("opponent_team", state.get("target_team", "Mexico"))
    if not rows:
        return (
            "No matching graph evidence was found. Check that the relevant event data has been "
            f"ingested for {analysis_team} and {opponent_team}."
        )

    england_rows = [row for row in rows if row.get("category") == "england_attacking_combo"]
    conceded_rows = [row for row in rows if row.get("category") == "mexico_conceded_combo"]
    lines = []
    if reason:
        lines.append(f"LLM report unavailable, so this is a deterministic graph summary. Reason: {reason}")
        lines.append("")
    lines.append(f"Matchup evidence for {analysis_team} vs {opponent_team}")
    lines.append("")

    if england_rows:
        lines.append(f"{analysis_team} chance combinations:")
        for row in england_rows[:5]:
            chain = _sequence_chain(row.get("sequence", []))
            lines.append(
                f"- xG {row.get('xg', 0):.2f}, minute {row.get('shot_minute')}, "
                f"shooter {row.get('shooter')}: {chain}"
            )
        lines.append("")

    if conceded_rows:
        lines.append(f"{opponent_team} conceded-chance patterns:")
        for row in conceded_rows[:5]:
            chain = _sequence_chain(row.get("sequence", []))
            lines.append(
                f"- {row.get('source_team')} created xG {row.get('xg', 0):.2f}, "
                f"minute {row.get('shot_minute')}, shooter {row.get('shooter')}: {chain}"
            )
        lines.append("")

    lines.append("Working inference:")
    if england_rows and conceded_rows:
        lines.append(
            f"- Prioritise {analysis_team}'s highest-value combinations that end in central-box shots, "
            f"then compare them against the same lanes {opponent_team} have conceded from."
        )
    elif england_rows:
        lines.append(f"- {analysis_team} have high-value attacking sequences loaded, but more {opponent_team} defensive data would sharpen the matchup inference.")
    elif conceded_rows:
        lines.append(f"- {opponent_team} conceded-chance patterns are loaded, but more {analysis_team} attacking data would sharpen the winning-combo inference.")
    return "\n".join(lines)


def _sequence_chain(sequence: list[dict[str, Any]]) -> str:
    ordered = sorted(sequence, key=lambda item: item.get("index") or 0)
    names: list[str] = []
    for item in ordered:
        player = item.get("player")
        if player and (not names or names[-1] != player):
            names.append(player)
    return " -> ".join(names[:8]) or "No player chain available"


def build_analyst_agent(settings: Settings | None = None):
    settings = settings or Settings.from_env()
    llm = ChatOpenAI(model=settings.openai_model, temperature=0)

    def classify_intent(state: AnalystState) -> AnalystState:
        query = state["coach_query"].lower()
        analysis_team = state.get("analysis_team", "England")
        opponent_team = state.get("opponent_team", state.get("target_team", "Mexico"))
        if (
            "combo" in query
            or "combination" in query
            or "winning" in query
            or ("england" in query and "mexico" in query)
        ):
            return {
                "intent": "matchup_winning_combos",
                "parameters": {
                    "analysis_team": analysis_team,
                    "opponent_team": opponent_team,
                    "min_xg": 0.10,
                    "limit": 12,
                },
            }
        if "vulnerab" in query or "weakness" in query or "exploit" in query:
            return {
                "intent": "opponent_vulnerabilities",
                "parameters": {
                    "opponent_team": opponent_team,
                    "min_xg": 0.05,
                    "examples": 5,
                    "limit": 10,
                },
            }
        if "xg" in query and ("sequence" in query or "passing" in query):
            return {
                "intent": "high_xg_sequences_against_team",
                "parameters": {"team": opponent_team, "min_xg": 0.15, "limit": 10},
            }
        if "shooter" in query or "shot" in query or "xg" in query:
            return {
                "intent": "dangerous_shooters_against_team",
                "parameters": {"team": opponent_team, "limit": 10},
            }
        return {
            "intent": "llm_generate",
            "parameters": {
                "team": opponent_team,
                "analysis_team": analysis_team,
                "opponent_team": opponent_team,
                "limit": 10,
            },
        }

    def generate_query(state: AnalystState) -> AnalystState:
        curated = get_curated_query(state["intent"])
        if curated:
            return {"cypher_query": curated}

        schema = """
Nodes:
(:Competition {id, name})
(:Season {id, year})
(:Match {id, name, utc_date, status, stage, matchday})
(:Team {id, name})
(:Player {id, name})
(:Event {id, match_id, index, period, timestamp, minute, second, type, possession, x, y, end_x, end_y, xg, outcome})
Relationships:
(:Competition)-[:HAS_SEASON]->(:Season)
(:Season)-[:HAS_MATCH]->(:Match)
(:Team)-[:PLAYED_IN {side}]->(:Match)
(:Match)-[:HAS_EVENT]->(:Event)
(:Event)-[:FOR_TEAM]->(:Team)
(:Event)-[:AGAINST_TEAM]->(:Team)
(:Event)-[:PERFORMED_BY]->(:Player)
(:Event)-[:RECEIVED_BY]->(:Player)
(:Event)-[:NEXT]->(:Event)
"""
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are an elite football data engineer. Write a read-only Cypher query for this schema. "
                    "Use $team, $analysis_team, $opponent_team and $limit parameters where useful. "
                    "Return only Cypher, no markdown.",
                ),
                (
                    "user",
                    "Schema:\n{schema}\n\nQuestion: {coach_query}\n"
                    "Analysis team: {analysis_team}\nOpponent team: {opponent_team}",
                ),
            ]
        )
        result = (prompt | llm).invoke(
            {
                "schema": schema,
                "coach_query": state["coach_query"],
                "analysis_team": state.get("analysis_team", "England"),
                "opponent_team": state.get("opponent_team", state.get("target_team", "Mexico")),
            }
        )
        cypher = result.content.replace("```cypher", "").replace("```", "").strip()
        return {"cypher_query": cypher}

    def validate_query(state: AnalystState) -> AnalystState:
        cypher = state["cypher_query"]
        if not is_read_only_query(cypher):
            return {"errors": "Generated query was rejected because it was not read-only."}
        return {"errors": None}

    def execute_graph_search(state: AnalystState) -> AnalystState:
        if state.get("errors"):
            return {"graph_data": []}
        try:
            with graph_client(settings) as graph:
                results = graph.execute(state["cypher_query"], state.get("parameters", {}))
            return {"graph_data": results, "errors": None}
        except Exception as exc:
            return {"graph_data": [], "errors": str(exc)}

    def draft_scouting_report(state: AnalystState) -> AnalystState:
        if state.get("errors"):
            return {"tactical_report": f"Analysis failed: {state['errors']}"}
        if not state.get("graph_data"):
            return {
                "tactical_report": (
                    "No matching graph data was found. Check that event data has been ingested for "
                    f"{state['target_team']} and that the query matches the available event depth."
                )
            }

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are the head opposition analyst. Translate graph output into actionable tactical advice. "
                    "Infer the clearest winning combinations for the analysis team and the opponent vulnerabilities. "
                    "Be specific about players, spaces, defensive triggers, and coaching interventions. "
                    "Separate evidence from inference when the data sample is thin. "
                    "Do not mention nodes, edges, Cypher, or database mechanics.",
                ),
                (
                    "user",
                    "Analysis team: {analysis_team}\nOpponent team: {opponent_team}\n"
                    "Question: {coach_query}\nData: {graph_data}",
                ),
            ]
        )
        try:
            result = (prompt | llm).invoke(
                {
                    "analysis_team": state.get("analysis_team", "England"),
                    "opponent_team": state.get("opponent_team", state.get("target_team", "Mexico")),
                    "coach_query": state["coach_query"],
                    "graph_data": str(state["graph_data"]),
                }
            )
            return {"tactical_report": result.content}
        except Exception as exc:
            return {"tactical_report": draft_fallback_report(state, str(exc))}

    workflow = StateGraph(AnalystState)
    workflow.add_node("intent_classifier", classify_intent)
    workflow.add_node("query_generator", generate_query)
    workflow.add_node("query_validator", validate_query)
    workflow.add_node("database_executor", execute_graph_search)
    workflow.add_node("report_writer", draft_scouting_report)
    workflow.add_edge(START, "intent_classifier")
    workflow.add_edge("intent_classifier", "query_generator")
    workflow.add_edge("query_generator", "query_validator")
    workflow.add_edge("query_validator", "database_executor")
    workflow.add_edge("database_executor", "report_writer")
    workflow.add_edge("report_writer", END)
    return workflow.compile()
