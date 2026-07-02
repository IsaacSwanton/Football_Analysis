from football_analyst.queries import get_curated_query


def test_matchup_queries_are_registered():
    assert get_curated_query("matchup_winning_combos")
    assert get_curated_query("opponent_vulnerabilities")
