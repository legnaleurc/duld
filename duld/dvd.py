import json
from abc import ABCMeta, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
from functools import partial
from typing import Any, override

from aiohttp import ClientSession
from wcpan.drive.core.types import Node

from .settings import DvdData


class DvdClient(metaclass=ABCMeta):
    @abstractmethod
    async def update_search_cache_by_nodes(self, nodes: list[Node]) -> None:
        pass


@asynccontextmanager
async def create_dvd_client(dvd: DvdData | None):
    if not dvd:
        yield EmptyDvdClient()
        return
    serializer = partial(json.dumps, cls=_NodeEncoder)
    async with ClientSession(json_serialize=serializer) as session:
        yield DefaultDvdClient(dvd, session=session)


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


class _NodeEncoder(json.JSONEncoder):
    @override
    def default(self, o: Any) -> Any:
        match o:
            case Node():
                return {
                    "__type__": "Node",
                    "__value__": asdict(o),
                }
            case datetime():
                return {
                    "__type__": "datetime",
                    "__value__": o.isoformat(),
                }
            case _:
                return super().default(o)
