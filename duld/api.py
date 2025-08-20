import json
import logging
from pathlib import Path, PurePath
from typing import NotRequired, TypedDict

from aiohttp.web import Response, View
from aiohttp.web_exceptions import HTTPBadRequest, HTTPInternalServerError

from .hah import upload_finished_hah
from .keys import CONTEXT, SCHEDULER, UPLOADER
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
        ctx = self.request.app[CONTEXT]
        if not ctx.transmission:
            _L.error("no transmission")
            raise HTTPInternalServerError

        torrent_id = self.request.match_info["torrent_id"]
        if not torrent_id:
            _L.error("invalid torrent id")
            raise HTTPBadRequest

        group = self.request.app[SCHEDULER]
        uploader = self.request.app[UPLOADER]
        group.create_task(
            upload_by_id(
                uploader=uploader,
                upload_to=PurePath(ctx.upload_to),
                transmission=ctx.transmission,
                torrent_id=int(torrent_id),
            )
        )
        return Response(status=204)

    async def _upload_completed(self) -> Response:
        ctx = self.request.app[CONTEXT]
        if not ctx.transmission:
            _L.error("no transmission")
            raise HTTPInternalServerError

        try:
            torrents = get_completed(ctx.transmission)
        except Exception as e:
            _L.error(f"transmission error: {e}, data: {ctx.transmission}")
            raise HTTPInternalServerError

        group = self.request.app[SCHEDULER]
        uploader = self.request.app[UPLOADER]
        for t in torrents:
            group.create_task(
                upload_by_id(
                    uploader=uploader,
                    upload_to=PurePath(ctx.upload_to),
                    transmission=ctx.transmission,
                    torrent_id=t.id,
                )
            )
        result = json.dumps([_.id for _ in torrents])
        return _json_response(result)

    async def _add_urls(self, urls: list[str]) -> Response:
        ctx = self.request.app[CONTEXT]
        if not ctx.transmission:
            _L.error("no transmission")
            raise HTTPInternalServerError

        torrent_dict = await add_urls(urls, transmission=ctx.transmission)
        result: dict[str, dict[str, object] | None] = {
            url: (
                {
                    "id": torrent.id,
                    "name": torrent.name,
                }
                if torrent
                else None
            )
            for url, torrent in torrent_dict.items()
        }
        return _json_response(result)


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
