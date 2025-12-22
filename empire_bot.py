import os, time, requests, textwrap, json, numpy as np, cloudinary, cloudinary.uploader, config_empire as config, difflib
from PIL import Image, ImageDraw, ImageFont, ImageFile
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip, AudioFileClip
from groq import Groq
from datetime import datetime
from newspaper import Article
from duckduckgo_search import DDGS
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ImageFile.LOAD_TRUNCATED_IMAGES = True
cloudinary.config(cloud_name=config.CLOUDINARY_CLOUD_NAME, api_key=config.CLOUDINARY_API_KEY, api_secret=config.CLOUDINARY_API_SECRET)

# --- 1. SETUP & ASSETS ---
PREMIUM_SOURCES = ["reuters", "associated-press", "bbc-news", "cnn", "bloomberg", "the-wall-street-journal", "the-washington-post", "time", "wired", "the-verge", "techcrunch", "business-insider", "fortune", "cnbc", "abc-news", "cbs-news", "nbc-news", "politico", "axios", "the-hill", "usa-today", "the-independent", "the-telegraph", "france-24", "dw-news", "scmp", "the-hindu", "the-times-of-india", "variety", "hollywood-reporter", "rolling-stone", "ign", "espn", "bleacher-report", "national-geographic", "new-scientist", "scientific-american", "nature", "the-economist", "hacker-news", "ars-technica", "engadget", "gizmodo", "mashable", "vox", "new-york-magazine", "the-atlantic"]

# REMOVED: Old static tags. We now generate smart tags dynamically.

def log(step, msg): 
    # Enhanced Logging: Prints clearly to the console
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
    ads = ["gift guide", "buying guide", "deals", "save $", "shop", "top picks", "review"]
    if any(x in t for x in ads): return True
    if not os.path.exists("history_v2.txt"): return False
    with open("history_v2.txt", "r") as f:
        for l in f:
            if "|" in l and difflib.SequenceMatcher(None, t, l.split("|")[0].lower()).ratio() > 0.8: return True
    return False

def fetch_news():
    log("NEWS", "Sourcing...")
    cands = []
    for i in range(0, 30, 15):
        try:
            r = requests.get(f"https://newsapi.org/v2/top-headlines?sources={','.join(PREMIUM_SOURCES[i:i+15])}&apiKey={config.NEWS_API_KEY}", timeout=15).json()
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
    client = Groq(api_key=config.GROQ_API_KEY)
    model = get_best_groq_model(client)
    
    # 1. Video Data
    v_prompt = f"Analyze: {art['title']}\nContext: {ctx}\nReturn JSON: {{\"mood\": \"CRISIS/TECH/GENERAL\", \"headline\": \"5-8 words\", \"summary\": \"EXACTLY 20-25 words UNIQUE facts\"}}"
    v_data = json.loads(client.chat.completions.create(messages=[{"role":"user","content":v_prompt}], model=model, response_format={"type": "json_object"}).choices[0].message.content)
    
    # 2. Caption + Smart Hashtags (UPDATED)
    # Asking for 15 specific tags relevant to the news topic
    cap_prompt = (
        f"Write a caption for this news: '{art['title']}'. "
        f"Structure: Hook, 3 quick bullet points, and a question. "
        f"At the very end, generate 15 relevant, high-traffic hashtags specific to this news topic (mix of broad and niche). "
        f"Do NOT use generic tags like #news only. "
        f"Limit total response to 2000 chars."
    )
    caption = client.chat.completions.create(messages=[{"role":"user","content":cap_prompt}], model=model).choices[0].message.content.strip()
    
    # 3. Deep Dive
    div_prompt = f"250-word deep dive starting with '🧠 DEEP DIVE:' for: {art['title']}\nContext: {ctx}"
    comment = client.chat.completions.create(messages=[{"role":"user","content":div_prompt}], model=model).choices[0].message.content.strip()
    
    return v_data['mood'], v_data['headline'], v_data['summary'], caption, comment

