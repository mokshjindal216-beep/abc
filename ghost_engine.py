import os, time, requests, textwrap, json, numpy as np, cloudinary, cloudinary.uploader, difflib, re, random
from PIL import Image, ImageDraw, ImageFont, ImageFile, ImageEnhance, ImageOps
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip, AudioFileClip, vfx
from groq import Groq
from datetime import datetime
from newspaper import Article
from duckduckgo_search import DDGS
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- CONFIGURATION ---
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")
IG_USER_ID = os.getenv("IG_USER_ID")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
FB_PAGE_ID = os.getenv("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN")
YT_REFRESH_TOKEN = os.getenv("YT_REFRESH_TOKEN")
YT_CLIENT_ID = os.getenv("YT_CLIENT_ID")
YT_CLIENT_SECRET = os.getenv("YT_CLIENT_SECRET")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID")

ImageFile.LOAD_TRUNCATED_IMAGES = True
cloudinary.config(cloud_name=CLOUDINARY_CLOUD_NAME, api_key=CLOUDINARY_API_KEY, api_secret=CLOUDINARY_API_SECRET)

# --- ASSETS ---
def log(step, msg): 
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 👻 {step.upper()}: {msg}")

def ensure_ghost_assets():
    os.makedirs('ghost_assets', exist_ok=True)
    tracks = {
        "cinematic": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
        "deep": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-8.mp3", 
        "ambient": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3"
    }
    for n, u in tracks.items():
        if not os.path.exists(f"ghost_assets/{n}.mp3"): 
            os.system(f"wget -q -O ghost_assets/{n}.mp3 {u}")
    if not os.path.exists("Anton.ttf"): 
        os.system("wget -q -O Anton.ttf https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf")

# --- INTELLIGENCE ---
def get_groq_model(client):
    return random.choice(["llama-3.3-70b-versatile", "mixtral-8x7b-32768", "llama3-70b-8192"])

def is_toxic_content(title):
    t = title.lower()
    blocklist = [
        "gift guide", "buying guide", "deals", "save $", "shop", "top picks", "review", "best of",
        "opinion", "editorial", "watch:", "letter to", "horoscope", "perspective", "analysis", "column",
        "subscribe", "sign up", "deal of the day"
    ]
    if any(x in t for x in blocklist): return True
    if not os.path.exists("ghost_history.txt"): return False
    with open("ghost_history.txt", "r") as f:
        for l in f:
            if "|" in l and difflib.SequenceMatcher(None, t, l.split("|")[0].lower()).ratio() > 0.8: return True
    return False

def fetch_fresh_news():
    log("NEWS", "Scanning wire services...")
    cands = []
    sources = ["reuters", "associated-press", "bloomberg", "bbc-news", "wired", "the-verge", "techcrunch", "cnn", "time", "business-insider"]
    random.shuffle(sources)
    try:
        url = f"https://newsapi.org/v2/top-headlines?sources={','.join(sources[:6])}&apiKey={NEWS_API_KEY}"
        r = requests.get(url, timeout=20).json()
        if r.get('status') == 'ok': 
            for a in r['articles']:
                if a.get('urlToImage') and not is_toxic_content(a['title']):
                    cands.append(a)
    except: pass
    return cands[:5]

def analyze_story(art):
    client = Groq(api_key=GROQ_API_KEY)
    try:
        with DDGS() as ddgs: 
            res = ddgs.text(art['title'], max_results=1)
            ctx = res[0]['body'] if res else art['description']
    except: ctx = art['description']

    sys_msg = (
        f"Role: Senior News Editor. Story: {art['title']}\nContext: {ctx}\n"
        f"Task: Output JSON with keys:\n"
        f"- 'mood' (URGENT/TECH/CALM)\n"
        f"- 'headline' (Max 6 words, uppercase, impactful, NO clickbait)\n"
        f"- 'body' (One clear, objective sentence. Max 15 words.)"
    )
    try:
        raw = client.chat.completions.create(messages=[{"role":"user","content":sys_msg}], model=get_groq_model(client), response_format={"type": "json_object"}).choices[0].message.content
        data = json.loads(raw)
    except: data = {"mood": "CALM", "headline": "BREAKING NEWS", "body": art['title']}

    cap = client.chat.completions.create(messages=[{"role":"user","content":f"Caption for: {art['title']}. Start with 'Source: {art['source']['name']}'. End with 10 relevant hashtags."}], model="llama3-70b-8192").choices[0].message.content.strip()
    return data, cap

