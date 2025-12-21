# newsroom.py
import os
import time
import requests
import textwrap
import random
import numpy as np
import cloudinary
import cloudinary.uploader
import config_v2 as config
import difflib
from PIL import Image, ImageDraw, ImageFont, ImageFile
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip, AudioFileClip
from groq import Groq
from datetime import datetime
from newspaper import Article
from duckduckgo_search import DDGS
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Prevent crashes on partial images
ImageFile.LOAD_TRUNCATED_IMAGES = True

# --- SETUP CLOUDINARY ---
cloudinary.config(
  cloud_name = config.CLOUDINARY_CLOUD_NAME,
  api_key = config.CLOUDINARY_API_KEY,
  api_secret = config.CLOUDINARY_API_SECRET
)

PREMIUM_SOURCES = [
    "reuters", "associated-press", "bloomberg", "bbc-news", "cnn", 
    "the-wall-street-journal", "the-washington-post", "time", "wired", 
    "the-verge", "techcrunch", "business-insider", "abc-news", "cbs-news", 
    "nbc-news", "politico", "al-jazeera-english", "financial-times", 
    "the-guardian-uk", "fortune"
]

# --- UTILS ---
def log(step, message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔹 {step}: {message}")

def get_retry_session():
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": config.TELEGRAM_ADMIN_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, data=payload, timeout=10)
    except: pass

def ensure_assets():
    os.makedirs('assets/audio', exist_ok=True)
    if not os.path.exists("assets/audio/track.mp3"):
        os.system("wget -q -O assets/audio/track.mp3 https://github.com/rafaelreis-hotmart/Audio-Sample-files/raw/master/sample.mp3")
    if not os.path.exists("Anton.ttf"):
        os.system("wget -q -O Anton.ttf https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf")

def get_font(size=60):
    try: return ImageFont.truetype("Anton.ttf", size)
    except: return ImageFont.load_default()

def get_best_groq_model(client):
    try:
        models = client.models.list()
        for m in models.data:
            if "llama-3.3-70b" in m.id: return m.id
        return "llama-3.3-70b-versatile"
    except: return "llama-3.3-70b-versatile"

# --- INTELLIGENT DEDUPLICATION ---
def is_duplicate(new_headline, similarity_threshold=0.8):
    if not os.path.exists("history_v2.txt"): return False
    with open("history_v2.txt", "r") as f:
        history = [line.strip().split("|")[0] for line in f if "|" in line]
    for old_headline in history:
        if difflib.SequenceMatcher(None, new_headline.lower(), old_headline.lower()).ratio() > similarity_threshold:
            log("FILTER", f"❌ Duplicate: '{old_headline}'")
            return True
    return False

def save_to_history(headline, url):
    with open("history_v2.txt", "a") as f:
        f.write(f"{headline}|{url}\n")

# --- STEP 1: SOURCING ---
def fetch_premium_news():
    log("NEWS", "Fetching Premium Headlines...")
    candidates = []
    session = get_retry_session()
    try:
        sources_str = ",".join(PREMIUM_SOURCES[:12]) 
        url = f"https://newsapi.org/v2/top-headlines?sources={sources_str}&pageSize=30&apiKey={config.NEWS_API_KEY}"
        data = session.get(url, timeout=20).json()
        if data.get('status') == 'ok':
            candidates.extend([a for a in data.get('articles', []) if a.get('urlToImage')])
    except Exception as e: log("WARN", f"NewsAPI Error: {e}")

    unique_candidates = [art for art in candidates if not is_duplicate(art['title'])]
    return unique_candidates[:10]

# --- STEP 2: RESEARCH ---
def perform_deep_research(article):
    log("RESEARCH", f"Analyzing: {article['title']}")
    try:
        art = Article(article['url'])
        art.download()
        art.parse()
        if len(art.text) > 500: return art.text[:2500]
    except: pass
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(article['title'], max_results=3))
            return "\n".join([res['body'] for res in results])
    except: return article.get('description', '')

