# 飞书一键注册 — `claudeteam feishu connect`（浏览器授权）

## 目的

证明「一次授权 = 建 App + 建群 + 拉人 + 落凭证」这条注册链路真的成立，并且
注册完之后**事件入站走 `scripts/feishu_channel/sidecar.js run`**（官方
WebSocket → NDJSON），群里发一句话 manager 真能收到回。这是 host_smoke 的
**前置**——host_smoke 默认你已经跑过本篇。

覆盖：

- `claudeteam init`（首次部署自动跑 `feishu connect`）/ 或单独 `claudeteam feishu connect`
- 设备授权流程（RFC 8628，官方 `@larksuite/channel` SDK）——浏览器点授权，扫码备选
- 群自动创建 + 把授权人拉进群
- 凭证落盘 `state/feishu_app.json`（0600）+ `chat_id` 写进 `claudeteam.toml`
- `claudeteam up` 后主管自动发起全员点名（自检）
- 群里发消息 → manager 回（证明 sidecar 入站通了）

## 适用范围

- 平台：macOS / Linux 本机部署（host 模式）。Docker 部署不走扫码，App 凭证来自
  `.env`（env 覆盖 `state/feishu_app.json`），不在本篇范围。
- 已装：Python 3.10+、tmux、node + npx、`lark-cli`（出站发卡用）、至少一个
  agent CLI（`claude` / `codex` / …）在 PATH 上。
- 已跑：`pip install -e .`（`claudeteam` 在 PATH 上）。
- 在浏览器点一次「授权」（远程服务器则复制终端里的链接到本地浏览器，或扫码）——
  要真人点一次，agent 代不了。

## 前置条件

```bash
cd /path/to/ClaudeTeam
source .venv/bin/activate
# 若之前已注册过：本篇要验证「从零注册」，先确认没有残留凭证
ls state/feishu_app.json 2>/dev/null && echo "已存在——connect 会跳过；想重测先移走它"
```

> `claudeteam feishu connect` 在 `state/feishu_app.json` 已存在时会跳过注册。
> 要从零重测就先把它移开（`mv state/feishu_app.json /tmp/`）。

## 操作（Given / When / Then）

### 1. 注册（浏览器授权）

**Given** 没有 `state/feishu_app.json`、终端是交互式 TTY，
**When** 跑

```bash
claudeteam init                  # 首次部署：写完 toml 后自动跑 feishu connect
# 或单独：
claudeteam feishu connect
# 跳过扫码（CI / 已有凭证）：claudeteam init --no-connect
```

**Then** 浏览器自动打开飞书授权页；终端也会醒目打印这条授权链接 + 一个二维码
（远程服务器/无浏览器时用）。

> `claudeteam init` 只在交互式 TTY 上自动跑 connect；非 TTY（或带 `--no-connect`）
> 时跳过，凭证已存在时也跳过。

### 2. 真人授权

**Given** 浏览器已弹出授权页（或终端打印了链接 + 二维码），
**When** 在浏览器里点「授权」（或复制链接到浏览器 / 用飞书 App 扫码），
**Then** 进度回到终端继续。

> 只有不支持「一次性开通」的租户上，才会**再弹一次授权页**（授权 IM 权限 +
> 消息事件）——再点一次「授权」即可。支持一次开通的租户只授权一次。

### 3. 落盘核对（机判）

**Given** 授权完成，
**When** 看磁盘，
**Then** 满足全部三条：

```bash
# (a) App 凭证落盘且权限 0600
ls -l state/feishu_app.json          # 期望 -rw-------（0600）
python3 -c "import json; d=json.load(open('state/feishu_app.json')); print('app_id' in d and bool(d.get('app_id')))"
# 期望 True（含 app_id，且非空；app_secret 同理但不要打印出来）

# (b) chat_id 写进 toml
grep -E '^\s*chat_id\s*=\s*"oc_' claudeteam.toml
# 期望命中一行 chat_id = "oc_..."

# (c) 飞书里出现「ClaudeTeam」群、你（授权人）在群里
CHAT=$(grep -E '^\s*chat_id' claudeteam.toml | sed -E 's/.*"(oc_[^"]+)".*/\1/')
LARK_CLI_NO_PROXY=1 lark-cli im +chat-search --query "ClaudeTeam" --as user --format json \
  | python3 -c "import json,sys; print([c.get('chat_id') for c in json.load(sys.stdin).get('data',{}).get('items',[])])"
# 期望列表里含上面的 $CHAT
```

**通过条件**：(a) 文件存在且 mode 是 `-rw-------`；(b) `grep` 命中一行；
(c) 群能搜到且 chat_id 对得上、你在成员里（飞书 App 里直接看群也行）。

### 4. 上线 + 主管点名（自检，全程无需真人）

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

### 5. 入站回环（证明 sidecar 通了）

**Given** 团队已上线，
**When** 在群里发一句带锚定的话，

```bash
ANCHOR="connect-回环-$(date +%s)"
LARK_CLI_NO_PROXY=1 lark-cli im +messages-send \
  --chat-id "$CHAT" --text "@manager 收到请回复 $ANCHOR" --as user
```

**Then** 60 秒内群里能看到 manager 的回复卡，**内容里带 `$ANCHOR`**——证明
`node scripts/feishu_channel/sidecar.js run` 的 WebSocket 入站 → router →
manager 整条链路通了（不是回复以前的消息）。

```bash
# 旁证：sidecar 入站进程在跑
ps -ef | grep -E "feishu_channel/sidecar\.js run" | grep -v grep
# 旁证：health 的 inbound 行从「none observed yet」翻成「last event …」
claudeteam health | grep -i inbound
```

## 期望（一句话）

授权完成后：`state/feishu_app.json`（0600）+ `claudeteam.toml` 的
`chat_id` 都写好、ClaudeTeam 群里有你、`claudeteam up` 全员报到、群里发一句
`@manager` 能在 60 秒内拿到带锚定的回复。

## 失败排查

- **浏览器没打开 / 没打印链接**——确认是交互式 TTY（`claudeteam init` 非 TTY 会跳过 connect）；
  或凭证已存在被跳过（`ls state/feishu_app.json`，想重测先移走）。
- **`state/feishu_app.json` 不是 0600**——connect 写盘权限有问题，重跑 connect；
  出站发卡 / sidecar 都靠 `feishu/lark.py:subprocess_env()` 从这个文件注入
  `FEISHU_APP_ID/SECRET` + tenant token。
- **群没建出来 / 你不在群**——重新授权一次（第二个授权页可能没点到）。
- **报到卡没出现**——`claudeteam health` 看是不是某个 agent 没起；CLI 没登录
  见 [host_smoke.md](host_smoke.md) §1 的排查。
- **§5 manager 不回**——先确认 sidecar 进程在跑（上面那条 `ps`）；再看
  `state/router.log` 是不是 ROUTE 到 manager；inbound 行没翻说明入站没进来，
  查 sidecar stderr。

## 不在范围

- 斜杠命令矩阵 / 普通文本路由 / 反向路由 / catchup / lazy：跑通本篇后看
  [host_smoke.md](host_smoke.md)。
- Docker 部署（凭证走 `.env` 覆盖、入站同样是 sidecar）：见
  [`docs/DEPLOYMENT.md`](../../docs/DEPLOYMENT.md) 的 Docker 段。
- 用户 OAuth（`--as user` 模拟自己发消息）：见 [host_smoke.md](host_smoke.md) §2。
