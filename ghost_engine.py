import os, time, requests, textwrap, json, numpy as np, cloudinary, cloudinary.uploader, difflib, re, random, math, io
from PIL import Image, ImageDraw, ImageFont, ImageFile, ImageEnhance, ImageOps, ImageFilter, ImageChops
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip, AudioFileClip, vfx, CompositeAudioClip
# --- FIX: Import AudioArrayClip directly from source ---
from moviepy.audio.AudioClip import AudioArrayClip
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

# --- 1. ASSETS & STEALTH UTILS ---
def log(step, msg): 
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 👁️‍🗨️ {step.upper()}: {msg}")

def ensure_assets():
    os.makedirs('ghost_assets', exist_ok=True)
    # The 6 Fonts of Chaos
    fonts = {
        "Anton": "https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf",
        "Oswald": "https://github.com/google/fonts/raw/main/ofl/oswald/static/Oswald-Bold.ttf",
        "Roboto": "https://github.com/google/fonts/raw/main/apache/robotocondensed/static/RobotoCondensed-Bold.ttf",
        "Bebas": "https://github.com/google/fonts/raw/main/ofl/bebasneue/BebasNeue-Regular.ttf",
        "Lobster": "https://github.com/google/fonts/raw/main/ofl/lobster/Lobster-Regular.ttf",
        "Courier": "https://github.com/google/fonts/raw/main/apache/courierprime/CourierPrime-Bold.ttf"
    }
    for n, u in fonts.items():
        if not os.path.exists(f"ghost_assets/{n}.ttf"): os.system(f"wget -q -O ghost_assets/{n}.ttf {u}")
    
    tracks = {
        "news1": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
        "news2": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3"
    }
    for n, u in tracks.items():
        if not os.path.exists(f"ghost_assets/{n}.mp3"): os.system(f"wget -q -O ghost_assets/{n}.mp3 {u}")

def get_random_agent():
    # Rotates User-Agents to prevent IP blocking
    return random.choice([
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ])

def get_thief_filename():
    # Mimics iPhone filenames to fool metadata scanners
    prefix = random.choice(["IMG_", "RPReplay_", "WhatsApp_Video_", "Clip_"])
    num = random.randint(1000, 9999)
    return f"{prefix}{num}.mp4"

# --- 2. INTELLIGENCE (Smart Model + Deep Research) ---
def get_best_groq_model(client):
    try:
        # Dynamic Model Selection (No hardcoding)
        models = client.models.list()
        active_ids = [m.id for m in models.data]
        priority = ["llama-3.3-70b-versatile", "mixtral-8x7b-32768", "llama3-70b-8192"]
        for p in priority:
            if p in active_ids: return p
        return active_ids[0]
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
    log("NEWS", "Deep scanning feeds...")
    cands = []
    sources = ["reuters", "associated-press", "bloomberg", "bbc-news", "cnn", "the-verge", "wired"]
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
    model = get_best_groq_model(client)
    
    # 1. Research (from abc_bot logic)
    try:
        with DDGS() as ddgs: 
            res = ddgs.text(art['title'], max_results=2)
            ctx = "\n".join([r['body'] for r in res]) if res else art['description']
    except: ctx = art['description']

    # 2. Content Gen
    sys_msg = (
        f"Story: {art['title']}\nContext: {ctx}\n"
        f"Goal: Viral News Short.\n"
        f"Output JSON: {{'headline': '4-6 words UPPERCASE PUNCHY', 'summary': '15-20 words engaging fact.'}}"
    )
    try:
        raw = client.chat.completions.create(messages=[{"role":"user","content":sys_msg}], model=model, response_format={"type": "json_object"}).choices[0].message.content
        data = json.loads(raw)
    except: data = {"headline": art['title'][:50], "summary": art['description'][:100]}
    
    # 3. Caption Gen
    cap_prompt = f"Write a caption for: {art['title']}. Include 3 bullet points summary. End with 15 hashtags."
    cap = client.chat.completions.create(messages=[{"role":"user","content":cap_prompt}], model=model).choices[0].message.content.strip()
    
    return data, cap

