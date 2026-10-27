# tingjian 独立 SSH 部署

这套流程只从 `GaoSeafood/tingjian` 的 `main` 分支部署，不调用 `ad.gaoseafood.com` 或其他仓库的 Webhook。部署目标是现有 1Panel Compose 项目 `tingjian`。

## 已知生产布局

截至 2026-10-27，VPS 提供的只读信息显示：

* Compose 项目名为 `tingjian`，工作目录为 `/opt/1panel/apps/tingjian`。
* 活动配置由 `/opt/1panel/apps/tingjian/docker-compose.yml` 与一个位于 `/var/cache/github-deploy/` 的生成配置共同组成。容器标签报告的文件名是临时名；部署命令会从**正在运行的应用容器标签**读取真实文件列表，每次部署前重新核对文件仍存在。
* 活动应用镜像使用 `localhost/github-deploy/tingjian:<完整提交 SHA>`。
* `/opt/1panel/apps/tingjian` 不是 Git 工作区。

因此服务器上不需要也不应该在该目录创建 Git checkout。部署不改生产目录下的 `.env`、Compose 文件或持久卷。

## 合并前的最小只读核查

以下命令只读取容器元数据与 Compose 配置；不会拉取镜像、写文件或重启容器。先确认 `GENERATED` 与 `docker inspect` 报告的当前路径一致：

```bash
BASE=/opt/1panel/apps/tingjian/docker-compose.yml
GENERATED=/var/cache/github-deploy/tingjian-compose.k6G0uoZ3.yaml

docker compose version
docker inspect tingjian-web-1 --format 'project={{index .Config.Labels "com.docker.compose.project"}} service={{index .Config.Labels "com.docker.compose.service"}} workdir={{index .Config.Labels "com.docker.compose.project.working_dir"}} files={{index .Config.Labels "com.docker.compose.project.config_files"}} image={{.Config.Image}} state={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}'
test -r "$BASE" && test -r "$GENERATED"
docker compose -p tingjian -f "$BASE" -f "$GENERATED" config --quiet
docker compose -p tingjian -f "$BASE" -f "$GENERATED" config --services
docker compose -p tingjian -f "$BASE" -f "$GENERATED" config --images

for name in tingjian-web-1 tingjian-worker-1 tingjian-worker-ai-1 tingjian-db-1 tingjian-redis-1; do
  docker inspect "$name" --format '{{.Name}} service={{index .Config.Labels "com.docker.compose.service"}} image={{.Config.Image}} state={{.State.Status}} mounts={{range .Mounts}}{{.Type}}:{{.Name}}->{{.Destination}};{{end}}'
done
```

The output must confirm that all five service names exist, the running app containers share the expected SHA-tagged local image, PostgreSQL and Redis are healthy, and their volume mount names and destinations match the current installation. Do not paste `.env` contents or the full rendered Compose configuration into chat. If the generated file name, services, mounts, health, project name, or image format differ, stop and revise the deployment settings before enabling the workflow.

## Deployment behavior

1. Pull request runs continue to run backend syntax and frontend build checks only. The production job runs on `main` pushes or a manual run against `main`, after both checks pass, through the `tingjian-production` GitHub Environment.
2. GitHub Actions verifies the required secrets and uses strict SSH host-key checking. The host key must be checked against a fingerprint obtained independently from the VPS console.
3. Actions sends a gzip-compressed Git archive for the exact commit SHA to the restricted SSH command. It does not require Git or a GitHub credential on the VPS.
4. The forced command accepts only `check` or `deploy <40-character SHA>`. `check` is read-only. Deployment stages source under the deploy account's private state directory and builds `localhost/github-deploy/tingjian:<SHA>` there, outside `/opt/1panel/apps/tingjian`.
5. The deploy command reads the active Compose file list from the running `web`, `worker`, and `worker-ai` container labels. It confirms they agree, retains the 1Panel generated config, and rechecks the image and file list after the build before appending a small image override for those three application services.
6. It updates only `web`, `worker`, and `worker-ai` with `--no-deps --no-build --pull never`. It does not run `down`, prune images, update PostgreSQL or Redis, or remove volumes. The web health check and running worker states must pass within four minutes.
7. If application startup or the health check fails after the update begins, the script attempts to restore the previously running local image for those three services. This cannot undo database migrations or guarantee zero task interruption; retain a separate database backup before an application release that changes the schema.

The local image repository and Compose project name are checked against the current VPS report. If 1Panel changes those names or moves the project, the script fails closed and needs a reviewed update.

## One-time server setup

Perform this only after the read-only checks above pass. An administrator installs the reviewed script as root-owned and creates a paths-only config file:

```bash
sudo install -o root -g root -m 0755 ./ops/deploy-production.sh /usr/local/bin/tingjian-deploy
sudo tee /etc/tingjian-deploy.conf >/dev/null <<'EOF'
TINGJIAN_COMPOSE_DIR=/opt/1panel/apps/tingjian
TINGJIAN_COMPOSE_PROJECT=tingjian
TINGJIAN_IMAGE_REPOSITORY=localhost/github-deploy/tingjian
EOF
sudo chown root:root /etc/tingjian-deploy.conf
sudo chmod 0644 /etc/tingjian-deploy.conf
```

The dedicated SSH account needs access to the local Docker daemon to build and update these containers. Membership in the `docker` group is effectively root-level host access, so use a dedicated account and key. Restrict the public key in `authorized_keys` with:

```text
command="/usr/local/bin/tingjian-deploy",restrict ssh-ed25519 AAAA... tingjian-actions
```

The script is root-owned but runs as that dedicated account; it accepts no shell command, port forwarding, PTY, or arbitrary deployment path. Verify the installed wrapper with the key using `check`; it reads Docker metadata and Compose configuration without changing them.

## GitHub Environment

In this repository, create Environment `tingjian-production` before merging the draft PR, so the first `main` push has its connection settings:

| Name | Type | Value |
| --- | --- | --- |
| `TINGJIAN_SSH_HOST` | Secret | VPS hostname or IP reachable from GitHub-hosted Actions |
| `TINGJIAN_SSH_USER` | Secret | Dedicated restricted deployment account |
| `TINGJIAN_SSH_KEY` | Secret | Private key matching only the forced-command public key |
| `TINGJIAN_SSH_KNOWN_HOSTS` | Secret | Host key line verified against the VPS console fingerprint |
| `TINGJIAN_SSH_PORT` | Variable | SSH port; defaults to `22` when empty |

Limit the Environment deployment branch to `main`. Add required reviewers if the first release should wait for a manual gate. Never use `StrictHostKeyChecking=no` or trust unverified `ssh-keyscan` output.

## Cutover

1. Complete the read-only VPS checks and confirm the server's generated Compose file remains available.
2. Install the forced-command wrapper, run `check`, validate the VPS host key, and configure the Environment.
3. Review the CI run for the draft PR. Keep the PR unmerged until all settings are ready; merging activates the new `main` deployment job.
4. On the first successful deployment, verify the web health, both workers, database, Redis, and a real user-facing workflow. Then disable only the old `tingjian` webhook route if it is still enabled. Do not change shared deployment routes for other projects.

The workflow and this document do not install the server script, write GitHub secrets, merge the PR, or change production by themselves.
