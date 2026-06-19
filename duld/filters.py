import sqlite3
from collections.abc import Iterable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


class FilterStoreError(Exception):
    pass


class FilterNotFoundError(FilterStoreError):
    pass


class DuplicateFilterError(FilterStoreError):
    pass


@dataclass(frozen=True)
class FilterData:
    id: int
    regexp: str

    def to_dict(self) -> dict[str, int | str]:
        return {"id": self.id, "regexp": self.regexp}


class FilterStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def init(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS filters (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        regexp TEXT NOT NULL UNIQUE
                    )
                    """
                )

    def list(self) -> list[FilterData]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT id, regexp FROM filters ORDER BY id").fetchall()
        return [_to_filter_data(_) for _ in rows]

    def create(self, regexp: str) -> FilterData:
        try:
            with closing(self._connect()) as conn:
                with conn:
                    cursor = conn.execute(
                        "INSERT INTO filters (regexp) VALUES (?)",
                        (regexp,),
                    )
                    row = conn.execute(
                        "SELECT id, regexp FROM filters WHERE id = ?",
                        (cursor.lastrowid,),
                    ).fetchone()
        except sqlite3.IntegrityError as e:
            raise DuplicateFilterError from e
        assert row is not None
        return _to_filter_data(row)

    def update(self, id_: int, regexp: str) -> FilterData:
        try:
            with closing(self._connect()) as conn:
                with conn:
                    cursor = conn.execute(
                        "UPDATE filters SET regexp = ? WHERE id = ?",
                        (regexp, id_),
                    )
                    if cursor.rowcount == 0:
                        raise FilterNotFoundError
                    row = conn.execute(
                        "SELECT id, regexp FROM filters WHERE id = ?",
                        (id_,),
                    ).fetchone()
        except sqlite3.IntegrityError as e:
            raise DuplicateFilterError from e
        assert row is not None
        return _to_filter_data(row)

    def delete(self, id_: int) -> None:
        with closing(self._connect()) as conn:
            with conn:
                cursor = conn.execute("DELETE FROM filters WHERE id = ?", (id_,))
                if cursor.rowcount == 0:
                    raise FilterNotFoundError

    def regexps(self) -> Iterable[str]:
        return (_.regexp for _ in self.list())

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn


def create_filter_store(path: str) -> FilterStore:
    store = FilterStore(Path(path))
    store.init()
    return store


def _to_filter_data(row: sqlite3.Row) -> FilterData:
    return FilterData(id=row["id"], regexp=row["regexp"])
