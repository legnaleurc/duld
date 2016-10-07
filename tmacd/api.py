from tornado import web as tw, ioloop as ti

from . import torrent


class TorrentsHandler(tw.RequestHandler):

    def post(self):
        torrent_ids = torrent.get_completed()
        loop = ti.IOLoop.current()
        for torrent_id in torrent_ids:
            loop.add_callback(torrent.process_torrent, torrent_id)
        self.write(torrent_ids)

    def put(self, torrent_id):
        if not torrent_id:
            self.set_status(400)
            return

        loop = ti.IOLoop.current()
        loop.add_callback(torrent.process_torrent, torrent_id)
        self.set_status(204)
