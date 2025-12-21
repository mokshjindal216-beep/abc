# newsroom.py
import os
import time
import requests
import textwrap
import random
import numpy as np
import cloudinary
import cloudinary.uploader
import config_v2 as config # <--- USES THE NEW CONFIG
import difflib
from PIL import Image, ImageDraw, ImageFont, ImageFile
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip, AudioFileClip
from groq import Groq
from datetime import datetime
from newspaper import Article
from duckduckgo_search import DDGS

# Prevent crashes on partial images
ImageFile.LOAD_TRUNCATED_IMAGES = True

# --- CONFIGURATION ---
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

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": config.TELEGRAM_ADMIN_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, data=payload)
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

# --- DYNAMIC MODEL SELECTOR ---
def get_best_groq_model(client):
    """Asks Groq what models are available and picks the best Llama 3."""
    try:
        models = client.models.list()
        # Prioritize 70b versatile, then 8b instant
        for m in models.data:
            if "llama-3.3-70b" in m.id: return m.id
        for m in models.data:
            if "llama-3.1-70b" in m.id: return m.id
        return "llama3-70b-8192" # Fallback
    except:
        return "llama-3.3-70b-versatile" # Hard fallback

# --- INTELLIGENT DEDUPLICATION ---
def is_duplicate(new_headline, similarity_threshold=0.8):
    # Uses a SEPARATE history file for this V2 bot
    if not os.path.exists("history_v2.txt"): return False
    
    with open("history_v2.txt", "r") as f:
        history = [line.strip().split("|")[0] for line in f if "|" in line]
    
    for old_headline in history:
        ratio = difflib.SequenceMatcher(None, new_headline.lower(), old_headline.lower()).ratio()
        if ratio > similarity_threshold:
            log("FILTER", f"❌ Duplicate detected ({int(ratio*100)}% match): '{old_headline}'")
            return True
    return False

def save_to_history(headline, url):
    with open("history_v2.txt", "a") as f:
        f.write(f"{headline}|{url}\n")

# --- STEP 1: SOURCING ---
def fetch_premium_news():
    log("NEWS", "Fetching Premium Headlines...")
    candidates = []
    
    # 1. NewsAPI
    try:
        sources_str = ",".join(PREMIUM_SOURCES[:12]) 
        url = f"https://newsapi.org/v2/top-headlines?sources={sources_str}&pageSize=30&apiKey={config.NEWS_API_KEY}"
        data = requests.get(url).json()
        if data.get('status') == 'ok':
            for art in data.get('articles', []):
                if art.get('urlToImage'):
                    candidates.append(art)
    except Exception as e: log("WARN", f"NewsAPI Error: {e}")

    # 2. GNews Fallback
    if len(candidates) < 5:
        try:
            url = f"https://gnews.io/api/v4/top-headlines?lang=en&token={config.GNEWS_API_KEY}"
            data = requests.get(url).json()
            if data.get('articles'):
                for art in data['articles']:
                    src = art['source']['name'].lower()
                    if any(x in src for x in ['bbc', 'cnn', 'reuters', 'ap', 'bloomberg']):
                        if art.get('image'):
                            candidates.append({
                                "title": art['title'],
                                "description": art['description'],
                                "urlToImage": art['image'],
                                "url": art['url'],
                                "source": {"name": art['source']['name']}
                            })
        except: pass

    # Filter Duplicates
    unique_candidates = []
    for art in candidates:
        if not is_duplicate(art['title']):
            unique_candidates.append(art)
    
    return unique_candidates[:10]

# --- STEP 2: RESEARCH ---
def perform_deep_research(article):
    log("RESEARCH", f"Analyzing: {article['title']}")
    context_text = ""
    
    try:
        art = Article(article['url'])
        art.download()
        art.parse()
        if len(art.text) > 500:
            return art.text[:2500]
    except: pass

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(article['title'], max_results=3))
            for res in results: context_text += f"{res['body']}\n"
            return context_text
    except: pass
    
    return article['description']

