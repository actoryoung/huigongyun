#!/bin/sh
set -e

# Simple checks for the worker non-root behavior. Run locally after build.

echo "Container user name:"
docker run --rm huigongyun:worker-nonroot id -u -n || true

echo "Container user id:"
docker run --rm huigongyun:worker-nonroot id -u || true

HOSTDIR="/tmp/hgy-test"
mkdir -p "$HOSTDIR"
chmod 777 "$HOSTDIR"

echo "Attempt to touch a file in mounted host dir from container:"
docker run --rm -v "$HOSTDIR":/app/data huigongyun:worker-nonroot sh -c "touch /app/data/ok && ls -l /app/data/ok" || true

echo "Host view of the file:"
ls -l "$HOSTDIR"/ok || true
