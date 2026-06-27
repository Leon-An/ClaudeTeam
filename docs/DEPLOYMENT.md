# Deployment Guide

End-to-end setup for ClaudeTeam. Covers host-native, Docker, config,
multi-team isolation, and common failures.

## Bringing up a team end-to-end

Whether you're a human reading this or an AI agent driving the
deployment, the flow is the same:

1. **Feishu app + group** — run `claudeteam feishu connect` (or `claudeteam init`, which calls it). A browser opens to the Feishu auth page — click approve (or open the printed link / scan the QR). That creates the app, grants its IM scopes + message event, auto-creates the team group with you in it, and saves the App creds (`state/feishu_app.json`, 0600) + `chat_id` (`claudeteam.toml`). Already have an app? Put its App ID / Secret / chat_id into those files (or `.env` for Docker) and skip it.
2. **Host or Docker** — Docker is simplest (`docker compose`, no host Python); host iterates faster but needs Python 3.10+, tmux, and the agent CLIs locally. Both are covered below.
3. **Config** — `feishu connect` already wrote `chat_id`; `claudeteam init` generated the rest of `claudeteam.toml` with three default agents (`manager` + `worker_cc` on Claude Code, `worker_codex` on Codex). Keep them for a quick smoke or edit `[team.agents.*]` first. (Bot creds live in `state/feishu_app.json`, never the toml; only Docker/advanced deploys override via `FEISHU_APP_ID`/`FEISHU_APP_SECRET` in `.env`.)
4. **Launch** — `claudeteam up`, then `claudeteam health` (expect all green).
5. **Verify (autonomous — no human)** — on a fresh `up` the manager runs a team roll-call: it announces in the group, summons every worker, and each worker reports back. Verification passes when you see the manager's summons plus every worker reporting.
6. **If anything goes red** — see [Common failures](#common-failures): Claude OAuth stale, container env not picked up, WebSocket drop, codex update prompt, etc.

---

## Prerequisites


| Requirement      | Version | Why                                                                                                                                                                                                                   |
| ---------------- | ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Python           | 3.10+   | `pyproject.toml` pins `requires-python = ">=3.10"`                                                                                                                                                                    |
| `python3-venv`   | apt pkg | **Debian/Ubuntu only**: not bundled with system `python3`. Without it `python3 -m venv .venv` errors `ensurepip is not available`. Install: `sudo apt install -y python3.12-venv` (match your python3 minor version). |
| tmux             | any     | every agent runs in its own tmux window                                                                                                                                                                               |
| Node.js + npx    | 18+     | `lark-cli` (egress) + the `scripts/feishu_channel/` sidecar (registration + ingress) are node                                                                                                                         |
| At least one CLI | latest  | `claude` / `codex` / `kimi` / `gemini` / `qwen` (whichever your team uses)                                                                                                                                            |
| Feishu (Lark)    | any     | enterprise tenant; `claudeteam feishu connect` creates the app + grants `im:message` + WebSocket event                                                                                                          |


**Feishu app setup**: run `claudeteam feishu connect` (or just
`claudeteam init`, which calls it) — a browser opens to the auth page; click
approve (or open the printed link / scan the QR). That one device-flow approval
creates the app, grants the IM scopes + message event, auto-creates the team
group, and saves the creds to `state/feishu_app.json`. See the
[Bringing up a team](#bringing-up-a-team-end-to-end) walkthrough above.

Optional but recommended:

- `lark-cli` installed globally (`npm i -g @larksuite/cli`) — saves
  ~250 ms per invocation vs the `npx` fallback.

---

## Two deployment modes


| Mode       | When                                               | Notes                                                                                                                              |
| ---------- | -------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| **Host**   | macOS / Linux dev machine, you want fast iteration | `lark-cli` OAuth in your shell keychain, agent state under `./state/`                                                              |
| **Docker** | Headless / CI / multi-team isolation               | Image bundles Python + tmux + node; CLIs (claude/codex/...) you install yourself in a derived image, OR bind-mount the host binary |


Pick one and stick with it for a given Feishu chat — running both
against the same chat causes lark to silently split events between
the two subscribers. See `tests/scenarios/host_smoke.md` §8 for the
gory details.

---

## Host deploy (4 steps)

Needs **Python ≥ 3.10**, **tmux**, and **at least one agent CLI** (claude / codex / …) on PATH. No env exports — `claudeteam init` writes the `send_as` / `no_proxy` presets into `claudeteam.toml`, and state defaults to `~/.claudeteam`.

```bash
cd /path/to/ClaudeTeam

# 1. install the CLI (any Python >=3.10 — venv, conda, or pyenv all work)
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. create config + register the bot. A browser opens to the auth page —
#    just click approve (or open the link it prints / scan the QR). Creates
#    the app, auto-creates the team group, adds you, saves creds + chat_id.
#    (Already have an app, or scripting? add --no-connect.)
claudeteam init

# 3. install the slash hooks — must run BEFORE `up`
claudeteam install-hooks

# 4. launch, then verify
claudeteam up
claudeteam health
```

> **macOS:** the system `/usr/bin/python3` (3.9) is too old — install a newer one
> (`brew install python@3.12`) or use pyenv / conda. If `claudeteam` already
> resolves on PATH (e.g. via conda), skip the venv — just keep the agent CLIs on
> the same PATH.

**Tear down:** `claudeteam down` (stop, keep state) · `claudeteam reset` (also wipe state).

---

## Docker deploy

You don't need Python or `claudeteam` on the host — everything runs
in the container. The host only needs Docker + the host's
`~/.claude/.credentials.json` (extracted from macOS keychain on Mac
hosts) so the container can reuse your Claude OAuth.

> **macOS prereq:** Docker Desktop must be running before any
> `docker compose` command. `docker --version` succeeds whether the
> daemon is up or not, but every other command surfaces
> `failed to connect to the docker API at unix:///...docker.sock`
> until you `open -a Docker` and wait ~30 s for the whale icon to
> stop animating. Verify with `docker info | grep '^Server:'` —
> the Server section is missing when the daemon's down.

```bash
# 1. supply the app creds in .env (no QR in Docker). Don't have an app yet?
#    Register one on a host first with `claudeteam feishu connect`, then copy
#    its FEISHU_APP_ID / SECRET here.
cp .env.example .env
$EDITOR .env                    # set FEISHU_APP_ID + FEISHU_APP_SECRET

# 2. macOS only — materialise Claude OAuth from keychain into a file
#    the container can bind-mount. Skip on Linux (file is already there).
mkdir -p ~/.claude
security find-generic-password -s "Claude Code-credentials" -w \
  > ~/.claude/.credentials.json

# 3. build the image and start the container (the image bakes the
#    scripts/feishu_channel sidecar's node_modules for ingress)
docker compose build
docker compose up -d

# 4. bootstrap config inside the container (output lands in ./team-data/).
#    --no-connect because the QR scan is a host/TTY step; the app creds
#    come from .env in Docker.
docker compose exec --workdir /data claudeteam claudeteam init --no-connect
$EDITOR team-data/claudeteam.toml    # set chat_id + agents

# 5. launch the team + verify
docker compose exec claudeteam claudeteam install-hooks
docker compose exec claudeteam claudeteam up
docker compose exec claudeteam claudeteam health
docker compose exec claudeteam tmux attach -t ClaudeTeam   # see panes; Ctrl+B d to leave
```

> **macOS subscribe stalls (handled automatically):**
> On macOS — both Docker Desktop (`network_mode: host` partially
> emulated) and host-native — the WebSocket event stream can silent-drop:
> the sidecar child stays alive but stops delivering events. The router's
> `_watch_subscribe_health` thread detects this via the
> `router.stale_event_threshold_s` deadline and self-SIGTERMs for a
> watchdog respawn; catchup-on-restart then refetches the missed events
> from Feishu's REST API.
>
> The default threshold is **platform-aware**: Darwin → 120 s, Linux →
> 600 s. Linux WebSocket is stable so the looser default avoids
> respawning quiet chats; macOS gets a tighter default so the recovery
> loop completes in ~2 min instead of ~10. Override via toml
> (`router.stale_event_threshold_s = N`) or env (`CLAUDETEAM_ROUTER_STALE_S=N`)
> if your network warrants it.

**Compose mounts (read `docker-compose.yml` for the full list):**


| Host path                     | Container path                    | Purpose                                                                                                          |
| ----------------------------- | --------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `./src/`                      | `/app/src/`                       | Hot-reload: edit on host, container picks up next invocation                                                     |
| `./team-data/`                | `/data/`                          | `claudeteam.toml` + state survives `docker compose down`                                                         |
| `~/.lark-cli/config.json`     | `/root/.lark-cli/config.json`     | OAuth profile reused (file mount only — locks/ stays container-private to avoid host/container fcntl contention) |
| `~/.claude/.credentials.json` | `/root/.claude/.credentials.json` | Claude OAuth (RW so token refreshes persist back)                                                                |
| `~/.codex` / `~/.kimi`        | `/root/.codex` / `/root/.kimi`    | Per-CLI credentials                                                                                              |


The base image deliberately does **not** bake in `claude` / `codex` /
`kimi` — each has its own auth and license. Derive from `claudeteam:dev`
and `RUN` the install you actually need, or bind-mount the host binary
into the container's `$PATH`.

---

## Configuration: `claudeteam.toml`

Single TOML file (Cargo-style) replaces the old `team.json` +
`runtime_config.json`. Comment-friendly, documented in-place by
`claudeteam init`'s template.

Key sections:

```toml
chat_id      = "oc_..."                       # Feishu group chat_id
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

Defaults are wide open (everything visible) — flip individual keys
to `false` once the team's noise level needs trimming.

**Override precedence** (highest wins): `env` > `claudeteam.toml` > code default.
See `src/claudeteam/runtime/tunables.py` for the cascade.

---

## Model backend per agent (credentials + endpoint)

The adapters are **provider-agnostic** — nothing about DeepSeek/OpenAI/etc. is
baked into the code. You choose the backend through env + config:

- **Credential** is resolved by `runtime/agent_auth` with a fixed priority:
**long-term token > interactive login > API key** (a higher one present
overrides the lower). Secrets live in a gitignored env file
(`$CLAUDETEAM_SECRETS_FILE`, default `<state_dir>/.env`) — or the process env
— never in `claudeteam.toml`. Per-agent overrides use `<AGENT>_<VAR>`
(e.g. `WORKER_PI_OPENAI_API_KEY`).
  - **claude-code / codex / kimi**: their own token/login/api_key vars.
  - **All other CLIs** (minimax, opencode, codewhale, openclaw, trae, hermes,
  pi): the **API-key** tier — set `OPENAI_API_KEY`.
- **Endpoint**: set `OPENAI_BASE_URL` to your OpenAI-compatible endpoint
(e.g. `https://api.openai.com/v1`, a self-hosted vLLM/Ollama URL, or
`https://api.deepseek.com/v1`). **Model**: the `model` field in each agent's
`[team.agents.<name>]`.
- **Provider name** (only where a CLI needs one that selects an
OpenAI-compatible *chat/completions* client): override per CLI —
`CLAUDETEAM_TRAE_PROVIDER` (default `openrouter`),
`CLAUDETEAM_PI_PROVIDER` / `CLAUDETEAM_CODEWHALE_PROVIDER` (default `openai`).
- The **claude-code manager on a non-Anthropic backend** uses the
Anthropic-compatible vars instead: `ANTHROPIC_BASE_URL` +
`ANTHROPIC_AUTH_TOKEN` (+ `ANTHROPIC_MODEL` / `ANTHROPIC_DEFAULT_*_MODEL`).

Example (DeepSeek, via `docker -e` or the host shell):

```bash
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_API_KEY=sk-...                     # your DeepSeek key
CLAUDETEAM_TRAE_PROVIDER=openrouter        # chat/completions client
CLAUDETEAM_PI_PROVIDER=deepseek            # Pi's native DeepSeek provider
CLAUDETEAM_CODEWHALE_PROVIDER=deepseek
# manager (claude-code) on DeepSeek's Anthropic endpoint:
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
ANTHROPIC_AUTH_TOKEN=sk-...
```

See each CLI's `tests/scenarios/<cli>.md` for its specifics.

---

## Agents talking to each other: `send` vs `say`


| Command                                      | What it does                                        | Reaches the worker's tmux pane?                |
| -------------------------------------------- | --------------------------------------------------- | ---------------------------------------------- |
| `claudeteam send <to> <from> <msg>`          | Append a row to local `inbox.json`                  | **No** — only `claudeteam inbox <to>` reads it |
| `claudeteam say <agent> "<msg>" --to <role>` | Post into Feishu chat (subject to `[chat.publish]`) | Only if router relays it back                  |
| Feishu group → router → `deliver.apply`      | Inbound chat → inbox row + tmux pane inject         | **Yes** — the only path that wakes a worker    |


**Always pass `--to`** on `say`. `--to user` = answering the boss;
`--to manager` = internal progress; `--to worker_<name>` = peer ping.
Skipping `--to` falls back to `user` for backwards compat but
defeats the publish filter.

---

## Multi-team isolation

Run multiple teams on one host by giving each its own state dir +
session name:

```bash
# team A
export CLAUDETEAM_STATE_DIR=/path/to/team-a/state
cd /path/to/team-a
claudeteam up   # session "TeamA"

# team B (different shell)
export CLAUDETEAM_STATE_DIR=/path/to/team-b/state
cd /path/to/team-b
claudeteam up   # session "TeamB"
```

Each team needs its **own Feishu app** (independent app_id/secret) —
sharing one app across teams causes credential leakage and event
routing conflicts. `claudeteam switch <team-dir>` emits the env
exports as one shell-evaluable line if you switch shells often.

---

## Slash commands (chat-side)

After `claudeteam install-hooks`, the manager pane recognises these:


| Slash                  | What it does                                                                              |
| ---------------------- | ----------------------------------------------------------------------------------------- |
| `/help`                | List all slash commands (card)                                                            |
| `/team`                | All agents' live pane state (marker-free probe)                                           |
| `/health`              | Server CPU / memory / disk card                                                           |
| `/usage`               | Token/credit usage (claude ccusage / codex / kimi)                                        |
| `/tmux [agent] [N]`    | Capture last N lines of an agent's pane                                                   |
| `/send <agent> <msg>`  | Inject a message into the agent's pane                                                    |
| `/compact [agent]`     | Compact the CLI's context (gemini/qwen send `/compress`) + scheduled re-identify          |
| `/stop [agent]`        | Interrupt the agent's current action (sends Esc; pane stays alive)                        |
| `/clear <agent>`       | `/clear` the CLI + re-inject identity (rehire shape)                                      |
| `/task [all]`          | Read-only task kanban                                                                     |
| `/shutdown [confirm]`  | Take agent panes offline, keep router/watchdog for `/restart` (two-step)                  |
| `/restart`             | Restart the whole team (≈ down→up)                                                        |
| `/login <cli> [agent]` | Trigger a CLI's re-auth; surfaces the verification URL/code (gated by `controls.allow_`*) |


Boss can also send these from chat — they zero-LLM dispatch through
the router, no manager round-trip.

---

## Verifying the deploy

**Autonomous e2e check (no human input):** on a fresh `claudeteam up` the manager runs a team roll-call — it announces in the group, summons every worker, and each worker reports back. The deploy is green when you see the manager's summons plus a report from every non-retired worker in the group.

Optional manual probes (you type these in the group):
1. `/health` → a card listing every agent + router + watchdog as green.
2. `/team` → each agent's heartbeat fresh (♥ < 30 s).
3. `@manager` + a task → manager replies < 30 s and (if it dispatches) worker `say` cards land in the group.

If any fail, see [Common failures](#common-failures) below.

---

## Common failures

### "claude: not found" / "codex: not found" in pane

CLI adapter looks up the binary on `$PATH`. Spawned panes inherit
your launching shell's PATH. If you started a fresh terminal and
forgot to `source .venv/bin/activate`, the pane has no project venv.

### "Not logged in" in claude pane (macOS host)

Claude Code stores OAuth in macOS keychain. Per-agent home isolation
means each pane has its own `~/.claude/.credentials.json` snapshot,
which goes stale. Fix: `claudeteam down && claudeteam up` re-materialises
from keychain.

### Container `router` reports `lark-cli failed (rc=2)` and stalls

Catchup tried to use `--as user` but the container only has bot
OAuth. Make sure `docker-compose.yml` has `CLAUDETEAM_LARK_SEND_AS=bot`
in its `environment:` block (the bundled compose file ships with this).
Verify inside the container:

```bash
docker compose exec claudeteam env | grep CLAUDETEAM_LARK_SEND_AS
```

### `router.log` shows "no live events … rotating subscribe" every ~120s

**This is usually NORMAL, not a fault — especially on macOS.** On an
idle chat the live WebSocket goes quiet; the router self-SIGTERMs via
`_watch_subscribe_health`, watchdog respawns it, and catchup-on-restart
refetches anything missed from Feishu's REST API. The recovery loop *is*
the design. Two log shapes distinguish the cases:

- `ℹ️ no live events for Ns — rotating subscribe (none inbound yet this session …)` — idle, no traffic yet. Expected; ignore.
- `⚠️ live events stopped after Ns idle …` — events WERE flowing and
stopped. More notable (esp. on Linux, where the WS is meant to be
stable).

**Don't trust the log to tell you inbound works — it never prints "I
received your message".** The at-a-glance truth is `claudeteam health`'s
`inbound:` line ("none observed yet" → "last event …") plus one real
human message in the group (see the verify step above). If the `⚠️`
variant is *constant*, check for a second sidecar WebSocket stealing
events (host vs container, or a stale orphan):

```bash
ps -ef | grep -E "feishu_channel/sidecar\.js run" | grep -v grep
```

### Manager loops on the same anchored message after `claudeteam up`

Catchup replays everything newer than the cursor; the daemon also
keeps a `state/router.seen` dedup set persisted across restarts (auto
truncates at 5000 entries). If you still see duplicates, deleting
`state/router.seen` and bumping the cursor in `state/router.cursor`
forward to "now" makes the next catchup skip everything older.

### `claudeteam say` from a pane fails HTTP 400 "Bot/User can NOT be out of the chat"

Symptom: `claudeteam say` from your launching shell **works**, but the
exact same call from inside an agent pane (manager / worker_*) returns
the HTTP 400 above. The cause: a pre-existing tmux
**server** started by an earlier `claudeteam up` (different checkout,
or a session you forgot you had) holds onto its original global env.
`tmux new-session` attaches to that server and inherits *its* env, not
your launching shell's.

The lifecycle prefix now embeds `FEISHU_APP_ID/SECRET` +
`LARKSUITE_CLI_APP_`* + `CLAUDETEAM_STATE_DIR` directly into each
spawn-cmd, so this should no longer trigger from a clean state. If you
still see it, the orphan-tmux trap is the cause:

```bash
# 1. surface stale tmux servers + orphan ClaudeTeam daemons
tmux ls 2>/dev/null
ps -ef | grep -E "claudeteam (router|watchdog)|feishu_channel/sidecar\.js" | grep -v grep

# 2. clean up
claudeteam down                           # graceful local stop
tmux kill-server                          # nuke ALL tmux servers (only if no
                                          # unrelated tmux work is in flight)
# alternative if you DO have other tmux work: kill JUST our session
tmux kill-session -t ClaudeTeam

# 3. relaunch from a shell that has the right env exported
claudeteam up
tmux show-environment -g | grep -E "FEISHU_APP_ID|CLAUDETEAM_STATE_DIR"  # verify
```

### `say` / sidecar can't find App credentials

Symptom: outbound cards fail to send, or the sidecar exits at startup
complaining it has no app id/secret. Creds resolve from a single source:
`state/feishu_app.json` (written by `claudeteam feishu connect`, mode
0600), which `feishu/lark.py:subprocess_env()` reads to inject
`FEISHU_APP_ID`/`FEISHU_APP_SECRET` + a tenant token into **both** the
sidecar (ingress) and lark-cli (egress).

```bash
ls -l state/feishu_app.json          # expect mode -rw------- (0600)
```

If the file is missing, re-run `claudeteam feishu connect` and re-scan.
For Docker / advanced deploys, the env (`FEISHU_APP_ID` /
`FEISHU_APP_SECRET`, or `LARKSUITE_CLI_*`) **overrides** the file — make
sure those are set in `.env` and visible inside the container
(`docker compose exec claudeteam env | grep FEISHU_APP_ID`).

### `worker_codex` shows "pane up but CLI not ready yet"

Codex CLI sometimes opens with an "update available" prompt that
blocks the ready marker. Fix:

```bash
tmux send-keys -t ClaudeTeam:worker_codex 3 Enter   # picks "Skip until next version"
claudeteam reidentify worker_codex
```

---

## Operator-friendly entry points


| Command                                                             | Purpose                                                        |
| ------------------------------------------------------------------- | -------------------------------------------------------------- |
| `claudeteam up` / `down`                                            | Bring team up / take it down                                   |
| `claudeteam health`                                                 | One-shot status (binaries, env, tmux, daemons, cursor, memory) |
| `claudeteam team`                                                   | Each agent's state + ♥ heartbeat                               |
| `claudeteam peek <agent> [N]`                                       | Pane snapshot for the 5-min check-in cadence                   |
| `claudeteam reidentify [<agent> | --all]`                           | Re-inject identity.md (after prompt change)                    |
| `claudeteam usage [--days N]`                                       | ccusage wrapper for claude-code agents                         |
| `claudeteam say <agent> "<msg>" --to <role>`                        | Post as agent into the chat                                    |
| `claudeteam remember <agent> <kind> "<note>"`                       | Write durable memory (auto-injected on next pane wake)         |
| `claudeteam remember <agent> <kind> "<note>" --team`                | Write **shared team experience** (every agent sees it on wake) |
| `claudeteam recall [<agent> | --team]`                              | Read per-agent memory, or the shared team experience           |
| `claudeteam remember <agent> <kind> "<note>" --team --update <E-n>` | Edit a shared experience entry in place                        |
| `claudeteam forget --team [--id <E-n>]`                             | Retire one shared entry (or wipe the pool with `--yes`)        |
| `claudeteam switch <team-dir>`                                      | Print env exports for multi-team UX                            |


`claudeteam --help` lists everything grouped by section.

---

## Where things live

```
src/claudeteam/
├── cli.py             single console-scripts entry; dispatch only
├── util.py            shared helpers (now_ms, atomic_write, env_str, ...)
├── commands/          one module per subcommand (~30-300 LOC each)
├── store/             local file-backed state (inbox, status, logs, tasks, memory)
├── agents/            CliAdapter base + per-CLI adapters + identity renderer
├── runtime/           config / paths / tmux / watchdog / pidlock / wake / lifecycle / tunables
└── feishu/            lark-cli wrapper + chat + router + slash + deliver + subscribe + catchup

tests/
├── unit/              per-module (stdlib runner)
├── integration/       end-to-end in-process
├── scenarios/         operator-run regression playbooks (markdown)
├── helpers.py         isolated_env() + run_cli() + attr/env patches + FakeProc
└── run.py             discovers + runs both unit/ and integration/
```

`CLAUDE.md` (project root) holds the building rules + active work
order — read it before making changes.

---

## Stuck? Found a bug?

The project is under active development — we **respond within 12 hours**.

- 🐛 **GitHub issue** — open one at
[zylMozart/ClaudeTeam/issues](https://github.com/zylMozart/ClaudeTeam/issues/new/choose).
Include OS, deploy mode (host vs Docker), and the failing command's
output (for `feishu connect` issues, the sidecar's stderr).
- 💬 **WeChat community group** — scan the QR below (refreshed weekly).



If you're an AI agent driving a deploy and a step fails after a real
attempt at recovery, surface this section to the user — there's a
real maintainer reachable, not a bot wall.