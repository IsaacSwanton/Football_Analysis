from football_analyst.agent import draft_fallback_report, is_read_only_query
from football_analyst.queries import get_curated_query


def test_curated_call_subquery_is_allowed_as_read_only():
    assert is_read_only_query(get_curated_query("matchup_winning_combos") or "")


def test_write_queries_are_rejected():
    assert not is_read_only_query("MATCH (n) DETACH DELETE n")


def test_fallback_report_uses_graph_data():
    report = draft_fallback_report(
        {
            "analysis_team": "England",
            "opponent_team": "Mexico",
            "graph_data": [
                {
                    "category": "england_attacking_combo",
                    "shot_minute": 89,
                    "shooter": "Jack Grealish",
                    "xg": 0.62,
                    "sequence": [
                        {"index": 1, "player": "Jude Bellingham"},
                        {"index": 2, "player": "Callum Wilson"},
                        {"index": 3, "player": "Jack Grealish"},
                    ],
                }
            ],
        },
        "connection error",
    )

    assert "Jude Bellingham -> Callum Wilson -> Jack Grealish" in report
    assert "LLM report unavailable" in report
