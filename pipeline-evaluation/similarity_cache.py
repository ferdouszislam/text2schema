"""Persist valid similarity decisions between evaluation runs."""

from collections.abc import Iterable, Iterator, Sequence
from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3


PairKey = tuple[str, str, str]

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS similarity_decisions (
    model TEXT NOT NULL,
    prompt_digest TEXT NOT NULL,
    kind TEXT NOT NULL,
    generated_name TEXT NOT NULL,
    target_name TEXT NOT NULL,
    decision INTEGER NOT NULL CHECK (decision IN (0, 1)),
    PRIMARY KEY (model, prompt_digest, kind, generated_name, target_name)
) WITHOUT ROWID
"""

_LOOKUP = """
SELECT decision FROM similarity_decisions
WHERE model = ? AND prompt_digest = ? AND kind = ?
    AND generated_name = ? AND target_name = ?
"""

_INSERT = """
INSERT INTO similarity_decisions (
    model, prompt_digest, kind, generated_name, target_name, decision
) VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT (model, prompt_digest, kind, generated_name, target_name) DO NOTHING
"""


class SimilarityCache:
    """Store the first decision for an ordered name pair and judging prompt."""

    def __init__(self, path: Path, model: str, prompt_digest: str):
        self._path = path
        self._scope = (model, prompt_digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as database:
            database.execute(_CREATE_TABLE)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        try:
            with closing(sqlite3.connect(self._path)) as database, database:
                yield database
        except sqlite3.Error as error:
            raise RuntimeError(f"Could not access similarity cache {self._path}. {error}") from error

    def _read(self, database: sqlite3.Connection, keys: Iterable[PairKey]) -> dict[PairKey, int]:
        decisions = {}
        for key in keys:
            row = database.execute(_LOOKUP, (*self._scope, *key)).fetchone()
            if row is not None:
                decisions[key] = row[0]
        return decisions

    def lookup(self, keys: Sequence[PairKey]) -> dict[PairKey, int]:
        """Return only the decisions already stored for these pairs."""
        if not keys:
            return {}
        with self._connect() as database:
            return self._read(database, keys)

    def store(self, decisions: dict[PairKey, int]) -> dict[PairKey, int]:
        """Commit a batch, retaining any decisions that another run saved first."""
        if not decisions:
            return {}
        with self._connect() as database:
            database.executemany(
                _INSERT,
                ((*self._scope, *key, decision) for key, decision in decisions.items()),
            )
            return self._read(database, decisions)
