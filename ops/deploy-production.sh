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

for binary in stat find grep realpath; do
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
  local ids_text container_id working_dir config_csv label_value service
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
  for label_value in "${raw_files[@]}"; do
    [[ -n "$label_value" ]] || die "Empty path in Compose config_files label"
    [[ "$label_value" == "$IMAGE_OVERRIDE" ]] && continue
    [[ "$label_value" == /* && -f "$label_value" && -r "$label_value" ]] || die "Missing or unreadable active Compose file: $label_value"
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
  echo "Read-only preflight OK: project=tingjian app_image=$CURRENT_IMAGE active_compose_files=${#DISCOVERED_FILES[@]}"
}

if [[ "$mode" == check ]]; then
  readonly_preflight
  exit 0
fi

for binary in flock install mktemp tar gzip cat sleep; do
  command -v "$binary" >/dev/null 2>&1 || die "Missing command: $binary"
done
install -d -m 0700 -- "$STATE_DIR"
exec 9>"$STATE_DIR/deploy.lock"
flock -w 300 9 || die "Another tingjian deployment holds the lock"

# Re-read active labels after acquiring the lock to avoid racing a 1Panel update.
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
