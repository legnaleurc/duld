#! /bin/sh

HOST='127.0.0.1'
PORT='1234'

exec curl -s -X PUT "http://$HOST:$PORT/api/v1/torrents/$TR_TORRENT_ID"