# --- 3. TITAN RENDERER (Visual Genetics + Audio Biometrics) ---
def apply_visual_genetics(img):
    # 1. Sub-Pixel Rotation (Breaks pixel matching)
    angle = random.uniform(-0.5, 0.5)
    img = img.rotate(angle, resample=Image.BICUBIC)
    
    # 2. Chromatic Aberration (Simulates cheap lens)
    r, g, b = img.split()
    r = ImageChops.offset(r, random.randint(-3, 3), 0)
    b = ImageChops.offset(b, random.randint(-3, 3), 0)
    img = Image.merge("RGB", (r, g, b))
    
    # 3. Film Grain (Noise Floor)
    if random.random() > 0.3:
        w, h = img.size
        # Generate noise array
        noise = np.random.randint(0, 30, (h, w, 3), dtype='uint8')
        noise_img = Image.fromarray(noise, 'RGB')
        # Blend
        img = ImageChops.add(img, noise_img, scale=4.0, offset=0)
        
    # 4. Pro Grade (Contrast/Sat)
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.1)
    
    return img

def fit_text_dynamic(draw, text, box_w, font_name, max_s):
    size = max_s
    try: font = ImageFont.truetype(f"ghost_assets/{font_name}.ttf", size)
    except: font = ImageFont.load_default()
    while size > 25:
        lines = textwrap.wrap(text, width=int(box_w / (size * 0.5)))
        h = sum([draw.textbbox((0,0), l, font=font)[3] for l in lines]) * 1.1
        if h < 1000: return font, lines
        size -= 5
        font = ImageFont.truetype(f"ghost_assets/{font_name}.ttf", size)
    return font, textwrap.wrap(text, width=20)

def render_skin(data, source_name):
    # 10 LAYOUTS (Biased towards "Classic" for pro look)
    skins = ["classic", "classic", "classic", "split", "boxed", "poster", "neon", "typewriter", "brutalist", "minimal"]
    layout = random.choice(skins)
    
    font_name = "Anton" if layout in ["classic", "poster"] else random.choice(["Oswald", "Roboto", "Bebas"])
    colors = ["#E63946", "#FFD700", "#00F0FF", "#FFFFFF", "#FF5733"]
    color = random.choice(colors)
    jx, jy = random.randint(-5, 5), random.randint(-5, 5) # Pixel Jitter
    
    overlay = Image.new('RGBA', (1080, 1920), (0,0,0,0))
    draw = ImageDraw.Draw(overlay)
    
    log("DESIGN", f"Skin: {layout.upper()} | Font: {font_name}")

    if layout == "classic":
        grad = Image.new('L', (1080, 1000), 0)
        for y in range(1000): ImageDraw.Draw(grad).line([(0,y),(1080,y)], fill=int((y/1000)*255))
        overlay.paste(Image.new('RGBA', (1080,1000), (0,0,0,240)), (0, 920), mask=grad)
        
        # Source Pill
        font_s = ImageFont.truetype("ghost_assets/Anton.ttf", 30)
        src_txt = f" {source_name.upper()} "
        draw.rounded_rectangle([(50+jx, 1050+jy), (50+jx+draw.textlength(src_txt, font_s)+20, 1100+jy)], radius=10, fill="#E63946")
        draw.text((60+jx, 1058+jy), src_txt, font=font_s, fill="white")
        
        f, l = fit_text_dynamic(draw, data['headline'], 1000, font_name, 110)
        y = 1150 + jy
        for line in l: draw.text((50+jx, y), line, font=f, fill="white"); y += f.size + 10
        
        # Summary Text
        f_b, l_b = fit_text_dynamic(draw, data['summary'], 900, "Roboto", 50)
        y += 40
        for line in l_b: draw.text((50+jx, y), line, font=f_b, fill="#DDDDDD"); y += f_b.size + 5

    elif layout == "split":
        draw.rectangle([(0, 1200+jy), (1080, 1920)], fill="black")
        draw.text((60+jx, 1160+jy), source_name.upper(), font=ImageFont.truetype("ghost_assets/Anton.ttf", 40), fill=color)
        f, l = fit_text_dynamic(draw, data['headline'], 900, "Oswald", 100)
        y = 1250 + jy
        for line in l: draw.text((50+jx, y), line, font=f, fill="white"); y += f.size + 10

    elif layout == "poster":
        f, l = fit_text_dynamic(draw, data['headline'], 1000, "Anton", 130)
        y = 500 + jy
        for line in l: 
            draw.text((50+jx, y), line, font=f, fill=(255,255,255, 230), stroke_width=3, stroke_fill="black")
            y += f.size + 15

    else: # Fallback / Boxed / Neon
        draw.rectangle([(100+jx, 800+jy), (980+jx, 1400+jy)], fill=(0,0,0,200), outline=color, width=6)
        f, l = fit_text_dynamic(draw, data['headline'], 800, font_name, 90)
        y = 900 + jy
        for line in l: draw.text((150+jx, y), line, font=f, fill="white"); y += f.size + 10

    return overlay

