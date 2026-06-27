# 飞书机器人注册 — `claudeteam feishu connect`（引导式自建应用）

## 目的

证明「引导式注册自建应用 → 验权 → 建群 → 落凭证」这条链路真的成立，并且注册完
之后**事件入站走 `scripts/feishu_channel/sidecar.js run`**（官方 WebSocket →
NDJSON），群里发一句**不 @** 的话 manager 真能收到回。这是 host_smoke 的**前置**
——host_smoke 默认你已经跑过本篇。

覆盖：

- `claudeteam init`（首次部署自动跑 `feishu connect`）/ 或单独 `claudeteam feishu connect`
- 引导式自建应用（企业自建应用）：控制台建 app → 贴 App ID/Secret → 一键权限
  deep-link → 发版 → 命令验权
- 群自动创建 + 把 owner 拉进群
- 凭证落盘 `state/feishu_app.json`（0600）+ `chat_id` 写进 `claudeteam.toml`
- `claudeteam up` 后主管自动发起全员点名（自检）
- 群里发**不 @** 的消息 → manager 回（证明 `im:message.group_msg` + sidecar 入站通了）

## 适用范围

- 平台：macOS / Linux 本机部署（host 模式）。Docker 部署见
  [`docs/DEPLOYMENT.md`](../../docs/DEPLOYMENT.md)：App 凭证走 `.env`、chat_id 手填，
  不在本篇范围。
- 已装：Python 3.10+、tmux、node + npx、`lark-cli`（出站发卡用）、至少一个
  agent CLI（`claude` / `codex` / …）在 PATH 上。
- 已跑：`pip install -e .`（`claudeteam` 在 PATH 上）。
- 有飞书企业 + 管理员账号——要在开发者后台**建一个自建应用**、点权限链接、发版批准。
  这几步要真人在浏览器做，agent 代不了；命令负责验权 + 建群。

## 前置条件

```bash
cd /path/to/ClaudeTeam
source .venv/bin/activate
# 本篇验证「从零注册」，先确认没有残留凭证
ls state/feishu_app.json 2>/dev/null && echo "已存在——connect 会覆盖；想干净重测先移走它"
```

## 操作（Given / When / Then）

### 1. 控制台建自建应用（真人，一次）

**Given** 还没有飞书应用，
**When** 打开 <https://open.feishu.cn/app> → 创建企业自建应用 → 填名字 →
「添加应用能力」加**机器人** → 「凭证与基础信息」复制 **App ID + App Secret**，
**Then** 手上拿到一对 `cli_...` / secret，准备贴给命令。

### 2. 跑 connect，贴凭证（引导）

**Given** 拿到了 App ID/Secret、终端是交互式 TTY，
**When** 跑

```bash
claudeteam init                  # 首次部署：写完 toml 后自动跑 feishu connect
# 或单独：
claudeteam feishu connect
# 跳过（CI / Docker / 已手填凭证）：claudeteam init --no-connect
```

按提示把 **App ID** 和 **App Secret** 粘进去，
**Then** 命令存好凭证（`state/feishu_app.json` 0600），打印一条**一键权限 deep-link**
+ ④⑤⑥ 控制台步骤，停在「按回车继续验证」。

> 只私聊 / @bot 够用、不想进后台？用 `claudeteam feishu connect --quick`：扫一次码
> 注册个人版应用（零后台），但群里必须 @bot——本篇不覆盖这条。

### 3. 控制台开权限 + 发版（真人）

**Given** 命令打印了 deep-link + 步骤、停在等回车，
**When** 在浏览器里：

1. 打开那条 deep-link → **确认**（一次把 7 个权限全勾上，含敏感的 `im:message.group_msg`）；
2. 事件与回调 → 订阅方式 = **使用长连接** → 添加事件**接收消息**；
3. 应用发布 → 创建版本 → 申请发布 → **批准**（你是管理员就直接批准）；

**Then** 回到终端**按回车**。命令拉一次已授权权限核对。

> `im:message.group_msg` 是敏感权限：必须 deep-link 勾上 + 发版 + 管理员批准后才生效。
> 少了它命令会报「权限未到位」并让你补齐重跑——这正是要拦住的点。

### 4. 落盘核对（机判）

**Given** 验权通过、群已建，
**When** 看磁盘，
**Then** 满足全部三条：

