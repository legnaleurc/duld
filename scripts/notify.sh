#! /bin/sh

HOST='127.0.0.1'
PORT='1234'

curl -s -G \
    --data-urlencode "torrent_root=$TR_TORRENT_DIR" \
    --data-urlencode "torrent_id=$TR_TORRENT_ID" \
    --data-urlencode "torrent_name=$TR_TORRENT_NAME" \
    "http://$HOST:$PORT/"
