from pathlib import Path

from football_analyst.visuals import _write_pitch_map, _write_vulnerabilities


def test_visual_exports_write_html(tmp_path: Path):
    pitch = _write_pitch_map(
        tmp_path / "pitch.html",
        [
            {
                "category": "mexico_conceded_combo",
                "source_team": "Argentina",
                "match_id": "sample",
                "shot_minute": 14,
                "shooter": "Lionel Messi",
                "xg": 0.24,
                "sequence": [
                    {"type": "Pass", "player": "Enzo Fernandez", "x": 54, "y": 48, "end_x": 66, "end_y": 42}
                ],
            }
        ],
        "England",
        "Mexico",
    )
    vuln = _write_vulnerabilities(
        tmp_path / "vulnerabilities.html",
        [{"lane": "central lane", "depth": "edge or inside box", "shots": 1, "total_xg": 0.24, "avg_xg": 0.24}],
        "Mexico",
    )

    assert pitch.exists()
    assert vuln.exists()
    assert "Pitch Map" in pitch.read_text(encoding="utf-8")
    assert "central lane" in vuln.read_text(encoding="utf-8")
