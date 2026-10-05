# 每日古诗词视频自动生成与推送系统 设计文档

## 1. 系统概述 (Overview)

### 1.1 背景与目标
为了实现传统文化古诗词的自动化传播，本项目设计并实现了一套**100% 免费、完全无服务器（Serverless）、全自动化的古诗词短视频生成与推送系统**。

系统每日定时挑选一首中国经典古诗词，深入理解其意境并自动生成配音（古诗朗读 + 白话文译文）、AI 水墨意境配图与排版字幕，最终合成为 MP4 高清短视频，自动推送至 Telegram 指定频道/群组/个人。

### 1.2 核心特性
- **零成本运行**：利用 GitHub Actions 作为算力平台，配合免费且无额度限制的 TTS/T2I 接口与 Gemini API。
- **智能去重**：自动持久化维护历史生成记录，确保选诗不重复。
- **多声线自然朗读**：采用微软 Edge-TTS 引擎，分别使用沉稳男声朗读古诗原文、标准女声朗读现代翻译。
- **意境配图生成**：结合 Gemini 提取的古诗意境 Prompt，通过 Pollinations AI (FLUX) 自动生成传统国风水墨画背景。
- **自动化流线处理**：利用 FFmpeg 与 MoviePy 进行轻量化音视频压制与排版绘制。

---

## 2. 系统架构与技术选型 (Architecture & Tech Stack)

### 2.1 整体架构图

```
 [Cron / Manual Trigger]
         │
         ▼
 ┌─────────────────────────────────────────────────────────────┐
 │                    GitHub Actions Runner                    │
 │                                                             │
 │  1. Gemini API (gemini-2.5-flash)                           │
 │     └─ 读取 history.json -> 排除历史诗词 -> 输出 JSON        │
 │                                                             │
 │  2. Edge-TTS Service                                        │
 │     ├─ 原文 -> 沉稳男声 (zh-CN-YunxiNeural) -> poem.mp3      │
 │     └─ 译文 -> 标准女声 (zh-CN-XiaoxiaoNeural) -> trans.mp3  │
 │                                                             │
 │  3. Pollinations AI (FLUX Engine)                           │
 │     └─ Image Prompt -> 下载 1080x1920 竖屏图 -> bg.jpg      │
 │                                                             │
 │  4. MoviePy & FFmpeg Engine                                 │
 │     └─ 图像 + 双语音 + 中文字体字幕 -> 合成 final_poem.mp4   │
 │                                                             │
 │  5. Telegram Bot API                                        │
 │     └─ 上传视频与 Markdown 文案 -> 推送至 TG Chat           │
 │                                                             │
 │  6. Git Auto Commit                                         │
 │     └─ 写回更新后的 history.json 并 Push 回仓库             │
 └─────────────────────────────────────────────────────────────┘
```

### 2.2 技术选型清单

| 模块 | 技术 / 服务 | 选用理由 |
| :--- | :--- | :--- |
| **计算与调度环境** | GitHub Actions (`ubuntu-latest`) | 提供免费 Linux 虚拟环境（2核 CPU, 7GB 内存），满足视频合成算力需求 |
| **大脑与意境理解** | Google Gemini API (`gemini-2.5-flash`) | 免费额度高，具备强上下文理解与结构化 JSON 输出能力 |
| **语音合成 (TTS)** | `edge-tts` (Microsoft Edge API) | 免费、无 API Key 限制、音效极高、支持多种中文高质量 Neural 声线 |
| **AI 图像生成** | Pollinations.ai (FLUX / SD) | 免费 REST API，免 Key，可快速生成高分辨率国风水墨图像 |
| **视频合成压制** | MoviePy + FFmpeg | Python 管道化处理，支持文字 Overlay、多音频轨拼接与 H.264 编码导出 |
| **推送通道** | Telegram Bot API (`sendVideo`) | 稳定支持大文件视频上传，格式适配良好 |

---

## 3. 详细设计与实现 (Detailed Design)

### 3.1 选诗与去重逻辑 (Poem Selection & Deduplication)

#### 数据持久化方案
使用仓库根目录下的 `history.json` 记录历史已生成的诗词：
```json
[
  { "title": "静夜思", "author": "唐·李白" },
  { "title": "春晓", "author": "唐·孟浩然" }
]
```

#### Gemini Prompt 控制逻辑
将最近的 300 首历史诗词拼接为黑名单列表传递给 Gemini，配合 `response_mime_type="application/json"` 进行强约束输出：

