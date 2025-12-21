# newsroom.py
import os
import time
import requests
import textwrap
import json
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

ImageFile.LOAD_TRUNCATED_IMAGES = True

cloudinary.config(
  cloud_name = config.CLOUDINARY_CLOUD_NAME,
  api_key = config.CLOUDINARY_API_KEY,
  api_secret = config.CLOUDINARY_API_SECRET
)

PREMIUM_SOURCES = ["reuters", "associated-press", "bloomberg", "bbc-news", "cnn", "the-wall-street-journal", "the-washington-post", "time", "wired", "the-verge", "techcrunch", "business-insider"]

def log(step, message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔹 {step}: {message}")

# --- RESTORED TELEGRAM ---
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

def get_best_groq_model(client):
    try:
        models = client.models.list()
        for m in models.data:
            if "llama-3.3-70b" in m.id: return m.id
        return "llama-3.3-70b-versatile"
    except: return "llama-3.3-70b-versatile"

# --- REFINED AD-BLOCKER ---
def is_duplicate_or_ad(title):
    t_low = title.lower()
    # Only block "gift" if it's paired with shopping words
    shopping_triggers = ["buy", "shop", "deals", "save", "under $", "gift guide", "discount"]
    if any(x in t_low for x in shopping_triggers):
        log("FILTER", f"❌ Shopping Ad blocked: {title}")
        return True
    
    if not os.path.exists("history_v2.txt"): return False
    with open("history_v2.txt", "r") as f:
        history = [line.strip().split("|")[0] for line in f if "|" in line]
    for old in history:
        if difflib.SequenceMatcher(None, title.lower(), old.lower()).ratio() > 0.8:
            return True
    return False

# --- STEP 1: SOURCING ---
def fetch_news():
    log("NEWS", "Sourcing Premium Hard News...")
    candidates = []
    try:
        sources = ",".join(PREMIUM_SOURCES[:10])
        url = f"https://newsapi.org/v2/top-headlines?sources={sources}&apiKey={config.NEWS_API_KEY}"
        data = requests.get(url, timeout=20).json()
        if data.get('status') == 'ok':
            for art in data.get('articles', []):
                if art.get('urlToImage') and not is_duplicate_or_ad(art['title']):
                    candidates.append(art)
    except: pass
    return candidates[:10]

# --- STEP 2: RESEARCH & AI ---
def perform_research(article):
    try:
        art = Article(article['url'])
        art.download(); art.parse()
        if len(art.text) > 400: return art.text[:2000]
    except: pass
    try:
        with DDGS() as ddgs:
            return "\n".join([r['body'] for r in ddgs.text(article['title'], max_results=3)])
    except: return article.get('description', '')

def generate_content(article, context):
    client = Groq(api_key=config.GROQ_API_KEY)
    model = get_best_groq_model(client)
    
    # 1. VIDEO JSON
    video_prompt = f"Analyze: {article['title']}\nContext: {context}\nReturn ONLY JSON: {{\"mood\": \"CRISIS/TECH/GENERAL\", \"headline\": \"5-8 words\", \"summary\": \"max 20 words\"}}"
    v_data = json.loads(client.chat.completions.create(messages=[{"role":"user","content":video_prompt}], model=model, response_format={"type": "json_object"}).choices[0].message.content)
    
    # 2. CAPTION
    cap_prompt = f"Write a viral IG caption with a hook, 3 bullets, a question, and 5 hashtags for: {article['title']}"
    caption = client.chat.completions.create(messages=[{"role":"user","content":cap_prompt}], model=model).choices[0].message.content.strip()
    
    # 3. DEEP DIVE
    div_prompt = f"Write a 250-word analytical deep dive starting with '🧠 DEEP DIVE:' for: {article['title']}\nContext: {context}"
    comment = client.chat.completions.create(messages=[{"role":"user","content":div_prompt}], model=model).choices[0].message.content.strip()
    
    return v_data['mood'], v_data['headline'], v_data['summary'], caption, comment

# --- STEP 3: RENDERER ---
def fit_text(draw, text, max_w, max_h, start_size):
    size = start_size
    while size > 20:
        font = ImageFont.truetype("Anton.ttf", size)
        lines = textwrap.wrap(text, width=int(max_w/(size*0.55)))
        th = sum([draw.textbbox((0,0), l, font=font)[3] - draw.textbbox((0,0), l, font=font)[1] + 12 for l in lines])
        if th < max_h: return font, lines
        size -= 5
    return ImageFont.truetype("Anton.ttf", 20), textwrap.wrap(text, width=25)

def render_video(article, mood, hl, summ):
    ensure_assets()
    color = "#FFD700" 
    if mood == "CRISIS": color = "#FF0000"
    elif mood == "TECH": color = "#00F0FF"
    
    try:
        r = requests.get(article['urlToImage'], timeout=20)
        with open("bg.jpg", "wb") as f: f.write(r.content)
        W, H = 1080, 1920
        overlay = Image.new('RGBA', (W, H), (0,0,0,0))
        draw = ImageDraw.Draw(overlay)
        
        # UI Darken
        grad = Image.new('L', (W, H), 0)
        for y in range(int(H*0.4), H): ImageDraw.Draw(grad).line([(0,y),(W,y)], fill=int((y-H*0.4)/(H*0.6)*255))
        overlay.paste(Image.new('RGBA',(W,H),(0,0,0,230)), (0,0), mask=grad)
        draw = ImageDraw.Draw(overlay)

        # Source
        f_s = ImageFont.truetype("Anton.ttf", 35)
        sn = f" {article['source']['name'].upper()} "
        draw.rounded_rectangle([(60,150), (60+draw.textlength(sn, f_s)+20, 210)], 12, fill=color)
        draw.text((70,160), sn, font=f_s, fill="black")
        
        # Headline
        f_h, h_l = fit_text(draw, hl.upper(), 900, 400, 100)
        curr_y = 850
        for l in h_l:
            draw.text((65, curr_y+5), l, font=f_h, fill="black")
            draw.text((60, curr_y), l, font=f_h, fill=color)
            curr_y += f_h.size + 15
        
        # Summary
        f_u, s_l = fit_text(draw, summ, 900, 1350-curr_y, 55)
        curr_y += 20
        for l in s_l:
            draw.text((60, curr_y), l, font=f_u, fill="white")
            curr_y += f_u.size + 10
            
        overlay.save("overlay.png")
        img = Image.open("bg.jpg").convert("RGB")
        bw, bh = img.size
        ratio = 1080/1920
        if bw/bh > ratio:
            nw = bh * ratio
            img = img.crop(((bw-nw)/2, 0, (bw+nw)/2, bh))
        else:
            nh = bw/ratio
            img = img.crop((0, (bh-nh)/2, bw, (bh-nh)/2 + nh))
        img.resize((1080, 1920), Image.LANCZOS).save("temp_bg.jpg")
        
        clip = ImageClip("temp_bg.jpg").set_duration(6).fl(lambda gf, t: np.array(Image.fromarray(gf(t)).resize([int(d*(1+0.04*t)) for d in Image.fromarray(gf(t)).size], Image.BILINEAR).crop((0,0,1080,1920))))
        final = CompositeVideoClip([clip, ImageClip("overlay.png").set_duration(6)])
        if os.path.exists("assets/audio/track.mp3"): final = final.set_audio(AudioFileClip("assets/audio/track.mp3").subclip(0,6))
        
        final.write_videofile("final.mp4", fps=24, codec='libx264', audio_codec='aac', preset='ultrafast', logger=None)
        return "final.mp4"
    except Exception as e: return None

# --- STEP 4: PUBLISH ---
def publish(video_path, caption, comment):
    try:
        up = cloudinary.uploader.upload(video_path, resource_type="video")
        url = f"https://graph.facebook.com/v18.0/{config.IG_USER_ID}/media"
        res = requests.post(url, data={"media_type": "REELS", "video_url": up['secure_url'], "caption": caption, "access_token": config.IG_ACCESS_TOKEN}).json()
        if 'id' not in res: return False
        
        cid = res['id']
        for _ in range(20):
            time.sleep(10)
            status = requests.get(f"https://graph.facebook.com/v18.0/{cid}", params={"fields":"status_code", "access_token": config.IG_ACCESS_TOKEN}).json()
            if status.get('status_code') == 'FINISHED':
                pub = requests.post(f"https://graph.facebook.com/v18.0/{config.IG_USER_ID}/media_publish", data={"creation_id": cid, "access_token": config.IG_ACCESS_TOKEN}).json()
                if 'id' in pub:
                    time.sleep(10)
                    requests.post(f"https://graph.facebook.com/v18.0/{pub['id']}/comments", data={"message": comment, "access_token": config.IG_ACCESS_TOKEN})
                    send_telegram(f"✅ *Newsroom V2 Live!*\n{caption[:100]}...")
                    return True
        return False
    except: return False

if __name__ == "__main__":
    ensure_assets()
    log("BOT", "Starting Fixed Newsroom V2...")
    articles = fetch_news()
    for art in articles:
        log("BOT", f"Trying: {art['title']}")
        try:
            ctx = perform_research(art)
            mood, hl, summ, cap, comm = generate_content(art, ctx)
            video = render_video(art, mood, hl, summ)
            if video and publish(video, cap, comm):
                with open("history_v2.txt", "a") as f: f.write(f"{art['title']}|{art['url']}\n")
                break
        except Exception as e: log("ERROR", f"Loop: {e}")
