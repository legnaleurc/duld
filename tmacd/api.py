import json

from tornado import web as tw, ioloop as ti

from . import torrent


class TorrentsHandler(tw.RequestHandler):

    def post(self):
        torrents = torrent.get_completed()
        uploader = self.settings['uploader']
        loop = ti.IOLoop.current()
        for t in torrents:
            loop.add_callback(torrent.upload_torrent, uploader, t.id)
        result = json.dumps([_.id for _ in torrents])
        self.write(result)

    def put(self, torrent_id):
        if not torrent_id:
            self.set_status(400)
            return

        uploader = self.settings['uploader']
        loop = ti.IOLoop.current()
        loop.add_callback(torrent.upload_torrent, uploader, torrent_id)
        self.set_status(204)


class PathesHandler(tw.RequestHandler):

    def put(self, path):
        uploader = self.settings['uploader']
        loop = ti.IOLoop.current()
        loop.add_callback(uploader.upload_path, path)
        self.set_status(204)
