from tornado import web as tw, ioloop as ti

from . import torrent


class TorrentsHandler(tw.RequestHandler):

    def post(self):
        torrent_ids = torrent.get_completed()
        uploader = self.settings['uploader']
        loop = ti.IOLoop.current()
        for torrent_id in torrent_ids:
            loop.add_callback(torrent.process_torrent, uploader, torrent_id)
        self.write(torrent_ids)

    def put(self, torrent_id):
        if not torrent_id:
            self.set_status(400)
            return

        uploader = self.settings['uploader']
        loop = ti.IOLoop.current()
        loop.add_callback(torrent.process_torrent, uploader, torrent_id)
        self.set_status(204)
