#!/bin/sh
# Run on the Linux Docker host, with paths belonging to that host.
set -eu
if [ "$#" -lt 2 ] || [ "$#" -gt 4 ]; then
  echo 'Usage: deploy/run.sh CONFIG_FILE DATA_DIRECTORY [NAME [IMAGE]]' >&2
  exit 2
fi
config=$(realpath "$1")
data=$(realpath "$2")
name=${3:-adhd-hub}
image=${4:-adhd-hub:local}
[ -f "$config" ] && [ -d "$data" ] || exit 2
if [ "$(id -u)" = 0 ]; then
  echo 'Run as the non-root owner of the private configuration and data directory.' >&2
  exit 2
fi
exec docker run --detach --name "$name" --network host \
  --user "$(id -u):$(id -g)" --read-only --cap-drop ALL \
  --security-opt no-new-privileges --pids-limit 128 --memory 512m --cpus 2 \
  --tmpfs /tmp:rw,nosuid,noexec,size=64m --restart unless-stopped \
  --log-opt max-size=10m --log-opt max-file=3 \
  --mount "type=bind,src=$config,dst=/config/hub.json,readonly" \
  --mount "type=bind,src=$data,dst=/data" "$image"