# --- STEP 3: MOOD & CONTENT ---
def generate_editorial_content(article, context_text):
    client = Groq(api_key=config.GROQ_API_KEY)
    model_id = get_best_groq_model(client)
    log("AI", f"Using Model: {model_id}")
    
    prompt = f"Analyze story. Mood (CRISIS, TECH, GENERAL). Headline (5-8 words). Summary (20 words).\nContext: {article['title']}\n{context_text}"
    response = client.chat.completions.create(messages=[{"role":"user","content":prompt}], model=model_id).choices[0].message.content.strip()
    
    mood, hl, summ = "GENERAL", "BREAKING NEWS", "Check caption."
    for line in response.split('\n'):
        if "MOOD:" in line: mood = line.split("MOOD:")[1].strip().upper()
        if "HEADLINE:" in line: hl = line.split("HEADLINE:")[1].strip().replace('"','')
        if "SUMMARY:" in line: summ = line.split("SUMMARY:")[1].strip()

    caption_prompt = f"Write IG Caption (Hook, 3 Bullets, Question) & Comment (250-word Deep Dive).\nContext: {context_text}"
    full_text = client.chat.completions.create(messages=[{"role":"user","content":caption_prompt}], model=model_id).choices[0].message.content.strip()
    
    if "🧠 DEEP DIVE:" in full_text:
        parts = full_text.split("🧠 DEEP DIVE:")
        return mood, hl, summ, parts[0].strip(), "🧠 DEEP DIVE:" + parts[1].strip()
    return mood, hl, summ, full_text, "Check story highlights!"

# --- STEP 4: DYNAMIC RENDERER ---
def fit_text_to_box(draw, text, font_path, max_width, max_height, start_size=100):
    size = start_size
    while size > 20:
        font = ImageFont.truetype(font_path, size)
        lines = textwrap.wrap(text, width=int(max_width/(size*0.6)))
        total_h = sum([draw.textbbox((0, 0), l, font=font)[3]-draw.textbbox((0, 0), l, font=font)[1] + 10 for l in lines])
        if total_h < max_height: return font, lines
        size -= 5
    return ImageFont.truetype(font_path, 20), textwrap.wrap(text, width=30)

