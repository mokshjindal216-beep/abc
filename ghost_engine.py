import os, time, requests, textwrap, json, numpy as np, cloudinary, cloudinary.uploader, difflib, re, random, math, io, string
from PIL import Image, ImageDraw, ImageFont, ImageFile, ImageEnhance, ImageOps, ImageFilter, ImageChops
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip, AudioFileClip, vfx, CompositeAudioClip
from groq import Groq
from datetime import datetime, timedelta
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

# --- 1. ASSETS & THE "THIEF" UTILS ---
def log(step, msg): 
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🏴‍☠️ {step.upper()}: {msg}")

def ensure_assets():
    os.makedirs('ghost_assets', exist_ok=True)
    # EXPANDED FONT ARMORY (10 Fonts)
    fonts = {
        "Anton": "https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf",
        "Oswald": "https://github.com/google/fonts/raw/main/ofl/oswald/static/Oswald-Bold.ttf",
        "Roboto": "https://github.com/google/fonts/raw/main/apache/robotocondensed/static/RobotoCondensed-Bold.ttf",
        "Bebas": "https://github.com/google/fonts/raw/main/ofl/bebasneue/BebasNeue-Regular.ttf",
        "Lobster": "https://github.com/google/fonts/raw/main/ofl/lobster/Lobster-Regular.ttf",
        "Courier": "https://github.com/google/fonts/raw/main/apache/courierprime/CourierPrime-Bold.ttf",
        "Pacifico": "https://github.com/google/fonts/raw/main/ofl/pacifico/Pacifico-Regular.ttf",
        "Bangers": "https://github.com/google/fonts/raw/main/ofl/bangers/Bangers-Regular.ttf",
        "Abril": "https://github.com/google/fonts/raw/main/ofl/abrilfatface/AbrilFatface-Regular.ttf",
        "Righteous": "https://github.com/google/fonts/raw/main/ofl/righteous/Righteous-Regular.ttf"
    }
    for n, u in fonts.items():
        if not os.path.exists(f"ghost_assets/{n}.ttf"): os.system(f"wget -q -O ghost_assets/{n}.ttf {u}")
    
    tracks = {
        "news1": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
        "news2": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
        "noise": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-15.mp3"
    }
    for n, u in tracks.items():
        if not os.path.exists(f"ghost_assets/{n}.mp3"): os.system(f"wget -q -O ghost_assets/{n}.mp3 {u}")

def get_random_agent():
    # Spoofs everything from iPhones to Linux boxes
    return random.choice([
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0"
    ])

def get_thief_filename():
    # Looks like a raw camera file
    prefix = random.choice(["IMG_", "DJI_", "GX01", "RPReplay_", "Clip_", "VID_"])
    num = random.randint(1000, 9999)
    return f"{prefix}{num}.mp4"

# --- 2. INTELLIGENCE ---
def get_groq_model(client):
    try:
        active = [m.id for m in client.models.list().data]
        priority = ["llama-3.3-70b-versatile", "mixtral-8x7b-32768"]
        for p in priority:
            if p in active: return p
        return active[0]
    except: return "llama-3.3-70b-versatile"

def is_garbage(title):
    t = title.lower()
    block = ["gift", "deal", "buy", "shop", "review", "best of", "opinion", "editorial", "horoscope"]
    if any(x in t for x in block): return True
    if not os.path.exists("ghost_history.txt"): return False
    with open("ghost_history.txt", "r") as f:
        for l in f:
            if "|" in l and difflib.SequenceMatcher(None, t, l.split("|")[0].lower()).ratio() > 0.8: return True
    return False

