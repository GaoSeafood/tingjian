#!/usr/bin/env bash
# Restricted GitHub Actions command for the existing 1Panel tingjian project.
# Install root-owned, then constrain the dedicated SSH key with:
# command="/usr/local/bin/tingjian-deploy",restrict ssh-ed25519 ...
set -Eeuo pipefail
umask 077
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

CONFIG=/etc/tingjian-deploy.conf
die() {
  echo "$*" >&2
  exit 2
}

for binary in stat find grep realpath python3; do
  command -v "$binary" >/dev/null 2>&1 || die "Missing command: $binary"
done
[[ -f "$CONFIG" && -r "$CONFIG" ]] || die "Missing readable $CONFIG"
[[ "$(stat -c '%u' "$CONFIG")" == 0 ]] || die "Deploy config must be root-owned"
if find "$CONFIG" -maxdepth 0 -perm /022 -print -quit | grep -q .; then
  die "Deploy config must not be writable by group or others"
fi
# This root-owned file contains paths only, never credentials.
# shellcheck disable=SC1090
source "$CONFIG"
: "${TINGJIAN_COMPOSE_DIR:?Set TINGJIAN_COMPOSE_DIR in $CONFIG}"
: "${TINGJIAN_COMPOSE_PROJECT:?Set TINGJIAN_COMPOSE_PROJECT in $CONFIG}"
: "${TINGJIAN_IMAGE_REPOSITORY:?Set TINGJIAN_IMAGE_REPOSITORY in $CONFIG}"

[[ "$TINGJIAN_COMPOSE_PROJECT" == tingjian ]] || die "Unexpected Compose project"
[[ "$TINGJIAN_IMAGE_REPOSITORY" == localhost/github-deploy/tingjian ]] || die "Unexpected local image repository"
[[ "$TINGJIAN_COMPOSE_DIR" == /opt/1panel/apps/tingjian ]] || die "Unexpected 1Panel app directory"
COMPOSE_DIR="$(realpath -e "$TINGJIAN_COMPOSE_DIR")"
BASE_COMPOSE_FILE="$COMPOSE_DIR/docker-compose.yml"
STALE_GENERATED_COMPOSE_FILE=/var/cache/github-deploy/tingjian-compose.k6G0uoZ3.yaml
[[ -f "$BASE_COMPOSE_FILE" ]] || die "Missing 1Panel Compose file: $BASE_COMPOSE_FILE"

# Do not let inherited shell settings select a different Compose project or daemon.
unset COMPOSE_FILE COMPOSE_PROJECT_NAME COMPOSE_PROFILES COMPOSE_ENV_FILES DOCKER_CONTEXT DOCKER_HOST || true

request="${SSH_ORIGINAL_COMMAND:-$*}"
if [[ "$request" == check ]]; then
  mode=check
  target=""
elif [[ "$request" =~ ^deploy[[:space:]]+([a-fA-F0-9]{40})$ ]]; then
  mode=deploy
  target="${BASH_REMATCH[1],,}"
else
  die "Only 'check' and 'deploy <40-character commit SHA>' are allowed"
fi

for binary in docker stat find grep realpath; do
  command -v "$binary" >/dev/null 2>&1 || die "Missing command: $binary"
done

STATE_DIR="$HOME/.local/state/tingjian-deploy"
IMAGE_OVERRIDE="$STATE_DIR/release-image.yml"
COMPOSE_COMMAND=()
DISCOVERED_FILES=()
IGNORED_GENERATED_FILES=0
CURRENT_IMAGE=""

inspect_label() {
  local container_id="$1"
  local label="$2"
  docker inspect --format "{{ index .Config.Labels \"$label\" }}" "$container_id"
}

get_running_service_ids() {
  local service="$1"
  docker ps -q \
    --filter "label=com.docker.compose.project=$TINGJIAN_COMPOSE_PROJECT" \
    --filter "label=com.docker.compose.service=$service"
}

get_all_service_ids() {
  local service="$1"
  docker ps -aq \
    --filter "label=com.docker.compose.project=$TINGJIAN_COMPOSE_PROJECT" \
    --filter "label=com.docker.compose.service=$service"
}

