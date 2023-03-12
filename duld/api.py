import asyncio
import json

from aiohttp.web import View, Response
from aiohttp.web_exceptions import HTTPBadRequest, HTTPInternalServerError

from .hah import HaHContext
from .settings import Data
from .torrent import get_completed, upload_torrent


class TorrentsHandler(View):
    async def post(self):
        ctx: Data = self.request.app["ctx"]
        if not ctx.transmission:
            raise HTTPInternalServerError

        torrents = get_completed(ctx.transmission)
        uploader = self.request.app["uploader"]
        for t in torrents:
            asyncio.create_task(
                upload_torrent(uploader, ctx.upload_to, ctx.transmission, t.id)
            )
        result = json.dumps([_.id for _ in torrents])
        result = result + "\n"
        return Response(text=result, content_type="application/json")

    async def put(self):
        ctx: Data = self.request.app["ctx"]
        if not ctx.transmission:
            raise HTTPInternalServerError

        torrent_id = self.request.match_info["torrent_id"]
        if not torrent_id:
            raise HTTPBadRequest

        uploader = self.request.app["uploader"]
        asyncio.create_task(
            upload_torrent(uploader, ctx.upload_to, ctx.transmission, int(torrent_id))
        )
        return Response(status=204)


class HaHHandler(View):
    async def post(self):
        hah_context: HaHContext = self.request.app["hah"]
        folders = hah_context.scan_finished()
        result = json.dumps(folders)
        result = result + "\n"
        return Response(text=result, content_type="application/json")
