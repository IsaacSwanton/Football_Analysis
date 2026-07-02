from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

from football_analyst.config import Settings


class GraphClient:
    def __init__(self, settings: Settings):
        settings.require_neo4j()
        self._database = settings.neo4j_database or None
        self._driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
        )

    def close(self) -> None:
        self._driver.close()

    def verify(self) -> None:
        self._driver.verify_connectivity()

    def execute(self, cypher: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        try:
            kwargs = {"database_": self._database} if self._database else {}
            records, _, _ = self._driver.execute_query(cypher, parameters or {}, **kwargs)
            return [record.data() for record in records]
        except Neo4jError as exc:
            raise RuntimeError(f"Neo4j query failed: {exc.message}") from exc


@contextmanager
def graph_client(settings: Settings | None = None) -> Iterator[GraphClient]:
    client = GraphClient(settings or Settings.from_env())
    try:
        yield client
    finally:
        client.close()
