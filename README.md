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
# create the host database file used by DULD_DB_FILE
touch /path/to/duld.sqlite

docker compose build
docker compose up
```

Set `exclude.dynamic` in your config to `/mnt/duld.sqlite` when using Docker
Compose. The host database file is mounted through `DULD_DB_FILE`.

## RESTful API

### POST /torrents

Upload all completed torrents.

200 - a list of torrent ID, in JSON

### PUT /torrents/{ID}

Upload torrent by ID.

204 - success
400 - invalid torrent ID

### GET /filters

List dynamic exclude filters.

200 - a list of filters, in JSON

### POST /filters

Create a dynamic exclude filter.

Request body:

```json
{"regexp": "^sample"}
```

200 - created filter, in JSON
400 - invalid regexp value
409 - regexp already exists

### PUT /filters/{ID}

Update a dynamic exclude filter by ID.

Request body:

```json
{"regexp": "^sample"}
```

200 - updated filter, in JSON
400 - invalid regexp value
404 - filter not found
409 - regexp already exists

### DELETE /filters/{ID}

Delete a dynamic exclude filter by ID.

204 - success
404 - filter not found
