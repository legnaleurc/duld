import json
import logging
from pathlib import Path, PurePath
from typing import NotRequired, TypedDict

from aiohttp.web import Response, View
from aiohttp.web_exceptions import HTTPBadRequest, HTTPInternalServerError

from .hah import upload_finished_hah
from .keys import CONTEXT, SCHEDULER, TORRENT_REGISTRY, UPLOADER
from .links import upload_from_url
from .torrent import add_urls, get_completed, upload_by_id


_L = logging.getLogger(__name__)


class CreateTorrentsData(TypedDict):
    urls: list[str]


class TorrentsHandler(View):
    async def post(self):
        if not self.request.has_body:
            return await self._upload_completed()

        payload: CreateTorrentsData = await self.request.json()
        if not payload or "urls" not in payload:
            raise HTTPBadRequest
        return await self._add_urls(payload["urls"])

    async def put(self):
        torrent_registry = self.request.app[TORRENT_REGISTRY]
        if not torrent_registry:
            _L.error("no torrent registry")
            raise HTTPInternalServerError

        client_name = self.request.match_info.get("client")
        torrent_id = self.request.match_info["torrent_id"]

        if not client_name:
            _L.error("no client name provided")
            raise HTTPBadRequest
        if not torrent_id:
            _L.error("invalid torrent id")
            raise HTTPBadRequest

        torrent_client = torrent_registry.get_client(client_name)
        if not torrent_client:
            _L.error(f"no torrent client found: {client_name}")
            raise HTTPInternalServerError

        ctx = self.request.app[CONTEXT]
        group = self.request.app[SCHEDULER]
        uploader = self.request.app[UPLOADER]
        group.create_task(
            upload_by_id(
                uploader=uploader,
                upload_to=PurePath(ctx.upload_to),
                torrent_client=torrent_client,
                torrent_id=torrent_id,
            )
        )
        return Response(status=204)

    async def _upload_completed(self) -> Response:
        torrent_registry = self.request.app[TORRENT_REGISTRY]
        if not torrent_registry:
            _L.error("no torrent registry")
            raise HTTPInternalServerError

        ctx = self.request.app[CONTEXT]
        group = self.request.app[SCHEDULER]
        uploader = self.request.app[UPLOADER]

        all_torrents = []
        clients = torrent_registry.get_all_clients()

        for client_name, client in clients.items():
            try:
                torrents = get_completed(client)
                for t in torrents:
                    group.create_task(
                        upload_by_id(
                            uploader=uploader,
                            upload_to=PurePath(ctx.upload_to),
                            torrent_client=client,
                            torrent_id=t.id,
                        )
                    )
                all_torrents.extend(
                    [{"id": t.id, "client": client_name} for t in torrents]
                )
            except Exception as e:
                _L.error(f"error getting completed torrents from {client_name}: {e}")

        return _json_response(all_torrents)

    async def _add_urls(self, urls: list[str]) -> Response:
        torrent_registry = self.request.app[TORRENT_REGISTRY]
        if not torrent_registry:
            _L.error("no torrent registry")
            raise HTTPInternalServerError

        clients = torrent_registry.get_all_clients()
        if not clients:
            _L.error("no torrent clients available")
            raise HTTPInternalServerError

        # Add URLs to all clients
        all_results: dict[str, dict[str, object] | None] = {}

        for client_name, torrent_client in clients.items():
            try:
                torrent_dict = await add_urls(urls, torrent_client=torrent_client)
                for url, torrent in torrent_dict.items():
                    if url not in all_results:
                        all_results[url] = {}

                    if torrent:
                        all_results[url][client_name] = {
                            "id": torrent.id,
                            "name": torrent.name,
                        }
                    else:
                        all_results[url][client_name] = None
            except Exception as e:
                _L.error(f"Failed to add URLs to client {client_name}: {e}")
                # Mark this client as failed for all URLs
                for url in urls:
                    if url not in all_results:
                        all_results[url] = {}
                    all_results[url][client_name] = None

        return _json_response(all_results)


class HaHHandler(View):
    async def post(self):
        ctx = self.request.app[CONTEXT]
        if not ctx.hah_path:
            _L.error("no hah")
            raise HTTPInternalServerError

        group = self.request.app[SCHEDULER]
        uploader = self.request.app[UPLOADER]
        folders = upload_finished_hah(
            hah_path=Path(ctx.hah_path),
            uploader=uploader,
            upload_to=PurePath(ctx.upload_to),
            group=group,
        )
        finished = [folder.name for folder in folders]
        return _json_response(finished)


class LinksData(TypedDict):
    url: str
    name: NotRequired[str]


class LinksHandler(View):
    async def post(self):
        data: LinksData = await self.request.json()
        if not data:
            raise HTTPBadRequest

        try:
            url = data["url"]
            name = data.get("name", None)
        except KeyError:
            raise HTTPBadRequest

        if not url:
            raise HTTPBadRequest

        ctx = self.request.app[CONTEXT]
        group = self.request.app[SCHEDULER]
        uploader = self.request.app[UPLOADER]
        group.create_task(
            upload_from_url(
                url,
                name,
                upload_to=PurePath(ctx.upload_to),
                uploader=uploader,
            )
        )
        return Response(status=204)


def _json_response(data: object) -> Response:
    result = json.dumps(data)
    result = result + "\n"
    return Response(text=result, content_type="application/json")