# --- RENDERER ---
def apply_visual_noise(img):
    img = img.convert("RGB")
    enhancer = ImageEnhance.Color(img)
    img = enhancer.enhance(random.uniform(0.85, 1.15))
    overlay = Image.new("RGB", img.size, (random.randint(0,20), random.randint(0,20), random.randint(0,20)))
    img = Image.blend(img, overlay, 0.05)
    return img

def create_cinematic_pan(img_path, duration):
    clip = ImageClip(img_path).set_duration(duration)
    w, h = clip.size
    def effect(get_frame, t):
        frame_img = Image.fromarray(get_frame(t))
        progress = t / duration
        zoom = 1.0 + (0.15 * progress)
        pan_speed = 40
        pan_offset = int(pan_speed * progress)
        new_w, new_h = int(w * zoom), int(h * zoom)
        frame_resized = frame_img.resize((new_w, new_h), Image.LANCZOS)
        center_x, center_y = new_w // 2, new_h // 2
        left = center_x - 540 + pan_offset
        top = center_y - 960
        if left < 0: left = 0
        if top < 0: top = 0
        return np.array(frame_resized.crop((left, top, left+1080, top+1920)))
    return clip.fl(effect)

def render_ghost_video(art, data):
    ensure_ghost_assets()
    duration = random.uniform(8.0, 14.0)
    try:
        r = requests.get(art['urlToImage'], timeout=15)
        with open("ghost_raw.jpg", "wb") as f: f.write(r.content)
        img = apply_visual_noise(Image.open("ghost_raw.jpg"))
        img.save("ghost_proc.jpg")
        
        bg_clip = create_cinematic_pan("ghost_proc.jpg", duration)
        
        overlay = Image.new('RGBA', (1080, 1920), (0,0,0,0))
        draw = ImageDraw.Draw(overlay)
        grad = Image.new('L', (1080, 800), 0)
        for y in range(800): ImageDraw.Draw(grad).line([(0,y),(1080,y)], fill=int((y/800)*255))
        overlay.paste(Image.new('RGBA', (1080,800), (0,0,0,220)), (0, 1120), mask=grad)
        
        font_s = ImageFont.truetype("Anton.ttf", 30)
        src_text = f" {art['source']['name'].upper()} "
        draw.rounded_rectangle([(50, 100), (50+draw.textlength(src_text, font_s)+20, 150)], radius=10, fill="#E63946")
        draw.text((60, 108), src_text, font=font_s, fill="white")
        
        font_h = ImageFont.truetype("Anton.ttf", 90)
        lines = textwrap.wrap(data['headline'], width=12)
        y = 1200
        for line in lines:
            draw.text((55, y+5), line, font=font_h, fill="black")
            draw.text((50, y), line, font=font_h, fill="white")
            y += 100
        
        font_b = ImageFont.truetype("Anton.ttf", 50)
        lines_b = textwrap.wrap(data['body'], width=25)
        y += 20
        for line in lines_b:
            draw.text((50, y), line, font=font_b, fill="#A8DADC")
            y += 60
            
        overlay.save("ghost_overlay.png")
        ui_clip = ImageClip("ghost_overlay.png").set_duration(duration)
        
        track = random.choice(["cinematic", "deep", "ambient"])
        audio = AudioFileClip(f"ghost_assets/{track}.mp3")
        start = random.uniform(0, audio.duration - duration)
        audio = audio.subclip(start, start+duration).audio_fadein(1).audio_fadeout(1).volumex(0.3)
        
        final = CompositeVideoClip([bg_clip, ui_clip]).set_audio(audio).set_duration(duration)
        final.write_videofile("ghost_out.mp4", fps=24, codec='libx264', audio_codec='aac', bitrate="4000k", preset="ultrafast", logger=None)
        return "ghost_out.mp4"
    except Exception as e:
        log("RENDER FAIL", str(e))
        return None

