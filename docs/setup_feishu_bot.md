# 飞书企业自建应用（机器人）创建指南

> 创建机器人有两条路，结果一样，选你顺手的：
>
> - 🤖 **agent-driven（本文）** —— AI agent 跑下面 7 个 stage，全程
>   只要扫一次 QR 登录，剩下的 agent 托管。
> - 🧑 **纯手动** —— 跟着
>   [`setup_feishu_bots_guide.pdf`](setup_feishu_bots_guide.pdf) 一步一步点，
>   截图密集，不需要 Playwright/Node 环境。

ClaudeTeam 部署需要一个飞书企业自建 App + 机器人能力 + 一组权限 +
事件订阅 + 卡片回调 + 已发布版本。整个流程由
[`scripts/feishu_bot_creator/create_feishu_bot.js`](../scripts/feishu_bot_creator/create_feishu_bot.js)
分成 **7 个 stage**，每个 stage 内部由 Playwright 跑完一段 UI 操作，
跑完即 exit；驱动它的 AI agent 用 `status` 自检结果，再用 `next`
推进到下一 stage。**用户全程只需要扫一次 QR 登录**，之后由 agent
托管完成，最后报回 `App ID` + `App Secret`。

如果 UI 改版导致脚本某个 stage 失败，drive 不会整套放弃：它自动留下
一个交接包（截图 + `failure.json`）并把浏览器挂在 CDP 上，agent
[接管这一个 stage](#stage-失败时-agent-接管这一-stage)、按对
应章节做完，再 `skip` 让 drive 接着自动跑剩下的——不必整套重来。

---

## Stage 失败时 agent 接管这一 stage

**核心原则：drive 失败不放弃，自动把这一 stage 交接给 agent，agent
按指示在浏览器里做完，再 `skip` 让 drive 继续跑后面的 stage。**
Feishu 开放平台 UI 改版频率不低（Monaco mount 时机、表单 disabled
状态、按钮文案随版本切换），所以"某个 stage 偶尔崩"是常态——stage
化的价值就是：崩一个不影响整体，agent 只补那一个。

### drive 失败时自动产出的"交接包"（不用翻日志）

任一 stage 的自动化抛错时，`cmd_drive` 会自动:

1. **截图**整页到 `.state/<bot>.<stage>.fail.png`
   —— agent 是多模态的，直接 `Read` 这张图就能看到出错现场
2. 写**结构化交接文件** `.state/<bot>.failure.json`，字段:
   - `stage` / `goal` —— 这一步要达成什么
   - `targetUrl` —— 该 stage 对应的开放平台页面
   - `instructions` —— 本文里对应的章节（如 `Stage 3 — import-scopes`）
   - `cookieFile` —— 登录态 cookie 路径（`.feishu_cookies.json`）
   - `cdpEndpoint` —— 见下
   - `currentUrl` / `error` —— 出错时的实际页面 + 报错首行
3. **保持浏览器打开**，并通过 CDP 暴露给 agent 接管：默认
   `http://127.0.0.1:9222`（用 `FEISHU_BOT_CDP_PORT` 改端口）

### agent 接管流程

1. `Read` `.state/<bot>.<stage>.fail.png` 看现场，读
   `.state/<bot>.failure.json` 拿 `goal` / `targetUrl` / `instructions`
2. **接管浏览器（二选一，优先 CDP）**：

   **① 接管同一个浏览器（推荐）** —— 它已登录、就停在出错页:
   ```js
   const { chromium } = require('playwright');
   const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
   const ctx  = browser.contexts()[0];
   const page = ctx.pages().find(p => p.url().includes('open.feishu.cn')) || ctx.pages()[0];
   // …在 page 上接着操作…（别 browser.close()，那会关掉 drive 的浏览器）
   ```

   **② 退路：开自己的浏览器 + 复用 cookie**（CDP 连不上时）:
   ```js
   const browser = await chromium.launch({ headless: false });
   const ctx = await browser.newContext();
   await ctx.addCookies(JSON.parse(require('fs').readFileSync('.feishu_cookies.json','utf-8')));
   const page = await ctx.newPage();
   await page.goto(targetUrl);   // failure.json 里的 targetUrl
   ```
   > Playwright MCP 同理：用 cookie 注入 + 导航到 `targetUrl`。配置是
   > **server-side** 的（写在飞书平台），在哪个浏览器里点完都生效。

3. 按本文该 stage 章节的 **「自动操作 / 对应 manual UI」** 把这一步做
   完（那一节就是 agent 的操作指示）。每点一两下截一次图核对，别一
   口气盲点一长串。
4. 做完后 `echo skip > .state/<bot>.cmd` —— drive 把这个 stage 标
   done、清掉交接包，自动推进到下一 stage。

### 反模式（别犯）

- **盲调**：反复 patch selector + `redo` 看 timeout 来反推 UI —— 每次
  redo 浪费 30s+，不 `Read` 截图就是闭眼调
- **一口气写一长串** `click X → click Y → click Z` —— 中途崩了不知道
  哪步变了；分段、每段一截图
- **commit 没真跑通的代码** —— 没在当前 Feishu UI 上验证过的 selector
  就是死代码，下次还撞同样的坑。摸通后再把 click 顺序 codify 回 stage
  函数（happy path），但**只 codify 真跑过的**

### 已知较脆的 stage

- **stage 3 import-scopes** —— Monaco 编辑器。脚本已做**多策略加固**
  （`fillMonaco`：monaco-API setValue → 聚焦 textarea 粘贴 →
  `keyboard.insertText`），失败概率大降；真撞 UI 改版时按上面接管，手
  动打开「批量导入」对话框把 `feishu_scopes.json` 粘进去即可（最简单
  的是 `pbcopy < feishu_scopes.json` 后在编辑器 `Cmd+V`）
- **stage 7 publish** —— 表单里 "Configure" 子按钮可能要先点一下生成
  bot 内部 config，Save 在 config 完前一直 disabled；具体 click 顺序随
  版本变，较易需要接管

---

## 入口命令（drive 模式 — chromium 一次开到底）

`drive` 是唯一入口，里面已经包含 login（首次跑时停下让用户扫
QR，cookies 持久化所以以后不再扫）：

```bash
cd scripts/feishu_bot_creator
npm install                                       # postinstall 自动装 chromium
node create_feishu_bot.js drive <bot-name> "<desc>" \
  > /tmp/drive-<bot-name>.log 2>&1 &
```

drive **自动连跑全部 7 个 stage**，happy path 不需要写任何命令文件，跑完
publish 自动退出。命令文件只在**某个 stage 硬失败、drive 停下交接**时才用到
（agent 读 state + log + 失败截图判断后写命令）：

```bash
# 你在打开的浏览器里手动补完了失败的 stage → 标记 done 并继续:
echo skip > scripts/feishu_bot_creator/.state/<bot-name>.cmd

# 重跑某个 stage (drive 不退出):
echo "redo events" > scripts/feishu_bot_creator/.state/<bot-name>.cmd

# 跳到下一 stage（不把当前标记为 done）:
echo next > scripts/feishu_bot_creator/.state/<bot-name>.cmd

# 提前结束:
echo quit > scripts/feishu_bot_creator/.state/<bot-name>.cmd
```

**`skip` 是核心 escape hatch** —— 当 Feishu UI 改版导致某个 stage 的
selector 失败时，agent 不必整套放弃。drive 已自动留下交接包（截图 +
`failure.json`）并把浏览器挂在 CDP 上；agent 按上面
[「agent 接管这一 stage」](#stage-失败时-agent-接管这一-stage)
接管、完成那一步，再 `echo skip` 让 drive 标 done 并继续。这就是 stage
化的真正价值 —— UI 飘移不会让流程整体崩，agent 只补那一个 stage。

状态 / 进度 / 失败交接查看：
- `scripts/feishu_bot_creator/.state/<bot-name>.json`：JSON state
  含 `appId` / `completedStages` / `lastError`
- `scripts/feishu_bot_creator/.state/<bot-name>.failure.json`：**仅在
  某 stage 失败时存在** —— agent 接管所需的 `goal` / `targetUrl` /
  `instructions` / `cookieFile` / `cdpEndpoint`（成功或 `skip` 后自动清掉）
- `scripts/feishu_bot_creator/.state/<bot-name>.<stage>.fail.png`：失败
  现场整页截图，`Read` 进来看
- `/tmp/drive-<bot-name>.log`：实时 stdout / stderr
- `node create_feishu_bot.js status --app <bot-name>`：单次打印
  state 表格

drive 跑完 publish 自动退出，浏览器关闭。Crash / kill 后再起一次
`drive` 命令从同一断点续跑（按 `completedStages` 跳过已做完的）。

> **底层命令** (`stage <id>` / `next` / `login` / `create` / `batch`)
> 在 `--help` 里有列, 主要给手动调试或批量预热用; agent 平时不用
> 关心, 直接 drive 即可.

---

## Stage 1 — `create-app`

**目标**：在飞书开放平台创建一个企业自建应用，从 URL 拿到 App ID。

**自动操作**：
1. 跳转 [https://open.feishu.cn/app](https://open.feishu.cn/app)
2. 点 **"Create Custom App"**（创建企业自建应用）
3. 在弹出的表单填 `--name` 给出的应用名
4. 在 textarea 填 `--desc` 给出的应用描述
5. 点 **"Create"**
6. 跳转后从 URL `…/app/cli_xxx/capability` 中正则匹配 App ID
7. 写入 `.state/<bot-name>.json` 的 `appId` 字段

**对应 manual UI**：登录开放平台 → 「创建企业自建应用」→ 填名字 +
描述 → 「创建」。完成后浏览器地址栏的 `cli_xxx` 就是 App ID。

**完成判断**：state 文件里 `appId` 非空，且 `completedStages` 含
`create-app`。

**失败常见原因**：用户未登录（前置 `login` 没跑或 cookie 过期）。
解决：跑 `node create_feishu_bot.js login` 重新扫码。

---

## Stage 2 — `add-bot`

**目标**：给应用添加"机器人"能力，否则后续没办法发卡 / 收消息。

**自动操作**：
1. 跳转 `…/app/<appId>/capability`
2. 在能力列表里点第一个 **"Add"** 按钮（机器人卡片）
3. 等待跳转到 `…/bot` 页面

**对应 manual UI**：进应用 → 左侧「添加应用能力」→ 找到「机器人」
卡片点「添加」。

**完成判断**：URL 里出现 `/bot`，且 `completedStages` 含 `add-bot`。

**失败常见原因**：能力列表的 "Add" 按钮顺序变了。解决：手动加完
机器人能力后跑 `next` 跳到 stage 3。

---

## Stage 3 — `import-scopes`

**目标**：通过 Monaco 编辑器批量粘贴
[`feishu_scopes.json`](../scripts/feishu_bot_creator/feishu_scopes.json)
里的 ~480 条权限作用域（IM / Docs / Drive / Calendar / Base / Wiki /
Mail 等），一次性全部添加。

**自动操作**：
1. 跳转 `…/app/<appId>/auth`（权限管理）
2. 点 **"Batch import/export scopes"**
3. 在弹出 dialog 的 Monaco editor 里 `Cmd+A` → `Backspace` 清空
4. 把 JSON 内容写到剪贴板，`Cmd+V` 粘贴
5. 点 **"Next, Review New Scopes"**
6. 点 **"Add"** 确认导入

**对应 manual UI**：左侧「权限管理」→「批量导入/导出权限」→ 选
「导入」→ 粘贴 `feishu_scopes.json` 全部内容 → 「下一步」→ 「添加」。

**完成判断**：导入对话框走完，bot-creator 打印
`Permissions imported: N scopes requested (...)`；`completedStages` 含
`import-scopes`。

> **注意（不是 bug）**：飞书的权限**只有在发布版本（stage 7）之后才激活**。
> 所以在 stage 3 这个时点去查"已生效 scope"必然是 **0**——这是预期现象，
> 不代表导入失败，更不代表 IM 核心权限缺失。早期版本在这里会吓人地打
> `0 applied · IM core MISSING — may fail`，已移除。真正的生效校验放到了
> publish 之后：stage 7 会打 `✅ scopes active … IM core granted`，或在确实
> 仍缺核心权限时才打 `⚠️ … MISSING after publish`。

**失败常见原因**：Monaco editor 的 textarea 被 span 覆盖（脚本就是
为此点 `.view-lines` 而不是 textarea）；或剪贴板权限被浏览器拦
截。解决：手动打开 batch import 对话框、粘贴 JSON 完成后跑 `next`。

---

## Stage 4 — `data-range`

**目标**：把"数据访问范围"设为「全部」，否则后续机器人在某些群
里读不到消息。

**自动操作**：
1. stage 3 导入权限后会自动弹"配置数据访问范围"对话框
2. 点对话框内的 **"Configure"**
3. 选 **"All"** → **"Save"** → **"Confirm"**
4. 如果对话框未弹（之前已配过），跳过这步

**对应 manual UI**：弹出对话框 →「配置」→ 选「全部」→ 「保存」→
「确认」。

**完成判断**：对话框消失，`completedStages` 含 `data-range`。

**失败常见原因**：对话框选择器变化。解决：手动在权限管理页面找
「配置数据范围」按钮设为「全部」，然后跑 `next`。

---

## Stage 5 — `events`

**目标**：把订阅模式设为**长连接（persistent connection）**而不是
回调 URL，并订阅所有 `message` 相关事件（Tenant + User token 双
tab 全勾）。

**自动操作**：
1. 跳转 `…/app/<appId>/event`
2. 找「Subscription mode」编辑按钮 → 点开 → 默认是长连接 → **Save**
3. 点 **"Add Events"** → 搜 `message` → Tenant Token tab 勾全部
   checkbox → User Token-Based Subscription tab 切换勾全部
4. **"Add"** 提交
5. 如果弹「建议添加的权限」对话框，点 **"Add Scopes"** 关掉

**对应 manual UI**：左侧「事件与回调」→「事件配置」→ 编辑订阅方
式 → 选「长连接」保存 →「添加事件」→ 搜 `message` → 两个 tab 全
勾 → 「添加」。

**完成判断**：事件列表里出现 `im.message.receive_v1` 等条目；
`completedStages` 含 `events`。

**失败常见原因**：tab 切换的文案 "User Token-Based Subscription" 改
了。解决：手动按上述步骤勾选完事件订阅后跑 `next`。

---

## Stage 6 — `callbacks`

**目标**：在「回调配置」tab 启用 **`card.action.trigger`**，让用户
点卡片按钮的事件能回到机器人（ClaudeTeam 不依赖这个但保留以备
未来用）。

**自动操作**：
1. 在 events 同一页切到 **"Callback Configuration"** tab
2. 编辑订阅方式 → 长连接 → Save
3. 点 **"Add callback"** → 勾第一个 checkbox（`card.action.trigger`）
   → **"Add"**

**对应 manual UI**：「事件与回调」→「回调配置」→ 编辑订阅方式 →
长连接保存 → 「添加回调」→ 勾「卡片回传交互」→ 「添加」。

**完成判断**：回调列表里出现 `card.action.trigger`；
`completedStages` 含 `callbacks`。

---

## Stage 7 — `publish`

**目标**：把以上所有配置打包成一个版本并发布上线，否则机器人不
会真的开始接事件。

**自动操作**：
1. 跳转 `…/app/<appId>/version`
2. 点 **"Create Version"**
3. 跳到表单，滚动到底部点 **"Save"**（保留默认值）
4. 在弹出确认框点 **"Publish"**

**对应 manual UI**：左侧「版本管理与发布」→「创建版本」→ 表单保
留默认 → 滚到底「保存」→ 弹出确认框「确认发布」。

**完成判断**：版本列表里出现新版本，状态「已启用」；
`completedStages` 含 `publish` —— 这时整个 7 stage 走完，agent
应该停下来去开放平台「凭证与基础信息」页读 App ID + App Secret，
报给用户。

---

## 完成之后

把 `App ID` + `App Secret` + 你把机器人加到的飞书群的 `chat_id`
喂给 `claudeteam`（写进 `.env` 或 `claudeteam.toml`），后面就走
[`docs/DEPLOYMENT.md`](DEPLOYMENT.md) 的 step 2-4。

`chat_id` 怎么拿：

```bash
LARK_CLI_NO_PROXY=1 lark-cli im +chat-search \
  --query "<群名关键字>" --as user
```

输出里的 `oc_xxxxxxxx` 就是 chat_id。
