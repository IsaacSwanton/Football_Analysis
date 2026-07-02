from football_analyst.sources.statsbomb_open import match_includes_team, match_label


def test_statsbomb_open_match_helpers():
    match = {
        "match_id": 123,
        "match_date": "2022-11-25",
        "home_team": {"home_team_name": "England"},
        "away_team": {"away_team_name": "United States"},
    }

    assert match_includes_team(match, ["England"])
    assert not match_includes_team(match, ["Mexico"])
    assert "England vs United States" in match_label(match)
