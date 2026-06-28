<p align="center">
  <b>English</b> · <a href="DEPLOYMENT_zh.md">简体中文</a> · <a href="DEPLOYMENT_docker.md">Docker →</a>
</p>

# Deployment Guide (Host)

Get a ClaudeTeam crew running — **just follow the 4 steps below, top to bottom**.
Config, model-backend, and troubleshooting reference live further down. Deploying
on Docker / a server → see [Docker deploy](DEPLOYMENT_docker.md).

> **Driving this with a coding agent?** Tell it: *read this doc, walk me through
> it; when there's a choice (which agent CLIs? do I already have a Feishu app?)
> **ask me, don't guess**.*

---

## Before you begin

Install these (the bits `pip` can't):

- **Python 3.9+** — macOS's built-in `/usr/bin/python3` (3.9) is fine, nothing
  extra to install. Debian/Ubuntu also needs `sudo apt install -y python3-venv`.
- **tmux** — one window per agent.
- **node + npx (18+)** — runs `lark-cli` (sending) + the Feishu sidecar (bot
  registration + event ingress).
- **≥ 1 agent CLI** — `claude` alone is enough (the default team uses only it);
  mixing in `codex` / `gemini` / `qwen` / … is **optional** (see the
  [adapter table](../README.md#multi-cli-adapter)).
- A **Feishu / Lark account** — a personal one can scan-register; an enterprise
  tenant unlocks "un-@'d in groups".

> 💡 Agents **reuse your existing local login**: if `claude` is logged in on this
> machine, the claude agents use it directly — **no separate login**. Same for any
> other CLI — logged in locally is enough.

---

## Step 1 · Install

```bash
# Code + the claudeteam command (-e = editable install: always tracks your
# checkout, never stuck on a stale version)
git clone https://github.com/zylMozart/ClaudeTeam.git && cd ClaudeTeam
python3 -m venv .venv && source .venv/bin/activate    # macOS's built-in 3.9 is fine
pip install -e .

# External tools pip can't install:
#   macOS:  brew install tmux node && npm i -g @larksuite/cli @anthropic-ai/claude-code
#   Debian: sudo apt install -y tmux nodejs npm && npm i -g @larksuite/cli @anthropic-ai/claude-code
```

> Install only the agent CLIs you'll use. The default team is all `claude-code`,
> so `claude` alone runs it; add `codex` etc. only if you want them.

## Step 2 · Configure your team

```bash
claudeteam init --no-connect      # writes claudeteam.toml (default: manager + 1 claude worker)
$EDITOR claudeteam.toml           # adjust agents to the CLIs you have / are logged into (below)
```

Open `claudeteam.toml`; `[team.agents.*]` is your roster. The default is two
`claude-code` agents — **install claude and it just works**. To add a worker on
another CLI (only if you've **installed + logged into** it), uncomment the example
init wrote and edit it:

```toml
[team.agents.worker_codex]
cli   = "codex-cli"     # add only if you have codex installed; otherwise leave it out
model = "gpt-5.5"
role  = "Codex worker"
```

> Don't want to configure from scratch? [`templates/`](../templates/) has ready
> domain teams (software-dev / research / marketing / data / content) — copy one
> and tweak. `claudeteam reidentify <agent> --print` previews an agent's rendered
> identity before `up`.

## Step 3 · Connect Feishu (tap/scan once → bot + group built)

```bash
claudeteam feishu connect --quick     # prints an auth link (auto-opens browser) + a QR; tap/scan
```

On confirm, Feishu **auto-creates** the bot app + team group (invites you) + creds
+ `chat_id` (written back to `claudeteam.toml`), zero console. The command then
**checks the group-message scope** `im:message.group_msg`:

- ✅ granted (most tenants) → the group works **without @-ing the bot**; you're done.
- ⚠️ your tenant dropped it → the command tells you: `@`-ing the bot in groups
  works; for un-@'d groups, use the guided flow below.

<details>
<summary><b>Guided self-built app</b> (only if <code>--quick</code> didn't get the group scope and you want un-@'d groups)</summary>

`claudeteam feishu connect` (without `--quick`) walks you through the console:

1. **Create the app** — open <https://open.feishu.cn/app> → 创建企业自建应用 → add
   the **机器人 (bot)** capability → copy the **App ID + App Secret**, paste when prompted.
2. **One-click scopes** — click the deep-link it prints (all 7 scopes incl. the
   sensitive `im:message.group_msg` pre-selected) → 确认.
3. **Event** — 事件与回调 → 订阅方式 = **使用长连接** → add the **接收消息** event.
4. **Publish** — 应用发布 → 创建版本 → 申请发布 → **批准** (tenant admins approve their own version instantly; personal-edition apps skip review).
5. Press **Enter** — the command verifies the scope, creates the group, saves creds → `state/feishu_app.json` (0600) + writes `chat_id`.

</details>

> Want one command for Steps 2+3 (default team, no agent edits)?
> `claudeteam init --quick` — writes the default config and connects Feishu in one go.

## Step 4 · Launch + verify

```bash
claudeteam install-hooks      # install slash-command hooks (MUST run before up)
claudeteam up                 # start the tmux crew + router + watchdog
claudeteam health             # infra self-check: binaries / env / tmux / router / watchdog
```

**The real signal is your Feishu group**: on a fresh `up` the manager **posts a
roll-call** and each worker reports in. See that = you're up. Then `@manager 你好`
→ reply in ~30 s.

> ⚠️ **Green `health` ≠ a working team** — it checks infrastructure (processes /
> tmux / daemons), not whether each agent's CLI is actually authenticated. **Go by
> the group roll-call.** No response? Usually an agent CLI isn't logged in on this
> machine (run `claude` to log in) or that CLI isn't installed. Optional manual
> probes (type in the group): `/health` (per-agent + router + watchdog card),
> `/team` (each agent's ♥ heartbeat < 30 s).

**Tear down:** `claudeteam down` (stop, keep state) · `claudeteam reset` (also wipe state).

---

## Configuration: `claudeteam.toml`

Single TOML file (Cargo-style, comment-friendly) — `claudeteam init` writes it,
documented in-place. App creds are **not** here (they live in
`state/feishu_app.json`); only `chat_id` + the team layout.

```toml
chat_id      = "oc_..."                       # Feishu group chat_id (written by `feishu connect`)
lark_profile = ""                             # lark-cli profile name; "" = default
default_model = "opus"                        # fallback when an agent doesn't pin one

[team]
session = "ClaudeTeam"                        # tmux session name

[team.agents.manager]
cli = "claude-code"                           # claude-code | codex-cli | gemini-cli | kimi-code | qwen-code
                                              #   | minimax | opencode | codewhale | openclaw | trae | hermes | pi
role = "团队主管"                             # rendered into identity.md
model = "opus"
specialty  = ["调度", "审阅"]                 # optional — manager sees this in dispatch prompt
tone       = "稳重克制"                       # optional — biases LLM tone
notes      = "always answer in Chinese"       # optional — free-form prompt addendum
playbook   = "manager.md"                     # optional — a role-instruction .md (→ its CLAUDE.md/AGENTS.md)
card_color = "blue"
publish_overrides = { worker_to_user = false } # per-agent override of [chat.publish]

[chat.publish]                                # who-talks-to-whom group filter
user_to_manager   = "always"                  # boss → manager (always lands)
manager_to_user   = "always"                  # manager → boss (always lands)
manager_to_worker = true                      # show dispatch cards in group
worker_to_manager = true                      # show worker progress in group
worker_to_user    = true                      # show worker completions in group
worker_to_worker  = true                      # show inter-worker pings in group
```

Defaults are wide open (everything visible) — flip individual keys to `false`
once the team's noise level needs trimming. **Override precedence** (highest
wins): `env` > `claudeteam.toml` > code default (see `runtime/tunables.py`).

**Team templates** — instead of hand-writing the roster, start from a domain
template in [`templates/`](../templates/) (software-dev, automated-research,
marketing-growth, data-analysis, content-ops): a ready `claudeteam.toml` plus a
per-role **playbook** `.md` per agent. An agent's `playbook` file becomes the bulk
of its identity — its native `CLAUDE.md` / `AGENTS.md` — layered on top of the team
protocol, so each shows up knowing its job, not just a one-line title. Copy a
folder's contents next to your `claudeteam.toml` (the `playbook` paths resolve
relative to it) and adapt. Write your own for any domain — it's just a `.md`.
Preview what an agent will get with `claudeteam reidentify <agent> --print` — it
renders that agent's identity (role + playbook + team protocol) to stdout, no live
team needed, so you can check a config or playbook edit before `up`.

---

## Agent CLIs

Each agent runs a coding CLI — install the ones you'll use (ClaudeTeam just needs it on PATH).
The default team is all `claude-code`, so `claude` alone runs it.

| Adapter | `cli` | Install |
| ------- | ----- | ------- |
| Claude Code | `claude-code` | `npm i -g @anthropic-ai/claude-code` |
| Codex CLI | `codex-cli` | `npm i -g @openai/codex` |
| Kimi Code | `kimi-code` | `uv tool install kimi-cli` |
| Gemini CLI | `gemini-cli` | `npm i -g @google/gemini-cli` |
| Qwen Code | `qwen-code` | `npm i -g qwen-code` |
| MiniMax Mini-Agent | `minimax` | `uv tool install "git+https://github.com/MiniMax-AI/Mini-Agent.git"` |
| opencode | `opencode` | `npm i -g opencode-ai` |
| CodeWhale | `codewhale` | `npm i -g codewhale` |
| OpenClaw | `openclaw` | `npm i -g openclaw` · needs Node ≥ 22 |
| Trae | `trae` | `uv tool install --with docker --with pexpect "git+https://github.com/bytedance/trae-agent.git"` |
| Hermes | `hermes` | `curl -fsSL https://hermes-agent.nousresearch.com/install.sh \| bash -s -- --skip-setup` |
| Pi | `pi` | `npm i -g @mariozechner/pi-coding-agent` |

The last seven are **OpenAI-compatible** (BYOK) — credentials + endpoint below.

---

## Model backend per agent (credentials + endpoint)

**A first boot needs none of this** — the 2 default agents run on your Claude
Code OAuth (reusing your local login). Come here only when you swap an agent onto
a non-Anthropic backend.

The adapters are **provider-agnostic** — nothing about DeepSeek/OpenAI/etc. is
baked in. You choose the backend through env + config:

- **Credential** — resolved by `runtime/agent_auth`, priority **token > login >
  api_key** (higher present overrides lower). Secrets live in a gitignored env
  file (`$CLAUDETEAM_SECRETS_FILE`, default `<state_dir>/.env`) or the process
  env — never in `claudeteam.toml`. Per-agent override: `<AGENT>_<VAR>` (e.g.
  `WORKER_PI_OPENAI_API_KEY`).
  - **claude-code / codex / kimi** — their own token/login/api_key vars.
  - **all other CLIs** (minimax, opencode, codewhale, openclaw, trae, hermes, pi)
    — the **api_key** tier: set `OPENAI_API_KEY`.
- **Endpoint** — `OPENAI_BASE_URL` (e.g. `https://api.openai.com/v1` or a
  self-hosted vLLM/Ollama URL — any OpenAI-compatible API). **Model** — the
  `model` field in each `[team.agents.<name>]`.
- **Provider name** (only where a CLI needs one selecting an OpenAI-compatible
  *chat/completions* client): `CLAUDETEAM_TRAE_PROVIDER` (default `openrouter`),
  `CLAUDETEAM_PI_PROVIDER` / `CLAUDETEAM_CODEWHALE_PROVIDER` (default `openai`).
- A **claude-code manager on a non-Anthropic backend** uses the
  Anthropic-compatible vars: `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`
  (+ `ANTHROPIC_MODEL` / `ANTHROPIC_DEFAULT_*_MODEL`).

Example — point the OpenAI-compatible workers (and, optionally, a claude-code
manager on a non-Anthropic backend) at **any** provider, via `docker -e` or the
host shell. Swap the host for whatever you use (a hosted API or a local server):

```bash
OPENAI_BASE_URL=https://your-provider.example/v1   # the provider's base URL
OPENAI_API_KEY=sk-...                              # your key for it
# a claude-code manager on a non-Anthropic backend uses the Anthropic-compatible vars:
ANTHROPIC_BASE_URL=https://your-provider.example/anthropic
ANTHROPIC_AUTH_TOKEN=sk-...
```

The per-CLI `CLAUDETEAM_<CLI>_PROVIDER` vars (see above) pick the
chat/completions client — leave them at their defaults unless your provider needs
a specific one. See each CLI's `tests/scenarios/<cli>.md` for concrete, per-provider specifics.

---

## Agents talking to each other: `send` vs `say`

| Command | What it does | Reaches the worker's pane? |
| --- | --- | --- |
| `claudeteam send <to> <from> <msg>` | Inbox row **+** tmux pane inject | **Yes** — wakes the recipient directly |
| `claudeteam say <agent> "<msg>" --to <role>` | Post into Feishu chat (subject to `[chat.publish]`) | Only if the router relays it back |
| Feishu group → router → `deliver.apply` | Inbound chat → inbox row + pane inject | **Yes** — wakes a worker on boss/manager input |

**Always pass `--to`** on `say`: `--to user` = answering the boss; `--to manager`
= internal progress; `--to worker_<name>` = peer ping. Omitting it falls back to
`user` and defeats the publish filter.

---

## Multi-team isolation

Run multiple teams on one host by giving each its own state dir + session name:

```bash
export CLAUDETEAM_STATE_DIR=/path/to/team-a/state && cd /path/to/team-a && claudeteam up
# different shell:
export CLAUDETEAM_STATE_DIR=/path/to/team-b/state && cd /path/to/team-b && claudeteam up
```

Each team needs its **own Feishu app** (independent app_id/secret) — sharing one
across teams causes credential leakage + event-routing conflicts.
`claudeteam switch <team-dir>` prints the env exports as one shell-evaluable line.

---

## Commands

**Operator CLI** — `claudeteam --help` lists everything grouped by section (it's
self-maintaining; trust it over any table here). The everyday ones: `up` / `down`
/ `health` / `team` / `peek <agent>` / `usage` / `reidentify` / `remember` /
`recall` / `switch`.

**Chat-side slash commands** (after `install-hooks`, recognised in the manager
pane; the boss can also send them — they zero-LLM dispatch through the router):

| Slash | What it does |
| --- | --- |
| `/help` | List all slash commands (card) |
| `/team` | All agents' live pane state |
| `/health` | Server CPU / memory / disk card |
| `/usage` | Token/credit usage (ccusage / codex / kimi) |
| `/tmux [agent] [N]` | Capture last N lines of a pane |
| `/send <agent> <msg>` | Inject a message into a pane |
| `/compact [agent]` | Compact the CLI's context + scheduled re-identify |
| `/stop [agent]` | Interrupt the agent (Esc; pane stays alive) |
| `/clear <agent>` | `/clear` the CLI + re-inject identity |
| `/task [all]` | Read-only task kanban |
| `/shutdown [confirm]` | Panes offline, keep router/watchdog for `/restart` |
| `/restart` | Restart the whole team (≈ down→up) |
| `/login <cli> [agent]` | Trigger a CLI re-auth; surfaces the verification URL/code |

---

## Common failures

### `claudeteam feishu connect` hangs / says "cancelled"

A non-interactive terminal (piped / non-TTY) or a Ctrl-C gives "cancelled (no
input / non-interactive terminal)" — re-run it in an **interactive** terminal.
`--quick` prints the link + QR before waiting for your confirm; if the browser
didn't auto-open, click the link the terminal printed.

### `claude: not found` / `codex: not found` in a pane

Panes inherit the launching shell's `$PATH`. If you opened a fresh terminal and
forgot `source .venv/bin/activate`, the pane has no project venv. Re-`up` from a
shell where the agent CLIs resolve.

### "Not logged in" in a claude pane (macOS host)

Each pane has its own `~/.claude/.credentials.json` snapshot (seeded from your
local login, per-agent home isolation), which can go stale vs the keychain. Fix:
`claudeteam down && up` re-materialises it.

### `router.log` shows "no live events … rotating subscribe" every ~120 s

**Usually NORMAL, not a fault — especially on macOS.** On an idle chat the
WebSocket goes quiet; the router self-SIGTERMs (`_watch_subscribe_health`),
watchdog respawns it, and catchup refetches anything missed from Feishu's REST
API — the recovery loop *is* the design. The platform-aware idle threshold is
Darwin 120 s / Linux 600 s (override `router.stale_event_threshold_s` in the toml
or `CLAUDETEAM_ROUTER_STALE_S`). Two shapes:

- `ℹ️ no live events for Ns — rotating subscribe (none inbound yet …)` — idle, expected.
- `⚠️ live events stopped after Ns idle …` — events WERE flowing and stopped (notable, esp. on Linux).

The log never prints "I received your message" — trust `claudeteam health`'s
`inbound:` line + one real group message instead. If the `⚠️` is *constant*,
look for a second sidecar stealing events:
`ps -ef | grep -E "feishu_channel/sidecar\.js run" | grep -v grep`.

### Manager loops on the same anchored message after `up`

Catchup replays everything newer than the cursor (with a `state/router.seen`
dedup set, auto-trimmed at 5000). Still duplicating? Delete `state/router.seen`
and bump `state/router.cursor` forward to "now" so the next catchup skips older.

### `say` from a pane fails HTTP 400 "Bot/User can NOT be out of the chat"

`say` from your launching shell works, but the same call from inside a pane
fails. Cause: a pre-existing tmux **server** (from an earlier `up`, different
checkout) holds its original global env, and `tmux new-session` inherits *that*,
not your shell's. The lifecycle prefix now embeds the creds per spawn-cmd, so a
clean state shouldn't trigger it. If it still does:

```bash
tmux ls 2>/dev/null
ps -ef | grep -E "claudeteam (router|watchdog)|feishu_channel/sidecar\.js" | grep -v grep
claudeteam down
tmux kill-session -t ClaudeTeam        # or `tmux kill-server` if no other tmux work
claudeteam up
```

### `say` / sidecar can't find App credentials

Outbound cards fail, or the sidecar exits complaining it has no app id/secret.
Creds resolve from one source: `state/feishu_app.json` (written by
`feishu connect`, 0600), which `feishu/lark.py:subprocess_env()` reads to inject
`FEISHU_APP_ID`/`SECRET` + a tenant token into both the sidecar (ingress) and
lark-cli (egress). `ls -l state/feishu_app.json` (expect `-rw-------`); if
missing, re-run `claudeteam feishu connect`.

### `worker_codex` (or any codex agent) shows "pane up but CLI not ready yet"

Codex sometimes opens with an "update available" prompt blocking the ready marker:

```bash
tmux send-keys -t ClaudeTeam:worker_codex 3 Enter   # "Skip until next version"
claudeteam reidentify worker_codex
```

---

## Where things live

```
src/claudeteam/
├── cli.py             single console-scripts entry; dispatch only
├── commands/          one module per subcommand (~30-300 LOC each)
├── store/             local file-backed state (inbox, status, logs, tasks, memory)
├── agents/            CliAdapter base + per-CLI adapters + identity renderer
├── runtime/           config / paths / tmux / watchdog / pidlock / wake / lifecycle / tunables
└── feishu/            lark-cli wrapper + chat + router + slash + deliver + subscribe + catchup
scripts/feishu_channel/  the @larksuite/channel sidecar (registration + ingress)
tests/                 unit/ + integration/ (stdlib runner) + scenarios/ (operator playbooks)
```

`CLAUDE.md` (project root) holds the building rules + active work order — read it
before changing code.

---

## Stuck? Found a bug?

Under active development — we **respond within 12 hours**.

- 🐛 **GitHub issue** — [open one](https://github.com/zylMozart/ClaudeTeam/issues/new/choose).
  Include OS, deploy mode (host vs Docker), and the failing command's output (for
  `feishu connect` issues, the sidecar's stderr).
- 💬 **WeChat community group** — scan the QR in the [README](../README.md#need-help--found-a-bug).

If you're an AI agent driving a deploy and a step fails after a real recovery
attempt, surface this section to the user — there's a real maintainer reachable.
