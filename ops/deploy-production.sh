#!/usr/bin/env bash
# tingjian-only GitHub Actions SSH deployment command.
# Install root-owned at /usr/local/bin/tingjian-deploy; restrict the SSH key
# using command="/usr/local/bin/tingjian-deploy",restrict in authorized_keys.
set -Eeuo pipefail
umask 077

CONFIG=/etc/tingjian-deploy.conf
if [[ ! -r "$CONFIG" ]]; then
  echo "Missing readable $CONFIG" >&2
  exit 2
fi
if [[ "$(stat -c '%u' "$CONFIG")" != 0 ]] || [[ -n "$(find "$CONFIG" -maxdepth 0 -perm /022 -print)" ]]; then
  echo "Deploy config must be root-owned and not writable by group/others" >&2
  exit 2
fi
# The root-owned config must define TINGJIAN_APP_DIR; it contains no secrets.
# shellcheck disable=SC1090
source "$CONFIG"
: "${TINGJIAN_APP_DIR:?Set TINGJIAN_APP_DIR in /etc/tingjian-deploy.conf}"
if [[ "$TINGJIAN_APP_DIR" != /* ]] || [[ ! -d "$TINGJIAN_APP_DIR" ]]; then
  echo "TINGJIAN_APP_DIR must be an existing absolute directory" >&2
  exit 2
fi

request="${SSH_ORIGINAL_COMMAND:-$*}"
if [[ "$request" == check ]]; then
  target=""
elif [[ "$request" =~ ^deploy[[:space:]]+([a-fA-F0-9]{40})$ ]]; then
  target="${BASH_REMATCH[1],,}"
else
  echo "Only 'check' and 'deploy <40-character commit SHA>' are allowed" >&2
  exit 2
fi

for binary in git docker flock; do
  if ! command -v "$binary" >/dev/null 2>&1; then
    echo "Missing command: $binary" >&2
    exit 2
  fi
done

cd "$TINGJIAN_APP_DIR"
if [[ "$(git rev-parse --show-toplevel)" != "$(pwd -P)" ]]; then
  echo "TINGJIAN_APP_DIR must be the Git repository root" >&2
  exit 2
fi
case "$(git remote get-url origin)" in
  git@github.com:GaoSeafood/tingjian|git@github.com:GaoSeafood/tingjian.git|https://github.com/GaoSeafood/tingjian|https://github.com/GaoSeafood/tingjian.git) ;;
  *) echo "Unexpected origin; refuse to deploy anything except GaoSeafood/tingjian" >&2; exit 2 ;;
esac
if [[ "$(git branch --show-current)" != main ]]; then
  echo "The production checkout must stay on branch main" >&2
  exit 2
fi
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "Tracked local modifications found; refuse to overwrite them" >&2
  exit 2
fi
if [[ ! -f .env ]]; then
  echo "Missing existing production .env; never create or replace it automatically" >&2
  exit 2
fi
docker compose -f docker-compose.yml config --quiet

if [[ "$request" == check ]]; then
  echo "tingjian preflight OK: repo, branch, clean files, .env, Docker Compose"
  exit 0
fi

mkdir -p "$HOME/.local/state"
exec 9>"$HOME/.local/state/tingjian-deploy.lock"
flock -w 300 9 || { echo "Another deployment holds the lock" >&2; exit 1; }

git fetch --no-tags origin main
latest_sha="$(git rev-parse FETCH_HEAD)"
if [[ "$target" != "$latest_sha" ]]; then
  echo "Skipping superseded commit $target (current main is $latest_sha)"
  exit 0
fi

previous_sha="$(git rev-parse HEAD)"
deploy_started=0
rollback_on_error() {
  local exit_code="$1"
  trap - ERR
  if [[ "$deploy_started" == 1 ]] && [[ "$(git rev-parse HEAD)" != "$previous_sha" ]]; then
    echo "Deployment failed; attempting application-only rollback to $previous_sha" >&2
    if git reset --hard "$previous_sha" &&
       docker compose -f docker-compose.yml build web worker worker-ai &&
       docker compose -f docker-compose.yml up -d --no-deps --wait --wait-timeout 240 web worker worker-ai; then
      echo "Application rollback completed; investigate the failed update" >&2
    else
      echo "ROLLBACK FAILED: manual recovery is required" >&2
    fi
  fi
  exit "$exit_code"
}
trap 'rollback_on_error "$?"' ERR

deploy_started=1
git merge --ff-only "$target"
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.yml build web worker worker-ai
docker compose -f docker-compose.yml up -d --no-deps --wait --wait-timeout 240 web worker worker-ai
docker compose -f docker-compose.yml ps web worker worker-ai
trap - ERR
echo "tingjian production deployment succeeded: $target"