# --- STEP 3: MOOD & CONTENT ---
def generate_editorial_content(article, context_text):
    client = Groq(api_key=config.GROQ_API_KEY)
    model_id = get_best_groq_model(client)
    log("AI", f"Using Model: {model_id}")
    
    # Ask for MOOD
    prompt = f"""
    Analyze this news story.
    1. Classify the MOOD as exactly one of: CRISIS, TECH, or GENERAL.
       - CRISIS: War, disaster, crime, death, scary politics.
       - TECH: Business, AI, crypto, science, startups.
       - GENERAL: Celebrity, viral, sports, feel-good.
    2. Write a 5-8 word viral headline (UPPERCASE).
    3. Write a summary (MAX 20 words).
    
    Format:
    MOOD: [Mood]
    HEADLINE: [Headline]
    SUMMARY: [Summary]
    
    Context: {article['title']}\n{context_text}
    """
    
    response = client.chat.completions.create(
        messages=[{"role":"user","content":prompt}],
        model=model_id
    ).choices[0].message.content.strip()
    
    lines = response.split('\n')
    mood = "GENERAL"
    hl = "BREAKING NEWS"
    summ = "Check caption for details."
    
    for line in lines:
        if line.startswith("MOOD:"): mood = line.replace("MOOD:", "").strip().upper()
        if line.startswith("HEADLINE:"): hl = line.replace("HEADLINE:", "").strip().replace('"','')
        if line.startswith("SUMMARY:"): summ = line.replace("SUMMARY:", "").strip()

    caption_prompt = f"""
    Write an Instagram Caption & First Comment.
    
    CAPTION:
    1. 🚨 HOOK: One shocking sentence.
    2. 👇 SCOOP: 3 bullet points.
    3. 🗣️ ASK: A question.
    4. #Hashtags: 5 tags.
    
    COMMENT:
    Start with "🧠 DEEP DIVE:" then write 200 words explaining the background.
    
    Context: {context_text}
    """
    
    full_text = client.chat.completions.create(
        messages=[{"role":"user","content":caption_prompt}],
        model=model_id
    ).choices[0].message.content.strip()
    
    if "🧠 DEEP DIVE:" in full_text:
        parts = full_text.split("🧠 DEEP DIVE:")
        caption = parts[0].strip()
        comment = "🧠 DEEP DIVE:" + parts[1].strip()
    else:
        caption = full_text
        comment = "Read more in our story highlights!"

    return mood, hl, summ, caption, comment

# --- STEP 4: DYNAMIC RENDERER ---
def fit_text_to_box(draw, text, font_path, max_width, max_height, start_size=100):
    size = start_size
    font = ImageFont.truetype(font_path, size)
    
    while size > 20:
        lines = textwrap.wrap(text, width=15)
        max_w = 0
        total_h = 0
        
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            max_w = max(max_w, w)
            total_h += h + 10
            
        if max_w < max_width and total_h < max_height:
            return font, lines
        
        size -= 5
        font = ImageFont.truetype(font_path, size)
        
    return font, textwrap.wrap(text, width=20)

