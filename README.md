# 🤖 每日古诗视频自动生成与 Telegram 推送 Bot

基于 GitHub Actions + Gemini API + Edge-TTS + Pollinations.ai + MoviePy 搭建的全自动化古诗视频生成系统。

## 🌟 特点
- **零成本**：无需服务器，全套使用免费 API 与开源工具。
- **不重复**：自动维护 `history.json` 并提交回 Git 仓库，确保 Gemini 每次生成新古诗。
- **高清配图与音效**：自动生成水墨意境画作为背景，搭载双声线自然语音朗读。

## 🛠️ 部署指南

### 1. 新建仓库并上传代码
将本项目的所有代码上传至你的 GitHub 私有仓库。

### 2. 配置仓库密钥 (Secrets)
进入 GitHub 仓库页面：`Settings -> Secrets and variables -> Actions`，添加以下 3 个环境变量：

| 变量名 | 含义 |
| :--- | :--- |
| `GEMINI_API_KEY` | Google AI Studio 申请的 Gemini API Key |
| `TG_BOT_TOKEN` | Telegram `@BotFather` 申请的机器人 Token |
| `TG_CHAT_ID` | 接收视频的群组/频道/个人 Chat ID (如 `-100xxxxxxxxxx`) |

### 3. 测试运行
在仓库的 **Actions** 页面选中 `Daily Poem Video Generator` 工作流，点击 **Run workflow** 即可进行手动触发测试。
