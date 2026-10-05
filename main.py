import os
import json
import random
import asyncio
import requests
from google import genai
from google.genai import types
import edge_tts
from moviepy.editor import ImageClip, AudioFileClip, TextClip, CompositeVideoClip, concatenate_audioclips

# --- 1. 配置与初始化 ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

HISTORY_FILE = "history.json"

if not GEMINI_API_KEY or not TG_BOT_TOKEN or not TG_CHAT_ID:
    raise ValueError("缺少必要的环境变量！请检查 GEMINI_API_KEY, TG_BOT_TOKEN, TG_CHAT_ID 设置。")

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

# --- 3. Gemini 智能选诗与生成元数据 ---
def get_poem_data():
    history = load_history()
    # 提取历史诗词名，最多排除最近 300 首，防止 Prompt 溢出
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
      "poem": "古诗原文（换行分割，如: 床前明月光\\n疑是地上霜\\n举头望明月\\n低头思故乡）",
      "translation": "现代白话文翻译（简短通顺）",
      "image_prompt": "适用于AI绘图的英文 Prompt，描述该诗表达的意境，传统中国水墨画或写实国风，包含场景、要素等，如: Traditional Chinese ink painting, moonlit quiet bedroom, peaceful night, high quality, 8k"
    }}
    只返回纯 JSON，不要带任何 Markdown 标记或额外说明。
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    
    poem_data = json.loads(response.text)
    
    # 追加到历史记录并保存
    history.append({
        "title": poem_data["title"],
        "author": poem_data["author"]
    })
    save_history(history)
    
    return poem_data

# --- 4. 生成语音 (Edge-TTS) ---
async def generate_audio(text, voice, output_path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

# --- 5. 生成配图 (Pollinations AI / FLUX 引擎) ---
def download_background_image(prompt_text, output_path):
    encoded_prompt = requests.utils.quote(f"{prompt_text}, masterpiece, traditional Chinese artistic style")
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&nologo=true&seed={random.randint(1, 999999)}"
    
    res = requests.get(image_url, timeout=60)
    if res.status_code == 200:
        with open(output_path, 'wb') as f:
            f.write(res.content)
    else:
        raise RuntimeError(f"图片下载失败，HTTP 状态码: {res.status_code}")

# --- 6. 视频合成 (MoviePy + FFmpeg) ---
def build_video(poem_data, poem_audio_path, trans_audio_path, image_path, output_video_path):
    audio_poem = AudioFileClip(poem_audio_path)
    audio_trans = AudioFileClip(trans_audio_path)
    
    # 制作一段 1.5 秒的无声静音作为中间过渡
    silent_gap = AudioFileClip(poem_audio_path).subclip(0, 0.1).volumex(0)
    # 拼接：诗词朗读 -> 停顿 -> 译文朗读
    final_audio = concatenate_audioclips([audio_poem, silent_gap, audio_trans])
    duration = final_audio.duration + 1.0 # 视频保留 1 秒片尾留白
    
    # 背景图片 Clip
    img_clip = ImageClip(image_path).set_duration(duration)
    
    # 拼接排版文本
    text_content = f"《{poem_data['title']}》\n{poem_data['author']}\n\n{poem_data['poem']}\n\n【译文】\n{poem_data['translation']}"
    
    # 文案 Overlays（使用 Linux 环境下自带的中文字体）
    txt_clip = TextClip(
        text_content, 
        fontsize=40, 
        color='white', 
        font='WenQuanYi-ZenHei', 
        method='caption',
        size=(900, 1500),
        align='Center'
    ).set_duration(duration).set_position(('center', 'center'))
    
    # 组合与渲染导出
    video = CompositeVideoClip([img_clip, txt_clip])
    video = video.set_audio(final_audio)
    video.write_videofile(
        output_video_path, 
        fps=24, 
        codec='libx264', 
        audio_codec='aac',
        temp_audiofile='temp-audio.m4a',
        remove_temp=True
    )

# --- 7. 发送 Telegram 视频 ---
def send_to_telegram(video_path, caption):
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendVideo"
    with open(video_path, 'rb') as video_file:
        files = {'video': video_file}
        data = {
            'chat_id': TG_CHAT_ID,
            'caption': caption,
            'parse_mode': 'Markdown'
        }
        res = requests.post(url, files=files, data=data)
        print("Telegram 推送响应:", res.json())

# --- 主入口 ---
async def main():
    print("1. 正在读取历史并选取新古诗...")
    poem_data = get_poem_data()
    print(f"今日古诗: 《{poem_data['title']}》 - {poem_data['author']}")
    
    poem_audio_path = "poem.mp3"
    trans_audio_path = "trans.mp3"
    bg_image_path = "bg.jpg"
    out_video_path = "final_poem.mp4"
    
    print("2. 生成 TTS 朗读音频...")
    # 古诗朗读：云希（沉稳男声）；译文朗读：晓晓（标准女声）
    await generate_audio(f"{poem_data['title']}。{poem_data['author']}。{poem_data['poem']}", "zh-CN-YunxiNeural", poem_audio_path)
    await generate_audio(f"译文含义：{poem_data['translation']}", "zh-CN-XiaoxiaoNeural", trans_audio_path)
    
    print("3. 生成意境背景图...")
    download_background_image(poem_data['image_prompt'], bg_image_path)
    
    print("4. 正在合成视频，请稍候...")
    build_video(poem_data, poem_audio_path, trans_audio_path, bg_image_path, out_video_path)
    
    print("5. 上传并推送至 Telegram Bot...")
    caption = f"📜 *《{poem_data['title']}》* — {poem_data['author']}\n\n{poem_data['poem']}\n\n💡 *译文*：\n{poem_data['translation']}"
    send_to_telegram(out_video_path, caption)
    print("运行完成！")

if __name__ == "__main__":
    asyncio.run(main())