# --- 3. RENDERER ---
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
    cfg = {"crisis": {"c": "#FF0000", "a": "assets/audio/crisis.mp3"}, "tech": {"c": "#00F0FF", "a": "assets/audio/tech.mp3"}, "general": {"c": "#FFD700", "a": "assets/audio/general.mp3"}}.get(mood.lower(), {"c": "#FFD700", "a": "assets/audio/general.mp3"})
    
    try:
        r = requests.get(art['urlToImage'], timeout=15)
        if r.status_code != 200 or len(r.content) < 1000: raise Exception("Invalid Image")
        with open("bg.jpg", "wb") as f: f.write(r.content)
        Image.open("bg.jpg").verify()
    except Exception as e: return None

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
        
        cy = 600
        f_h, h_l = fit_text(draw, hl.upper(), 900, 600, 140)
        for l in h_l:
            draw.text((65, cy+5), l, font=f_h, fill="black")
            draw.text((60, cy), l, font=f_h, fill=cfg["c"])
            cy += f_h.size + 15
        
        SAFE_LIMIT = 1500
        f_u, s_l = fit_text(draw, summ, 900, SAFE_LIMIT-cy, 100)
        cy += 30
        for l in s_l:
            if cy > SAFE_LIMIT: break
            draw.text((60, cy), l, font=f_u, fill="white")
            cy += f_u.size + 12
            
        overlay.save("overlay.png")
        img = Image.open("bg.jpg").convert("RGB")
        bw, bh = img.size; ratio = 1080/1920
        if bw/bh > ratio: nw = bh * ratio; img = img.crop(((bw-nw)/2, 0, (bw+nw)/2, bh))
        else: nh = bw/ratio; img = img.crop((0, (bh-nh)/2, bw, (bh-nh)/2 + nh))
        img.resize((1080, 1920), Image.LANCZOS).save("temp_bg.jpg")
        
        clip = ImageClip("temp_bg.jpg").set_duration(6).fl(lambda gf, t: np.array(Image.fromarray(gf(t)).resize([int(d*(1+0.04*t)) for d in Image.fromarray(gf(t)).size], Image.BILINEAR).crop((0,0,1080,1920))))
        final = CompositeVideoClip([clip, ImageClip("overlay.png").set_duration(6)])
        if os.path.exists(cfg["a"]): final = final.set_audio(AudioFileClip(cfg["a"]).subclip(0,6))
        final.write_videofile("final.mp4", fps=24, codec='libx264', audio_codec='aac', preset='ultrafast', logger=None)
        return "final.mp4"
    except: return None

# --- 4. PLATFORM POSTING (ENHANCED LOGGING) ---

def post_instagram(path, cap, comm):
    log("INSTA", "Posting with OLD Token...")
    try:
        up = cloudinary.uploader.upload(path, resource_type="video")
        r = requests.post(f"https://graph.facebook.com/v18.0/{config.IG_USER_ID}/media", data={"media_type": "REELS", "video_url": up['secure_url'], "caption": cap, "access_token": config.IG_ACCESS_TOKEN}).json()
        if 'id' in r:
            cid = r['id']
            log("INSTA_DEBUG", f"Container Created: {cid}")
            for _ in range(15):
                time.sleep(10)
                s = requests.get(f"https://graph.facebook.com/v18.0/{cid}", params={"fields":"status_code", "access_token": config.IG_ACCESS_TOKEN}).json()
                if s.get('status_code') == 'FINISHED':
                    p = requests.post(f"https://graph.facebook.com/v18.0/{config.IG_USER_ID}/media_publish", data={"creation_id": cid, "access_token": config.IG_ACCESS_TOKEN}).json()
                    if 'id' in p:
                        log("INSTA_SUCCESS", f"Published ID: {p['id']}")
                        time.sleep(5)
                        requests.post(f"https://graph.facebook.com/v18.0/{p['id']}/comments", data={"message": comm, "access_token": config.IG_ACCESS_TOKEN})
                        return True
        log("INSTA_FAIL", f"Raw Response: {r}")
        return False
    except Exception as e:
        log("INSTA_ERROR", str(e))
        return False

