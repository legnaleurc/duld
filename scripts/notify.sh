#! /bin/sh

HOST='127.0.0.1'
PORT='1234'

curl -s -X PUT "http://$HOST:$PORT/torrents/$TR_TORRENT_ID"
