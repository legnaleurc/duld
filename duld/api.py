import asyncio
import json

from aiohttp import web as aw

from . import torrent


class TorrentsHandler(aw.View):

    async def post(self):
        torrents = torrent.get_completed()
        uploader = self.request.app['uploader']
        for t in torrents:
            f = torrent.upload_torrent(uploader, t.id)
            asyncio.create_task(f)
        result = json.dumps([_.id for _ in torrents])
        result = result + '\n'
        return aw.Response(text=result, content_type='application/json')

    async def put(self):
        torrent_id = self.request.match_info['torrent_id']
        if not torrent_id:
            return aw.Response(status=400)

        uploader = self.request.app['uploader']
        f = torrent.upload_torrent(uploader, torrent_id)
        asyncio.create_task(f)
        return aw.Response(status=204)


class HaHHandler(aw.View):

    async def post(self):
        hah_context = self.request.app['hah']
        folders = hah_context.scan_finished()
        result = json.dumps(folders)
        result = result + '\n'
        return aw.Response(text=result, content_type='application/json')
