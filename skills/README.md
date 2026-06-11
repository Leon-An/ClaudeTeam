# skills — 可复用过程能力索引

一个 skill 一个目录，主文件固定叫 `SKILL.md`（frontmatter + 何时用/输入/步骤/产物 四段）。
身份只教"何时用哪个"，过程细节在触发时现读对应 SKILL.md。新增 skill = 加目录 + 本索引加一行。

| skill | 一句话 | 适用角色 |
|---|---|---|
| [verify-identity](verify-identity/SKILL.md) | 部署后逐员工拉整段 pane 实录、LLM 通读判断身份消息是否被正确处理；一票否决，失败提示用户登录 | 部署 agent / manager |

> 已有方案待落地（见 expert-skills-proposal.md，等老板拍板）：patrol（主管巡视）、reflect（反思）。
