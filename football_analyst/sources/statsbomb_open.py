from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from requests import RequestException

from football_analyst.config import Settings


@dataclass(frozen=True)
class StatsBombOpenClient:
    settings: Settings

    def _verify(self) -> bool | str:
        if self.settings.statsbomb_open_ca_bundle:
            return self.settings.statsbomb_open_ca_bundle
        return self.settings.statsbomb_open_verify_ssl

    def get_json(self, path: str) -> Any:
        url = f"{self.settings.statsbomb_open_base_url.rstrip('/')}/{path.lstrip('/')}"
        try:
            response = requests.get(url, timeout=60, verify=self._verify())
            response.raise_for_status()
            return response.json()
        except requests.exceptions.SSLError as exc:
            raise RuntimeError(
                "StatsBomb open-data could not be reached because SSL certificate verification failed. "
                "If you are behind a corporate proxy, set STATSBOMB_OPEN_CA_BUNDLE in .env to your "
                "company root CA certificate file. For a temporary local test only, set "
                "STATSBOMB_OPEN_VERIFY_SSL=false."
            ) from exc
        except RequestException as exc:
            raise RuntimeError(f"StatsBomb open-data request failed: {exc}") from exc

    def competitions(self) -> list[dict[str, Any]]:
        return self.get_json("competitions.json")

    def matches(self, competition_id: int, season_id: int) -> list[dict[str, Any]]:
        return self.get_json(f"matches/{competition_id}/{season_id}.json")

    def events(self, match_id: int | str) -> list[dict[str, Any]]:
        return self.get_json(f"events/{match_id}.json")


def match_includes_team(match: dict[str, Any], team_names: list[str]) -> bool:
    if not team_names:
        return True
    names = {
        (match.get("home_team") or {}).get("home_team_name", ""),
        (match.get("away_team") or {}).get("away_team_name", ""),
    }
    wanted = {name.lower() for name in team_names}
    return any(name.lower() in wanted for name in names)


def match_label(match: dict[str, Any]) -> str:
    home = (match.get("home_team") or {}).get("home_team_name", "Unknown")
    away = (match.get("away_team") or {}).get("away_team_name", "Unknown")
    date = match.get("match_date", "unknown date")
    return f"{match.get('match_id')} | {date} | {home} vs {away}"
