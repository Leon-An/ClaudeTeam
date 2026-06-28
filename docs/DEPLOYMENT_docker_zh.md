<p align="center">
  <a href="DEPLOYMENT_zh.md">← Host 部署</a> · <b>Docker 部署</b>
</p>

# Docker 部署

无头 / 服务器 / 多团队用 Docker。宿主上除了 Docker 什么都不要——镜像已烤进 `claudeteam`、
飞书 sidecar，以及 `claude`/`codex`/`kimi`（+`pi`/`hermes`）。通用的配置、模型后端、命令、
其余故障排查见 [Host 部署](DEPLOYMENT_zh.md)。

> **macOS：** 先启动 Docker Desktop（`open -a Docker`，等鲸鱼图标稳定）。daemon 没起来之前
> `docker compose` 会报 `failed to connect to the docker API …`——用
> `docker info | grep '^Server:'` 确认。

---

## 第 1 步 · 代码 + 凭证写进 `.env`

容器里没浏览器，扫码 / 控制台那步在容器内做不了，所以飞书 App 的凭证走 `.env`：

```bash
git clone https://github.com/zylMozart/ClaudeTeam.git && cd ClaudeTeam
cp .env.example .env
$EDITOR .env          # 填 FEISHU_APP_ID + FEISHU_APP_SECRET
#   还没有 App？在一台能开浏览器的机器（或一个 host）上跑一次
#   `claudeteam feishu connect`（或 --quick）注册，把 state/feishu_app.json 里的
#   app_id / app_secret 复制过来。
```

## 第 2 步 · 挂载源要先存在（重要）

compose 会 bind-mount 一批宿主路径进容器。**文件类**的挂载源（`~/.claude.json`、
`~/.lark-cli/config.json`）若不存在，Docker 会在那建个**空目录**、把应用搞坏。全新机器先：

```bash
mkdir -p ~/.codex ~/.kimi ~/.claude/projects ~/.lark-cli/cache
touch ~/.claude.json
# 仅 macOS：把 Claude OAuth 从 keychain 落成文件（Linux 本来就是文件）
mkdir -p ~/.claude
security find-generic-password -s "Claude Code-credentials" -w > ~/.claude/.credentials.json
```

> 不跑某个 CLI（比如没装 codex / kimi）？把 `docker-compose.yml` 里对应的挂载行删掉即可。

## 第 3 步 · 构建 + 起容器

```bash
docker compose build && docker compose up -d
```

## 第 4 步 · 容器内配置 + 起团队

```bash
# 凭证来自 .env，所以 init 用 --no-connect（跳过控制台引导）
docker compose exec --workdir /data claudeteam claudeteam init --no-connect
$EDITOR team-data/claudeteam.toml       # 设 chat_id + 按你有的 CLI 调整 agent
#   还没有群？在一台能开浏览器的机器上跑 `claudeteam feishu connect` 建群，
#   把输出的 oc_... 填进来。

docker compose exec claudeteam claudeteam install-hooks
docker compose exec claudeteam claudeteam up
docker compose exec claudeteam claudeteam health
docker compose exec claudeteam tmux attach -t ClaudeTeam   # 看 pane；Ctrl+B d 脱离
```

**起来了的判据** —— 和 Host 一样：主管在飞书群里跑全员点名（**不是**只看 `health` 绿）。

**拆除：** `docker compose down`（容器停掉，`./team-data/` 里的配置 + 状态还在）。

---

## Compose 挂载

完整列表见 `docker-compose.yml`：`./team-data/`→`/data/`（配置 + 状态）、
`~/.claude/.credentials.json`（Claude OAuth，RW 以便刷新持久化）、`~/.codex`/`~/.kimi`
（各 CLI 凭证）、`~/.lark-cli/...`、`./src/`→`/app/src/`（Python 热重载，改源码不用重建）。
镜像已烤进 `claude`/`codex`/`kimi`（+`pi`/`hermes`）；`gemini`/`qwen` 没烤——需要就从
`claudeteam:dev` 派生后装，或把宿主二进制 bind-mount 进去。

---

## 容器专属故障

### `router` 报 `lark-cli failed (rc=2)` 卡住

catchup 试了 `--as user`，但容器只有 bot OAuth。确保 `CLAUDETEAM_LARK_SEND_AS=bot`
在 `docker-compose.yml` 的 `environment:` 里（自带的 compose 已经有）：
`docker compose exec claudeteam env | grep CLAUDETEAM_LARK_SEND_AS`。

### `.env` 凭证 vs `state/feishu_app.json`

Docker 下 `.env` 里的 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` **覆盖** `state/feishu_app.json`。
确认生效：`docker compose exec claudeteam env | grep FEISHU_APP_ID`。

### `docker compose up -d` 又触发了构建

镜像已存在却还重建，多半是 compose 在补构建。先 `docker compose build` 显式建一次，之后
`up -d` 就直接用已有镜像。

---

通用故障排查（飞书连接、`claude: not found`、router 轮换、主管打转、`say` 报 400、凭证缺失
等）、配置 `claudeteam.toml`、模型后端、命令清单 —— 都见 [Host 部署](DEPLOYMENT_zh.md)。
