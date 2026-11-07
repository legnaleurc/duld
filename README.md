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
# prepare .env first, including COMPOSE_FILE
cp .env.example .env

docker compose build
docker compose up
```

Compose files are split by feature. Select them with `COMPOSE_FILE` in `.env`:

| File | Required when | Mount | Config value |
|---|---|---|---|
| `compose.yaml` | always | `DULD_CONFIG_FILE` | - |
| `compose.drive.yaml` | `upload.type: drive` | drive file, config and data dirs | - |
| `compose.local.yaml` | `upload.type: local` | `DULD_LOCAL_PATH` → `/mnt/local` | `upload_to: /mnt/local` |
| `compose.transmission.yaml` | `transmission` is set | `DULD_TM_PATH` → `/mnt/tm` (ro) | `transmission.download_dir: /mnt/tm` |
| `compose.hah.yaml` | `hah_path` is set | `DULD_HAH_PATH` → `/mnt/hah` | `hah_path: /mnt/hah` |
| `compose.exclude.yaml` | `exclude.dynamic` is set | `DULD_DB_PATH` → `/mnt/db` | `exclude.dynamic: /mnt/db/duld.sqlite` |

Host paths are never created automatically; every mounted path must exist
before running Docker Compose.

`exclude.dynamic` can also point into any other read-write mount, such as
`/mnt/data/duld.sqlite` with the drive backend, in which case
`compose.exclude.yaml` is not needed.

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
