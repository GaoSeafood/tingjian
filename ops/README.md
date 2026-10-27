# 独立 SSH 自动部署（tingjian）

本方案只适用于 `GaoSeafood/tingjian`。它不依赖 `ad.gaoseafood.com`、其他 GitHub 仓库或共享 Webhook 服务。

## 状态与切换顺序

1. **先不合并 PR**。目前主分支上的旧 Webhook 自动部署仍然生效，新分支仅用于审核。
2. 确认实际生产 VPS、Docker Compose 项目路径、部署账号、可访问 SSH 的方式；**不要猜路径，不要在聊天里粘贴私钥**。
3. 在 VPS 上完成下述准备，做只读 `check` 验证。
4. 在 GitHub 仓库 Settings → Environments 建立 `tingjian-production` 环境（首次可设人工审批）；配置其 Secrets/Variables。
5. 审阅后合并，首次推送 main 时会触发新 SSH 部署。观察日志、数据库与队列，再考虑禁用旧服务端的 `tingjian` Webhook。**不必为了它修改创量项目**。

## VPS 准备（管理员在服务器终端执行）

下面的 `<EXISTING_TINGJIAN_CHECKOUT>` 必须换成当前线上 `tingjian` 仓库根目录；它必须已经包含生产 `.env` 并运行着正确的 Compose 项目。请先通过 `docker compose ps` 核对，勿创建第二个 Compose 项目。确认当前项目的 Compose project name、bind 和 volumes；部署脚本不会新建数据库。

```bash
# 1) 根据你真实的部署账户及现有目录调整。建议专用系统账户、最小权限；
#    如果需加入 docker 组，请知悉其等同于高权限主机访问。
sudo install -o root -g root -m 0755 ops/deploy-production.sh /usr/local/bin/tingjian-deploy
sudo sh -c 'printf "%s\n" "TINGJIAN_APP_DIR=/absolute/path/to/existing/tingjian" > /etc/tingjian-deploy.conf'
sudo chown root:root /etc/tingjian-deploy.conf
sudo chmod 0644 /etc/tingjian-deploy.conf

# 2) 以计划用于 SSH 部署的账号检查其 Git、Docker 和 Docker Compose 权限：
#    此账号需能在已有仓库执行 git fetch、git merge，以及 docker compose。
#    当前脚本要求其处于 main 分支、跟踪文件无本地修改、.env 已存在。
#    仓库 origin 只能是 GaoSeafood/tingjian。生产服务器需要单独的 GitHub 只读拉取凭据。

# 3) 创建专门的 SSH keypair：私钥存入 GitHub Secrets，不可放进仓库。
#    将公钥追加到部署账号 ~/.ssh/authorized_keys；用强制命令约束：
# command="/usr/local/bin/tingjian-deploy",restrict ssh-ed25519 AAAA... tingjian-actions
#    如需针对内网端口转发等扩展，须先审查权限。此密钥不要复用在别的项目。
```

**注意**：部署脚本使用 `SSH_ORIGINAL_COMMAND` 读取 `check` 或 `deploy <40字符 SHA>`。上面 `command=...` 必须是 OpenSSH authorized_keys 公钥行的前缀，不能仅把脚本路径贴入 Secrets。部署账号必须被严格隔离；若可调用 Docker socket，依然具有很高权限。更严格的生产方案是专用部署代理/隔离构建器。

## GitHub Environment 配置

在 **本仓库**的 `tingjian-production` Environment 中创建：

| 名称 | 类型 | 内容 |
| --- | --- | --- |
| `TINGJIAN_SSH_HOST` | Secret | SSH 主机名/IP（不是网站域名，除非是同一可达 SSH 主机） |
| `TINGJIAN_SSH_USER` | Secret | 专用部署账号用户名 |
| `TINGJIAN_SSH_KEY` | Secret | 仅授权执行 `tingjian-deploy` 的 SSH 私钥 |
| `TINGJIAN_SSH_KNOWN_HOSTS` | Secret | **线下核对指纹后**保存的 SSH host public key known_hosts 行 |
| `TINGJIAN_SSH_PORT` | Variable | SSH 端口，留空默认 22 |

不要使用 `StrictHostKeyChecking=no`。也不要不经验证直接信任 `ssh-keyscan` 的输出；请与 VPS 控制台读取的 SSH 主机公钥指纹核对。若主机使用非 22 端口，known_hosts 的主机字段必须对应 `[host]:port`。

## 服务器部署逻辑

* `check`：只读检查仓库、分支、工作区、`.env` 和 Compose 配置；不部署。
* `deploy SHA`：对比 GitHub `main` 最新 SHA，**跳过已被新提交取代的版本**；加 `flock` 独占锁；只在当前仓库 `main` 快进。
* 构建 `web`、`worker`、`worker-ai` 镜像并对这三个服务执行 `up -d --no-deps --wait`。不会主动重建 `db`、`redis` 或使用 `down -v`。
* 部署命令执行失败，会尽力切回之前的 Git 提交并重建三个应用服务；回滚不撤销数据库迁移、不保证运行中任务零中断，生产前须独立备份数据库与持久化数据。
* 健康检查依赖现有 Compose 中 Web 的 `/api/health`；Worker 是否真正消费队列需另外检查。

## 常见失败

* SSH 无法连接：确认 VPN/VPS 防火墙、SSH 端口、主机指纹、key、账号和 GitHub Runner 可达性。
* Missing config / `.env` / git dirty：不要让工作流覆盖线上本地变动，先确认真实服务器状态。
* `git fetch` 失败：服务器需要自己访问**私有仓库**的 GitHub 只读凭据（不同于 Actions 到 VPS 的 SSH 密钥）。
* Compose 项目名字不同：可导致新建一套容器；正式启用前必须核实实际项目名、`docker compose ls`、卷名称和 `docker compose config`。
* 构建/健康失败：查看 VPS 的 Docker 构建输出、容器日志和实际健康状态。

## 后续加强（可选）

如持续发布需要更严谨的零停机能力，应先实现数据库备份、镜像按 SHA 发布、迁移兼容性验证和明确的回滚手册。现有脚本是第一阶段的受控部署方案，不是零停机/无损回滚方案。