def render_video(article, mood, headline, summary):
    log("VIDEO", f"Rendering with Mood: {mood}")
    ensure_assets()
    
    primary_color = "#FFD700" # Gold
    if "CRISIS" in mood: primary_color = "#FF0000" # Red
    elif "TECH" in mood: primary_color = "#00F0FF" # Blue
        
    try:
        resp = requests.get(article['urlToImage'], stream=True, timeout=10)
        with open("bg.jpg", "wb") as f: 
            for chunk in resp.iter_content(1024): f.write(chunk)
            
        W, H = 1080, 1920
        overlay = Image.new('RGBA', (W, H), (0,0,0,0))
        draw = ImageDraw.Draw(overlay)
        
        # Gradient
        gradient = Image.new('L', (W, H), 0)
        g_draw = ImageDraw.Draw(gradient)
        for y in range(int(H * 0.40), H):
            alpha = int((y - H * 0.40) / (H * 0.60) * 255)
            g_draw.line([(0, y), (W, y)], fill=alpha)
        
        black_out = Image.new('RGBA', (W, H), (0,0,0,0))
        black_out.paste(Image.new('RGBA', (W, H), (0,0,0,240)), (0,0), mask=gradient)
        overlay = Image.alpha_composite(overlay, black_out)
        draw = ImageDraw.Draw(overlay)

        # Source Badge
        source_name = f"  {article['source']['name'].upper()}  "
        font_src = get_font(35)
        length = draw.textlength(source_name, font_src)
        draw.rounded_rectangle([(60, 150), (60+length+20, 210)], radius=12, fill=primary_color)
        draw.text((70, 160), source_name, font_src, fill="black")

        # --- SAFE ZONE TEXT ---
        # Headline Box: Y=850, H=400
        font_hl, hl_lines = fit_text_to_box(draw, headline, "Anton.ttf", 900, 400, start_size=110)
        cursor_y = 850
        
        for line in hl_lines:
            draw.text((65, cursor_y+5), line, font=font_hl, fill="black")
            draw.text((60, cursor_y), line, font=font_hl, fill=primary_color)
            cursor_y += font_hl.size + 10
            
        cursor_y += 30
        
        # Summary Box: Ends at 1350 (Safe Zone)
        remaining_h = 1350 - cursor_y
        font_sum, sum_lines = fit_text_to_box(draw, summary, "Anton.ttf", 900, remaining_h, start_size=60)
        
        for line in sum_lines:
            draw.text((62, cursor_y+2), line, font=font_sum, fill="black")
            draw.text((60, cursor_y), line, font=font_sum, fill="white")
            cursor_y += font_sum.size + 10
            
        overlay.save("overlay.png")

        # Animation
        img_pil = Image.open("bg.jpg").convert("RGB")
        base_w, base_h = img_pil.size
        ratio = 1080/1920
        if base_w/base_h > ratio:
            new_w = base_h * ratio
            img_pil = img_pil.crop(((base_w - new_w)/2, 0, (base_w + new_w)/2, base_h))
        else:
            new_h = base_w / ratio
            img_pil = img_pil.crop((0, (base_h - new_h)/2, base_w, (base_h + new_h)/2))
        img_pil = img_pil.resize((1080, 1920), Image.LANCZOS)
        img_pil.save("temp_bg.jpg")

        img_clip = ImageClip("temp_bg.jpg").set_duration(6)
        img_clip = img_clip.fl(lambda gf, t: np.array(Image.fromarray(gf(t)).resize(
            [int(d*(1+0.04*t)) for d in Image.fromarray(gf(t)).size], 
            Image.BILINEAR
        ).crop((0,0,1080,1920))))

        track = "assets/audio/track.mp3"
        final = CompositeVideoClip([img_clip, ImageClip("overlay.png").set_duration(6)])
        if os.path.exists(track): 
            final = final.set_audio(AudioFileClip(track).subclip(0,6))
        
        final.write_videofile("final.mp4", fps=24, codec='libx264', audio_codec='aac', preset='ultrafast', threads=4, logger=None)
        return "final.mp4"
    
    except Exception as e:
        log("ERROR", f"Render failed: {e}")
        return None

# --- STEP 5: PUBLISH ---
def publish(video_path, caption, comment):
    try:
        # Cloudinary
        res = cloudinary.uploader.upload(video_path, resource_type="video")
        video_url = res['secure_url']
        
        # Insta Container
        url = f"https://graph.facebook.com/v18.0/{config.IG_USER_ID}/media"
        payload = {"media_type": "REELS", "video_url": video_url, "caption": caption, "access_token": config.IG_ACCESS_TOKEN}
        r = requests.post(url, data=payload).json()
        if 'id' not in r: return False
        
        container_id = r['id']
        log("INSTA", f"ID: {container_id}. Waiting...")
        
        # Poll
        for i in range(20):
            time.sleep(10)
            status = requests.get(f"https://graph.facebook.com/v18.0/{container_id}", 
                                params={"fields":"status_code", "access_token": config.IG_ACCESS_TOKEN}).json()
            
            if status.get('status_code') == 'FINISHED':
                pub = requests.post(f"https://graph.facebook.com/v18.0/{config.IG_USER_ID}/media_publish", 
                                  data={"creation_id": container_id, "access_token": config.IG_ACCESS_TOKEN}).json()
                if 'id' in pub:
                    media_id = pub['id']
                    log("SUCCESS", "Published!")
                    # Inject Comment
                    time.sleep(10)
                    requests.post(f"https://graph.facebook.com/v18.0/{media_id}/comments", 
                                data={"message": comment, "access_token": config.IG_ACCESS_TOKEN})
                    send_telegram(f"🚀 Published: {media_id}")
                    return True
        return False
    except Exception as e:
        log("ERROR", str(e))
        return False

if __name__ == "__main__":
    ensure_assets()
    log("BOT", "Starting Newsroom V2...")
    candidates = fetch_premium_news()
    
    if not candidates:
        log("BOT", "No candidates.")
    else:
        for i, article in enumerate(candidates):
            log("BOT", f"Processing: {article['title']}")
            try:
                # 1. Research
                context = perform_deep_research(article)
                # 2. Editorial
                mood, hl, summ, cap, comm = generate_editorial_content(article, context)
                # 3. Render
                video = render_video(article, mood, hl, summ)
                # 4. Publish
                if video and publish(video, cap, comm):
                    save_to_history(article['title'], article['url'])
                    break
            except Exception as e:
                log("ERROR", f"Failed: {e}")
