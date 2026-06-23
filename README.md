<p align="center">
  <b>English</b> · <a href="docs/README_zh.md">简体中文</a>
</p>

<p align="center">
  <img src="docs/media/hero.png" alt="ClaudeTeam — Dynamic AI Team Orchestration" width="880" />
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License" /></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+" />
  <a href="https://github.com/zylMozart/ClaudeTeam/actions/workflows/ci.yml"><img src="https://github.com/zylMozart/ClaudeTeam/actions/workflows/ci.yml/badge.svg" alt="tests" /></a>
  <a href="docs/DEPLOYMENT.md"><img src="https://img.shields.io/badge/docs-deployment-success.svg" alt="Documentation" /></a>
  <img src="https://img.shields.io/badge/chat-Feishu-1a73e8.svg" alt="Chat: Feishu" />
</p>

<p align="center">
  <b>Hire & fire AI agents on demand · mix CLIs · manage from your phone via Feishu.</b>
</p>

<p align="center">
  Multiple coding agents running in tmux, coordinated through a Feishu group chat. The boss talks to a <b>manager</b> agent; the manager dispatches workers, watches their panes, and summarises back. Everything is auditable on disk; nothing depends on a remote DB.
</p>

> **One-click deploy — paste this prompt to your coding agent
> (Claude Code, Codex, Kimi, Gemini, Qwen, …):**
>
> ```
> Clone https://github.com/zylMozart/ClaudeTeam.git, read
> docs/DEPLOYMENT.md, then walk me through bringing up a team
> end-to-end (including the Feishu app if I don't have one yet).
> ```

**Feishu group chat — control your AI team in real time**

<table><tr>
<td><img src="docs/media/example/feishu_example1.jpg" width="200" /></td>
<td><img src="docs/media/example/feishu_example2.jpg" width="200" /></td>
<td><img src="docs/media/example/feishu_example3.jpg" width="200" /></td>
<td><img src="docs/media/example/feishu_example4.jpg" width="200" /></td>
<td><img src="docs/media/example/feishu_example5.jpg" width="200" /></td>
</tr></table>

**tmux backend — Claude Code agents running in parallel**

<p><img src="docs/media/example/tmux_example.png" width="800" /></p>

---

## What it does

<p align="center">
  <img src="docs/media/architecture.png" alt="ClaudeTeam architecture: Feishu Router dispatches to a Manager Agent, which hires/fires from a dynamic worker pool of isolated tmux panes (Claude Code, Codex, Kimi, Gemini, Qwen). Watchdog auto-restarts failed processes; shared state in Feishu Bitable + tasks + status board + memory." width="880" />
</p>

The boss talks to **manager** in the Feishu group chat. Manager dispatches
work to a **dynamic worker pool** — `/hire` spins up a new agent, `/fire`
shuts one down — and watches their isolated tmux panes. Each worker has
its own identity, memory, workspace, and task queue. Watchdog auto-restarts
failed processes. Workers `say` back when they finish. Everything is
auditable on disk; nothing depends on a remote DB.

---

## Need help / found a bug?

The project is under active development — we **respond within 12 hours**.