discover_active_compose() {
  local ids_text container_id working_dir config_csv label_value service up_help
  local generated_count=0
  local -a project_ids raw_files app_ids
  ids_text="$(docker ps -q --filter "label=com.docker.compose.project=$TINGJIAN_COMPOSE_PROJECT")"
  [[ -n "$ids_text" ]] || die "No running containers found in Compose project tingjian"
  mapfile -t project_ids <<<"$ids_text"

  ids_text="$(get_running_service_ids web)"
  [[ -n "$ids_text" ]] || die "No running web container found in Compose project tingjian"
  mapfile -t app_ids <<<"$ids_text"
  working_dir="$(inspect_label "${app_ids[0]}" com.docker.compose.project.working_dir)"
  config_csv="$(inspect_label "${app_ids[0]}" com.docker.compose.project.config_files)"
  [[ "$working_dir" == "$COMPOSE_DIR" ]] || die "Running project working_dir does not match $COMPOSE_DIR"
  [[ -n "$config_csv" && "$config_csv" != '<no value>' ]] || die "Running containers do not expose Compose config_files labels"

  for container_id in "${project_ids[@]}"; do
    [[ "$(inspect_label "$container_id" com.docker.compose.project)" == "$TINGJIAN_COMPOSE_PROJECT" ]] || die "Unexpected project label"
    label_value="$(inspect_label "$container_id" com.docker.compose.project.working_dir)"
    [[ "$label_value" == "$working_dir" ]] || die "Compose working_dir labels disagree"
  done
  for service in web worker worker-ai; do
    ids_text="$(get_running_service_ids "$service")"
    [[ -n "$ids_text" ]] || die "No running $service container found in Compose project tingjian"
    mapfile -t app_ids <<<"$ids_text"
    for container_id in "${app_ids[@]}"; do
      label_value="$(inspect_label "$container_id" com.docker.compose.project.config_files)"
      [[ "$label_value" == "$config_csv" ]] || die "Application services use different Compose config_files"
    done
  done

  IFS=',' read -r -a raw_files <<<"$config_csv"
  DISCOVERED_FILES=()
  IGNORED_GENERATED_FILES=0
  for label_value in "${raw_files[@]}"; do
    [[ -n "$label_value" ]] || die "Empty path in Compose config_files label"
    [[ "$label_value" == "$IMAGE_OVERRIDE" ]] && continue
    if [[ "$label_value" == "$STALE_GENERATED_COMPOSE_FILE" ]]; then
      generated_count=$((generated_count + 1))
      (( generated_count <= 1 )) || die "Multiple generated tingjian Compose labels found"
      IGNORED_GENERATED_FILES=1
      continue
    fi
    [[ "$label_value" == "$BASE_COMPOSE_FILE" && -r "$label_value" ]] || die "Unexpected active Compose file label: $label_value"
    DISCOVERED_FILES+=("$label_value")
  done
  [[ "${DISCOVERED_FILES[0]:-}" == "$BASE_COMPOSE_FILE" ]] || die "The active Compose file list does not start with $BASE_COMPOSE_FILE"

  COMPOSE_COMMAND=(docker compose --project-name "$TINGJIAN_COMPOSE_PROJECT" --project-directory "$COMPOSE_DIR")
  for label_value in "${DISCOVERED_FILES[@]}"; do
    COMPOSE_COMMAND+=(-f "$label_value")
  done
  "${COMPOSE_COMMAND[@]}" config --quiet

  local services
  services="$("${COMPOSE_COMMAND[@]}" config --services)"
  for label_value in web worker worker-ai db redis; do
    grep -Fxq "$label_value" <<<"$services" || die "Active Compose config is missing service $label_value"
  done
  up_help="$("${COMPOSE_COMMAND[@]}" up --help)"
  grep -q -- '--no-build' <<<"$up_help" || die "Installed Docker Compose does not support --no-build"
  grep -q -- '--pull' <<<"$up_help" || die "Installed Docker Compose does not support --pull"
}

