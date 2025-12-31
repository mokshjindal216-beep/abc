import os, time, requests, textwrap, json, numpy as np, cloudinary, cloudinary.uploader, difflib, re, random, math, io
from PIL import Image, ImageDraw, ImageFont, ImageFile, ImageEnhance, ImageOps, ImageFilter, ImageChops
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip, AudioFileClip, vfx, CompositeAudioClip
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

# --- 1. ASSETS ---
def log(step, msg): 
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🧬 {step.upper()}: {msg}")

def ensure_assets():
    os.makedirs('ghost_assets', exist_ok=True)
    fonts = {
        "Anton": "https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf",
        "Oswald": "https://github.com/google/fonts/raw/main/ofl/oswald/static/Oswald-Bold.ttf",
        "Roboto": "https://github.com/google/fonts/raw/main/apache/robotocondensed/static/RobotoCondensed-Bold.ttf",
        "Bebas": "https://github.com/google/fonts/raw/main/ofl/bebasneue/BebasNeue-Regular.ttf",
        "Lobster": "https://github.com/google/fonts/raw/main/ofl/lobster/Lobster-Regular.ttf"
    }
    for n, u in fonts.items():
        if not os.path.exists(f"ghost_assets/{n}.ttf"): os.system(f"wget -q -O ghost_assets/{n}.ttf {u}")
        
    tracks = {
        "news1": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
        "news2": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
        "drum": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-8.mp3",
        "noise": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-15.mp3"
    }
    for n, u in tracks.items():
        if not os.path.exists(f"ghost_assets/{n}.mp3"): os.system(f"wget -q -O ghost_assets/{n}.mp3 {u}")

def get_random_agent():
    return random.choice([
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
    ])

# --- 2. INTELLIGENCE ---
def get_groq_model(client):
    try:
        active = [m.id for m in client.models.list().data]
        priority = ["llama-3.3-70b-versatile", "mixtral-8x7b-32768", "llama3-70b-8192"]
        for p in priority:
            if p in active: return p
        return active[0]
    except: return "llama-3.3-70b-versatile"

def is_garbage(title):
    t = title.lower()
    block = ["gift", "deal", "buy", "shop", "review", "best of", "opinion", "editorial", "watch:", "horoscope", "letter", "column", "analysis", "perspective", "save", "subscribe", "sign up", "forecast", "stock", "market"]
    if any(x in t for x in block): return True
    if not os.path.exists("ghost_history.txt"): return False
    with open("ghost_history.txt", "r") as f:
        for l in f:
            if "|" in l and difflib.SequenceMatcher(None, t, l.split("|")[0].lower()).ratio() > 0.8: return True
    return False

def fetch_news():
    log("NEWS", "Mimicry scan active...")
    cands = []
    sources = ["reuters", "associated-press", "bloomberg", "bbc-news", "wired", "the-verge", "techcrunch", "cnn", "time", "business-insider"]
    random.shuffle(sources)
    try:
        headers = {"User-Agent": get_random_agent()}
        url = f"https://newsapi.org/v2/top-headlines?sources={','.join(sources[:5])}&apiKey={NEWS_API_KEY}"
        r = requests.get(url, headers=headers, timeout=20).json()
        if r.get('status') == 'ok': 
            for a in r['articles']:
                if a.get('urlToImage') and not is_garbage(a['title']):
                    cands.append(a)
    except Exception as e: log("ERR", str(e))
    return cands[:5]

def analyze_story(art):
    client = Groq(api_key=GROQ_API_KEY)
    model = get_groq_model(client)
    try:
        with DDGS() as ddgs: 
            res = ddgs.text(art['title'], max_results=1)
            ctx = res[0]['body'] if res else art['description']
    except: ctx = art['description']

    sys_msg = (
        f"Story: {art['title']}\nContext: {ctx}\n"
        f"Output JSON: {{'headline': '4-7 words UPPERCASE', 'body': '1 punchy sentence', 'mood': 'neutral'}}"
    )
    try:
        raw = client.chat.completions.create(messages=[{"role":"user","content":sys_msg}], model=model, response_format={"type": "json_object"}).choices[0].message.content
        data = json.loads(raw)
    except: data = {"headline": art['title'][:50], "body": art['description'][:100], "mood": "neutral"}
    
    cap = client.chat.completions.create(messages=[{"role":"user","content":f"Caption for: {art['title']}. Start with 'Source: {art['source']['name']}'. End with 10 hashtags."}], model=model).choices[0].message.content.strip()
    return data, cap

# --- 3. MIMICRY RENDERER (V10) ---
def apply_chromatic_aberration(img):
    r, g, b = img.split()
    r = ImageChops.offset(r, random.randint(-4, 4), random.randint(-2, 2))
    b = ImageChops.offset(b, random.randint(-4, 4), random.randint(-2, 2))
    return Image.merge("RGB", (r, g, b))