def fetch_news():
    log("NEWS", "Scanning global spectrum...")
    cands = []
    sources = ["reuters", "associated-press", "bloomberg", "bbc-news", "cnn", "the-verge", "wired", "time"]
    random.shuffle(sources)
    try:
        url = f"https://newsapi.org/v2/top-headlines?sources={','.join(sources[:5])}&apiKey={NEWS_API_KEY}"
        r = requests.get(url, headers={"User-Agent": get_random_agent()}, timeout=20).json()
        if r.get('status') == 'ok': 
            for a in r['articles']:
                if a.get('urlToImage') and not is_garbage(a['title']):
                    cands.append(a)
    except Exception as e: log("ERR", str(e))
    return cands

def analyze_story(art):
    client = Groq(api_key=GROQ_API_KEY)
    model = get_groq_model(client)
    try:
        with DDGS() as ddgs: 
            res = ddgs.text(art['title'], max_results=1)
            ctx = res[0]['body'] if res else art['description']
    except: ctx = art['description']

    # Instructing AI to be punchy and viral
    sys_msg = f"Story: {art['title']}\nContext: {ctx}\nOutput JSON: {{'headline': '4-7 words UPPERCASE IMPACTFUL', 'body': '1 short sentence'}}"
    try:
        raw = client.chat.completions.create(messages=[{"role":"user","content":sys_msg}], model=model, response_format={"type": "json_object"}).choices[0].message.content
        data = json.loads(raw)
    except: data = {"headline": art['title'][:50], "body": art['description'][:100]}
    
    cap = client.chat.completions.create(messages=[{"role":"user","content":f"Viral Caption for: {art['title']}. End with 15 relevant hashtags."}], model=model).choices[0].message.content.strip()
    return data, cap

# --- 3. THE SHADOW RENDERER (PROCEDURAL GENERATION) ---
def generate_procedural_dust(w, h):
    # Generates a UNIQUE dust/scratch layer every time
    # This ensures no two videos have the same pixel mask
    dust = Image.new('RGBA', (w, h), (0,0,0,0))
    draw = ImageDraw.Draw(dust)
    
    # Random scratches
    for _ in range(random.randint(5, 15)):
        x1 = random.randint(0, w)
        y1 = random.randint(0, h)
        x2 = x1 + random.randint(-50, 50)
        y2 = y1 + random.randint(-50, 50)
        width = random.randint(1, 3)
        fill = (255, 255, 255, random.randint(20, 50))
        draw.line([(x1,y1), (x2,y2)], fill=fill, width=width)
        
    # Random specks
    for _ in range(random.randint(20, 50)):
        x = random.randint(0, w)
        y = random.randint(0, h)
        r = random.randint(1, 3)
        fill = (255, 255, 255, random.randint(30, 80))
        draw.ellipse((x-r, y-r, x+r, y+r), fill=fill)
        
    return dust

def apply_shadow_grade(img):
    # Pro Contrast
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(random.uniform(1.1, 1.2))
    
    # Color Shift (Subtle)
    r, g, b = img.split()
    r = ImageChops.offset(r, random.randint(-3, 3), 0)
    b = ImageChops.offset(b, random.randint(-3, 3), 0)
    img = Image.merge("RGB", (r, g, b))
    
    # Vignette
    w, h = img.size
    # Create gradient mask
    radius = min(w, h) * 1.5
    gradient = Image.new('L', (w, h), 0)
    draw = ImageDraw.Draw(gradient)
    # Draw radial gradient simulation
    draw.ellipse((w/2 - radius/2, h/2 - radius/2, w/2 + radius/2, h/2 + radius/2), fill=255)
    gradient = gradient.filter(ImageFilter.GaussianBlur(100))
    # Apply vignette
    black = Image.new('RGB', (w, h), 0)
    img = Image.composite(img, black, gradient)
    
    return img

def fit_text_dynamic(draw, text, box_w, font_name, max_s):
    size = max_s
    try: font = ImageFont.truetype(f"ghost_assets/{font_name}.ttf", size)
    except: font = ImageFont.load_default()
    while size > 30:
        lines = textwrap.wrap(text, width=int(box_w / (size * 0.5)))
        h = sum([draw.textbbox((0,0), l, font=font)[3] for l in lines]) * 1.1
        if h < 1000: return font, lines
        size -= 5
        font = ImageFont.truetype(f"ghost_assets/{font_name}.ttf", size)
    return font, textwrap.wrap(text, width=20)