validate_live_compose() {
  python3 - "$TINGJIAN_COMPOSE_PROJECT" "$COMPOSE_DIR" "$BASE_COMPOSE_FILE" <<'PY'
import json
import subprocess
import sys

project, compose_dir, compose_file = sys.argv[1:]

def run(args):
    result = subprocess.run(args, text=True, capture_output=True)
    if result.returncode:
        if result.stderr:
            sys.stderr.write(result.stderr)
        raise SystemExit(2)
    return result.stdout

model = json.loads(run([
    "docker", "compose", "--project-name", project,
    "--project-directory", compose_dir, "-f", compose_file,
    "config", "--format", "json",
]))
services = ("web", "worker", "worker-ai", "db", "redis")
if not set(services).issubset(model.get("services", {})):
    raise SystemExit("Stable Compose config does not define all expected services")
network_defs = model.get("networks") or {}
volume_defs = model.get("volumes") or {}

def mounts(rows, runtime=False):
    normalized = []
    for row in rows or []:
        if runtime:
            kind = row.get("Type", "").lower()
            source = row.get("Source", "") if kind == "bind" else row.get("Name", "")
            target = row.get("Destination", "")
            read_only = not row.get("RW", True)
        else:
            kind = row.get("type", "volume")
            source = row.get("source") or ""
            if kind == "volume" and source:
                definition = volume_defs.get(source) or {}
                if definition.get("external"):
                    source = definition.get("name") or source
                else:
                    source = definition.get("name") or f"{project}_{source}"
            target = row.get("target", "")
            read_only = bool(row.get("read_only", False))
        normalized.append((kind, str(source), str(target), bool(read_only)))
    return sorted(normalized)

def ports(service, host_config):
    expected = []
    for row in service.get("ports") or []:
        published = row.get("published")
        if published in (None, ""):
            raise SystemExit("Stable Compose config has a dynamic port; review before deployment")
        expected.append((str(row["target"]), str(row.get("protocol") or "tcp"),
                         str(row.get("host_ip") or "0.0.0.0"), str(published)))
    actual = []
    for container_port, bindings in (host_config.get("PortBindings") or {}).items():
        target, protocol = container_port.split("/", 1)
        for binding in bindings or []:
            actual.append((target, protocol, str(binding.get("HostIp") or "0.0.0.0"),
                           str(binding.get("HostPort") or "")))
    return sorted(expected), sorted(actual)

def networks(service):
    configured = service.get("networks") or {"default": None}
    names = []
    for name, options in configured.items():
        definition = network_defs.get(name) or {}
        if definition.get("external"):
            names.append(str(definition.get("name") or name))
        else:
            names.append(str(definition.get("name") or f"{project}_{name}"))
    return sorted(names)

for service_name in services:
    service = model["services"][service_name]
    ids = run([
        "docker", "ps", "-q",
        "--filter", f"label=com.docker.compose.project={project}",
        "--filter", f"label=com.docker.compose.service={service_name}",
    ]).split()
    if not ids:
        raise SystemExit(f"No running container found for {service_name}")
    for container_id in ids:
        container = json.loads(run(["docker", "inspect", container_id]))[0]
        if mounts(service.get("volumes")) != mounts(container.get("Mounts"), True):
            raise SystemExit(f"Stable Compose mounts differ from running {service_name}")
        expected_ports, actual_ports = ports(service, container.get("HostConfig") or {})
        if expected_ports != actual_ports:
            raise SystemExit(f"Stable Compose port bindings differ from running {service_name}")
        live_networks = sorted((container.get("NetworkSettings", {}).get("Networks") or {}).keys())
        if networks(service) != live_networks:
            raise SystemExit(f"Stable Compose networks differ from running {service_name}")

        actual_env = dict(item.split("=", 1) for item in (container.get("Config", {}).get("Env") or []) if "=" in item)
        for key, value in (service.get("environment") or {}).items():
            key = str(key)
            if value is None:
                if key not in actual_env:
                    raise SystemExit(f"Stable Compose environment key is missing from running {service_name}")
            elif actual_env.get(key) != str(value):
                raise SystemExit(f"Stable Compose environment differs from running {service_name}")

        for field, container_field in (("command", "Cmd"), ("entrypoint", "Entrypoint")):
            expected = service.get(field)
            if expected is not None and expected != container.get("Config", {}).get(container_field):
                raise SystemExit(f"Stable Compose {field} differs from running {service_name}")
        expected_restart = str(service.get("restart") or "no")
        actual_restart = str((container.get("HostConfig", {}).get("RestartPolicy") or {}).get("Name") or "no")
        if expected_restart != actual_restart:
            raise SystemExit(f"Stable Compose restart policy differs from running {service_name}")

print("Stable Compose mounts, ports, networks, commands, restart policies, and explicit environment match running containers")
PY
}