def render_video(article, mood, headline, summary):
    log("VIDEO", f"Rendering with Mood: {mood}")
    ensure_assets()
    session = get_retry_session()
    primary_color = "#FFD700" # Gold
    if "CRISIS" in mood: primary_color = "#FF0000"
    elif "TECH" in mood: primary_color = "#00F0FF"

    try:
        resp = session.get(article['urlToImage'], stream=True, timeout=20)
        with open("bg.jpg", "wb") as f: f.write(resp.content)
            
        W, H = 1080, 1920
        overlay = Image.new('RGBA', (W, H), (0,0,0,0))
        draw = ImageDraw.Draw(overlay)
        
        # UI Gradient
        gradient = Image.new('L', (W, H), 0)
        for y in range(int(H * 0.40), H):
            alpha = int((y - H * 0.40) / (H * 0.60) * 255)
            ImageDraw.Draw(gradient).line([(0, y), (W, y)], fill=alpha)
        
        black_out = Image.new('RGBA', (W, H), (0,0,0,0))
        black_out.paste(Image.new('RGBA', (W, H), (0,0,0,240)), (0,0), mask=gradient)
        overlay = Image.alpha_composite(overlay, black_out)
        draw = ImageDraw.Draw(overlay)

        # Badge - FIXED fill argument error
        font_src = get_font(35)
        src_name = f"  {article['source']['name'].upper()}  "
        length = draw.textlength(src_name, font=font_src)
        draw.rounded_rectangle([(60, 150), (60+length+20, 210)], radius=12, fill=primary_color)
        draw.text((70, 160), src_name, font=font_src, fill="black")

        # Text Safe Zone
        font_hl, hl_lines = fit_text_to_box(draw, headline, "Anton.ttf", 900, 400, 110)
        cursor_y = 850
        for l in hl_lines:
            draw.text((65, cursor_y+5), l, font=font_hl, fill="black")
            draw.text((60, cursor_y), l, font=font_hl, fill=primary_color)
            cursor_y += font_hl.size + 10
        
        font_sum, sum_lines = fit_text_to_box(draw, summary, "Anton.ttf", 900, 1350-cursor_y-30, 60)
        cursor_y += 30
        for l in sum_lines:
            draw.text((62, cursor_y+2), l, font=font_sum, fill="black")
            draw.text((60, cursor_y), l, font=font_sum, fill="white")
            cursor_y += font_sum.size + 10
            
        overlay.save("overlay.png")
        img = Image.open("bg.jpg").convert("RGB")
        bw, bh = img.size
        ratio = 1080/1920
        if bw/bh > ratio:
            nw = bh * ratio
            img = img.crop(((bw - nw)/2, 0, (bw + nw)/2, bh))
        else:
            nh = bw / ratio
            img = img.crop((0, (bh - nh)/2, bw, (bh + nh)/2))
        img.resize((1080, 1920), Image.LANCZOS).save("temp_bg.jpg")

        img_clip = ImageClip("temp_bg.jpg").set_duration(6)
        img_clip = img_clip.fl(lambda gf, t: np.array(Image.fromarray(gf(t)).resize(
            [int(d*(1+0.04*t)) for d in Image.fromarray(gf(t)).size], Image.BILINEAR).crop((0,0,1080,1920))))

        final = CompositeVideoClip([img_clip, ImageClip("overlay.png").set_duration(6)])
        if os.path.exists("assets/audio/track.mp3"): final = final.set_audio(AudioFileClip("assets/audio/track.mp3").subclip(0,6))
        final.write_videofile("final.mp4", fps=24, codec='libx264', audio_codec='aac', preset='ultrafast', logger=None)
        return "final.mp4"
    except Exception as e:
        log("ERROR", f"Render failed: {e}")
        return None

# --- STEP 5: PUBLISH ---
def publish(video_path, caption, comment):
    try:
        res = cloudinary.uploader.upload(video_path, resource_type="video")
        url = f"https://graph.facebook.com/v18.0/{config.IG_USER_ID}/media"
        payload = {"media_type": "REELS", "video_url": res['secure_url'], "caption": caption, "access_token": config.IG_ACCESS_TOKEN}
        r = requests.post(url, data=payload, timeout=20).json()
        if 'id' not in r: return False
        
        cid = r['id']
        for _ in range(20):
            time.sleep(10)
            status = requests.get(f"https://graph.facebook.com/v18.0/{cid}", params={"fields":"status_code", "access_token": config.IG_ACCESS_TOKEN}, timeout=10).json()
            if status.get('status_code') == 'FINISHED':
                pub = requests.post(f"https://graph.facebook.com/v18.0/{config.IG_USER_ID}/media_publish", data={"creation_id": cid, "access_token": config.IG_ACCESS_TOKEN}, timeout=20).json()
                if 'id' in pub:
                    time.sleep(10)
                    requests.post(f"https://graph.facebook.com/v18.0/{pub['id']}/comments", data={"message": comment, "access_token": config.IG_ACCESS_TOKEN}, timeout=20)
                    send_telegram(f"🚀 Published: {pub['id']}")
                    return True
        return False
    except Exception as e: return False

if __name__ == "__main__":
    ensure_assets()
    log("BOT", "Starting Newsroom V2...")
    candidates = fetch_premium_news()
    if candidates:
        for article in candidates:
            log("BOT", f"Processing: {article['title']}")
            try:
                context = perform_deep_research(article)
                mood, hl, summ, cap, comm = generate_editorial_content(article, context)
                video = render_video(article, mood, hl, summ)
                if video and publish(video, cap, comm):
                    save_to_history(article['title'], article['url'])
                    break
            except Exception as e: log("ERROR", f"Failed: {e}")
