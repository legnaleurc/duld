import re
from abc import ABCMeta, abstractmethod
from collections.abc import Iterable
from typing import TypedDict, override

from aiohttp import ClientSession

from .settings import ExcludeData


type _Filter = re.Pattern[str]
type FilterList = list[_Filter]


class _FilterData(TypedDict):
    id: int
    regexp: str


class DfdClient(metaclass=ABCMeta):
    @abstractmethod
    async def fetch_filters(self) -> FilterList:
        pass


def create_dfd_client(
    exclude_data: ExcludeData | None,
    *,
    session: ClientSession,
) -> DfdClient:
    if not exclude_data:
        return _StaticDfdClient(static=[])
    static = _to_regex_list(exclude_data.static if exclude_data.static else [])
    if not exclude_data.dynamic:
        return _StaticDfdClient(static=static)
    return _DefaultDfdClient(
        static=static, dynamic=exclude_data.dynamic, session=session
    )


def should_exclude(name: str, exclude_list: FilterList) -> bool:
    return any(_.match(name) is not None for _ in exclude_list)


class _StaticDfdClient(DfdClient):
    def __init__(self, *, static: FilterList) -> None:
        self._const = static

    @override
    async def fetch_filters(self) -> FilterList:
        return self._const


class _DefaultDfdClient(DfdClient):
    def __init__(
        self, *, static: FilterList, dynamic: str, session: ClientSession
    ) -> None:
        self._const = static
        self._url = dynamic
        self._curl = session

    @override
    async def fetch_filters(self) -> FilterList:
        async with self._curl.get(self._url) as response:
            response.raise_for_status()
            filters: list[_FilterData] = await response.json()
        rv = _to_regex_list(_["regexp"] for _ in filters)
        return self._const + rv


def _to_regex_list(raw_regex_iter: Iterable[str]) -> FilterList:
    non_empty = (_ for _ in raw_regex_iter if _)
    maybe_regex = (_to_pattern(_) for _ in non_empty)
    return [_ for _ in maybe_regex if _]


def _to_pattern(pattern: str) -> _Filter | None:
    try:
        return re.compile(pattern, re.I)
    except Exception:
        return None