capture_current_runtime() {
  local service ids_text container_id image status health
  local -a service_ids
  CURRENT_IMAGE=""

  for service in web worker worker-ai; do
    ids_text="$(get_running_service_ids "$service")"
    [[ -n "$ids_text" ]] || die "No running $service container found in project tingjian"
    mapfile -t service_ids <<<"$ids_text"
    for container_id in "${service_ids[@]}"; do
      image="$(docker inspect --format '{{.Config.Image}}' "$container_id")"
      if [[ -z "$CURRENT_IMAGE" ]]; then
        CURRENT_IMAGE="$image"
      elif [[ "$image" != "$CURRENT_IMAGE" ]]; then
        die "Running application services use different images"
      fi
    done
  done

  [[ "$CURRENT_IMAGE" == "$TINGJIAN_IMAGE_REPOSITORY:"* ]] || die "Current app image is outside the expected local image repository"
  image="${CURRENT_IMAGE#"$TINGJIAN_IMAGE_REPOSITORY:"}"
  [[ "$image" =~ ^[a-f0-9]{40}$ ]] || die "Current app image does not use a full commit SHA tag"
  docker image inspect "$CURRENT_IMAGE" >/dev/null 2>&1 || die "Current application image is not available locally for rollback"

  for service in db redis; do
    ids_text="$(get_running_service_ids "$service")"
    [[ -n "$ids_text" ]] || die "No running $service container found in project tingjian"
    mapfile -t service_ids <<<"$ids_text"
    for container_id in "${service_ids[@]}"; do
      status="$(docker inspect --format '{{.State.Status}}' "$container_id")"
      [[ "$status" == running ]] || die "$service is not running"
      health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id")"
      [[ "$health" == healthy ]] || die "$service is not healthy (status: $health)"
    done
  done

  ids_text="$(get_running_service_ids web)"
  mapfile -t service_ids <<<"$ids_text"
  for container_id in "${service_ids[@]}"; do
    health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id")"
    [[ "$health" == healthy ]] || die "web is not healthy (status: $health)"
  done
}

readonly_preflight() {
  discover_active_compose
  capture_current_runtime
  validate_live_compose
  echo "Read-only preflight OK: project=tingjian app_image=$CURRENT_IMAGE stable_compose_files=${#DISCOVERED_FILES[@]} ignored_generated_labels=$IGNORED_GENERATED_FILES"
}

if [[ "$mode" == check ]]; then
  readonly_preflight
  exit 0
fi

for binary in flock install mktemp tar gzip cat sleep python3; do
  command -v "$binary" >/dev/null 2>&1 || die "Missing command: $binary"
done
install -d -m 0700 -- "$STATE_DIR"
exec 9>"$STATE_DIR/deploy.lock"
flock -w 300 9 || die "Another tingjian deployment holds the lock"

# Re-read runtime metadata after acquiring the lock; the preflight repeats after build.
readonly_preflight
PREVIOUS_IMAGE="$CURRENT_IMAGE"
TARGET_IMAGE="$TINGJIAN_IMAGE_REPOSITORY:$target"
if [[ "$PREVIOUS_IMAGE" == "$TARGET_IMAGE" ]]; then
  cat >/dev/null
  echo "tingjian already runs commit $target; no production changes made"
  exit 0
fi
PREVIOUS_COMPOSE_FILES="${DISCOVERED_FILES[*]}"
stage_dir="$(mktemp -d "$STATE_DIR/source.XXXXXX")"
deployment_started=0