def generate_light_leak(w, h):
    leak = Image.new('RGBA', (w, h), (0,0,0,0))
    draw = ImageDraw.Draw(leak)
    for _ in range(random.randint(1, 3)):
        x, y = random.randint(0, w), random.randint(0, h)
        radius = random.randint(200, 600)
        color = random.choice([(255, 200, 150, 40), (255, 255, 255, 30), (255, 100, 50, 20)])
        draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=color)
    return leak.filter(ImageFilter.GaussianBlur(50))

def apply_mimicry_grade(img):
    img = img.convert("RGB")
    img = apply_chromatic_aberration(img)
    enhancer = ImageEnhance.Color(img)
    img = enhancer.enhance(random.uniform(0.8, 1.2))
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(random.uniform(0.9, 1.15))
    return img

def fit_text_jitter(draw, text, box_w, font_name, max_s):
    size = max_s
    font = ImageFont.truetype(f"ghost_assets/{font_name}.ttf", size)
    while size > 30:
        lines = textwrap.wrap(text, width=int(box_w / (size * 0.5)))
        h = sum([draw.textbbox((0,0), l, font=font)[3] for l in lines]) * 1.1
        if h < 1000: return font, lines
        size -= 5
        font = ImageFont.truetype(f"ghost_assets/{font_name}.ttf", size)
    return font, textwrap.wrap(text, width=20)

def render_skin(img, data, source_name):
    layout = random.choice(["classic", "split", "boxed", "minimal", "poster"])
    font = random.choice(["Anton", "Oswald", "Roboto", "Bebas", "Lobster"])
    color = random.choice(["#E63946", "#FFD700", "#00F0FF", "#FFFFFF", "#FF5733"])
    jx, jy = random.randint(-12, 12), random.randint(-12, 12)
    
    overlay = Image.new('RGBA', (1080, 1920), (0,0,0,0))
    draw = ImageDraw.Draw(overlay)
    
    if layout == "classic":
        grad = Image.new('L', (1080, 1000), 0)
        for y in range(1000): ImageDraw.Draw(grad).line([(0,y),(1080,y)], fill=int((y/1000)*255))
        overlay.paste(Image.new('RGBA', (1080,1000), (0,0,0,230)), (0, 920), mask=grad)
        f, l = fit_text_jitter(draw, data['headline'], 1000, font, 100)
        y = 1100 + jy
        for line in l: draw.text((50+jx, y), line, font=f, fill="white"); y += f.size + 10
    elif layout == "split":
        draw.rectangle([(0, 1200+jy), (1080, 1920)], fill="black")
        draw.rectangle([(50+jx, 1150+jy), (300+jx, 1220+jy)], fill=color) 
        draw.text((60+jx, 1160+jy), source_name, font=ImageFont.truetype(f"ghost_assets/{font}.ttf", 40), fill="black")
        f, l = fit_text_jitter(draw, data['headline'], 900, font, 90)
        y = 1300 + jy
        for line in l: draw.text((50+jx, y), line, font=f, fill="white"); y += f.size + 10
    elif layout == "boxed":
        draw.rectangle([(100+jx, 800+jy), (980+jx, 1400+jy)], fill=(0,0,0,200), outline=color, width=5)
        f, l = fit_text_jitter(draw, data['headline'], 800, font, 80)
        y = 900 + jy
        for line in l: draw.text((150+jx, y), line, font=f, fill="white"); y += f.size + 10
    elif layout == "minimal":
        f, l = fit_text_jitter(draw, data['headline'], 1000, font, 110)
        y = 250 + jy
        for line in l: draw.text((55+jx, y+5), line, font=f, fill="black"); draw.text((50+jx, y), line, font=f, fill="white"); y += f.size + 10
    elif layout == "poster":
        f, l = fit_text_jitter(draw, data['headline'], 1000, font, 140)
        y = 500 + jy
        for line in l: draw.text((50+jx, y), line, font=f, fill=(255,255,255, 220), stroke_width=3, stroke_fill="black"); y += f.size + 15

    if layout != "boxed":
        fb, lb = fit_text_jitter(draw, data['body'], 900, "Roboto", 45)
        yb = 1600 + jy
        for line in lb: draw.text((50+jx, yb), line, font=fb, fill="#E0E0E0"); yb += 50
    return overlay

