<p align="center">
  <b>English</b> · <a href="DEPLOYMENT_zh.md">简体中文</a>
</p>

# Deployment Guide

Get a ClaudeTeam crew running — **host or Docker — in 5 steps**. Config,
model-backend, and troubleshooting reference live below the quickstarts.

> **Driving this with a coding agent?** Tell it: *read this doc, then walk me
> through it — and **ask me, never guess** (which agent CLIs? host or Docker? do
> I already have a Feishu app?).* The happy path is 5 commands; the agent's job
> is to pick the right options **with** you and run them.

---

## Before you begin

**Pick a mode first** — and don't run both against the same Feishu chat, or
Feishu silently splits events between the two subscribers.

| | **Host** | **Docker** |
|---|---|---|
| Choose when | your dev machine, fast iteration | headless / server / multi-team |
| Host needs | Python ≥3.10, tmux, node+npx, ≥1 agent CLI | just Docker 20.10+ & Compose v2 |
| State lives in | `~/.claudeteam` (or `./state/`) | `./team-data/` (survives `compose down`) |

**Host prerequisites** (Docker bakes these into the image — skip if you chose Docker):

- **Python ≥ 3.10** — *macOS: the system `/usr/bin/python3` is 3.9, too old →
  `brew install python@3.12` or pyenv. Debian/Ubuntu: also
  `sudo apt install -y python3-venv`, else `venv` errors `ensurepip is not available`.*
- **tmux** — one window per agent.
- **node + npx (18+)** — `lark-cli` (sending) + the `scripts/feishu_channel/`
  sidecar (bot registration + event ingress).
