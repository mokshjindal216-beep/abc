# newsroom.py
import os, time, requests, textwrap, json, numpy as np, cloudinary, cloudinary.uploader, config_v2 as config, difflib
from PIL import Image, ImageDraw, ImageFont, ImageFile, UnidentifiedImageError
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip, AudioFileClip
from groq import Groq
from datetime import datetime
from newspaper import Article
from duckduckgo_search import DDGS

ImageFile.LOAD_TRUNCATED_IMAGES = True
cloudinary.config(cloud_name=config.CLOUDINARY_CLOUD_NAME, api_key=config.CLOUDINARY_API_KEY, api_secret=config.CLOUDINARY_API_SECRET)

# 50 PREMIER SOURCES
PREMIUM_SOURCES = ["reuters", "associated-press", "bbc-news", "cnn", "bloomberg", "the-wall-street-journal", "the-washington-post", "time", "wired", "the-verge", "techcrunch", "business-insider", "fortune", "cnbc", "abc-news", "cbs-news", "nbc-news", "politico", "axios", "the-hill", "usa-today", "the-independent", "the-telegraph", "france-24", "dw-news", "scmp", "the-hindu", "the-times-of-india", "variety", "hollywood-reporter", "rolling-stone", "ign", "espn", "bleacher-report", "national-geographic", "new-scientist", "scientific-american", "nature", "the-economist", "hacker-news", "ars-technica", "engadget", "gizmodo", "mashable", "vox", "new-york-magazine", "the-atlantic"]

GENERIC_TAGS = "#news #breakingnews #viral #trending"

