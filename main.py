# main.py
import os
import time
import requests
import textwrap
import random
import cloudinary
import cloudinary.uploader
import config
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip, AudioFileClip
from groq import Groq
from datetime import datetime

# --- SETUP CLOUDINARY ---
cloudinary.config(
  cloud_name = config.CLOUDINARY_CLOUD_NAME,
  api_key = config.CLOUDINARY_API_KEY,
  api_secret = config.CLOUDINARY_API_SECRET
)

# --- SYSTEM UTILS ---
def log(step, message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔹 {step}: {message}")

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": config.TELEGRAM_ADMIN_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, data=payload)
    except: pass

# --- DEDUPLICATION SYSTEM ---
HISTORY_FILE = "processed_news.txt"

def load_history():
    if not os.path.exists(HISTORY_FILE): return set()
    with open(HISTORY_FILE, "r") as f:
        return set(line.strip() for line in f)

def save_to_history(url):
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{url}\n")

# --- ASSET MANAGER ---
def ensure_assets():
    # 1. Audio
    os.makedirs('assets/audio', exist_ok=True)
    if not os.path.exists("assets/audio/track.mp3"):
        log("ASSETS", "Downloading Audio (First Run Only)...")
        os.system("wget -q -O assets/audio/track.mp3 https://github.com/rafaelreis-hotmart/Audio-Sample-files/raw/master/sample.mp3")
    else:
        log("ASSETS", "Audio found in cache.")

    # 2. Fonts (Backup)
    if not os.path.exists("Anton.ttf"):
        log("ASSETS", "Downloading Backup Font...")
        os.system("wget -q -O Anton.ttf https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf")

def get_font(type="headline", size=60):
    try:
        path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if type=="headline" else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        return ImageFont.truetype(path, size)
    except:
        return ImageFont.truetype("Anton.ttf", size) if os.path.exists("Anton.ttf") else ImageFont.load_default()

# --- NEWS ENGINE ---
def fetch_news():
    log("NEWS", "Fetching Headlines...")
    history = load_history()
    candidates = []
    
    # NewsAPI
    try:
        url = f"https://newsapi.org/v2/top-headlines?country=us&apiKey={config.NEWS_API_KEY}"
        data = requests.get(url).json()
        if data.get('status') == 'ok':
            for art in data.get('articles', []):
                if art.get('urlToImage') and art['url'] not in history:
                    candidates.append(art)
    except Exception as e: log("WARN", f"NewsAPI Error: {e}")

    # GNews
    if len(candidates) < 5:
        try:
            url = f"https://gnews.io/api/v4/top-headlines?lang=en&token={config.GNEWS_API_KEY}"
            data = requests.get(url).json()
            if data.get('articles'):
                for art in data['articles']:
                    if art.get('image') and art['url'] not in history:
                        candidates.append({
                            "title": art['title'],
                            "description": art['description'],
                            "urlToImage": art['image'],
                            "url": art['url'],
                            "source": {"name": art['source']['name']}
                        })
        except: pass
    
    log("NEWS", f"Found {len(candidates)} new candidates.")
    return candidates[:15]

def pick_viral_winner(articles):
    if not articles: return None
    client = Groq(api_key=config.GROQ_API_KEY)
    
    prompt = "Articles:\n"
    for i, a in enumerate(articles): prompt += f"{i}. {a['title']}\n"
    
    try:
        completion = client.chat.completions.create(
            messages=[{"role": "system", "content": "Pick the index (0-14) of the most VIRAL story. Return ONLY the number."},{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile"
        )
        idx = int(''.join(filter(str.isdigit, completion.choices[0].message.content)))
        return articles[idx] if idx < len(articles) else articles[0]
    except: return articles[0]

# --- CONTENT GENERATOR ---
def generate_content(article):
    client = Groq(api_key=config.GROQ_API_KEY)
    model = "llama-3.3-70b-versatile"
    
    hl = client.chat.completions.create(messages=[{"role":"user","content":f"Viral 5-8 word headline for: '{article['title']}'. UPPERCASE. No quotes. Aggressive."}], model=model).choices[0].message.content.strip().replace('"','')
    summ = client.chat.completions.create(messages=[{"role":"user","content":f"Summarize in MAX 25 words. Article: '{article['title']}'. Text only."}], model=model).choices[0].message.content.strip()
    
    caption_prompt = f"""
    Write an engaging Instagram Caption for: '{article['title']}'.
    Structure:
    1. A catchy hook sentence.
    2. THREE bullet points (•) summarizing insights.
    3. A question for the audience.
    4. 5 viral hashtags.
    No intro text.
    """
    caption = client.chat.completions.create(messages=[{"role":"user","content":caption_prompt}], model=model).choices[0].message.content.strip()
    
    return hl, summ, caption

# --- VIDEO ENGINE (Fast Zoom + Safe Layout) ---
def create_video(article, headline, summary):
    log("VIDEO", "Rendering...")
    ensure_assets()
    
    with open("bg.jpg", "wb") as f: f.write(requests.get(article['urlToImage']).content)
    
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

    # Source Pill
    source = f"  {article['source']['name'].upper()}  "
    font_src = get_font("body", 35)
    w = draw.textlength(source, font=font_src)
    draw.rounded_rectangle([(60, 150), (60+w+20, 210)], radius=12, fill="#FFD700")
    draw.text((70, 160), source, font=font_src, fill="black")

    # Text
    cursor = 850
    font_hl = get_font("headline", 100)
    font_sum = get_font("body", 50)

    for line in textwrap.wrap(headline, width=13):
        draw.text((65, cursor+5), line, font=font_hl, fill="black")
        draw.text((60, cursor), line, font=font_hl, fill="#FFD700")
        cursor += 110
    
    cursor += 30
    for line in textwrap.wrap(summary, width=30):
        if cursor > 1500: break
        draw.text((62, cursor+2), line, font=font_sum, fill="black")
        draw.text((60, cursor), line, font=font_sum, fill="white")
        cursor += 60
    
    overlay.save("overlay.png")

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

    img = ImageClip("temp_bg.jpg").set_duration(6)
    img = img.fl(lambda gf, t: np.array(Image.fromarray(gf(t)).resize([int(d*(1+0.04*t)) for d in Image.fromarray(gf(t)).size], Image.BILINEAR).crop((0,0,1080,1920))))

    track = "assets/audio/track.mp3"
    final = CompositeVideoClip([img, ImageClip("overlay.png").set_duration(6)])
    if os.path.exists(track): final = final.set_audio(AudioFileClip(track).subclip(0,6))
    
    final.write_videofile("final.mp4", fps=24, codec='libx264', audio_codec='aac', preset='ultrafast', threads=4, logger=None)
    return "final.mp4"

# --- UPLOAD ENGINE ---
def upload_and_post(video_path, caption):
    log("UPLOAD", "Uploading to Cloudinary...")
    try:
        res = cloudinary.uploader.upload(video_path, resource_type="video")
        video_url = res['secure_url']
    except Exception as e: return log("ERROR", f"Cloudinary failed: {e}")

    log("INSTA", "Creating Reel Container...")
    url = f"https://graph.facebook.com/v18.0/{config.IG_USER_ID}/media"
    payload = {"media_type": "REELS", "video_url": video_url, "caption": caption, "access_token": config.IG_ACCESS_TOKEN}
    
    r = requests.post(url, data=payload).json()
    if 'id' not in r: return log("ERROR", f"Container failed: {r}")
    
    container_id = r['id']
    log("INSTA", f"Waiting for processing (ID: {container_id})...")
    
    for _ in range(12):
        time.sleep(10)
        status = requests.get(f"https://graph.facebook.com/v18.0/{container_id}", params={"fields":"status_code", "access_token": config.IG_ACCESS_TOKEN}).json()
        if status.get('status_code') == 'FINISHED':
            log("INSTA", "Publishing...")
            pub = requests.post(f"https://graph.facebook.com/v18.0/{config.IG_USER_ID}/media_publish", data={"creation_id": container_id, "access_token": config.IG_ACCESS_TOKEN}).json()
            if 'id' in pub:
                log("SUCCESS", "✅ Posted successfully!")
                send_telegram("✅ *Video Posted!*")
                return True
    
    log("ERROR", "Instagram Timed Out.")
    return False

if __name__ == "__main__":
    ensure_assets()
    log("BOT", "Checking for News...")
    candidates = fetch_news()
    winner = pick_viral_winner(candidates)
    
    if winner:
        log("BOT", f"Selected: {winner['title']}")
        hl, summ, caption = generate_content(winner)
        video = create_video(winner, hl, summ)
        if upload_and_post(video, caption):
            save_to_history(winner['url'])
    else:
        log("BOT", "No suitable new news found.")
