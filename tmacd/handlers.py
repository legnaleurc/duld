from aiohttp import web

from .torrent import process_torrent


class TorrentsHandler(web.View):

    async def put(self):
        torrent_id = self.request.match_info['id']
        if not torrent_id:
            return web.Response(status=400)

        loop = asyncio.get_event_loop()
        asyncio.ensure_future(process_torrent(torrent_id), loop=loop)
        return web.Response(status=204)