write_image_override() {
  local image="$1" temporary_file
  temporary_file="$(mktemp "$STATE_DIR/release-image.XXXXXX")"
  cat >"$temporary_file" <<EOF
services:
  web:
    image: "$image"
  worker:
    image: "$image"
  worker-ai:
    image: "$image"
EOF
  chmod 0600 "$temporary_file"
  mv -f -- "$temporary_file" "$IMAGE_OVERRIDE"
}

wait_for_app() {
  local deadline=$((SECONDS + 240)) service ids_text container_id status health pending
  local -a service_ids
  while (( SECONDS < deadline )); do
    pending=0
    for service in web worker worker-ai; do
      ids_text="$(get_all_service_ids "$service")"
      if [[ -z "$ids_text" ]]; then
        pending=1
        continue
      fi
      mapfile -t service_ids <<<"$ids_text"
      [[ "${#service_ids[@]}" -eq 1 ]] || { echo "Unexpected number of $service containers" >&2; return 1; }
      container_id="${service_ids[0]}"
      status="$(docker inspect --format '{{.State.Status}}' "$container_id")"
      [[ "$status" == running ]] || { echo "$service container state is $status" >&2; return 1; }
      if [[ "$service" == web ]]; then
        health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id")"
        [[ "$health" != unhealthy && "$health" != none ]] || { echo "web health check is $health" >&2; return 1; }
        [[ "$health" == healthy ]] || pending=1
      fi
    done
    [[ "$pending" == 0 ]] && return 0
    sleep 3
  done
  echo "Timed out waiting for web health and running workers" >&2
  return 1
}

rollback_on_error() {
  local exit_code="$1"
  trap - ERR
  if [[ "$deployment_started" == 1 ]]; then
    echo "Deployment failed; attempting to restore application image $PREVIOUS_IMAGE" >&2
    write_image_override "$PREVIOUS_IMAGE"
    local -a rollback_compose=("${COMPOSE_COMMAND[@]}" -f "$IMAGE_OVERRIDE")
    if "${rollback_compose[@]}" up -d --no-deps --no-build --pull never web worker worker-ai && wait_for_app; then
      echo "Application image rollback completed; investigate the failed update" >&2
    else
      echo "ROLLBACK FAILED: manual recovery is required" >&2
    fi
  fi
  exit "$exit_code"
}

cleanup() {
  rm -rf -- "$stage_dir"
}
trap cleanup EXIT

# GitHub Actions streams a gzip-compressed git archive for exactly this SHA.
tar --extract --gzip --file=- --directory="$stage_dir" --no-same-owner --no-same-permissions
[[ -f "$stage_dir/Dockerfile" && -f "$stage_dir/docker-compose.yml" ]] || die "Source archive is missing Dockerfile or docker-compose.yml"
[[ ! -e "$stage_dir/.env" ]] || die "Refusing a source archive that contains .env"

docker build \
  --label "org.opencontainers.image.revision=$target" \
  --tag "$TARGET_IMAGE" \
  "$stage_dir"
built_revision="$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$TARGET_IMAGE")"
[[ "$built_revision" == "$target" ]] || die "Built image revision label does not match requested SHA"

readonly_preflight
[[ "$CURRENT_IMAGE" == "$PREVIOUS_IMAGE" ]] || die "The running app image changed during the build; refusing to update production"
[[ "${DISCOVERED_FILES[*]}" == "$PREVIOUS_COMPOSE_FILES" ]] || die "The active Compose files changed during the build; refusing to update production"

write_image_override "$TARGET_IMAGE"
RELEASE_COMPOSE=("${COMPOSE_COMMAND[@]}" -f "$IMAGE_OVERRIDE")
if ! "${RELEASE_COMPOSE[@]}" config --quiet; then
  write_image_override "$PREVIOUS_IMAGE"
  die "New image override failed Compose validation; production was not updated"
fi

trap 'rollback_on_error "$?"' ERR
deployment_started=1
"${RELEASE_COMPOSE[@]}" up -d --no-deps --no-build --pull never web worker worker-ai
wait_for_app
"${RELEASE_COMPOSE[@]}" ps web worker worker-ai
trap - ERR
echo "tingjian production deployment succeeded: $target"
