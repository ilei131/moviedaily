# 🤖 古诗词视频生成与 Telegram 推送 Bot（手动触发）

基于 GitHub Actions + Gemini API + Edge-TTS + Pollinations.ai / HuggingFace + MoviePy 搭建的古诗短视频生成系统，每次手动触发生成并推送一首。

## 🌟 特点
- **零成本**：无需服务器，全套使用免费 API 与开源工具。
- **不重复**：自动维护 `history.json` 并提交回 Git 仓库，确保 Gemini 每次生成新古诗；失败时指数退避自动重试 3 次。
- **主备图像生成**：Pollinations.ai 优先，失败自动切换 HuggingFace FLUX.1-schnell，并含图片质量校验。
- **动态视频效果**：Ken Burns 缓慢缩放 + 逐句同步字幕 + 标题固定显示。
- **双声线朗读**：沉稳男声 (Yunxi) 朗读原文，标准女声 (Xiaoxiao) 朗读译文。
- **可选背景音乐**：从 Pixabay 自动下载免费古风 BGM，低音量混音不抢人声。

## 🛠️ 部署指南

### 1. 新建仓库并上传代码
将本项目的所有代码上传至你的 GitHub 私有仓库。

### 2. 配置仓库密钥 (Secrets)
进入 GitHub 仓库页面：`Settings -> Secrets and variables -> Actions`，添加以下环境变量：

| 变量名 | 含义 | 是否必填 |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | Google AI Studio 申请的 Gemini API Key | ✅ 必填 |
| `TG_BOT_TOKEN` | Telegram `@BotFather` 申请的机器人 Token | ✅ 必填 |
| `TG_CHAT_ID` | 接收视频的群组/频道/个人 Chat ID (如 `-100xxxxxxxxxx`) | ✅ 必填 |
| `TG_CHANNEL_ID` | 同步推送的频道 ID（如 `@ChinesePoetryDaily`） | 可选 |
| `HF_TOKEN` | HuggingFace Access Token（[申请地址](https://huggingface.co/settings/tokens)），图像备用方案 | 可选 |
| `PIXABAY_API_KEY` | Pixabay API Key（[申请地址](https://pixabay.com/api/docs/)），用于 BGM | 可选 |

### 3. 测试运行
在仓库的 **Actions** 页面选中 `Daily Poem Video Generator` 工作流，点击 **Run workflow** 即可进行手动触发测试。