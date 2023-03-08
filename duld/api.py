import asyncio
import json

from aiohttp.web import View, Response

from .torrent import get_completed, upload_torrent


class TorrentsHandler(View):
    async def post(self):
        torrents = get_completed()
        uploader = self.request.app["uploader"]
        for t in torrents:
            f = upload_torrent(uploader, t.id)
            asyncio.create_task(f)
        result = json.dumps([_.id for _ in torrents])
        result = result + "\n"
        return Response(text=result, content_type="application/json")

    async def put(self):
        torrent_id = self.request.match_info["torrent_id"]
        if not torrent_id:
            return Response(status=400)

        uploader = self.request.app["uploader"]
        f = upload_torrent(uploader, int(torrent_id))
        asyncio.create_task(f)
        return Response(status=204)


class HaHHandler(View):
    async def post(self):
        hah_context = self.request.app["hah"]
        folders = hah_context.scan_finished()
        result = json.dumps(folders)
        result = result + "\n"
        return Response(text=result, content_type="application/json")