def render_video(art, data):
    ensure_assets()
    duration = random.uniform(8.5, 13.5)
    
    try:
        r = requests.get(art['urlToImage'], headers={"User-Agent": get_random_agent()}, timeout=15)
        # FIX: Robust Image Loading (Handle WebP/PNG/JPG)
        try:
            img = Image.open(io.BytesIO(r.content)).convert("RGB")
        except:
            return None # Skip broken images

        w, h = img.size
        tr = 1080/1920
        if w/h > tr:
            nw = int(h*tr); left = (w-nw)//2; img = img.crop((left, 0, left+nw, h))
        else:
            nh = int(w/tr); top = (h-nh)//2; img = img.crop((0, top, w, top+nh))
        img = img.resize((1080, 1920), Image.LANCZOS)
        
        img = apply_mimicry_grade(img)
        img.save("bg.jpg")
        
        # Drunk Camera
        clip_bg = ImageClip("bg.jpg").set_duration(duration)
        w, h = clip_bg.size
        drift_x = random.randint(-30, 30)
        drift_speed = random.uniform(0.8, 1.2)
        
        def drunk_scroll(gf, t):
            frame = Image.fromarray(gf(t))
            zoom = 1.05 + (0.08 * math.sin(t * 0.4)) + (0.02 * t)
            new_w, new_h = int(w*zoom), int(h*zoom)
            frame = frame.resize((new_w, new_h), Image.LANCZOS)
            cx, cy = new_w//2, new_h//2
            pan_x = int(drift_x * math.sin(t * drift_speed))
            left = cx - 540 + pan_x; top = cy - 960
            if left < 0: left = 0
            if top < 0: top = 0
            return np.array(frame.crop((left, top, left+1080, top+1920)))
            
        clip_bg = clip_bg.fl(drunk_scroll)
        
        overlay = render_skin(img, data, art['source']['name'])
        leak = generate_light_leak(1080, 1920)
        overlay.paste(leak, (0,0), leak)
        overlay.save("ov.png")
        clip_ui = ImageClip("ov.png").set_duration(duration)
        
        # Audio Phase & Vibrato
        track = random.choice(["news1", "news2", "drum"])
        main = AudioFileClip(f"ghost_assets/{track}.mp3")
        noise = AudioFileClip("ghost_assets/noise.mp3").volumex(0.06)
        if main.duration > duration:
            start = random.uniform(0, main.duration - duration)
            main = main.subclip(start, start+duration)
        main = main.fx(vfx.speedx, random.uniform(0.97, 1.03))
        
        final_audio = CompositeAudioClip([main, noise.set_duration(duration)])
        final = CompositeVideoClip([clip_bg, clip_ui]).set_audio(final_audio).set_duration(duration)
        
        # V10: iPhone VFR Simulation
        fps = random.choice([23.976, 24.00, 29.97, 30.00])
        br = str(random.randint(4000, 6000)) + "k"
        final.write_videofile("out.mp4", fps=fps, codec='libx264', audio_codec='aac', bitrate=br, preset="ultrafast", logger=None)
        return "out.mp4"
    except Exception as e:
        log("RENDER FAIL", str(e))
        return None

# --- 4. DISTRIBUTION ---
def post_ig(path, cap):
    if not IG_ACCESS_TOKEN: return False
    try:
        url = cloudinary.uploader.upload(path, resource_type="video")['secure_url']
        r1 = requests.post(f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media", data={"media_type": "REELS", "video_url": url, "caption": cap, "access_token": IG_ACCESS_TOKEN}).json()
        if 'id' in r1:
            cid = r1['id']
            for _ in range(20):
                time.sleep(5)
                stat = requests.get(f"https://graph.facebook.com/v18.0/{cid}", params={"fields":"status_code", "access_token": IG_ACCESS_TOKEN}).json()
                if stat.get('status_code') == 'FINISHED':
                    requests.post(f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media_publish", data={"creation_id": cid, "access_token": IG_ACCESS_TOKEN})
                    return True
        return False
    except: return False

def post_fb_fixed(path, cap):
    if not FB_ACCESS_TOKEN: return False
    try:
        log("FB", "Init upload...")
        init = requests.post(f"https://graph.facebook.com/v18.0/{FB_PAGE_ID}/video_reels", data={"upload_phase":"start", "access_token": FB_ACCESS_TOKEN}).json()
        vid_id = init.get('video_id')
        up_url = init.get('upload_url')
        if not vid_id: return False
        with open(path, 'rb') as f:
            requests.post(up_url, headers={"Authorization": f"OAuth {FB_ACCESS_TOKEN}", "file_size": str(os.path.getsize(path))}, data=f)
        log("FB", "Processing...")
        time.sleep(20) 
        fin = requests.post(f"https://graph.facebook.com/v18.0/{FB_PAGE_ID}/video_reels", data={"upload_phase":"finish", "video_id": vid_id, "video_state":"PUBLISHED", "description": cap, "access_token": FB_ACCESS_TOKEN}).json()
        return fin.get('success', False)
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
    ensure_assets()
    log("SYS", "Mimicry V10 Online")
    news = fetch_news()
    if news:
        target = news[0]
        log("TARGET", target['title'])
        data, cap = analyze_story(target)
        video = render_video(target, data)
        if video:
            ig = post_ig(video, cap)
            fb = post_fb_fixed(video, cap)
            yt = post_yt_sleeper(video, data['headline'], cap)
            msg = f"🧬 Posted: {data['headline']}\nIG:{ig} FB:{fb} YT:{yt}"
            log("DONE", msg)
            if TELEGRAM_BOT_TOKEN: requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", data={"chat_id": TELEGRAM_ADMIN_ID, "text": msg})
            with open("ghost_history.txt", "a") as f: f.write(f"{target['title']}|{target['url']}|{datetime.now()}\n")
    else:
        log("SYS", "No safe news found.")
