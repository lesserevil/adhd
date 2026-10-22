#!/bin/sh
# Run on the Linux Docker host, with paths belonging to that host.
set -eu
if [ "$#" -lt 2 ] || [ "$#" -gt 4 ]; then
  echo 'Usage: deploy/run.sh CONFIG_FILE DATA_DIRECTORY [NAME [IMAGE]]' >&2
  exit 2
fi
config_dir=$(realpath "$(dirname "$1")")
config_name=$(basename "$1")
config="$config_dir/$config_name"
container_config="/config/$config_name"
serve_command=$(python3 -c 'import json,sys; print(json.dumps(["serve",sys.argv[1]]))' "$container_config")
data=$(realpath "$2")
name=${3:-adhd-hub}
image=${4:-adhd-hub:local}
[ -d "$config_dir" ] && [ -d "$data" ] || exit 2
if [ "$(id -u)" = 0 ]; then
  echo 'Run as the non-root owner of the private configuration and data directory.' >&2
  exit 2
fi
exec docker run --detach --name "$name" --network host \
  --user "$(id -u):$(id -g)" --read-only --cap-drop ALL \
  --security-opt no-new-privileges --pids-limit 128 --memory 512m --cpus 2 \
  --tmpfs /tmp:rw,nosuid,noexec,size=64m --restart unless-stopped \
  --log-opt max-size=10m --log-opt max-file=3 \
  --env "ADHD_CONFIG_FILE=$container_config" \
  --mount "type=bind,src=$config_dir,dst=/config" \
  --mount "type=bind,src=$data,dst=/data" "$image" "$serve_command"
