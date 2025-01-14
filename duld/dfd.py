import re
from abc import ABCMeta, abstractmethod
from collections.abc import Iterable
from typing import TypedDict, override

from aiohttp import ClientSession


type Pattern = re.Pattern[str]
type PatternList = list[Pattern]


class _FilterData(TypedDict):
    id: int
    regexp: str


class DfdClient(metaclass=ABCMeta):
    @abstractmethod
    async def fetch_filters(self) -> PatternList:
        pass


def create_dfd_client(
    *,
    exclude_pattern: list[str] | None,
    exclude_url: str | None,
    session: ClientSession,
) -> DfdClient:
    pattern = _to_regex_list(exclude_pattern if exclude_pattern else [])
    if not exclude_url:
        return _SimpleDfdClient(exclude_pattern=pattern)
    return _DefaultDfdClient(
        exclude_pattern=pattern, exclude_url=exclude_url, session=session
    )


def should_exclude(name: str, exclude_list: PatternList) -> bool:
    return any(_.match(name) is not None for _ in exclude_list)


class _SimpleDfdClient(DfdClient):
    def __init__(self, *, exclude_pattern: PatternList) -> None:
        self._const = exclude_pattern

    @override
    async def fetch_filters(self) -> PatternList:
        return self._const


class _DefaultDfdClient(DfdClient):
    def __init__(
        self, *, exclude_pattern: PatternList, exclude_url: str, session: ClientSession
    ) -> None:
        self._const = exclude_pattern
        self._url = exclude_url
        self._curl = session

    @override
    async def fetch_filters(self) -> PatternList:
        async with self._curl.get(self._url) as response:
            filters: list[_FilterData] = await response.json()
        rv = _to_regex_list(_["regexp"] for _ in filters)
        return self._const + rv


def _to_regex_list(raw_regex_iter: Iterable[str]) -> PatternList:
    non_empty = (_ for _ in raw_regex_iter if _)
    maybe_regex = (_to_pattern(_) for _ in non_empty)
    return [_ for _ in maybe_regex if _]


def _to_pattern(pattern: str) -> Pattern | None:
    try:
        return re.compile(pattern, re.I)
    except Exception:
        return None
