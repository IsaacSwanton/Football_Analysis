from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    neo4j_uri: str
    neo4j_username: str
    neo4j_password: str
    neo4j_database: str
    football_data_api_key: str
    football_data_base_url: str
    football_data_ca_bundle: str
    football_data_verify_ssl: bool
    statsbomb_open_base_url: str
    statsbomb_open_ca_bundle: str
    statsbomb_open_verify_ssl: bool

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            neo4j_uri=os.getenv("NEO4J_URI", ""),
            neo4j_username=os.getenv("NEO4J_USERNAME", "neo4j"),
            neo4j_password=os.getenv("NEO4J_PASSWORD", ""),
            neo4j_database=os.getenv("NEO4J_DATABASE", ""),
            football_data_api_key=os.getenv("FOOTBALL_DATA_API_KEY", ""),
            football_data_base_url=os.getenv(
                "FOOTBALL_DATA_BASE_URL",
                "https://api.football-data.org/v4",
            ),
            football_data_ca_bundle=os.getenv("FOOTBALL_DATA_CA_BUNDLE", ""),
            football_data_verify_ssl=os.getenv("FOOTBALL_DATA_VERIFY_SSL", "true").lower()
            not in {"0", "false", "no"},
            statsbomb_open_base_url=os.getenv(
                "STATSBOMB_OPEN_BASE_URL",
                "https://raw.githubusercontent.com/statsbomb/open-data/master/data",
            ),
            statsbomb_open_ca_bundle=os.getenv("STATSBOMB_OPEN_CA_BUNDLE", ""),
            statsbomb_open_verify_ssl=os.getenv("STATSBOMB_OPEN_VERIFY_SSL", "true").lower()
            not in {"0", "false", "no"},
        )

    def require_neo4j(self) -> None:
        supported_schemes = {"neo4j+s", "neo4j", "bolt+s", "bolt"}
        missing = [
            name
            for name, value in {
                "NEO4J_URI": self.neo4j_uri,
                "NEO4J_USERNAME": self.neo4j_username,
                "NEO4J_PASSWORD": self.neo4j_password,
            }.items()
            if not value or "your-" in value
        ]
        if missing:
            raise RuntimeError(
                "Missing Neo4j configuration: "
                + ", ".join(missing)
                + ". Update .env with your AuraDB credentials."
            )
        scheme = urlparse(self.neo4j_uri).scheme
        if scheme not in supported_schemes:
            raise RuntimeError(
                f"NEO4J_URI uses '{scheme or 'no'}' scheme, but the Neo4j driver needs one of "
                f"{', '.join(sorted(supported_schemes))}. In Aura Console, copy the database "
                "Connection URI, which usually starts with neo4j+s://, not the https:// browser URL."
            )
