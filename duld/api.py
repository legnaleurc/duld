import json
from pathlib import Path, PurePath

from aiohttp.web import View, Response
from aiohttp.web_exceptions import HTTPBadRequest, HTTPInternalServerError

from .hah import upload_finished
from .torrent import get_completed, upload_by_id
from .keys import CONTEXT, UPLOADER, SCHEDULER


class TorrentsHandler(View):
    async def post(self):
        ctx = self.request.app[CONTEXT]
        if not ctx.transmission:
            raise HTTPInternalServerError

        torrents = get_completed(ctx.transmission)
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
        result = result + "\n"
        return Response(text=result, content_type="application/json")

    async def put(self):
        ctx = self.request.app[CONTEXT]
        if not ctx.transmission:
            raise HTTPInternalServerError

        torrent_id = self.request.match_info["torrent_id"]
        if not torrent_id:
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


class HaHHandler(View):
    async def post(self):
        ctx = self.request.app[CONTEXT]
        if not ctx.hah_path:
            raise HTTPInternalServerError

        group = self.request.app[SCHEDULER]
        uploader = self.request.app[UPLOADER]
        folders = upload_finished(
            hah_path=Path(ctx.hah_path),
            uploader=uploader,
            upload_to=PurePath(ctx.upload_to),
            group=group,
        )
        result = json.dumps(folders)
        result = result + "\n"
        return Response(text=result, content_type="application/json")