def render_video(art, data):
    ensure_assets()
    duration = random.uniform(9.0, 13.0)
    
    try:
        # Robust Download
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
        
        # APPLY VISUAL GENETICS (The 100x Upgrade)
        img = apply_visual_genetics(img)
        img.save("bg.jpg")
        
        # Drunk Camera
        clip_bg = ImageClip("bg.jpg").set_duration(duration)
        w, h = clip_bg.size
        drift_x = random.randint(-15, 15)
        def drunk_scroll(gf, t):
            frame = Image.fromarray(gf(t))
            zoom = 1.05 + (0.05 * math.sin(t * 0.5))
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
        
        # AUDIO BIOMETRICS (Noise Floor + Pitch Shift)
        track_name = random.choice(["news1", "news2"])
        if os.path.exists(f"ghost_assets/{track_name}.mp3"):
            main_audio = AudioFileClip(f"ghost_assets/{track_name}.mp3")
            if main_audio.duration > duration: main_audio = main_audio.subclip(0, duration)
            
            # Pitch Shift
            main_audio = main_audio.fx(vfx.speedx, random.uniform(0.98, 1.02))
            
            # Generate Synthetic Noise Floor (1% Volume)
            # This fills "Digital Silence" with data
            noise_rate = 44100
            noise_duration = duration
            noise_data = np.random.uniform(-0.01, 0.01, (int(noise_duration*noise_rate), 2))
            noise_audio = AudioArrayClip(noise_data, fps=noise_rate)
            
            final_audio = CompositeAudioClip([main_audio, noise_audio])
            final = CompositeVideoClip([clip_bg, clip_ui]).set_audio(final_audio).set_duration(duration)
        else:
            final = CompositeVideoClip([clip_bg, clip_ui]).set_duration(duration)

        fps = random.choice([29.97, 30.00, 24.00])
        br = str(random.randint(4500, 6000)) + "k"
        out_name = get_thief_filename()
        
        # Scrub Metadata
        final.write_videofile(out_name, fps=fps, codec='libx264', audio_codec='aac', bitrate=br, preset="ultrafast", logger=None, ffmpeg_params=["-metadata", "title=", "-metadata", "artist="])
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
            for _ in range(25): 
                time.sleep(5)
                s = requests.get(f"https://graph.facebook.com/v18.0/{cid}", params={"fields":"status_code", "access_token": IG_ACCESS_TOKEN}).json()
                if s.get('status_code') == 'FINISHED':
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
        
        file_size = os.path.getsize(path)
        with open(path, 'rb') as f:
            requests.post(up_url, headers={"Authorization": f"OAuth {FB_ACCESS_TOKEN}", "offset": "0", "file_size": str(file_size)}, data=f.read())
        
        # SMART POLLING (Wait up to 6 mins)
        log("FB", "Polling status...")
        for _ in range(36): 
            time.sleep(10)
            stat = requests.get(f"https://graph.facebook.com/v18.0/{vid_id}", params={"fields":"status", "access_token": FB_ACCESS_TOKEN}).json()
            
            up_stat = stat.get('status', {}).get('uploading_phase', {}).get('status')
            proc_stat = stat.get('status', {}).get('processing_phase', {}).get('status')
            
            if proc_stat == 'complete':
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
    log("SYS", "Shadow Syndicate V20 Online")
    
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
                ig = post_ig(video_path, cap)
                fb = post_fb(video_path, cap)
                yt = post_yt(video_path, data['headline'], cap)
                
                status_msg = f"👁️‍🗨️ Posted: {data['headline']}\nIG:{ig} FB:{fb} YT:{yt}"
                log("SUCCESS", status_msg)
                send_telegram(status_msg)
                
                with open("ghost_history.txt", "a") as f: f.write(f"{target['title']}|{target['url']}|{datetime.now()}\n")
                break # Success
            else:
                log("WARN", "Render failed. Next...")
        except Exception as e:
            log("SKIP", f"Error: {str(e)}. Next...")
            continue
