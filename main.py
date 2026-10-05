import os
import json
import random
import asyncio
import requests
import math
import subprocess
import glob
from PIL import Image
from google import genai
from google.genai import types
import edge_tts
from moviepy.editor import (ImageClip, AudioFileClip, TextClip,
                            CompositeVideoClip, concatenate_audioclips,
                            CompositeAudioClip)

# --- 0. 配置与常量 ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
HF_TOKEN = os.getenv("HF_TOKEN", None)
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", None)

HISTORY_FILE = "history.json"
IMAGE_WIDTH, IMAGE_HEIGHT = 1080, 1920
MIN_IMAGE_SIZE_KB = 30

if not GEMINI_API_KEY or not TG_BOT_TOKEN or not TG_CHAT_ID:
    raise ValueError("缺少必要的环境变量！请检查 GEMINI_API_KEY, TG_BOT_TOKEN, TG_CHAT_ID 设置。")

# --- 中文字体自动发现 ---
def _discover_chinese_font():
    candidates = [
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    for pattern in ['/usr/share/fonts/**/*.ttc', '/usr/share/fonts/**/*.ttf']:
        matches = glob.glob(pattern, recursive=True)
        if matches:
            return matches[0]
    return 'WenQuanYi-ZenHei'

FONT_PATH = _discover_chinese_font()
print(f"使用字体: {FONT_PATH}")

client = genai.Client(api_key=GEMINI_API_KEY)

# --- 2. 历史记录管理 ---
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"读取历史记录失败，初始化为空列表: {e}")
            return []
    return []

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

# --- 3. Gemini 智能选诗（含 JSON 校验 + 多重试机制）---
def get_poem_data(max_retries=3):
    history = load_history()
    excluded_poems = [f"《{item['title']}》({item['author']})" for item in history[-300:]]
    excluded_str = "、".join(excluded_poems) if excluded_poems else "无"

    prompt = f"""
    请随机选择一首中国经典古诗（避免过于偏门）。

    【强制排除规则】绝不能选择以下已选过的古诗列表中的任何一首：
    {excluded_str}

    请严格按以下 JSON 格式输出：
    {{
      "title": "诗名",
      "author": "朝代·作者",
      "poem": "古诗原文（换行分割，如: 床前明月光\\n疑是地上霜）",
      "translation": "现代白话文翻译（简短通顺）",
      "image_prompt": "适用于AI绘图的英文Prompt，传统中国水墨画或写实国风",
      "image_prompt_2": "第二个英文Prompt，不同视角或场景，与第一个互补但风格一致"
    }}
    只返回纯JSON，不要带任何Markdown标记或额外说明。
    """

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            print(f"Gemini 第 {attempt}/{max_retries} 次尝试...")
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            poem_data = json.loads(response.text)
            required_keys = ["title", "author", "poem", "translation", "image_prompt"]
            for key in required_keys:
                if key not in poem_data or not poem_data[key]:
                    raise ValueError(f"Gemini 返回缺少必要字段: {key}")
            print(f"Gemini 选诗成功: 《{poem_data['title']}》")

            if "image_prompt_2" not in poem_data or not poem_data.get("image_prompt_2"):
                poem_data["image_prompt_2"] = poem_data.get("image_prompt", "") + ", different composition"

            history.append({"title": poem_data["title"], "author": poem_data["author"]})
            save_history(history)
            return poem_data

        except Exception as e:
            last_error = e
            if attempt < max_retries:
                wait_sec = 2 ** attempt
                print(f"第 {attempt} 次失败 ({e})，{wait_sec} 秒后重试...")
                import time
                time.sleep(wait_sec)

    raise RuntimeError(f"Gemini API 调用失败（已重试 {max_retries} 次）: {last_error}")