def post_facebook(path, cap, deep_dive):
    log("FB", f"Posting to New Page ID: {config.FB_PAGE_ID}...")
    full_desc = f"{cap}\n\n---\n{deep_dive}"
    try:
        # 1. Start
        init = requests.post(f"https://graph.facebook.com/v18.0/{config.FB_PAGE_ID}/video_reels", data={"upload_phase": "start", "access_token": config.FB_ACCESS_TOKEN}).json()
        if 'video_id' not in init: 
            log("FB_INIT_FAIL", f"Could not start upload. Response: {init}")
            return False
        
        vid_id = init['video_id']
        log("FB_DEBUG", f"Video ID Reserved: {vid_id}")
        
        # 2. Upload
        with open(path, 'rb') as f:
            requests.post(init['upload_url'], headers={"Authorization": f"OAuth {config.FB_ACCESS_TOKEN}"}, files={'video_file_chunk': f})
        
        # 3. Publish
        fin = requests.post(f"https://graph.facebook.com/v18.0/{config.FB_PAGE_ID}/video_reels", data={"upload_phase": "finish", "video_id": vid_id, "video_state": "PUBLISHED", "description": full_desc[:5000], "access_token": config.FB_ACCESS_TOKEN}).json()
        
        if 'success' in fin and fin['success']:
            log("FB_SUCCESS", "Video Published Successfully.")
            return True
        else:
            log("FB_PUBLISH_FAIL", f"Final Response: {fin}")
            return False
            
    except Exception as e:
        log("FB_CRITICAL_ERROR", str(e))
        return False

def post_youtube(path, title, deep_dive):
    log("YOUTUBE", "Posting Short (Limited Schedule)...")
    try:
        creds = Credentials(None, refresh_token=config.YT_REFRESH_TOKEN, token_uri="https://oauth2.googleapis.com/token", client_id=config.YT_CLIENT_ID, client_secret=config.YT_CLIENT_SECRET)
        youtube = build("youtube", "v3", credentials=creds)
        request = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {"title": title[:100], "description": deep_dive, "tags": ["shorts", "news"]}, # Hashtags are now in deep_dive/caption
                "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
            },
            media_body=MediaFileUpload(path)
        )
        res = request.execute()
        if 'id' in res:
            log("YT_SUCCESS", f"Video ID: {res['id']}")
            return True
        else:
            log("YT_FAIL", f"API Response: {res}")
            return False
    except Exception as e:
        log("YT_ERROR", f"Exception: {str(e)}")
        return False

# --- 5. EXECUTION LOOP ---
if __name__ == "__main__":
    ensure_assets()
    log("BOT", "Empire Engine V3 Running...")
    
    current_hour = datetime.utcnow().hour
    should_post_yt = (current_hour % 4 == 0)
    log("SCHEDULER", f"Current UTC Hour: {current_hour}. Posting to YouTube? {'YES' if should_post_yt else 'NO (Saving Quota)'}")
    
    cands = fetch_news()
    if not cands: log("BOT", "No News.")
    else:
        for i, art in enumerate(cands):
            log("BOT", f"Candidate #{i+1}: {art['title']}")
            try:
                ctx = perform_research(art)
                m, h, s, cp, cm = generate_content(art, ctx)
                v = render_video(art, m, h, s)
                if v:
                    ig = post_instagram(v, cp, cm)
                    fb = post_facebook(v, cp, cm)
                    yt = False
                    if should_post_yt:
                        yt = post_youtube(v, h + " #shorts", cm)
                    
                    if ig or fb or yt:
                        with open("history_v2.txt", "a") as f: f.write(f"{art['title']}|{art['url']}\n")
                        log("FINAL_STATUS", f"IG:{ig} | FB:{fb} | YT:{yt}")
                        break
                    else: log("WARN", "All Uploads Failed.")
                else: log("WARN", "Render Failed.")
            except Exception as e: log("ERROR", e)
