<p align="center">
  <a href="DEPLOYMENT.md">English</a> · <b>简体中文</b>
</p>

# 部署指南

把一个 ClaudeTeam 团队跑起来——**host 或 Docker，5 步搞定**。配置、模型后端、故障
排查参考都在快速开始下面。

> **用 coding agent 来部署？** 告诉它：*读这份文档，然后一步步带我走——而且**要问我、
> 别瞎猜**（用哪些 agent CLI？host 还是 Docker？我是不是已经有飞书 App 了？）。* 顺利
> 路径就 5 条命令；agent 的任务是**和你一起**选对选项再执行。

---

## 开始之前

**先选一种模式**——别拿同一个飞书会话同时跑两种，否则飞书会把事件悄悄分给两个订阅者。

| | **Host** | **Docker** |
|---|---|---|
| 何时选 | 你的开发机、快速迭代 | 无头 / 服务器 / 多团队 |
| 宿主需要 | Python ≥3.10、tmux、node+npx、≥1 个 agent CLI | 只要 Docker 20.10+ 和 Compose v2 |
| 状态存在哪 | `~/.claudeteam`（或 `./state/`） | `./team-data/`（`compose down` 后仍在） |

**Host 前置依赖**（Docker 已把这些烤进镜像——选 Docker 就跳过）：

- **Python ≥ 3.10** —— *macOS：系统自带 `/usr/bin/python3` 是 3.9，太旧 →
  `brew install python@3.12` 或用 pyenv。Debian/Ubuntu：还要
  `sudo apt install -y python3-venv`，否则 `venv` 会报 `ensurepip is not available`。*
- **tmux** —— 每个 agent 一个 window。
- **node + npx (18+)** —— `lark-cli`（发送）+ `scripts/feishu_channel/` sidecar
  （机器人注册 + 事件入站）。
