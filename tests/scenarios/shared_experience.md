# 团队共享经验库（shared experience）

验证「全队共读共写的经验库」这条链路：任何 agent 写入的团队级教训，落到
`state/share/experience.jsonl`，并在**每个** agent 下次唤醒时自动注入上下文。

不覆盖：per-agent 私有记忆（看 `claudeteam recall <agent>`，那是各自的
`agents/<name>/memory.jsonl`）、私有工作区（`agents/<name>/workspace/`）。

## 范围

- 类型：local-only（不依赖 tmux / 飞书 / 真模型）
- 凭证：无
- 操作员：boss / manager / 任意 worker

## Given

- ClaudeTeam 已 `pip install -e .`（`claudeteam` 在 PATH）。
- `CLAUDETEAM_STATE_DIR` 指向一个可写目录（决定 `state/share/` 落点）。

## When / Then

### 1. 写入团队经验（任意 agent 都能写）

```bash
claudeteam remember worker_cc learning "本仓库测试用 python3 tests/run.py" --team
# → 🤝 team experience: [learning] by worker_cc  [<ts>]
```

- **Then**：`state/share/experience.jsonl` 出现一行，`by` 记录贡献者
  （`worker_cc`），内容逐字一致。
- **Then**：它**没有**写进 `worker_cc` 的私有记忆——
  `claudeteam recall worker_cc` 看不到这条（私有/共享两个池子分开）。

### 2. 全队可读（不需要 agent 名）

```bash
claudeteam recall --team
# → 🤝 team shared experience: 1 entry (oldest first, capped at 20)
#     [<ts>] [learning] 本仓库测试用 python3 tests/run.py  (@worker_cc)
```

- **Then**：列出全部团队经验，标注贡献者 `@worker_cc`。
- `claudeteam recall --team --json` 输出原始记录，便于 jq / CI。

### 3. 新 agent 唤醒时自动注入

模拟一个 worker 重新拿到身份提示：

```bash
claudeteam reidentify worker_codex      # 或首次 hire / 唤醒
# 检查注入到该 agent 的身份/唤醒文本里带上了团队经验
```

- **Then**：worker_codex 的唤醒提示 / 原生记忆文件（claude 的
  `~/.claude/CLAUDE.md`）里出现 `## 团队共享经验（全队可见）` 段，
  含第 1 步写的那条——**即使写入者是别的 agent**。这就是"经验不按人
  重复踩坑"的闭环。

### 4. 私有工作区存在且独立

```bash
ls -d "${CLAUDETEAM_STATE_DIR}/agents/worker_cc/workspace"
```

- **Then**：每个被 provision 的 agent 都有自己的 `workspace/` 目录；
  身份文件里告诉它"长报告/草稿写这里，别堆共享仓库根"。

## 清理

```bash
claudeteam recall --team --json    # 留档
# 经验库随 state 目录走；要清空：删除 state/share/experience.jsonl
```
