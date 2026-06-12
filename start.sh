#!/bin/bash
# ClaudeTeam 一键启动脚本
set -e

cd /root/ClaudeTeam
source .venv/bin/activate

# 飞书配置
export CLAUDETEAM_STATE_DIR=/root/ClaudeTeam/state
export LARK_CLI_NO_PROXY=1
export CLAUDETEAM_LARK_SEND_AS=bot
export FEISHU_APP_ID=cli_aa9549ea1bb9dcfe
export FEISHU_APP_SECRET=uVWXwmoIFd7a2PhHSVc8nhssXgpSeKjL
export LARKSUITE_CLI_APP_ID=cli_aa9549ea1bb9dcfe
export LARKSUITE_CLI_APP_SECRET=uVWXwmoIFd7a2PhHSVc8nhssXgpSeKjL

# mimo API（Anthropic 兼容 — Claude Code 用）
export ANTHROPIC_BASE_URL=https://token-plan-cn.xiaomimimo.com/anthropic
export ANTHROPIC_API_KEY=tp-cg44rjhtnag1hvwv28mv4wvpmlhpjsgim0gi9ohczt2e0nzv

# mimo API（OpenAI 兼容 — Codex CLI 用）
export OPENAI_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1
export OPENAI_API_KEY=tp-cg44rjhtnag1hvwv28mv4wvpmlhpjsgim0gi9ohczt2e0nzv

echo "🚀 正在启动 ClaudeTeam..."
claudeteam up ""

echo ""
echo "✅ ClaudeTeam 已启动！"
echo "   飞书群里发消息即可指挥 AI 团队"
echo "   常用命令："
echo "     claudeteam health   # 查看状态"
echo "     claudeteam team     # 查看团队"
echo "     claudeteam down     # 停止团队"
