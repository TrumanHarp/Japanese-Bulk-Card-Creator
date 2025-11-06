# dictionary.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
import sqlite3


@dataclass
class DictEntry:
    ent_seq: int
    expression: str
    reading: Optional[str]
    glosses: List[str]
    pos: Optional[str]
    common: bool


class Dictionary:
    """Wrapper around a JMdict-style SQLite database."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    def _conn_or_open(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
        return self._conn

    def lookup(self, term: str) -> Optional[DictEntry]:
        """Lookup a single term (exact match)."""
        conn = self._conn_or_open()
        cur = conn.cursor()

        row = cur.execute(
            """
            SELECT ent_seq,
                   expression,
                   reading,
                   gloss1,
                   gloss2,
                   gloss3,
                   pos,
                   common
            FROM entries
            WHERE expression = ? OR reading = ?
            ORDER BY common DESC
            LIMIT 1
            """,
            (term, term),
        ).fetchone()

        if not row:
            return None

        ent_seq, expression, reading, g1, g2, g3, pos, common = row
        glosses = [g for g in (g1, g2, g3) if g]

        return DictEntry(
            ent_seq=ent_seq,
            expression=expression,
            reading=reading,
            glosses=glosses,
            pos=pos,
            common=bool(common),
        )

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
