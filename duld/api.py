import asyncio
import json

from aiohttp import web as aw

from . import torrent


class TorrentsHandler(aw.View):

    async def post(self):
        torrents = torrent.get_completed()
        uploader = self.request.app['uploader']
        loop = asyncio.get_event_loop()
        for t in torrents:
            f = torrent.upload_torrent(uploader, t.id)
            loop.create_task(f)
        result = json.dumps([_.id for _ in torrents])
        result = result + '\n'
        return aw.Response(text=result, content_type='application/json')

    async def put(self):
        torrent_id = self.request.match_info['torrent_id']
        if not torrent_id:
            return aw.Response(status=400)

        uploader = self.request.app['uploader']
        loop = asyncio.get_event_loop()
        f = torrent.upload_torrent(uploader, torrent_id)
        loop.create_task(f)
        return aw.Response(status=204)
