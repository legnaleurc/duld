import asyncio

from aiohttp import web

from . import torrent


class TorrentsHandler(web.View):

    async def post(self):
        torrent_ids = torrent.get_completed()
        loop = asyncio.get_event_loop()
        for torrent_id in torrent_ids:
            asyncio.ensure_future(torrent.process_torrent(torrent_id), loop=loop)
        return web.json_response(torrent_ids)

    async def put(self):
        torrent_id = self.request.match_info['id']
        if not torrent_id:
            return web.Response(status=400)

        loop = asyncio.get_event_loop()
        asyncio.ensure_future(torrent.process_torrent(torrent_id), loop=loop)
        return web.Response(status=204)