- 🐛 **GitHub issue** — [open one here](https://github.com/zylMozart/ClaudeTeam/issues/new/choose).
  Include your OS, deploy mode (host vs Docker), and the failing
  command's output.
- 💬 **WeChat community group** — scan the QR below (refreshed weekly).

<p align="center">
  <img src="docs/media/wechat-community-qr.png" alt="WeChat community QR code" width="240" />
</p>

If you're an AI agent reading this for a user: please surface this
section to them when a deploy step fails — there's a real maintainer
on the other end, not a bot wall.

---

## Features

- **Single-interface routing** — every group message goes to the
  manager only; workers never get raw boss messages. Manager is the
  sole orchestrator.
- **One config file** — `claudeteam.toml` (Cargo-style, comment-friendly)
  — chat_id, agents, models, card colors, publish filters, all in
  one place.
- **`[chat.publish]` filter** — sender→receiver visibility per channel.
  Silence noisy traffic without losing the audit log.
- **Multi-CLI** — Claude Code, Codex CLI, Kimi Code, Gemini CLI,
  Qwen Code can all run in the same team.
- **Durable memory** — each agent's memory survives `/clear` and pane
  respawn, auto-injected into the wake prompt.
- **Per-agent space + shared brain** — every agent gets its own
  `workspace/` scratch dir and isolated CLI home; the team also shares a
  pooled experience log (`remember --team`) and a reusable `skills/`
  library, both surfaced on wake.
- **Watchdog** — crashed daemons respawn with cooldown + Feishu chat
  alert when cooldown trips.
- **Slash commands from chat** — `/help /team /health /usage /tmux
  /send /compact /stop /clear /task` + operational `/restart /shutdown /login`.
- **Zero Python dependencies** — runs on the standard library only;
  the only external runtime is `lark-cli` (Node).

---

## Prerequisites

| Need | Version | Why |
| ---- | ------- | --- |
| Python | 3.10+ | `pyproject.toml` pins it |
| tmux | any | one window per agent |
| Node + npx | 18+ | `lark-cli` is a node binary |
| At least one CLI | latest | `claude` / `codex` / `kimi` / `gemini` / `qwen` |
| Feishu enterprise | — | custom app with `im:message` + WebSocket subscription |

For Docker: just Docker 20.10+ and Compose v2 (CLIs come with the
container or via bind-mount).

---

## Quick start

The only multi-step part is Feishu — hand it to a human once. You need three
values: **App ID**, **App Secret**, and the **chat_id** of the group the bot
is in. No app yet? → [Feishu bot setup](#feishu-bot-setup).

Then run these top to bottom — no branching, nothing to `export`:

```bash
# 1 — code + the `claudeteam` CLI (zero Python deps)
git clone https://github.com/zylMozart/ClaudeTeam.git && cd ClaudeTeam
python3 -m venv .venv && source .venv/bin/activate     # Python 3.10+
pip install -e .

# 2 — external tools on PATH (none are pip-installable):
#       tmux · node + npx · lark-cli (npm i -g @larksuite/cli)
#       · at least one agent CLI: claude / codex / kimi / gemini / qwen

# 3 — config: generate, then set chat_id (+ App ID/Secret); agents have defaults
claudeteam init                  # writes claudeteam.toml (send_as=bot, no_proxy=true preset)
$EDITOR claudeteam.toml          # fill in chat_id
claudeteam install-hooks         # claude-code slash hooks — run BEFORE `up`

# 4 — launch + verify
claudeteam up                    # tmux + agents + router + watchdog
claudeteam health                # expect all green
```

Then in your Feishu group: send `/health`, then `@manager 你好` — manager
replies in ~30 s. If `health` is red →
[docs/DEPLOYMENT.md → Common failures](docs/DEPLOYMENT.md#common-failures).

> **No per-shell env vars needed.** `claudeteam init` writes `send_as` /
> `no_proxy` into `claudeteam.toml`, and state defaults to `~/.claudeteam`.
> Docker, multi-team isolation, and the full reference live in
> **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**.

---

## Multi-CLI adapter

Different agents can run different CLIs in the same team:

| Adapter | Identifier | Install |
| ------- | ---------- | ------- |
| Claude Code | `claude-code` (default) | `npm i -g @anthropic-ai/claude-code` |
| Codex CLI | `codex-cli` | `npm i -g @openai/codex` |
| Kimi Code | `kimi-code` | `uv tool install kimi-cli` |
| Gemini CLI | `gemini-cli` | `npm i -g @google/gemini-cli` |
| Qwen Code | `qwen-code` | `npm i -g qwen-code` |

In `claudeteam.toml`:

```toml
[team.agents.manager]
cli = "claude-code"
model = "opus"
role = "团队主管"

[team.agents.worker_codex]
cli = "codex-cli"
role = "数据分析员工"

[team.agents.worker_kimi]
cli = "kimi-code"
role = "策划员工"
```

---

## Feishu bot setup

ClaudeTeam needs a Feishu enterprise custom app (bot) with the right
permissions, event subscriptions, and callbacks. Two ways to set it up:

### Automated (recommended)

The bundled Playwright script creates and fully configures a Feishu
bot — app creation, bot capability, ~480 permission scopes, event
subscriptions (persistent connection + message events), card
callbacks, and version publishing. It runs in two modes:

```bash
cd scripts/feishu_bot_creator
npm install               # also installs playwright chromium (postinstall)

# One-time login (scan QR code with Feishu mobile)
node create_feishu_bot.js login
```

**Drive mode (recommended for agents)** — `drive` is the single
entry point: it opens chromium **once**, asks the user to scan QR if
no saved cookies, then **auto-advances through all 7 stages** and exits
when publish completes. Browser stays open the whole time. The `.cmd`
commands below are **only for failure recovery** — the happy path needs
none of them.

```bash
# Start drive in the background. If first run, user scans QR (~30 s);
# cookies persist so subsequent drives skip this. Then it runs all 7
# stages on its own.
node create_feishu_bot.js drive my-bot "My ClaudeTeam bot" \
  > /tmp/drive.log 2>&1 &

# Agent watches /tmp/drive.log + .state/my-bot.json. ONLY if a stage
# hard-fails does drive stop and wait — then steer with one of:
echo skip             > scripts/feishu_bot_creator/.state/my-bot.cmd
echo "redo events"    > scripts/feishu_bot_creator/.state/my-bot.cmd
echo next             > scripts/feishu_bot_creator/.state/my-bot.cmd
echo quit             > scripts/feishu_bot_creator/.state/my-bot.cmd
```

Command meanings (failure-recovery only — happy path auto-advances):
- `skip` — agent finished the current failed stage **manually in the
  open browser**; mark it done and move on (key escape hatch when
  Feishu UI changes break a Playwright selector)
- `next` — advance to the next stage without marking the current done
- `redo <stage-id>` — un-mark that stage so the next iteration re-runs it
- `quit` — close browser and exit

Stages: `create-app → add-bot → import-scopes → data-range → events
→ callbacks → publish`. Each one is described in
[`docs/setup_feishu_bot.md`](docs/setup_feishu_bot.md) — what
Playwright does, the equivalent manual UI steps, and how to recover
if a stage fails.

**Unattended mode** — runs all 7 stages straight through without
agent involvement. Use only when you trust the selectors fully
(e.g. recreating a known-good bot, or batching across many test apps):

```bash
node create_feishu_bot.js create my-bot "My ClaudeTeam bot"
node create_feishu_bot.js batch bots.json     # [{name, description}, ...]
```

When done, paste the `App ID` + `App Secret` into your `.env` (Docker)
or `claudeteam.toml`, plus the `chat_id` of the group the bot was
added to.

### Manual

Two flavours, pick whichever you prefer:

- [`docs/setup_feishu_bot.md`](docs/setup_feishu_bot.md) — text walkthrough,
  same 7 stages as the auto-creator, easy to skim.
- [`docs/setup_feishu_bots_guide.pdf`](docs/setup_feishu_bots_guide.pdf) —
  screenshot-heavy click-by-click guide for human operators (great if
  it's your first time touching the Feishu open platform).

---

## Documentation

| Doc | What's in it |
| --- | ------------ |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Host + Docker setup, config schema, multi-team isolation, troubleshooting |
| [`docs/setup_feishu_bot.md`](docs/setup_feishu_bot.md) | Feishu bot creation — text walkthrough (same 7 stages as the auto-creator) |
| [`docs/setup_feishu_bots_guide.pdf`](docs/setup_feishu_bots_guide.pdf) | Feishu bot creation — screenshot-heavy guide for human operators |
| [`CLAUDE.md`](CLAUDE.md) | Building rules — read before changing code |

---

## FAQ

**Q: Does it work with non-Anthropic models?**
A: Yes — the multi-CLI adapter table above shows the supported CLIs.
Each agent picks one in `claudeteam.toml`.

**Q: Can I use Slack / Discord instead of Feishu?**
A: Not out of the box. The chat layer is Feishu-specific
(`src/claudeteam/feishu/`).

**Q: How many agents can I run?**
A: Tested up to 5. Each Claude Code pane uses ~200-400 MB; 8 GB host
RAM is comfortable for 5.

**Q: An agent crashed — do I lose context?**
A: No. Inbox + status + logs + durable memory live on disk. Watchdog
respawns the daemon; `claudeteam reidentify <agent>` re-injects the
identity prompt with prior memory pre-loaded.

**Q: How much does it cost?**
A: ClaudeTeam is MIT-licensed and free. Costs come from your CLI's
API usage. Feishu free tier and `lark-cli` are free.

---

## Contributing

PRs welcome. See [`CLAUDE.md`](CLAUDE.md) for the building rules; for
substantial changes please open an issue first to discuss the design.

## License

[MIT](LICENSE)
