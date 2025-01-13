from abc import ABCMeta, abstractmethod
from typing import override

from aiohttp import ClientSession
from wcpan.drive.core.types import Node

from .settings import DvdData


class DvdClient(metaclass=ABCMeta):
    @abstractmethod
    async def update_search_cache_by_nodes(self, nodes: list[Node]) -> None:
        pass


def create_dvd_client(dvd: DvdData | None, *, session: ClientSession) -> DvdClient:
    if not dvd:
        return EmptyDvdClient()
    return DefaultDvdClient(dvd, session=session)


class EmptyDvdClient(DvdClient):
    @override
    async def update_search_cache_by_nodes(self, nodes: list[Node]) -> None:
        pass


class DefaultDvdClient(DvdClient):
    def __init__(self, dvd: DvdData, *, session: ClientSession) -> None:
        self._dvd = dvd
        self._curl = session

    @override
    async def update_search_cache_by_nodes(self, nodes: list[Node]) -> None:
        headers = self._create_headers()
        async with self._curl.post(
            self._dvd.caches_searches_url, headers=headers, json=nodes
        ) as response:
            response.raise_for_status()

    def _create_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._dvd.token:
            headers["Authorization"] = f"Token {self._dvd.token}"
        return headers