- **PATH 上至少 1 个 agent CLI** —— `claude` / `codex` / `pi` / `opencode` / …
  （见[适配表](../README_zh.md#多-cli-适配)）。
- 一个**飞书 / Lark 企业租户** —— `claudeteam init` 替你注册应用。

`up` 之后，`claudeteam health` 会把这些（binaries、env、tmux、daemons）逐项报
✓/✗——用它确认环境，别手动一个个查。

---

## 快速开始 — Host

```bash
# 1. 代码 + `claudeteam` CLI（零 Python 依赖）
git clone https://github.com/zylMozart/ClaudeTeam.git && cd ClaudeTeam
python3 -m venv .venv && source .venv/bin/activate      # 任意 Python >=3.10
pip install -e .

# 2. PATH 上的外部工具（都不是 pip 能装的）——见“开始之前”：
#    tmux · node+npx · lark-cli (npm i -g @larksuite/cli) · >=1 个 agent CLI

# 3. 配置 + 机器人——注册一个自建飞书应用（引导式；见“飞书机器人”一节）
claudeteam init        # 写 claudeteam.toml，然后带你走一个自建应用：
                       # 在控制台建好 -> 点它打印的权限 deep-link -> 发版 -> 贴 App ID/Secret。
                       # 它会验证权限、建团队群、保存凭证 + chat_id。
                       # 只私聊 / @bot？-> `claudeteam feishu connect --quick`（扫一次码）。

# 4. 装斜杠命令钩子（必须在 `up` 之前）
claudeteam install-hooks

# 5. 启动 + 验证
claudeteam up
claudeteam health      # 成功 = 每行全绿：binaries、env、tmux、router、watchdog
```

**起来了的标志** —— 飞书群里**主管发起全员点名、每个 worker 逐一汇报**（自主自检，
[详见](#验证部署)）。然后发 `/health`，再 `@manager 你好` → 约 30 秒内回复。`health`
有红？→ [常见故障](#常见故障)。

**拆除：** `claudeteam down`（停掉，保留状态）· `claudeteam reset`（连状态一起清）。

---

## 快速开始 — Docker

同样 5 步骨架。宿主上除了 Docker 什么都不要——它会 bind-mount 你的 Claude OAuth，
让容器复用。

> **macOS：** 先启动 Docker Desktop（`open -a Docker`，等鲸鱼图标稳定）。daemon 没起
> 来之前 `docker compose` 会报 `failed to connect to the docker API …`——用
> `docker info | grep '^Server:'` 确认。

```bash
# 1. 代码 + 凭证写进 .env（Docker 没有浏览器步骤）
git clone https://github.com/zylMozart/ClaudeTeam.git && cd ClaudeTeam
cp .env.example .env
$EDITOR .env           # 填 FEISHU_APP_ID + FEISHU_APP_SECRET。
                       # 还没有 App？在一台 host 上用 `claudeteam feishu connect` 注册一个，
                       # 把值复制过来。

# 2. 仅 macOS——把 Claude OAuth 从 keychain 落成文件（Linux：本来就是文件）
mkdir -p ~/.claude
security find-generic-password -s "Claude Code-credentials" -w > ~/.claude/.credentials.json

# 3. 构建 + 启动容器（镜像已烤进 sidecar 的 node_modules）
docker compose build && docker compose up -d

# 4. 容器内配置（凭证来自 .env，所以 --no-connect 跳过引导式控制台步骤）
docker compose exec --workdir /data claudeteam claudeteam init --no-connect
$EDITOR team-data/claudeteam.toml       # 设 chat_id + 调整 agents
                                        #   还没有群？在一台能开浏览器的机器上跑
                                        #   `claudeteam feishu connect` 建群，再把 oc_... 复制过来

# 5. 启动 + 验证
docker compose exec claudeteam claudeteam install-hooks
docker compose exec claudeteam claudeteam up
docker compose exec claudeteam claudeteam health
docker compose exec claudeteam tmux attach -t ClaudeTeam   # 看 pane；Ctrl+B d 脱离
```

**起来了的标志** —— 和 Host 一样：主管在群里跑点名、`claudeteam health` 全绿。

**Compose 挂载**（完整列表见 `docker-compose.yml`）：`./team-data/`→`/data/`
（配置 + 状态）、`~/.claude/.credentials.json`（Claude OAuth，RW 以便刷新持久化）、
`~/.codex`/`~/.kimi`（各 CLI 凭证）、`./src/`→`/app/src/`（热重载）。基础镜像
**刻意不**烤进 `claude`/`codex`/`kimi`——从 `claudeteam:dev` 派生后装你需要的，或把宿主
二进制 bind-mount 进去。

---

## 飞书机器人（第 3 步详解）

`claudeteam init` 会替你跑 `claudeteam feishu connect`（在交互式 TTY 上）。它注册一个
**自建应用（企业自建应用）**——只有这种应用飞书才允许收**群里不 @ 的消息**——并一步步
带你做。验证 + 建群由命令完成；你只需在控制台做一次这几步：

1. **建应用** —— 打开 <https://open.feishu.cn/app> → 创建企业自建应用 →「添加应用能力」
   加**机器人** → 复制 **App ID + App Secret**，命令提示时粘贴进去。
2. **一键授权** —— 命令会打印一条权限 deep-link，已把全部 7 个权限（含敏感的
   `im:message.group_msg`）勾上。打开 → 确认。
3. **事件** —— 事件与回调 → 订阅方式 = **使用长连接** → 添加事件**接收消息**。
4. **发版** —— 应用发布 → 创建版本 → 申请发布 → **批准**（你是租户管理员就能直接批准
   自己的版本；个人版应用免审核）。
5. 按**回车** —— 命令验证 `im:message.group_msg` 已到位、建好团队群、把 App 凭证存到
   `state/feishu_app.json`（0600）+ `chat_id` 写进 `claudeteam.toml`。

**为什么要自建应用、而不是扫一次码：** 收群里不 @ 的消息（普通文字 + 斜杠命令 +
catchup 补漏）需要**敏感权限** `im:message.group_msg`，飞书只在自建应用上、经控制台 +
管理员批准才给。扫一次码的 PersonalAgent **拿不到**，所以群里你得对什么都 `@` 一下机器人。

> **`--quick`（扫一次码，仅私聊 / @bot）：** `claudeteam feishu connect --quick` 用扫码
> 注册一个 PersonalAgent 应用——零控制台点击，但群里用户必须 `@` 机器人（且 catchup
> 没法补漏群里漏掉的消息）。只私聊机器人、或者总是 `@` 它的话，够用。

> **Docker / 脚本化：** `claudeteam init --no-connect`，然后把
> `FEISHU_APP_ID` / `FEISHU_APP_SECRET` 写进 `.env`（env **覆盖**凭证文件）、`chat_id`
> 写进 `team-data/claudeteam.toml`。

底层：`scripts/feishu_channel/` 下一个薄薄的 sidecar，包了官方
[`@larksuite/channel`](https://www.npmjs.com/package/@larksuite/channel) SDK，注册和
WebSocket 事件入站都走它。

---

## 验证部署

**自主自检（无需真人）：** 一次全新的 `up` 之后，主管会跑一轮全员点名——在群里宣布、
逐一召唤每个 worker，每个 worker 各自回报。**绿 = 你在群里看到主管的召唤 + 每个未退休
worker 的汇报**。

可选的手动探针（在群里输入）：

1. `/health` → 一张卡，每个 agent + router + watchdog 都绿。
2. `/team` → 每个 agent 的 ♥ 心跳新鲜（< 30 秒）。
3. `@manager` + 一个任务 → 30 秒内回复，被派单的 worker 发 `say` 卡。

有任何红 → [常见故障](#常见故障)。

---

## 配置：`claudeteam.toml`

单个 TOML 文件（Cargo 风格、可写注释）——`claudeteam init` 生成它，注释就地说明。App 凭证
**不**在这里（它们在 `state/feishu_app.json`）；这里只有 `chat_id` + 团队布局。

```toml
chat_id      = "oc_..."                       # 飞书群 chat_id（由 `feishu connect` 写入）
lark_profile = ""                             # lark-cli profile 名；"" = 默认
default_model = "opus"                        # agent 没指定 model 时的回退

[team]
session = "ClaudeTeam"                        # tmux session 名

[team.agents.manager]
cli = "claude-code"                           # claude-code | codex-cli | gemini-cli | kimi-code | qwen-code
                                              #   | minimax | opencode | codewhale | openclaw | trae | hermes | pi
role = "团队主管"                             # 渲染进 identity.md
model = "opus"
specialty  = ["调度", "审阅"]                 # 可选——manager 派单 prompt 里会看到
tone       = "稳重克制"                       # 可选——影响 LLM 语气
notes      = "always answer in Chinese"       # 可选——自由形式的 prompt 加料
playbook   = "manager.md"                     # 可选——角色指令 .md（→ 该 agent 的 CLAUDE.md/AGENTS.md）
card_color = "blue"
publish_overrides = { worker_to_user = false } # 单 agent 覆盖 [chat.publish]

[chat.publish]                                # 谁对谁可见的群过滤
user_to_manager   = "always"                  # 老板 → 主管（必达）
manager_to_user   = "always"                  # 主管 → 老板（必达）
manager_to_worker = true                      # 群里显示派单卡
worker_to_manager = true                      # 群里显示 worker 进度
worker_to_user    = true                      # 群里显示 worker 完成
worker_to_worker  = true                      # 群里显示 worker 之间的互 ping
```

默认全开（什么都可见）——等团队噪声需要削减时，再把单个键翻成 `false`。**覆盖优先级**
（高者胜）：`env` > `claudeteam.toml` > 代码默认（见 `runtime/tunables.py`）。

**团队模板** —— 与其从零写团队，不如从 [`templates/`](../templates/) 里的领域模板起步
（software-dev / automated-research / marketing-growth / data-analysis / content-ops）：
一个现成的 `claudeteam.toml` + 每个 agent 一份角色 **playbook** `.md`。某个 agent 的
`playbook` 文件会成为它身份的主体——它原生的 `CLAUDE.md` / `AGENTS.md`——叠加在团队协议
之上，于是每个 agent 一上线就知道自己该干什么，而不只是一行头衔。把某个文件夹的内容拷到
你的 `claudeteam.toml` 旁边（`playbook` 路径相对它解析）改一改即可。任何领域都能自己写，
就是一个 `.md`。

---

## 每个 agent 的模型后端（凭证 + 端点）

**首次启动这些都不用** —— 3 个默认 agent 跑在你的 Claude Code OAuth 上。只有当你把某个
agent 切到非 Anthropic 后端时才来看这一节。

适配器是**provider 无关的**——DeepSeek/OpenAI/等等没有任何东西被写死在里面。后端由
env + config 选定：

- **凭证** —— 由 `runtime/agent_auth` 解析，优先级 **token > login > api_key**（高者
  存在就覆盖低者）。密钥放在一个 gitignore 的 env 文件（`$CLAUDETEAM_SECRETS_FILE`，
  默认 `<state_dir>/.env`）或进程 env——**绝不**放 `claudeteam.toml`。单 agent 覆盖：
  `<AGENT>_<VAR>`（例 `WORKER_PI_OPENAI_API_KEY`）。
  - **claude-code / codex / kimi** —— 各自的 token/login/api_key 变量。
  - **其它所有 CLI**（minimax、opencode、codewhale、openclaw、trae、hermes、pi）——
    走 **api_key** 那档：设 `OPENAI_API_KEY`。
- **端点** —— `OPENAI_BASE_URL`（例 `https://api.openai.com/v1` 或一个自建 vLLM/Ollama
  URL——任意 OpenAI 兼容 API）。**模型** —— 每个 `[team.agents.<name>]` 里的 `model` 字段。
- **Provider 名**（仅当某个 CLI 需要它来选一个 OpenAI 兼容的 *chat/completions* 客户端
  时）：`CLAUDETEAM_TRAE_PROVIDER`（默认 `openrouter`）、`CLAUDETEAM_PI_PROVIDER` /
  `CLAUDETEAM_CODEWHALE_PROVIDER`（默认 `openai`）。
- 一个**跑在非 Anthropic 后端上的 claude-code 主管**用 Anthropic 兼容变量：
  `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`（+ `ANTHROPIC_MODEL` /
  `ANTHROPIC_DEFAULT_*_MODEL`）。

示例 —— 把 OpenAI 兼容的 worker（以及可选的、跑在非 Anthropic 后端上的 claude-code
主管）指向**任意** provider，通过 `docker -e` 或宿主 shell。把 host 换成你实际用的
（某个托管 API 或本地 server）：

```bash
OPENAI_BASE_URL=https://your-provider.example/v1   # provider 的 base URL
OPENAI_API_KEY=sk-...                              # 你的 key
# 跑在非 Anthropic 后端上的 claude-code 主管用 Anthropic 兼容变量：
ANTHROPIC_BASE_URL=https://your-provider.example/anthropic
ANTHROPIC_AUTH_TOKEN=sk-...
```

各 CLI 的 `CLAUDETEAM_<CLI>_PROVIDER` 变量（见上）用来选 chat/completions 客户端——
除非你的 provider 需要特定值，否则保持默认即可。各 CLI 的具体配置见
`tests/scenarios/<cli>.md`。

---

## agent 之间通信：`send` vs `say`

| 命令 | 干什么 | 到得了 worker 的 pane 吗？ |
| --- | --- | --- |
| `claudeteam send <to> <from> <msg>` | inbox 记一行 **+** 注入 tmux pane | **是**——直接唤醒收件人 |
| `claudeteam say <agent> "<msg>" --to <role>` | 发进飞书会话（受 `[chat.publish]` 约束） | 仅当 router 把它转回来时 |
| 飞书群 → router → `deliver.apply` | 入站会话 → inbox 一行 + 注入 pane | **是**——老板/主管输入会唤醒 worker |

**`say` 永远带 `--to`**：`--to user` = 回老板；`--to manager` = 内部进度；
`--to worker_<name>` = 同级 ping。不带的话会回退成 `user`，并让 publish 过滤失效。

---

## 多团队隔离

在一台宿主上跑多个团队——给每个团队各自的 state dir + session 名：

```bash
export CLAUDETEAM_STATE_DIR=/path/to/team-a/state && cd /path/to/team-a && claudeteam up
# 另一个 shell：
export CLAUDETEAM_STATE_DIR=/path/to/team-b/state && cd /path/to/team-b && claudeteam up
```

每个团队都需要**自己的飞书 App**（独立的 app_id/secret）——多团队共用一个会导致凭证
泄漏 + 事件路由冲突。`claudeteam switch <team-dir>` 会把 env 导出打印成一行可被 shell
求值的内容。

---

## 命令

**运维 CLI** —— `claudeteam --help` 按分组列出全部（它自维护；比这里任何表都可信）。
日常那几个：`up` / `down` / `health` / `team` / `peek <agent>` / `usage` /
`reidentify` / `remember` / `recall` / `switch`。

**会话侧斜杠命令**（`install-hooks` 之后，在 manager pane 里被识别；老板也能发——它们
零 LLM、经 router 直接派发）：

| 斜杠 | 干什么 |
| --- | --- |
| `/help` | 列出全部斜杠命令（卡片） |
| `/team` | 所有 agent 的 pane 实时状态 |
| `/health` | 服务器 CPU / 内存 / 磁盘 卡片 |
| `/usage` | Token/额度用量（ccusage / codex / kimi） |
| `/tmux [agent] [N]` | 抓某个 pane 的最后 N 行 |
| `/send <agent> <msg>` | 往某个 pane 注入一条消息 |
| `/compact [agent]` | 压缩 CLI 上下文 + 排期重新 identify |
| `/stop [agent]` | 打断 agent（Esc；pane 仍活着） |
| `/clear <agent>` | `/clear` 这个 CLI + 重注入身份 |
| `/task [all]` | 只读任务看板 |
| `/shutdown [confirm]` | pane 下线，保留 router/watchdog 以便 `/restart` |
| `/restart` | 重启整个团队（≈ down→up） |
| `/login <cli> [agent]` | 触发某个 CLI 重新登录；显示验证 URL/码 |

---

## 常见故障

### pane 里 `claude: not found` / `codex: not found`

pane 继承启动它的那个 shell 的 `$PATH`。如果你开了个新终端、忘了
`source .venv/bin/activate`，pane 就没有项目 venv。从一个能解析到 agent CLI 的 shell
重新 `up`。

### claude pane 报 "Not logged in"（macOS host）

每个 pane 有自己的 `~/.claude/.credentials.json` 快照（每 agent 的 home 隔离），它相对
keychain 可能过期。修法：`claudeteam down && up` 重新落一份。

### 容器 `router` 报 `lark-cli failed (rc=2)` 卡住

catchup 试了 `--as user`，但容器只有 bot OAuth。确保 `CLAUDETEAM_LARK_SEND_AS=bot`
在 `docker-compose.yml` 的 `environment:` 里（自带的 compose 已经有）：
`docker compose exec claudeteam env | grep CLAUDETEAM_LARK_SEND_AS`。

### `router.log` 每 ~120 秒打印 "no live events … rotating subscribe"

**通常是正常的、不是故障——尤其 macOS 上。** 空闲会话上 WebSocket 会安静下来；router
自己 self-SIGTERM（`_watch_subscribe_health`），watchdog 重生它，catchup 从飞书 REST
API 把漏掉的重新拉回来——这套恢复循环**就是设计**。平台相关的空闲阈值是 Darwin 120 秒
/ Linux 600 秒（用 toml 里的 `router.stale_event_threshold_s` 或
`CLAUDETEAM_ROUTER_STALE_S` 覆盖）。两种形态：

- `ℹ️ no live events for Ns — rotating subscribe (none inbound yet …)` —— 空闲，预期。
- `⚠️ live events stopped after Ns idle …` —— 事件本来在流、然后停了（值得注意，Linux 上尤其）。

日志永远不会打印 "I received your message"——改信 `claudeteam health` 的 `inbound:` 行
+ 一条真实群消息。如果 `⚠️` *一直*出现，找找是不是有第二个 sidecar 在偷事件：
`ps -ef | grep -E "feishu_channel/sidecar\.js run" | grep -v grep`。

### `up` 后主管在同一条锚定消息上打转

catchup 会重放所有比 cursor 新的消息（带一个 `state/router.seen` 去重集，自动在 5000
条处裁剪）。还在重复？删掉 `state/router.seen`，把 `state/router.cursor` 往前推到
“现在”，让下次 catchup 跳过更旧的。

### pane 里 `say` 报 HTTP 400 "Bot/User can NOT be out of the chat"

从你启动的 shell 里 `say` 能成，但同样的调用从 pane 内部就失败。原因：一个早就存在的
tmux **server**（来自更早一次 `up`、不同 checkout）持有它最初的全局 env，
`tmux new-session` 继承的是*那个*、不是你当前 shell 的。lifecycle 前缀现在已按 spawn-cmd
嵌入凭证，所以干净状态下不该触发。若仍然触发：

```bash
tmux ls 2>/dev/null
ps -ef | grep -E "claudeteam (router|watchdog)|feishu_channel/sidecar\.js" | grep -v grep
claudeteam down
tmux kill-session -t ClaudeTeam        # 没有别的 tmux 活儿就用 `tmux kill-server`
claudeteam up
```

### `say` / sidecar 找不到 App 凭证

出站卡片失败，或 sidecar 退出抱怨没有 app id/secret。凭证只从一个源解析：
`state/feishu_app.json`（由 `feishu connect` 写入，0600），`feishu/lark.py:subprocess_env()`
读它，往 sidecar（入站）和 lark-cli（出站）注入 `FEISHU_APP_ID`/`SECRET` + 一个 tenant
token。`ls -l state/feishu_app.json`（期望 `-rw-------`）；缺了就重跑
`claudeteam feishu connect`。Docker 下，`.env` 的 `FEISHU_APP_ID`/`SECRET` **覆盖**这个
文件（`docker compose exec claudeteam env | grep FEISHU_APP_ID`）。

### `worker_codex` 显示 "pane up but CLI not ready yet"

Codex 有时开机带一个 "update available" 提示，挡住了 ready 标记：

```bash
tmux send-keys -t ClaudeTeam:worker_codex 3 Enter   # "Skip until next version"
claudeteam reidentify worker_codex
```

---

## 文件都在哪

```
src/claudeteam/
├── cli.py             单一 console-scripts 入口；只做派发
├── commands/          每个子命令一个模块（各 ~30-300 LOC）
├── store/             本地文件状态（inbox、status、logs、tasks、memory）
├── agents/            CliAdapter 基类 + 各 CLI 适配器 + 身份渲染
├── runtime/           config / paths / tmux / watchdog / pidlock / wake / lifecycle / tunables
└── feishu/            lark-cli 封装 + chat + router + slash + deliver + subscribe + catchup
scripts/feishu_channel/  @larksuite/channel sidecar（注册 + 入站）
tests/                 unit/ + integration/（stdlib runner）+ scenarios/（运维 playbook）
```

`CLAUDE.md`（项目根）放着开发规则 + 当前工作单——改代码前先读它。

---

## 卡住了？发现 bug？

active development 中——我们**12 小时内回应**。

- 🐛 **GitHub issue** —— [开一个](https://github.com/zylMozart/ClaudeTeam/issues/new/choose)。
  附上 OS、部署模式（host / Docker）、失败命令的输出（`feishu connect` 的问题就附
  sidecar 的 stderr）。
- 💬 **微信社区群** —— 扫 [README](../README_zh.md#遇到问题--提-bug) 里的二维码。

如果你是替用户跑部署的 AI agent、在真正尝试恢复后某步仍失败——把这一节抛给用户，后面
有真人维护者可联系。