```python
# 核心排除逻辑示例
excluded_poems = [f"《{item['title']}》({item['author']})" for item in history[-300:]]
prompt = f"""
请随机选择一首中国经典古诗。
【强制排除规则】绝不能选择以下已选过的古诗列表中的任何一首：
{"、".join(excluded_poems)}
...
"""
```

### 3.2 语音与图像处理设计 (Audio & Image Generation)

1. **音频处理**：
   - 古诗原文：使用 `zh-CN-YunxiNeural`（云希，沉稳大气的男声）。
   - 译文部分：使用 `zh-CN-XiaoxiaoNeural`（晓晓，清晰温和的女声）。
   - 间隔设置：中间插入 1.5 秒的无声片段，提升听感过渡。
2. **图像生成**：
   - Prompt 注入：将 Gemini 提取的英文意境 Prompt 追加 `, traditional Chinese artistic style, masterpiece`。
   - 尺寸控制：请求 `1080x1920` 竖屏画幅，适配现代手机短视频浏览习惯。

### 3.3 视频渲染与排版 (Video Compositing)

使用 MoviePy 构建合成图层：
- **底层 (Base Layer)**：`ImageClip`（将生成的背景图延长至音频总时长 + 1 秒）。
- **上层 (Text Overlay Layer)**：`TextClip` 绘制包含标题、作者、原文及译文的文字块。
- **字体兼容**：在 Linux Runner 环境中自动安装并读取 `WenQuanYi-ZenHei`（文泉驿正黑）字体，避免中文字符乱码。
- **输出规格**：
  - 容器格式：MP4 (`libx264` 编码)
  - 音频格式：AAC
  - 帧率：24 FPS

---

## 4. 接口与数据格式规范 (Data Format)

### 4.1 Gemini API 返回数据格式
```json
{
  "title": "静夜思",
  "author": "唐·李白",
  "poem": "床前明月光\n疑是地上霜\n举头望明月\n低头思故乡",
  "translation": "明亮的月光洒在床前，好像地上铺了一层洁白的霜。抬起头望着明月，低头思念起故乡。",
  "image_prompt": "Traditional Chinese ink painting, peaceful night, bright full moon in sky, ancient bedroom with window, misty mountains, high quality, 8k"
}
```

### 4.2 Telegram Bot 发送报文
- **Endpoint**: `https://api.telegram.org/bot<TG_BOT_TOKEN>/sendVideo`
- **Payload**:
  - `chat_id`: 目标对话 ID
  - `video`: 视频文件流 (`final_poem.mp4`)
  - `caption`: Markdown 格式排版的古诗信息卡片
  - `parse_mode`: `Markdown`

---

## 5. 安全与部署配置 (Deployment & Security)

### 5.1 环境变量 (Secrets) 管理
所有敏感凭据保存在 GitHub Repository Secrets 中，不硬编码在项目代码内：

| Secret 名称 | 描述 |
| :--- | :--- |
| `GEMINI_API_KEY` | Google AI Studio 申请的 Gemini API 密钥 |
| `TG_BOT_TOKEN` | Telegram BotFather 颁发的 Bot Token |
| `TG_CHAT_ID` | Telegram 目标接收者 ID（个人/群组/频道） |

### 5.2 CI/CD 流程构建 (`daily_poem_video.yml`)
1. **触发条件**：
   - 定时触发：每日 UTC 00:00（北京时间 08:00）。
   - 手动触发：支持 `workflow_dispatch` 随时测试。
2. **作业步骤**：
   - 环境准备：安装 Python 3.10、FFmpeg 以及中文字体包 (`fonts-wqy-zenhei`)。
   - 依赖安装：安装 Python 第三方库。
   - 脚本执行：运行 `main.py` 生成视频并发送。
   - 状态回写：通过 `git commit` 将更新后的 `history.json` 自动推送回仓库主分支。

---

## 6. 异常处理与容错机制 (Error Handling)

1. **网络超时**：图像下载接口设置 `timeout=60`，防死锁。
2. **历史记录防损坏**：读取 `history.json` 时包含 `try-except` 捕获，若读取失败自动回退为空列表，保证核心推送不中断。
3. **避免死循环/溢出**：对传入 Gemini 的历史记录截取最近 300 首，既保证长期不重复，又防止 Prompt 超出模型的上下文限制。