def render_skin(data, source_name):
    # 15 LAYOUT ENGINES (Classic, Poster, Cyber, Paper, etc.)
    skins = ["classic", "classic", "split", "boxed", "poster", "neon", "brutalist", "paper", "typewriter", "cinematic", "news", "bold", "clean", "glitch", "minimal"]
    layout = random.choice(skins)
    
    # Procedural Color Palette Generator
    def random_color():
        return "#%06x" % random.randint(0, 0xFFFFFF)
    
    # Safe professional colors + 20% chance of wild color
    pro_colors = ["#E63946", "#FFD700", "#00F0FF", "#FFFFFF", "#FF5733", "#C70039", "#2A9D8F"]
    color = random.choice(pro_colors) if random.random() > 0.2 else random_color()
    
    jx, jy = random.randint(-6, 6), random.randint(-6, 6) # Jitter
    
    overlay = Image.new('RGBA', (1080, 1920), (0,0,0,0))
    draw = ImageDraw.Draw(overlay)
    
    log("DESIGN", f"Skin: {layout.upper()} | Palette: {color}")

    # --- LAYOUT LOGIC ---
    if layout == "classic":
        grad = Image.new('L', (1080, 1000), 0)
        for y in range(1000): ImageDraw.Draw(grad).line([(0,y),(1080,y)], fill=int((y/1000)*255))
        overlay.paste(Image.new('RGBA', (1080,1000), (0,0,0,230)), (0, 920), mask=grad)
        
        # Source Pill
        font_s = ImageFont.truetype("ghost_assets/Anton.ttf", 30)
        src = f" {source_name.upper()} "
        draw.rounded_rectangle([(50+jx, 1050+jy), (50+jx+draw.textlength(src, font_s)+20, 1100+jy)], radius=10, fill=color)
        draw.text((60+jx, 1058+jy), src, font=font_s, fill="black")
        
        f, l = fit_text_dynamic(draw, data['headline'], 1000, "Anton", 110)
        y = 1150 + jy
        for line in l: draw.text((50+jx, y), line, font=f, fill="white"); y += f.size + 10

    elif layout == "poster":
        f, l = fit_text_dynamic(draw, data['headline'], 1000, "Anton", 140)
        y = 400 + jy
        for line in l: 
            draw.text((50+jx, y), line, font=f, fill=(255,255,255, 240), stroke_width=4, stroke_fill="black")
            y += f.size + 15
            
    elif layout == "paper":
        draw.rectangle([(50+jx, 1100+jy), (1030+jx, 1600+jy)], fill="#F4F1EA") # Cream paper
        f, l = fit_text_dynamic(draw, data['headline'], 900, "Courier", 80)
        y = 1150 + jy
        for line in l: draw.text((80+jx, y), line, font=f, fill="#1A1A1A"); y += f.size + 10
        
    elif layout == "news":
        draw.rectangle([(0, 1300+jy), (1080, 1920)], fill="#B71C1C") # Red breaking news bar
        draw.text((50+jx, 1320+jy), "BREAKING NEWS", font=ImageFont.truetype("ghost_assets/Bebas.ttf", 60), fill="white")
        f, l = fit_text_dynamic(draw, data['headline'], 1000, "Oswald", 90)
        y = 1400 + jy
        for line in l: draw.text((50+jx, y), line, font=f, fill="white"); y += f.size + 10

    else: # Fallback / Split / Minimal / Others
        draw.rectangle([(0, 1200+jy), (1080, 1920)], fill="black")
        draw.text((60+jx, 1160+jy), source_name.upper(), font=ImageFont.truetype("ghost_assets/Anton.ttf", 40), fill=color)
        f, l = fit_text_dynamic(draw, data['headline'], 900, "Oswald", 100)
        y = 1250 + jy
        for line in l: draw.text((50+jx, y), line, font=f, fill="white"); y += f.size + 10

    # Add Procedural Dust Layer
    dust = generate_procedural_dust(1080, 1920)
    overlay.paste(dust, (0,0), dust)
    
    return overlay

