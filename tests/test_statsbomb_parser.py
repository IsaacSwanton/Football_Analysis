from football_analyst.sources.statsbomb import normalise_events


def test_normalise_events_adds_opponents_and_shot_xg():
    events = [
        {
            "id": "1",
            "index": 1,
            "period": 1,
            "minute": 10,
            "second": 2,
            "type": {"name": "Pass"},
            "possession": 4,
            "team": {"id": 1, "name": "Argentina"},
            "player": {"id": 10, "name": "Lionel Messi"},
            "location": [60.0, 40.0],
            "pass": {
                "recipient": {"id": 11, "name": "Angel Di Maria"},
                "end_location": [70.0, 30.0],
            },
        },
        {
            "id": "2",
            "index": 2,
            "period": 1,
            "minute": 10,
            "second": 5,
            "type": {"name": "Shot"},
            "possession": 4,
            "team": {"id": 1, "name": "Argentina"},
            "player": {"id": 11, "name": "Angel Di Maria"},
            "location": [104.0, 38.0],
            "shot": {"statsbomb_xg": 0.31, "outcome": {"name": "Saved"}},
        },
    ]

    rows = normalise_events(
        events,
        match_id="sample",
        teams=[
            {"team_id": "1", "team_name": "Argentina"},
            {"team_id": "2", "team_name": "Mexico"},
        ],
    )

    assert rows[0]["opponent_team_id"] == "2"
    assert rows[0]["recipient_name"] == "Angel Di Maria"
    assert rows[1]["xg"] == 0.31
    assert rows[1]["type"] == "Shot"


def test_normalise_events_uses_provider_team_ids_for_opponents():
    events = [
        {
            "id": "1",
            "index": 1,
            "type": {"name": "Shot"},
            "possession": 1,
            "team": {"id": 779, "name": "Argentina"},
            "player": {"id": 10, "name": "Lionel Messi"},
            "shot": {"statsbomb_xg": 0.22},
        }
    ]

    rows = normalise_events(
        events,
        match_id="sample",
        teams=[
            {"team_id": "771", "team_name": "Mexico"},
            {"team_id": "779", "team_name": "Argentina"},
        ],
    )

    assert rows[0]["team_id"] == "779"
    assert rows[0]["opponent_team_id"] == "771"