# --- DISTRIBUTION ---
def post_ig(path, cap):
    if not IG_ACCESS_TOKEN: return False
    try:
        url = cloudinary.uploader.upload(path, resource_type="video")['secure_url']
        r1 = requests.post(f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media", data={"media_type": "REELS", "video_url": url, "caption": cap, "access_token": IG_ACCESS_TOKEN}).json()
        if 'id' in r1:
            cid = r1['id']
            for _ in range(15):
                time.sleep(5)
                stat = requests.get(f"https://graph.facebook.com/v18.0/{cid}", params={"fields":"status_code", "access_token": IG_ACCESS_TOKEN}).json()
                if stat.get('status_code') == 'FINISHED':
                    requests.post(f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media_publish", data={"creation_id": cid, "access_token": IG_ACCESS_TOKEN})
                    return True
        return False
    except: return False

def post_fb(path, cap):
    if not FB_ACCESS_TOKEN: return False
    try:
        init = requests.post(f"https://graph.facebook.com/v18.0/{FB_PAGE_ID}/video_reels", data={"upload_phase":"start", "access_token": FB_ACCESS_TOKEN}).json()
        with open(path, 'rb') as f: requests.post(init['upload_url'], headers={"Authorization": f"OAuth {FB_ACCESS_TOKEN}", "file_size": str(os.path.getsize(path))}, data=f)
        time.sleep(10)
        requests.post(f"https://graph.facebook.com/v18.0/{FB_PAGE_ID}/video_reels", data={"upload_phase":"finish", "video_id": init['video_id'], "video_state":"PUBLISHED", "description": cap, "access_token": FB_ACCESS_TOKEN})
        return True
    except: return False

def post_yt_sleeper(path, title, desc):
    if not YT_REFRESH_TOKEN or len(str(YT_REFRESH_TOKEN)) < 5: 
        log("YT", "Sleeper Mode (No Keys) - Skipping")
        return False
    try:
        creds = Credentials(None, refresh_token=YT_REFRESH_TOKEN, token_uri="https://oauth2.googleapis.com/token", client_id=YT_CLIENT_ID, client_secret=YT_CLIENT_SECRET)
        youtube = build("youtube", "v3", credentials=creds)
        body = {"snippet": {"title": title[:95], "description": desc, "tags": ["news", "shorts"], "categoryId": "25"}, "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
        youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(path)).execute()
        return True
    except: return False

if __name__ == "__main__":
    ensure_ghost_assets()
    log("SYSTEM", "Ghost Engine Online.")
    news = fetch_fresh_news()
    if news:
        target = news[0]
        log("TARGET", target['title'])
        data, cap = analyze_story(target)
        video = render_ghost_video(target, data)
        if video:
            ig = post_ig(video, cap)
            fb = post_fb(video, cap)
            yt = post_yt_sleeper(video, data['headline'], cap)
            msg = f"👻 Posted: {data['headline']}\nIG:{ig} FB:{fb} YT:{yt}"
            log("SUCCESS", msg)
            if TELEGRAM_BOT_TOKEN: requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", data={"chat_id": TELEGRAM_ADMIN_ID, "text": msg})
            with open("ghost_history.txt", "a") as f: f.write(f"{target['title']}|{target['url']}|{datetime.now()}\n")