def render_video(art, data):
    ensure_assets()
    duration = random.uniform(9.5, 13.5)
    
    try:
        r = requests.get(art['urlToImage'], headers={"User-Agent": get_random_agent()}, timeout=10)
        if r.status_code != 200: raise Exception("Img DL Failed")
        try: img = Image.open(io.BytesIO(r.content)).convert("RGB")
        except: raise Exception("Img Corrupt")

        w, h = img.size
        tr = 1080/1920
        if w/h > tr:
            nw = int(h*tr); left = (w-nw)//2; img = img.crop((left, 0, left+nw, h))
        else:
            nh = int(w/tr); top = (h-nh)//2; img = img.crop((0, top, w, top+nh))
        img = img.resize((1080, 1920), Image.LANCZOS)
        
        img = apply_shadow_grade(img)
        img.save("bg.jpg")
        
        # Drunk Camera (Smoothed)
        clip_bg = ImageClip("bg.jpg").set_duration(duration)
        w, h = clip_bg.size
        drift_x = random.randint(-15, 15)
        def drunk_scroll(gf, t):
            frame = Image.fromarray(gf(t))
            # Sine wave zoom + Linear zoom combination
            zoom = 1.05 + (0.05 * math.sin(t * 0.5)) + (0.01 * t)
            new_w, new_h = int(w*zoom), int(h*zoom)
            frame = frame.resize((new_w, new_h), Image.LANCZOS)
            cx, cy = new_w//2, new_h//2
            pan_x = int(drift_x * math.sin(t))
            left = cx - 540 + pan_x; top = cy - 960
            if left < 0: left = 0
            if top < 0: top = 0
            return np.array(frame.crop((left, top, left+1080, top+1920)))
        clip_bg = clip_bg.fl(drunk_scroll)
        
        overlay = render_skin(data, art['source']['name'])
        overlay.save("ov.png")
        clip_ui = ImageClip("ov.png").set_duration(duration)
        
        # Audio Drift
        track_name = random.choice(["news1", "news2"])
        if os.path.exists(f"ghost_assets/{track_name}.mp3"):
            audio = AudioFileClip(f"ghost_assets/{track_name}.mp3")
            if audio.duration > duration: audio = audio.subclip(0, duration)
            audio = audio.fx(vfx.speedx, random.uniform(0.98, 1.02))
            
            # Volume Automation (Fade in/out randomly)
            audio = audio.audio_fadein(random.uniform(0.5, 1.5)).audio_fadeout(random.uniform(0.5, 1.5))
            
            final = CompositeVideoClip([clip_bg, clip_ui]).set_audio(audio).set_duration(duration)
        else:
            final = CompositeVideoClip([clip_bg, clip_ui]).set_duration(duration)

        fps = random.choice([29.97, 30.00, 24.00, 25.00])
        br = str(random.randint(4500, 6000)) + "k"
        out_name = get_thief_filename()
        
        # METADATA SPOOFING (The "iPhone" Lie)
        final.write_videofile(out_name, fps=fps, codec='libx264', audio_codec='aac', bitrate=br, preset="ultrafast", logger=None, 
            ffmpeg_params=[
                "-metadata", "title=", 
                "-metadata", "artist=",
                "-metadata", "creation_time=" + (datetime.now() - timedelta(hours=random.randint(1,5))).isoformat()
            ])
        return out_name
    except Exception as e:
        raise e 