```bash
# (a) App 凭证落盘且权限 0600
ls -l state/feishu_app.json          # 期望 -rw-------（0600）
python3 -c "import json; d=json.load(open('state/feishu_app.json')); print('app_id' in d and bool(d.get('app_id')))"
# 期望 True（含 app_id 且非空；app_secret 同理但别打印出来）

# (b) chat_id 写进 toml
grep -E '^\s*chat_id\s*=\s*"oc_' claudeteam.toml
# 期望命中一行 chat_id = "oc_..."

# (c) 飞书里出现「ClaudeTeam」群、owner 在群里
CHAT=$(grep -E '^\s*chat_id' claudeteam.toml | sed -E 's/.*"(oc_[^"]+)".*/\1/')
LARK_CLI_NO_PROXY=1 lark-cli im +chat-search --query "ClaudeTeam" --as user --format json \
  | python3 -c "import json,sys; print([c.get('chat_id') for c in json.load(sys.stdin).get('data',{}).get('items',[])])"
# 期望列表里含上面的 $CHAT
```

**通过条件**：(a) 文件 mode `-rw-------`；(b) `grep` 命中一行；(c) 群能搜到且
chat_id 对得上、你在成员里（飞书 App 里直接看群也行）。

### 5. 上线 + 主管点名（自检，全程无需真人）

**Given** 凭证 + chat_id 都就位，
**When**

```bash
claudeteam install-hooks         # 要在 up 之前
claudeteam up
```

**Then** 首次 `up` 后主管（manager）**自动发起全员点名**：先在群里宣布，再逐一通知
每个 worker，各 worker 自己在群里汇报身份与状态，最后主管汇总。`claudeteam health` 全绿。

> 若 `chat_id` 没设，`claudeteam up` 会直接报错并指向 `claudeteam feishu connect`。

**通过条件（看群里，无需真人发消息）**：`claudeteam up` 后几分钟内，群里能看到主管的
点名公告 + 每个非退休 worker 的汇报 + 主管的汇总。看到这些 = 主管派单 + worker 在群里回
整条链路都通。

### 6. 入站回环 — 不 @ 也能收（证明 `im:message.group_msg` + sidecar 通了）

**Given** 团队已上线，
**When** 在群里发一句**不 @ 任何人**的带锚定的话，

```bash
ANCHOR="connect-回环-$(date +%s)"
LARK_CLI_NO_PROXY=1 lark-cli im +messages-send \
  --chat-id "$CHAT" --text "收到请回复 $ANCHOR" --as user
```

**Then** 60 秒内群里能看到 manager 的回复卡，**内容里带 `$ANCHOR`**——证明自建应用的
`im:message.group_msg` 生效（不 @ 也推给 bot）+ `node scripts/feishu_channel/sidecar.js run`
的 WebSocket 入站 → router → manager 整条链路通了（不是回复以前的消息）。

```bash
# 旁证：sidecar 入站进程在跑
ps -ef | grep -E "feishu_channel/sidecar\.js run" | grep -v grep
# 旁证：health 的 inbound 行从「none observed yet」翻成「last event …」
claudeteam health | grep -i inbound
```

## 期望（一句话）

验权通过后：`state/feishu_app.json`（0600）+ `claudeteam.toml` 的 `chat_id` 都写好、
ClaudeTeam 群里有你、`claudeteam up` 全员报到、群里发一句**不 @** 的话能在 60 秒内
拿到带锚定的回复。

## 失败排查

- **命令报「权限未到位（缺 im:message.group_msg）」**——deep-link 没确认 / 没发版 /
  没批准；按 §3 补齐再回车（或重跑 connect）。这是最常见的卡点。
- **`state/feishu_app.json` 不是 0600**——connect 写盘权限有问题，重跑 connect；出站
  发卡 / sidecar 都靠 `feishu/lark.py:subprocess_env()` 从这个文件注入
  `FEISHU_APP_ID/SECRET` + tenant token。
- **群没建出来**——看命令尾部是不是「建群失败」；确认 app 有 `im:chat` 权限（deep-link 已含）。
- **报到卡没出现**——`claudeteam health` 看是不是某个 agent 没起；CLI 没登录见
  [host_smoke.md](host_smoke.md) §1 的排查。
- **§6 不 @ manager 不回**——先确认 sidecar 进程在跑（上面那条 `ps`）；再确认 app
  **真有** `im:message.group_msg`（个人版 / `--quick` 拿不到，群里就必须 @bot）；再看
  `state/router.log` 是不是 ROUTE 到 manager；inbound 行没翻说明入站没进来，查 sidecar stderr。

## 不在范围

- 斜杠命令矩阵 / 反向路由 / catchup / lazy：跑通本篇后看 [host_smoke.md](host_smoke.md)。
- Docker 部署（凭证走 `.env` 覆盖、chat_id 手填、入站同样是 sidecar）：见
  [`docs/DEPLOYMENT.md`](../../docs/DEPLOYMENT.md) 的 Docker 段。
- `--quick` 个人版扫码流（DM/@bot-only）：本篇只覆盖默认的自建应用流。
- 用户 OAuth（`--as user` 模拟自己发消息）：见 [host_smoke.md](host_smoke.md) §2。