# --- 4. 生成语音 (Edge-TTS) ---
async def generate_audio(text, voice, output_path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

# --- 5. 图像质量校验 ---
def validate_image(file_path):
    if not os.path.exists(file_path):
        return False
    size_kb = os.path.getsize(file_path) / 1024
    if size_kb < MIN_IMAGE_SIZE_KB:
        print(f"图片过小 ({size_kb:.1f}KB)，可能损坏")
        return False
    try:
        img = Image.open(file_path)
        w, h = img.size
        if w < IMAGE_WIDTH * 0.5 or h < IMAGE_HEIGHT * 0.5:
            print(f"图片分辨率不达标 ({w}x{h})")
            return False
        print(f"图片校验通过: {w}x{h}, {size_kb:.1f}KB")
        return True
    except Exception as e:
        print(f"图片校验异常: {e}")
        return False

# --- 6. Pollinations.ai 主方案 ---
def download_pollinations_image(prompt, output_path, max_retries=2):
    for attempt in range(max_retries):
        try:
            full_prompt = f"{prompt}, masterpiece, traditional Chinese artistic style"
            encoded = requests.utils.quote(full_prompt)
            url = f"https://image.pollinations.ai/prompt/{encoded}?width={IMAGE_WIDTH}&height={IMAGE_HEIGHT}&nologo=true&nofeed=true&seed={random.randint(1, 999999)}"
            res = requests.get(url, timeout=90)
            if res.status_code == 200 and len(res.content) > 1000:
                with open(output_path, 'wb') as f:
                    f.write(res.content)
                if validate_image(output_path):
                    return True
        except Exception as e:
            print(f"Pollinations 第{attempt+1}次失败: {e}")
    return False

# --- 7. HuggingFace FLUX.1-schnell 备用方案 ---
def download_huggingface_image(prompt, output_path):
    if not HF_TOKEN:
        print("未配置 HF_TOKEN，跳过 HuggingFace 备用方案")
        return False
    try:
        api_url = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"
        headers = {"Authorization": f"Bearer {HF_TOKEN}"}
        payload = {"inputs": f"{prompt}, traditional Chinese ink painting style, vertical composition"}
        res = requests.post(api_url, headers=headers, json=payload, timeout=120)
        if res.status_code == 200 and len(res.content) > 1000:
            with open(output_path, 'wb') as f:
                f.write(res.content)
            if validate_image(output_path):
                return True
        print(f"HuggingFace 返回异常: {res.status_code}")
    except Exception as e:
        print(f"HuggingFace 备用方案失败: {e}")
    return False

# --- 8. 主备切换图像下载入口 ---
def download_background_image(prompt, output_path):
    print(f"尝试 Pollinations.ai 生成图像...")
    if download_pollinations_image(prompt, output_path):
        print("Pollinations.ai 图像生成成功")
        return
    print("Pollinations 失败，尝试 HuggingFace FLUX.1-schnell 备用方案...")
    if download_huggingface_image(prompt, output_path):
        print("HuggingFace 备用方案成功")
        return
    raise RuntimeError("所有图像生成方案均失败，请检查网络或 API 配置")

# --- 9. 背景音乐下载 (Pixabay) ---
def download_bgm(output_path):
    if not PIXABAY_API_KEY:
        print("未配置 PIXABAY_API_KEY，跳过背景音乐")
        return None
    try:
        params = {"key": PIXABAY_API_KEY, "q": "chinese traditional peaceful", "per_page": 5}
        res = requests.get("https://pixabay.com/api/", params=params, timeout=15)
        if res.status_code == 200:
            hits = res.json().get("hits", [])
            if hits:
                hits.sort(key=lambda x: x.get("duration", 999))
                music_url = hits[0].get("previewURL") or ""
                if music_url:
                    music_res = requests.get(music_url, timeout=30)
                    if music_res.status_code == 200 and len(music_res.content) > 1000:
                        with open(output_path, 'wb') as f:
                            f.write(music_res.content)
                        print("背景音乐下载成功")
                        return output_path
        print("Pixabay 暂无合适音乐")
    except Exception as e:
        print(f"背景音乐下载失败: {e}")
    return None

# --- 10. 逐句字幕时长估算 ---
def estimate_line_durations(poem_lines, total_duration):
    durations = []
    total_chars = sum(len(line.strip()) for line in poem_lines if line.strip())
    if total_chars == 0:
        n = max(len(poem_lines), 1)
        return [total_duration / n] * n
    for line in poem_lines:
        chars = len(line.strip())
        durations.append(total_duration * chars / total_chars if chars > 0 else 0)
    return durations

# --- 11. 视频合成 (Ken Burns + 逐句字幕 + 多图轮播 + 淡入淡出 + BGM) ---
def build_video(poem_data, poem_audio_path, trans_audio_path, image_paths, bgm_path, output_video_path):
    audio_poem = AudioFileClip(poem_audio_path)
    audio_trans = AudioFileClip(trans_audio_path)

    silent_gap = AudioFileClip(poem_audio_path).subclip(0, 0.1).volumex(0)
    final_audio = concatenate_audioclips([audio_poem, silent_gap, audio_trans])
    total_duration = final_audio.duration + 1.0
    poem_duration = audio_poem.duration
    trans_start_time = poem_duration + 1.5

    # --- 多图轮播 (Ken Burns 缓慢推进 + 交叉淡入淡出) ---
    num_images = len(image_paths)
    seg = total_duration / num_images
    image_clips = []
    for i, img_path in enumerate(image_paths):
        clip = (ImageClip(img_path)
                .set_start(i * seg)
                .set_duration(seg + 0.8)
                .resize(lambda t, idx=i: (int(IMAGE_WIDTH * (1 + 0.05 * (t - idx * seg) / max(seg, 0.1))),
                                           int(IMAGE_HEIGHT * (1 + 0.05 * (t - idx * seg) / max(seg, 0.1)))))
                .set_position(('center', 'center'))
                .crossfadein(0.6)
                .crossfadeout(0.6))
        image_clips.append(clip)

    # --- 逐句字幕（原文逐行动态出现）---
    poem_lines = [l.strip() for l in poem_data['poem'].split('\n') if l.strip()]
    line_durations = estimate_line_durations(poem_lines, poem_duration)
    subtitle_clips = []
    current_time = 0.0
    for i, (line, dur) in enumerate(zip(poem_lines, line_durations)):
        if dur <= 0:
            continue
        end_time = min(current_time + dur, poem_duration)
        if end_time <= current_time:
            continue
        txt = TextClip(
            line, fontsize=52, color='white', font=FONT_PATH,
            stroke_color='black', stroke_width=2,
            method='caption', size=(900, None), align='Center'
        ).set_start(current_time).set_duration(end_time - current_time).set_position(('center', 0.72), relative=True)
        subtitle_clips.append(txt)
        current_time = end_time

    # 译文字幕
    if poem_data.get('translation'):
        trans_txt = TextClip(
            f"【译文】\n{poem_data['translation']}",
            fontsize=36, color='#F5F5DC', font=FONT_PATH,
            stroke_color='black', stroke_width=1.5,
            method='caption', size=(880, None), align='Center'
        ).set_start(trans_start_time).set_duration(audio_trans.duration).set_position(('center', 0.72), relative=True)
        subtitle_clips.append(trans_txt)

    # 标题与作者（顶部固定）
    title_clip = TextClip(
        f"《{poem_data['title']}》\n{poem_data['author']}",
        fontsize=44, color='#FFD700', font=FONT_PATH,
        stroke_color='black', stroke_width=2,
        method='caption', size=(900, None), align='Center'
    ).set_duration(total_duration).set_position(('center', 0.08), relative=True)

    # --- 合成所有图层 ---
    all_clips = image_clips + subtitle_clips + [title_clip]
    video = CompositeVideoClip(all_clips, size=(IMAGE_WIDTH, IMAGE_HEIGHT))

    # --- 背景音乐混音 ---
    if bgm_path and os.path.exists(bgm_path) and os.path.getsize(bgm_path) > 1000:
        try:
            bgm = AudioFileClip(bgm_path)
            if bgm.duration < total_duration:
                n_loops = int(total_duration / bgm.duration) + 1
                bgm = concatenate_audioclips([bgm] * n_loops)
            bgm = bgm.subclip(0, total_duration).volumex(0.12)
            final_audio_with_bgm = CompositeAudioClip([final_audio, bgm])
            video = video.set_audio(final_audio_with_bgm)
            print("背景音乐混音成功")
        except Exception as e:
            print(f"背景音乐混音失败: {e}")
            video = video.set_audio(final_audio)
    else:
        video = video.set_audio(final_audio)

    # --- 导出 ---
    video.write_videofile(
        output_video_path,
        fps=24, codec='libx264', audio_codec='aac',
        temp_audiofile='temp-audio.m4a', remove_temp=True,
        preset='medium', bitrate='2000k'
    )

# --- 12. 嵌入视频封面 ---
def embed_video_cover(video_path, cover_image_path):
    try:
        temp_path = video_path.replace('.mp4', '_cover.mp4')
        subprocess.run([
            'ffmpeg', '-i', video_path, '-i', cover_image_path,
            '-map', '0', '-map', '1', '-c', 'copy',
            '-disposition:v:1', 'attached_pic',
            temp_path
        ], check=True, capture_output=True)
        os.replace(temp_path, video_path)
        print("视频封面已嵌入")
        return True
    except Exception as e:
        print(f"封面嵌入失败: {e}")
        return False

# --- 13. 发送 Telegram 视频 ---
def send_to_telegram(video_path, caption):
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendVideo"
    with open(video_path, 'rb') as video_file:
        files = {'video': video_file}
        data = {'chat_id': TG_CHAT_ID, 'caption': caption, 'parse_mode': 'Markdown'}
        res = requests.post(url, files=files, data=data)
        print("Telegram 推送响应:", res.json())

# --- 主入口 ---
async def main():
    print("=" * 50)
    print("1. 正在读取历史并选取新古诗...")
    poem_data = get_poem_data()
    print(f"今日古诗: 《{poem_data['title']}》 — {poem_data['author']}")
    print(f"原文:\n{poem_data['poem']}")

    poem_audio_path = "poem.mp3"
    trans_audio_path = "trans.mp3"
    bg_image_1_path = "bg_1.jpg"
    bg_image_2_path = "bg_2.jpg"
    bgm_path = "bgm.mp3"
    out_video_path = f"{poem_data['title']}.mp4"

    print("2. 生成 TTS 朗读音频...")
    await generate_audio(f"{poem_data['title']}。{poem_data['author']}。{poem_data['poem']}", "zh-CN-YunxiNeural", poem_audio_path)
    await generate_audio(f"译文含义：{poem_data['translation']}", "zh-CN-XiaoxiaoNeural", trans_audio_path)

    print("3. 生成意境背景图（主图）...")
    download_background_image(poem_data['image_prompt'], bg_image_1_path)

    print("3b. 生成意境背景图（辅图）...")
    try:
        download_background_image(poem_data.get('image_prompt_2', poem_data['image_prompt']), bg_image_2_path)
    except Exception as e:
        print(f"辅图生成失败，复用主图: {e}")
        import shutil
        shutil.copy(bg_image_1_path, bg_image_2_path)

    image_paths = [bg_image_1_path, bg_image_2_path]

    print("4. 下载背景音乐...")
    download_bgm(bgm_path)

    print("5. 正在合成视频 (Ken Burns + 逐句字幕 + 多图轮播 + BGM)...")
    build_video(poem_data, poem_audio_path, trans_audio_path, image_paths, bgm_path, out_video_path)

    print("5b. 嵌入视频封面...")
    embed_video_cover(out_video_path, bg_image_1_path)

    print("6. 上传并推送至 Telegram Bot...")
    caption = f"📜 *《{poem_data['title']}》* — {poem_data['author']}\n\n{poem_data['poem']}\n\n💡 *译文*\n{poem_data['translation']}"
    send_to_telegram(out_video_path, caption)
    print("=" * 50)
    print("🎉 运行完成！")

if __name__ == "__main__":
    asyncio.run(main())