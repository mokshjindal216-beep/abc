import os, time, requests, textwrap, json, numpy as np, cloudinary, cloudinary.uploader, difflib, re, random
from PIL import Image, ImageDraw, ImageFont, ImageFile, ImageFilter
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip, AudioFileClip, vfx
from groq import Groq
from datetime import datetime
from newspaper import Article
from duckduckgo_search import DDGS
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- CONFIGURATION (READS DIRECTLY FROM YOUR SECRETS) ---
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

# --- 1. SETUP & ASSETS ---
PREMIUM_SOURCES = [
    "reuters", "associated-press", "bloomberg", "the-wall-street-journal", 
    "the-economist", "bbc-news", "wired", "the-verge", "techcrunch", 
    "national-geographic", "scientific-american", "nature", "cnn", 
    "time", "business-insider"
]

def log(step, msg): 
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔹 {step.upper()}: {msg}")

def ensure_assets():
    os.makedirs('assets/audio', exist_ok=True)
    tracks = {"crisis": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3", "tech": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3", "general": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3"}
    for n, u in tracks.items():
        if not os.path.exists(f"assets/audio/{n}.mp3"): os.system(f"wget -q -O assets/audio/{n}.mp3 {u}")
    if not os.path.exists("Anton.ttf"): os.system("wget -q -O Anton.ttf https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf")

# --- 2. INTELLIGENCE ---
def get_best_groq_model(client):
    try:
        models = client.models.list()
        for m in models.data:
            if "llama-3.3-70b" in m.id: return m.id
        return "llama-3.3-70b-versatile"
    except: return "llama-3.3-70b-versatile"

def is_garbage(title):
    t = title.lower()
    ads = ["gift guide", "buying guide", "deals", "save $", "shop", "top picks", "review", "best of"]
    if any(x in t for x in ads): return True
    if not os.path.exists("history_v2.txt"): return False
    with open("history_v2.txt", "r") as f:
        for l in f:
            if "|" in l and difflib.SequenceMatcher(None, t, l.split("|")[0].lower()).ratio() > 0.8: return True
    return False

def fetch_news():
    log("NEWS", "Sourcing from Elite List...")
    cands = []
    try:
        # Uses NEWS_API_KEY directly
        r = requests.get(f"https://newsapi.org/v2/top-headlines?sources={','.join(PREMIUM_SOURCES)}&apiKey={NEWS_API_KEY}", timeout=15).json()
        if r.get('status') == 'ok': cands.extend([a for a in r['articles'] if a.get('urlToImage') and not is_garbage(a['title'])])
    except: pass
    return cands[:15]

def perform_research(article):
    log("RESEARCH", f"Scanning: {article['title']}")
    try:
        art = Article(article['url']); art.download(); art.parse()
        if len(art.text) > 500: return art.text[:2500]
    except: pass
    try:
        with DDGS() as ddgs: return "\n".join([r['body'] for r in ddgs.text(article['title'], max_results=3)])
    except: return article.get('description', '')

def generate_content(art, ctx):
    client = Groq(api_key=GROQ_API_KEY)
    model = get_best_groq_model(client)
    
    # 1. Video Data
    v_prompt = (
        f"Analyze this news: {art['title']}\nContext: {ctx}\n"
        f"Goal: Create a SCRIPT for a viral short video.\n"
        f"Return JSON: {{\"mood\": \"CRISIS/TECH/GENERAL\", "
        f"\"headline\": \"5-8 words. CLICKBAIT STYLE (e.g. 'You Won't Believe X').\", "
        f"\"summary\": \"EXACTLY 20-25 words. HIGH ENERGY FACTS. No filler.\"}}"
    )
    v_data = json.loads(client.chat.completions.create(messages=[{"role":"user","content":v_prompt}], model=model, response_format={"type": "json_object"}).choices[0].message.content)
    
    # 2. Caption
    cap_prompt = (
        f"Write a caption for: '{art['title']}'. "
        f"Style: Viral News Anchor. "
        f"Structure: \n1. A shocking Hook question.\n2. Three quick bullet points.\n3. A debate question.\n"
        f"At the end, generate exactly 15 hashtags. Mix Broad (e.g. #News) and Niche (e.g. #{v_data['headline'].split()[0]})."
    )
    caption = client.chat.completions.create(messages=[{"role":"user","content":cap_prompt}], model=model).choices[0].message.content.strip()
    
    # 3. Deep Dive
    div_prompt = f"250-word deep dive starting with '🧠 DEEP DIVE:' for: {art['title']}\nContext: {ctx}. Tone: Informative but casual/fun."
    comment = client.chat.completions.create(messages=[{"role":"user","content":div_prompt}], model=model).choices[0].message.content.strip()
    
    return v_data['mood'], v_data['headline'], v_data['summary'], caption, comment

# --- 3. TITANIUM RENDERER (Volume 20-25%, Skins, Grain) ---
def fit_text(draw, text, max_w, max_h, start_size):
    size = start_size
    while size > 25:
        try: font = ImageFont.truetype("Anton.ttf", size)
        except: font = ImageFont.load_default()
        lines = textwrap.wrap(text, width=int(max_w/(size*0.55)))
        th = sum([draw.textbbox((0,0), l, font=font)[3] - draw.textbbox((0,0), l, font=font)[1] + 15 for l in lines])
        if th < max_h: return font, lines
        size -= 4
    return ImageFont.load_default(), textwrap.wrap(text, width=30)

def add_film_grain(img, opacity=0.04): # 4% Ghost Grain
    arr = np.array(img)
    h, w, c = arr.shape
    noise = np.random.randint(0, 255, (h, w, c), dtype='uint8')
    grain = Image.fromarray(noise).convert("RGBA")
    grain.putalpha(int(255 * opacity))
    img = img.convert("RGBA")
    img.paste(grain, (0,0), grain)
    return img.convert("RGB")

def render_video(art, mood, hl, summ):
    ensure_assets()
    cfg = {"crisis": {"c": "#FF0000", "a": "assets/audio/crisis.mp3"}, "tech": {"c": "#00F0FF", "a": "assets/audio/tech.mp3"}, "general": {"c": "#FFD700", "a": "assets/audio/general.mp3"}}.get(mood.lower(), {"c": "#FFD700", "a": "assets/audio/general.mp3"})
    
    try:
        r = requests.get(art['urlToImage'], timeout=15)
        with open("bg.jpg", "wb") as f: f.write(r.content)
        Image.open("bg.jpg").verify()
    except Exception as e: return None

    try:
        W, H = 1080, 1920
        overlay = Image.new('RGBA', (W, H), (0,0,0,0))
        draw = ImageDraw.Draw(overlay)
        grad = Image.new('L', (W, H), 0)
        
        # --- SKINS ---
        skin = random.choice(["classic", "headline", "poster"])
        log("RENDER", f"Applying Skin: {skin.upper()}")

        if skin == "classic":
            for y in range(int(H*0.45), H): ImageDraw.Draw(grad).line([(0,y),(W,y)], fill=int((y-H*0.45)/(H*0.55)*255))
            overlay.paste(Image.new('RGBA',(W,H),(0,0,0,240)), (0,0), mask=grad)
            f_s = ImageFont.truetype("Anton.ttf", 35)
            sn = f" {art['source']['name'].upper()} "
            draw.rounded_rectangle([(60,150), (60+draw.textlength(sn, f_s)+20, 210)], 12, fill=cfg["c"])
            draw.text((70,160), sn, font=f_s, fill="black")
            cy = 600
            f_h, h_l = fit_text(draw, hl.upper(), 900, 600, 140)
            for l in h_l:
                draw.text((65, cy+5), l, font=f_h, fill="black")
                draw.text((60, cy), l, font=f_h, fill=cfg["c"])
                cy += f_h.size + 15
            f_u, s_l = fit_text(draw, summ, 900, 1500-cy, 100)
            cy += 30
            for l in s_l:
                draw.text((60, cy), l, font=f_u, fill="white")
                cy += f_u.size + 12

        elif skin == "headline":
            overlay.paste(Image.new('RGBA',(W,H),(0,0,0,100)), (0,0))
            box_color = (139, 0, 0, 230) if "crisis" in mood.lower() else (20, 20, 20, 230)
            draw.rectangle([(0, 200), (W, 700)], fill=box_color)
            cy = 250
            f_h, h_l = fit_text(draw, hl.upper(), 1000, 450, 140)
            for l in h_l:
                draw.text((50, cy), l, font=f_h, fill="white")
                cy += f_h.size + 10
            f_s = ImageFont.truetype("Anton.ttf", 40)
            sn = f" SOURCE: {art['source']['name'].upper()} "
            draw.text((50, 1600), sn, font=f_s, fill=cfg["c"])
            cy = 1300
            f_u, s_l = fit_text(draw, summ, 1000, 400, 90)
            for l in s_l:
                draw.text((50, cy), l, font=f_u, fill="white", stroke_width=2, stroke_fill="black")
                cy += f_u.size + 10

        elif skin == "poster":
            overlay.paste(Image.new('RGBA',(W,H),(0,0,0,80)), (0,0))
            f_h, h_l = fit_text(draw, hl.upper(), 950, 800, 160)
            total_h = sum([f_h.size for _ in h_l])
            start_y = (H - total_h) / 2 - 100
            for l in h_l:
                draw.text((60, start_y+5), l, font=f_h, fill="black")
                draw.text((55, start_y), l, font=f_h, fill=cfg["c"])
                start_y += f_h.size + 15
            f_u, s_l = fit_text(draw, summ, 900, 500, 80)
            start_y += 50
            for l in s_l:
                draw.text((60, start_y), l, font=f_u, fill="white", stroke_width=3, stroke_fill="black")
                start_y += f_u.size + 10

        overlay.save("overlay.png")
        
        img = Image.open("bg.jpg").convert("RGB")
        bw, bh = img.size; ratio = 1080/1920
        if bw/bh > ratio: nw = bh * ratio; img = img.crop(((bw-nw)/2, 0, (bw+nw)/2, bh))
        else: nh = bw/ratio; img = img.crop((0, (bh-nh)/2, bw, (bh-nh)/2 + nh))
        img = img.resize((1080, 1920), Image.LANCZOS)
        
        if skin == "poster": img = add_film_grain(img, opacity=0.04) # Grain
        img.save("temp_bg.jpg")
        
        clip = ImageClip("temp_bg.jpg").set_duration(6).fl(lambda gf, t: np.array(Image.fromarray(gf(t)).resize([int(d*(1+0.04*t)) for d in Image.fromarray(gf(t)).size], Image.BILINEAR).crop((0,0,1080,1920))))
        final = CompositeVideoClip([clip, ImageClip("overlay.png").set_duration(6)])
        
        # AUDIO JITTER + VOLUME 20-25%
        if os.path.exists(cfg["a"]): 
            vol = random.uniform(0.20, 0.25)
            speed = random.uniform(0.98, 1.02)
            audio = AudioFileClip(cfg["a"]).subclip(0,7).fx(vfx.speedx, speed).volumex(vol).subclip(0,6)
            final = final.set_audio(audio)
            
        final.write_videofile("final.mp4", fps=24, codec='libx264', audio_codec='aac', bitrate=str(random.randint(3000, 5500))+"k", preset='ultrafast', logger=None)
        return "final.mp4"
    except Exception as e:
        log("RENDER_FAIL", str(e))
        return None

# --- 4. POSTING LOGIC ---
def send_telegram(msg):
    try:
        if TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_ID:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", data={"chat_id": TELEGRAM_ADMIN_ID, "text": msg})
    except: pass

def post_instagram(path, cap, comm):
    try:
        up = cloudinary.uploader.upload(path, resource_type="video")
        r = requests.post(f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media", data={"media_type": "REELS", "video_url": up['secure_url'], "caption": cap, "access_token": IG_ACCESS_TOKEN}).json()
        if 'id' in r:
            cid = r['id']
            for _ in range(15):
                time.sleep(10)
                s = requests.get(f"https://graph.facebook.com/v18.0/{cid}", params={"fields":"status_code", "access_token": IG_ACCESS_TOKEN}).json()
                if s.get('status_code') == 'FINISHED':
                    p = requests.post(f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media_publish", data={"creation_id": cid, "access_token": IG_ACCESS_TOKEN}).json()
                    if 'id' in p:
                        time.sleep(5)
                        requests.post(f"https://graph.facebook.com/v18.0/{p['id']}/comments", data={"message": comm, "access_token": IG_ACCESS_TOKEN})
                        return True
        return False
    except: return False

def post_facebook(path, cap, deep_dive):
    try:
        init = requests.post(f"https://graph.facebook.com/v18.0/{FB_PAGE_ID}/video_reels", data={"upload_phase": "start", "access_token": FB_ACCESS_TOKEN}).json()
        if 'video_id' not in init: return False
        vid_id, upload_url = init['video_id'], init['upload_url']
        with open(path, 'rb') as f: requests.post(upload_url, headers={"Authorization": f"OAuth {FB_ACCESS_TOKEN}", "offset": "0", "file_size": str(os.path.getsize(path))}, data=f.read())
        time.sleep(30)
        fin = requests.post(f"https://graph.facebook.com/v18.0/{FB_PAGE_ID}/video_reels", data={"upload_phase": "finish", "video_id": vid_id, "video_state": "PUBLISHED", "description": f"{cap}\n\n---\n{deep_dive}", "access_token": FB_ACCESS_TOKEN}).json()
        return 'success' in fin and fin['success']
    except: return False

def post_youtube(path, title, description, tags):
    try:
        creds = Credentials(None, refresh_token=YT_REFRESH_TOKEN, token_uri="https://oauth2.googleapis.com/token", client_id=YT_CLIENT_ID, client_secret=YT_CLIENT_SECRET)
        youtube = build("youtube", "v3", credentials=creds)
        tag_list = [t.strip("#") for t in tags.split() if t.startswith("#")][:15]
        request = youtube.videos().insert(part="snippet,status", body={"snippet": {"title": title[:100], "description": description, "tags": tag_list}, "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}, media_body=MediaFileUpload(path))
        return 'id' in request.execute()
    except: return False

if __name__ == "__main__":
    ensure_assets()
    log("BOT", "Empire Titanium Engine V4 (Direct Secrets)...")
    cands = fetch_news()
    if cands:
        for art in cands:
            try:
                ctx = perform_research(art)
                m, h, s, cp, cm = generate_content(art, ctx)
                v = render_video(art, m, h, s)
                if v:
                    ig = post_instagram(v, cp, cm)
                    fb = post_facebook(v, cp, cm)
                    yt = post_youtube(v, h + " #shorts", f"{cp}\n\n---\n{cm}", cp)
                    msg = f"📰 {art['title']}\nIG:{ig} FB:{fb} YT:{yt}"
                    send_telegram(msg)
                    if ig or fb or yt:
                        with open("history_v2.txt", "a") as f: f.write(f"{art['title']}|{art['url']}\n")
                        log("SUCCESS", msg)
                        break
            except Exception as e: log("ERROR", str(e))
