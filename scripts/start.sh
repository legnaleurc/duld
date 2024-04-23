#! /bin/sh

if [ -z "$DULD_UID" ] || [ -z "$DULD_GID" ] ; then
    exit 1
fi

exec setpriv \
    --reuid="$DULD_UID" \
    --regid="$DULD_GID" \
    --groups="$DULD_GID" \
    poetry run -- \
    python3 -m duld --settings=/mnt/duld.yaml