# --- 4. DISTRIBUTION (SMART POLLING) ---
def post_ig(path, cap):
    if not IG_ACCESS_TOKEN: return False
    try:
        url = cloudinary.uploader.upload(path, resource_type="video")['secure_url']
        r1 = requests.post(f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media", data={"media_type": "REELS", "video_url": url, "caption": cap, "access_token": IG_ACCESS_TOKEN}).json()
        if 'id' in r1:
            cid = r1['id']
            for _ in range(25): # Wait longer
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
        log("FB", "Uploading...")
        init = requests.post(f"https://graph.facebook.com/v18.0/{FB_PAGE_ID}/video_reels", data={"upload_phase":"start", "access_token": FB_ACCESS_TOKEN}).json()
        vid_id = init.get('video_id')
        up_url = init.get('upload_url')
        if not vid_id: return False
        
        with open(path, 'rb') as f:
            requests.post(up_url, headers={"Authorization": f"OAuth {FB_ACCESS_TOKEN}", "file_size": str(os.path.getsize(path))}, data=f)
        
        # AGGRESSIVE POLLING
        log("FB", "Polling status...")
        for _ in range(40): # 400 Seconds (6+ mins)
            time.sleep(10)
            stat = requests.get(f"https://graph.facebook.com/v18.0/{vid_id}", params={"fields":"status", "access_token": FB_ACCESS_TOKEN}).json()
            
            upload_status = stat.get('status', {}).get('uploading_phase', {}).get('status')
            process_status = stat.get('status', {}).get('processing_phase', {}).get('status')
            
            if upload_status == 'complete' and process_status == 'complete':
                log("FB", "Ready. Publishing...")
                fin = requests.post(f"https://graph.facebook.com/v18.0/{FB_PAGE_ID}/video_reels", data={"upload_phase":"finish", "video_id": vid_id, "video_state":"PUBLISHED", "description": cap, "access_token": FB_ACCESS_TOKEN}).json()
                return fin.get('success', False)
                
        return False
    except: return False

def post_yt(path, title, desc):
    if not YT_REFRESH_TOKEN or len(str(YT_REFRESH_TOKEN)) < 5: return False
    try:
        creds = Credentials(None, refresh_token=YT_REFRESH_TOKEN, token_uri="https://oauth2.googleapis.com/token", client_id=YT_CLIENT_ID, client_secret=YT_CLIENT_SECRET)
        youtube = build("youtube", "v3", credentials=creds)
        body = {"snippet": {"title": title[:95], "description": desc, "tags": ["news", "shorts"], "categoryId": "25"}, "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
        youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(path)).execute()
        return True
    except: return False

def send_telegram(msg):
    if TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_ID:
        try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", data={"chat_id": TELEGRAM_ADMIN_ID, "text": msg})
        except: pass

if __name__ == "__main__":
    ensure_assets()
    log("SYS", "Shadow Syndicate V18 Online")
    
    # 1. HUMAN HESITATION (Wait before starting)
    time.sleep(random.randint(5, 30))
    
    news_list = fetch_news()
    if not news_list:
        log("SYS", "No news found.")
        exit(0)
    
    # THE IMMORTAL LOOP
    for i, target in enumerate(news_list):
        log("TRY", f"Attempt {i+1}: {target['title'][:30]}...")
        try:
            data, cap = analyze_story(target)
            video_path = render_video(target, data)
            
            if video_path and os.path.exists(video_path):
                # HUMAN HESITATION (Wait before upload)
                time.sleep(random.randint(2, 10))
                
                ig = post_ig(video_path, cap)
                fb = post_fb(video_path, cap)
                yt = post_yt(video_path, data['headline'], cap)
                
                status_msg = f"🏴‍☠️ Posted: {data['headline']}\nIG:{ig} FB:{fb} YT:{yt}"
                log("SUCCESS", status_msg)
                send_telegram(status_msg)
                
                with open("ghost_history.txt", "a") as f: f.write(f"{target['title']}|{target['url']}|{datetime.now()}\n")
                break # Success!
            else:
                log("WARN", "Render failed. Next...")
        except Exception as e:
            log("SKIP", f"Error: {str(e)}. Next...")
            continue
