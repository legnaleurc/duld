# duld

Let Transmission and HaH upload completed torrents to Cloud Drive.

## Requirements

You have to setup wcpan.drive first.

Modify Transmission settings:

```json
{
    "script-torrent-done-enabled": true,
    "script-torrent-done-filename": "/path/to/scripts/notify.sh",
}
```

Transmission must be able to execute the script, watch out permission problem.

Look `duld.example.yaml` and create your own configuration.

## Run Daemon

```shell
python3 -m duld --settings=duld.yaml
```

## Use Docker Compose

```shell
# prepare .env first
cp .env.example .env

docker compose build
docker compose up
```

## RESTful API

### POST /torrents

Upload all completed torrents.

200 - a list of torrent ID, in JSON

### PUT /torrents/{ID}

Upload torrent by ID.

204 - success
400 - invalid torrent ID