def log(step, msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔹 {step.upper()}: {msg}")

def send_telegram(msg):
    try: requests.post(f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage", data={"chat_id": config.TELEGRAM_ADMIN_ID, "text": msg, "parse_mode": "Markdown"}, timeout=5)
    except: pass

def ensure_assets():
    os.makedirs('assets/audio', exist_ok=True)
    # MOOD AUDIO TRACKS
    tracks = {
        "crisis": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3", 
        "tech": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3", 
        "general": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3"
    }
    for n, u in tracks.items():
        if not os.path.exists(f"assets/audio/{n}.mp3"): os.system(f"wget -q -O assets/audio/{n}.mp3 {u}")
    if not os.path.exists("Anton.ttf"): os.system("wget -q -O Anton.ttf https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf")

# DYNAMIC MODEL SELECTOR (Asks Groq what it has)
def get_best_groq_model(client):
    try:
        models = client.models.list()
        # Prefer 70b Llama 3.3
        for m in models.data:
            if "llama-3.3-70b" in m.id: return m.id
        # Fallback to 3.1
        for m in models.data:
            if "llama-3.1-70b" in m.id: return m.id
        return "llama3-70b-8192"
    except: return "llama-3.3-70b-versatile"

def is_garbage(title):
    t = title.lower()
    # Context-aware ad filter
    ads = ["gift guide", "buying guide", "deals under", "best deals", "save $", "shop the", "top picks for christmas"]
    if any(x in t for x in ads): return True
    if not os.path.exists("history_v2.txt"): return False
    with open("history_v2.txt", "r") as f:
        for l in f:
            if "|" in l and difflib.SequenceMatcher(None, t, l.split("|")[0].lower()).ratio() > 0.8: return True
    return False

def fetch_news():
    log("NEWS", "Sourcing from Whitelist...")
    cands = []
    for i in range(0, 30, 15):
        try:
            r = requests.get(f"https://newsapi.org/v2/top-headlines?sources={','.join(PREMIUM_SOURCES[i:i+15])}&apiKey={config.NEWS_API_KEY}", timeout=15).json()
            if r.get('status') == 'ok': cands.extend([a for a in r['articles'] if a.get('urlToImage') and not is_garbage(a['title'])])
        except: pass
    return cands[:15]

# --- RESEARCH ENGINE (Scrape -> Fallback to Search) ---
def perform_research(article):
    log("RESEARCH", f"Analyzing: {article['title']}")
    
    # 1. Try Scraping
    try:
        art = Article(article['url'])
        art.download()
        art.parse()
        if len(art.text) > 500:
            log("RESEARCH", "Scraped article text successfully.")
            return art.text[:2500]
    except: pass
    
    # 2. Fallback to Search
    log("RESEARCH", "Scrape failed/blocked. Switching to DuckDuckGo Search...")
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(article['title'], max_results=3))
            summary = "\n".join([res['body'] for res in results])
            log("RESEARCH", "Search context retrieved.")
            return summary
    except: 
        log("WARN", "Search failed. Using description only.")
        return article.get('description', '')

def generate_content(art, ctx):
    client = Groq(api_key=config.GROQ_API_KEY)
    model = get_best_groq_model(client)
    log("AI", f"Using Model: {model}")
    
    # MOOD ANALYSIS + STRICT LIMITS
    v_prompt = f"Analyze: {art['title']}\nContext: {ctx}\nReturn JSON: {{\"mood\": \"CRISIS/TECH/GENERAL\", \"headline\": \"5-8 words\", \"summary\": \"EXACTLY 20-25 words UNIQUE facts\"}}"
    v_data = json.loads(client.chat.completions.create(messages=[{"role":"user","content":v_prompt}], model=model, response_format={"type": "json_object"}).choices[0].message.content)
    
    cap_prompt = f"IG Caption for: {art['title']}. Hook, 3 bullets, question, 5 tags. Limit 2200 chars."
    caption = client.chat.completions.create(messages=[{"role":"user","content":cap_prompt}], model=model).choices[0].message.content.strip() + f"\n.\n.\n{GENERIC_TAGS}"
    
    div_prompt = f"250-word deep dive starting with '🧠 DEEP DIVE:' for: {art['title']}\nContext: {ctx}"
    comment = client.chat.completions.create(messages=[{"role":"user","content":div_prompt}], model=model).choices[0].message.content.strip()
    
    return v_data['mood'], v_data['headline'], v_data['summary'], caption, comment

def fit_text(draw, text, max_w, max_h, start_size):
    size = start_size
    while size > 25:
        font = ImageFont.truetype("Anton.ttf", size)
        lines = textwrap.wrap(text, width=int(max_w/(size*0.55)))
        th = sum([draw.textbbox((0,0), l, font=font)[3] - draw.textbbox((0,0), l, font=font)[1] + 15 for l in lines])
        if th < max_h: return font, lines
        size -= 4
    return ImageFont.truetype("Anton.ttf", 25), textwrap.wrap(text, width=28)

def render_video(art, mood, hl, summ):
    ensure_assets()
    
    # MOOD CONFIG (Color AND Audio)
    cfg = {
        "crisis": {"c": "#FF0000", "a": "assets/audio/crisis.mp3"}, 
        "tech": {"c": "#00F0FF", "a": "assets/audio/tech.mp3"}, 
        "general": {"c": "#FFD700", "a": "assets/audio/general.mp3"}
    }.get(mood.lower(), {"c": "#FFD700", "a": "assets/audio/general.mp3"})
    
    try:
        r = requests.get(art['urlToImage'], timeout=15)
        if r.status_code != 200 or len(r.content) < 1000: raise Exception("Invalid Image")
        with open("bg.jpg", "wb") as f: f.write(r.content)
        Image.open("bg.jpg").verify() 
    except Exception as e:
        log("RENDER", f"Image Failed: {e}")
        return None

    try:
        W, H = 1080, 1920
        overlay = Image.new('RGBA', (W, H), (0,0,0,0))
        draw = ImageDraw.Draw(overlay)
        grad = Image.new('L', (W, H), 0)
        for y in range(int(H*0.45), H): ImageDraw.Draw(grad).line([(0,y),(W,y)], fill=int((y-H*0.45)/(H*0.55)*255))
        overlay.paste(Image.new('RGBA',(W,H),(0,0,0,240)), (0,0), mask=grad)
        
        f_s = ImageFont.truetype("Anton.ttf", 35)
        sn = f" {art['source']['name'].upper()} "
        draw.rounded_rectangle([(60,150), (60+draw.textlength(sn, f_s)+20, 210)], 12, fill=cfg["c"])
        draw.text((70,160), sn, font=f_s, fill="black")
        
        f_h, h_l = fit_text(draw, hl.upper(), 900, 450, 110)
        cy = 880
        for l in h_l:
            draw.text((65, cy+5), l, font=f_h, fill="black")
            draw.text((60, cy), l, font=f_h, fill=cfg["c"])
            cy += f_h.size + 15
        
        # SAFE ZONE ENFORCED (Y=1344)
        SAFE_LIMIT = 1344
        f_u, s_l = fit_text(draw, summ, 900, SAFE_LIMIT-cy, 55)
        cy += 20
        for l in s_l:
            if cy > SAFE_LIMIT: break # CUTOFF PROTECTION
            draw.text((60, cy), l, font=f_u, fill="white")
            cy += f_u.size + 12
            
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
        if os.path.exists(cfg["a"]): final = final.set_audio(AudioFileClip(cfg["a"]).subclip(0,6))
        final.write_videofile("final.mp4", fps=24, codec='libx264', audio_codec='aac', preset='ultrafast', logger=None)
        return "final.mp4"
    except Exception as e:
        log("ERROR", f"Render Crash: {e}")
        return None

def publish(path, cap, comm):
    try:
        up = cloudinary.uploader.upload(path, resource_type="video")
        r = requests.post(f"https://graph.facebook.com/v18.0/{config.IG_USER_ID}/media", data={"media_type": "REELS", "video_url": up['secure_url'], "caption": cap, "access_token": config.IG_ACCESS_TOKEN}).json()
        if 'id' not in r: return False
        cid = r['id']
        for _ in range(15):
            time.sleep(10)
            s = requests.get(f"https://graph.facebook.com/v18.0/{cid}", params={"fields":"status_code", "access_token": config.IG_ACCESS_TOKEN}).json()
            if s.get('status_code') == 'FINISHED':
                p = requests.post(f"https://graph.facebook.com/v18.0/{config.IG_USER_ID}/media_publish", data={"creation_id": cid, "access_token": config.IG_ACCESS_TOKEN}).json()
                if 'id' in p:
                    time.sleep(10)
                    requests.post(f"https://graph.facebook.com/v18.0/{p['id']}/comments", data={"message": comm, "access_token": config.IG_ACCESS_TOKEN})
                    send_telegram(f"✅ *V2 Live:* {cap[:100]}...")
                    return True
        return False
    except: return False

# RESTORED MAIN LOOP WITH RESEARCH
if __name__ == "__main__":
    ensure_assets()
    log("BOT", "V2 Running...")
    cands = fetch_news()
    if not cands: log("BOT", "No News.")
    else:
        for i, art in enumerate(cands):
            log("BOT", f"Candidate #{i+1}: {art['title']}")
            try:
                # 1. Research (Scrape or Search)
                ctx = perform_research(art)
                
                # 2. AI Content (Mood, Text, Deep Dive)
                m, h, s, cp, cm = generate_content(art, ctx)
                
                # 3. Render (Audio, Color, Safe Zone)
                v = render_video(art, m, h, s)
                
                # 4. Publish
                if v and publish(v, cp, cm):
                    with open("history_v2.txt", "a") as f: f.write(f"{art['title']}|{art['url']}\n")
                    log("SUCCESS", "Done.")
                    break
                else: log("WARN", "Failed, trying next...")
            except Exception as e: log("ERROR", e)
