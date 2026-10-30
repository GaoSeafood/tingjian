# 听见

一个自托管的视频听写与文案工作台。上传本地视频或粘贴公开视频链接后，系统默认只进行语音听写；听写完成后，再由用户主动选择“找亮点”或“复刻改编”。

## 网页与桌面端

本仓库维护听见网页、转写后端、后台任务和服务端部署。批量视频下载 APP 的独立源码在 [`GaoSeafood/tingjian-desktop`](https://github.com/GaoSeafood/tingjian-desktop)，由 Electron、桌面界面和本机 Python 引擎组成，分别构建和发布。

网页内的链接下载仍是本服务的一种任务类型，继续保留；它与桌面 APP 的本机批量下载不是同一个运行入口。桌面端可调用网页的登录与账号服务，但不共享源码目录、安装包构建或服务器数据卷。仓库整理不新增桌面授权接口、不修改账号权限或数据库。

## 第一版能力

- 本地视频或音频上传，最大文件大小可配置
- 视频链接可单独创建下载任务；下载和听写互不强制，下载文件按原视频保留策略在服务器临时保存并自动清理
- B站、抖音、快手、YouTube、小红书、微博等公开视频链接解析，支持从整段分享文案中自动提取链接，也支持腾讯等直链
- 支持 MiMo-V2.5-ASR、自定义 Whisper 兼容 ASR 或 AssemblyAI；AssemblyAI 会在云端完成多人对话说话人标记和时间码
- 保留 OpenAI Whisper 兼容的自定义 ASR 接口
- 可编辑听写稿，支持复制及 TXT / SRT 导出
- B站、YouTube 链接默认尝试字幕优先：获取作者字幕或原语言自动字幕，失败时回退语音转写；也可选择始终根据音频听写。稿件标明来源和语言，不把机器翻译字幕当成原语言字幕
- AI 分析前保存听写修改；改写稿可保存并保留生成、编辑、恢复版本，防止旧页面覆盖新稿
- 当前视频问答附可核对的原文时间点，长稿在当前任务内检索相关片段；每次问答计入一次总结额度
- 听写稿修改后标记已有 AI 结果已过期，支持主动重新生成；AI 超时失败会释放预留次数
- 可选的视频画面分析：按时长抽取关键帧，识别场景、画面文字和视觉吸引力
- 用户主动触发找亮点：时间点、原话、推荐理由、标题、分类与评分
- 找亮点会自动结合已完成的画面分析结果
- 用户主动触发复刻改编，可填写新的主题或改编方向
- 文案 AI 支持 New API、Sub2API 等 OpenAI 兼容接口；备用模型仅在明确配置后使用
- 管理员可测试已保存的 AI 配置，发送简短请求验证实际调用，而非只检查密钥是否存在
- 管理员可手动创建普通用户账号；每个用户的任务、文案和历史记录相互隔离
- 原视频默认 24 小时后删除，也可以立即删除；历史记录支持手动删除，失败任务的原媒体也会在 24 小时后清理
- 长链接任务会根据时长自动切换为只下载音频模式，避免下载和转码不必要的视频流

## 架构

快手支持 `www.kuaishou.com/f/分享码`、`v.kuaishou.com/分享码` 和 `www.kuaishou.com/short-video/作品ID` 等公开作品链接。后端直接读取分享页的视频数据并下载到任务临时目录，再使用现有 ASR 服务听写；无需新增解析服务或登录 Cookie。需要登录、验证码或已失效的作品会提示失败，可改为上传本地视频。分享页和媒体下载的每次重定向都会验证 HTTPS、平台/CDN 域名与公网地址，并遵循原有文件大小和清理策略。

解析方式调研参考：[`JoeanAmier/KS-Downloader`](https://github.com/JoeanAmier/KS-Downloader) 的分享页数据结构，以及 [`zyipeng/video-downloader`](https://github.com/zyipeng/video-downloader) 的快手分享页解析方案。本仓库独立实现所需适配，不引入这些项目的源码或运行依赖。

- 前端：React + Vite
- API：FastAPI
- 后台任务：RQ + Redis
- 数据库：PostgreSQL
- 视频处理：FFmpeg + yt-dlp
- 部署：Docker Compose

## 部署

```bash
cp .env.example .env
# 编辑 .env，至少设置登录密码、SESSION_SECRET 和数据库密码
docker compose up -d --build
```

服务启动后，用管理员账号进入“管理员设置”，选择 ASR 服务并填写对应 API Key（多人对话建议选择 AssemblyAI），再填写 Sub2API API Key 和模型名，并在“朋友账号”区域手动创建普通用户账号。普通用户只能修改自己的登录密码，不能查看或修改接口密钥。密钥会加密保存且不会在页面回显。

管理后台位于网页域名下的 `/admin` 路径。只有管理员账号会显示管理后台入口；普通用户无法访问管理页面或管理员 API。

服务默认只监听 `127.0.0.1:18092`。在 Tailscale 服务器上可将 `APP_BIND` 设置为该服务器的 Tailscale IPv4，避免直接暴露到公网。需要公网访问时，建议在前面加 Caddy/Nginx，使用 HTTPS 域名反向代理到应用端口。不要把生产域名、服务器地址或密钥写进仓库。

## YouTube 访问

YouTube 提取使用 Node.js、yt-dlp EJS 和固定版本 bgutil PO Token Provider。新部署通过 Compose 内网连接访问组件，不发布 4416 端口。组件正常运行并不保证能通过数据中心出口的登录验证。

如出现“要求登录验证”，管理员可在“管理后台 → 系统设置 → YouTube 访问”上传自己主动导出的 Netscape 格式 YouTube cookies.txt，并重试任务。仅保留有效的 youtube.com 域 Cookie，文件权限为 0600；API 不回显内容，支持移除。该登录态只用于管理员自己的字幕、听写、视频下载和画面分析任务，普通用户不会借用管理员账号访问受限内容。上传成功仅表示文件已保存，仍需真实链接验证可用性。

已有独立部署配置的安装，不要用仓库 Compose 覆盖生产配置。可用 `docker compose -p tingjian-youtube -f ops/youtube-provider.compose.yml up -d` 在现有 `tingjian_default` 网络启动访问组件（其他网络名通过 `TINGJIAN_NETWORK` 指定），在原应用的 web、worker、worker-ai 配置中增加 `YOUTUBE_POT_PROVIDER_URL=http://bgutil-provider:4416`，然后仅更新这三个应用服务。保留原 `.env`、数据库、Redis 和媒体卷。独立部署助手只更新应用镜像，不会自动应用这些额外配置；部署后应检查后台组件状态与真实链接结果。

## 安全说明

- `.env` 不进入版本库，不要在聊天、截图或日志中公开任何 API Key。
- URL 下载限制为 HTTPS、公网地址与受支持的平台，避免请求进入服务器内网。
- 不开放自助注册；管理员为朋友创建独立账号，不要共享管理员密码。
- 仅处理你有权使用和下载的视频内容。

## 设计稿

- `design/upload-screen.png`：上传与最近任务页面
- `design/transcript-screen.png`：听写完成后的编辑与 AI 操作页面

## 开发与交接

- 面向开发 Agent 的项目约定、关键业务规则和验证命令见 [`AGENTS.md`](AGENTS.md)。
- 前端生产构建：`npm --prefix frontend ci && npm --prefix frontend run build`
- 后端语法检查：`python -m compileall -q backend/app`（需本机已安装 Python）
- 后端回归检查：先安装 `backend/requirements-test.txt`，再运行 `PYTHONPATH=backend python -m unittest discover -s backend/tests -v`。测试覆盖快手解析、字幕回退、版本持久化、用户隔离和 AI 额度恢复，使用合成响应，无需网络或 ASR 密钥
- 数据库升级仅增加任务字段和 `workspace_versions` 表；旧结果在首次编辑或重新生成时纳入版本历史。已有数据和原媒体清理策略保留
- 完整运行建议使用 Docker Compose；本地 `.env`、数据库和媒体数据不会提交到版本库。