- **≥ 1 agent CLI** on PATH — `claude` / `codex` / `pi` / `opencode` / … (see the
  [adapter table](../README.md#multi-cli-adapter)).
- A **Feishu / Lark enterprise tenant** — `claudeteam init` registers the app for you.

After `up`, `claudeteam health` reports each of these (binaries, env, tmux,
daemons) as ✓/✗ — use it to confirm your setup rather than checking by hand.

---

## Quickstart — Host

```bash
# 1. Code + the `claudeteam` CLI (zero Python deps)
git clone https://github.com/zylMozart/ClaudeTeam.git && cd ClaudeTeam
python3 -m venv .venv && source .venv/bin/activate      # any Python >=3.10
pip install -e .

# 2. External tools on PATH (none are pip-installable) — see "Before you begin":
#    tmux · node+npx · lark-cli (npm i -g @larksuite/cli) · >=1 agent CLI

# 3. Config + bot — register a self-built Feishu app (guided; see "The Feishu bot")
claudeteam init        # writes claudeteam.toml, then walks you through a self-built app:
                       # create it in the console -> click the permission deep-link it prints
                       # -> publish -> paste App ID/Secret. It verifies scopes, creates your
                       # team group, saves creds + chat_id.
                       # Only DM / @bot the bot? -> `claudeteam feishu connect --quick` (one scan).

# 4. Install slash hooks (MUST run before `up`)
claudeteam install-hooks

# 5. Launch + verify
claudeteam up
claudeteam health      # SUCCESS = every line green: binaries, env, tmux, router, watchdog
```

**You're up when** — in your Feishu group the **manager posts a roll-call and
each worker reports in** (the autonomous self-check, [details](#verifying-the-deploy)).
Then send `/health`, then `@manager 你好` → reply in ~30 s. Red `health`? →
[Common failures](#common-failures).

**Tear down:** `claudeteam down` (stop, keep state) · `claudeteam reset` (also wipe state).

---

## Quickstart — Docker

Same 5-step spine. Nothing but Docker on the host — it bind-mounts your Claude
OAuth so the container reuses it.

> **macOS:** start Docker Desktop first (`open -a Docker`, wait for the whale to
> settle). `docker compose` errors `failed to connect to the docker API …` until
> the daemon is up — check with `docker info | grep '^Server:'`.

```bash
# 1. Code + credentials in .env (no browser step in Docker)
git clone https://github.com/zylMozart/ClaudeTeam.git && cd ClaudeTeam
cp .env.example .env
$EDITOR .env           # set FEISHU_APP_ID + FEISHU_APP_SECRET.
                       # No app yet? Register one on a host with `claudeteam feishu connect`,
                       # then copy its values here.

# 2. macOS only — materialise Claude OAuth from keychain (Linux: already a file)
mkdir -p ~/.claude
security find-generic-password -s "Claude Code-credentials" -w > ~/.claude/.credentials.json

# 3. Build + start the container (image bakes the sidecar's node_modules)
docker compose build && docker compose up -d

# 4. Config inside the container (creds come from .env, so --no-connect skips the guided console steps)
docker compose exec --workdir /data claudeteam claudeteam init --no-connect
$EDITOR team-data/claudeteam.toml       # set chat_id + tweak agents
                                        #   no group yet? run `claudeteam feishu connect` on a
                                        #   desktop host to create it, then copy its oc_... here

# 5. Launch + verify
docker compose exec claudeteam claudeteam install-hooks
docker compose exec claudeteam claudeteam up
docker compose exec claudeteam claudeteam health
docker compose exec claudeteam tmux attach -t ClaudeTeam   # watch panes; Ctrl+B d to detach
```

**You're up when** — same as Host: the manager runs the roll-call in the group
and `claudeteam health` is green.

**Compose mounts** (full list in `docker-compose.yml`): `./team-data/`→`/data/`
(config + state), `~/.claude/.credentials.json` (Claude OAuth, RW so refreshes
persist), `~/.codex`/`~/.kimi` (per-CLI creds), `./src/`→`/app/src/` (hot-reload).
The base image bakes in `claude`, `codex`, `kimi` (plus `pi`/`hermes`); `gemini`
and `qwen` are **not** included — derive from `claudeteam:dev` and install those,
or bind-mount the host binary.

**Mount sources must exist before `up -d`.** Docker turns a missing *file*
mount-source (e.g. `~/.claude.json`, `~/.lark-cli/config.json`) into an empty
*directory*, which then breaks the app. On a fresh box, first:
`mkdir -p ~/.codex ~/.kimi ~/.claude/projects ~/.lark-cli/cache && touch ~/.claude.json`,
materialize the Claude OAuth file (Step 2), and **delete any mount line in
`docker-compose.yml` for a CLI you don't run** (e.g. drop `~/.codex`/`~/.kimi`
on a claude-only box).

---

## The Feishu bot (Step 3, in depth)

`claudeteam init` runs `claudeteam feishu connect` for you (on an interactive
TTY). It registers a **self-built app (企业自建应用)** — the only kind Feishu lets
receive **un-@'d group messages** — and walks you through it. The command does
the verifying + group-creation; you do these console steps once:

1. **Create the app** — open <https://open.feishu.cn/app> → 创建企业自建应用 → add
   the **机器人 (bot)** capability → copy the **App ID + App Secret** and paste
   them when the command prompts.
2. **Grant scopes in one click** — the command prints a permission deep-link with
   all 7 scopes pre-selected (including the sensitive `im:message.group_msg`).
   Open it → 确认.
3. **Event** — 事件与回调 → 订阅方式 = **使用长连接** → add the **接收消息** event.
4. **Publish** — 应用发布 → 创建版本 → 申请发布 → **批准** (if you're the tenant
   admin you approve your own version instantly; personal-edition apps skip review).
5. Press **Enter** — the command verifies `im:message.group_msg` landed, creates
   the team group, and saves App creds → `state/feishu_app.json` (0600) + `chat_id`
   → `claudeteam.toml`.

**Why a self-built app, not one-scan:** receiving un-@'d group messages (plain
text + slash commands + catchup recovery) requires the **sensitive**
`im:message.group_msg` scope, which Feishu grants only to a self-built app via
console + admin approval. A one-scan PersonalAgent **can't** get it, so in groups
you'd have to `@` the bot for everything.

> **`--quick` (one-scan, DM/@bot-only):** `claudeteam feishu connect --quick`
> registers a PersonalAgent app via a QR scan — zero console clicks, but in
> groups users must `@` the bot (and catchup can't recover missed group messages).
> Fine if you only DM the bot or always `@` it.

**Docker / scripting:** `claudeteam init --no-connect`, then put
`FEISHU_APP_ID` / `FEISHU_APP_SECRET` into `.env` (env **overrides** the creds
file) and `chat_id` into `team-data/claudeteam.toml`.

Under the hood: a thin `scripts/feishu_channel/` sidecar over the official
[`@larksuite/channel`](https://www.npmjs.com/package/@larksuite/channel) SDK,
used for both registration and the WebSocket event ingress.

---

## Verifying the deploy

**Autonomous self-check (no human input):** on a fresh `up` the manager runs a
team roll-call — announces in the group, summons each worker, and every worker
reports back. **Green = you see the manager's summons plus a report from every
non-retired worker** in the group.

Optional manual probes (type these in the group):

1. `/health` → a card with every agent + router + watchdog green.
2. `/team` → each agent's ♥ heartbeat fresh (< 30 s).
3. `@manager` + a task → reply < 30 s, and dispatched workers post `say` cards.

Anything red → [Common failures](#common-failures).

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

## Model backend per agent (credentials + endpoint)

**A first boot needs none of this** — the 3 default agents run on your Claude
Code OAuth. Come here only when you swap an agent onto a non-Anthropic backend.

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

### `claude: not found` / `codex: not found` in a pane

Panes inherit the launching shell's `$PATH`. If you opened a fresh terminal and
forgot `source .venv/bin/activate`, the pane has no project venv. Re-`up` from a
shell where the agent CLIs resolve.

### "Not logged in" in a claude pane (macOS host)

Each pane has its own `~/.claude/.credentials.json` snapshot (per-agent home
isolation), which can go stale vs the keychain. Fix: `claudeteam down && up`
re-materialises it.

### Container `router` reports `lark-cli failed (rc=2)` and stalls

Catchup tried `--as user` but the container only has bot OAuth. Ensure
`CLAUDETEAM_LARK_SEND_AS=bot` is in `docker-compose.yml`'s `environment:` (the
bundled compose ships it): `docker compose exec claudeteam env | grep CLAUDETEAM_LARK_SEND_AS`.

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
missing, re-run `claudeteam feishu connect`. For Docker, the `.env`
`FEISHU_APP_ID`/`SECRET` **override** the file (`docker compose exec claudeteam env | grep FEISHU_APP_ID`).

### `worker_codex` shows "pane up but CLI not ready yet"

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
