import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

def _keep_alive():
    port = int(os.environ.get("PORT", 10000))
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is running")
        def log_message(self, *a):
            pass
    try:
        HTTPServer(("0.0.0.0", port), H).serve_forever()
    except Exception as e:
        print("keep_alive err: " + str(e))

threading.Thread(target=_keep_alive, daemon=True).start()

import json
import time
import glob
import re
import io
import html
import requests
import yt_dlp
import subprocess
import shutil
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ParseMode

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "1159182662") or 0)
except:
    ADMIN_ID = 0

DATA_FILE = "users.json"
URL_RE = re.compile(r'https?://[^\s<>"]+')

def extract_url(text):
    m = URL_RE.search(text or "")
    return m.group(0).rstrip(").,") if m else ""

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, dict) and "users" in d:
                    return d
        except Exception as e:
            print("load err: " + str(e))
    return {"users": {}}

def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(DATA, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("save failed: " + str(e))

DATA = load_data()

DEFAULT_USER = {
    "lang": None, "vip": 0, "state": "home",
    "support_mode": False, "translate_mode": False, "summarize_mode": False, "pdf_mode": False,
    "points": 0, "invites": 0, "invited_by": None, "invited_users": [],
    "last_link": "", "pdf_photos": [], "history": [], "favs": [],
    "quality": "720", "download_mode": "video", "story_mode": False, "movie_mode": False, "wallpaper_mode": False,
    "gif_mode": False, "compress_mode": False,
}

def normalize_list(lst):
    out = []
    for h in (lst or []):
        if isinstance(h, dict) and h.get("url"):
            out.append({"url": str(h["url"]), "title": str(h.get("title", h["url"]))[:80], "time": int(h.get("time", time.time()))})
        elif isinstance(h, str) and h.strip():
            out.append({"url": h.strip(), "title": h.strip()[:80], "time": int(time.time())})
    return out

def get_user(uid):
    uid = str(uid)
    if uid not in DATA["users"] or not isinstance(DATA["users"][uid], dict):
        DATA["users"][uid] = dict(DEFAULT_USER)
        save_data()
    u = DATA["users"][uid]
    for k, v in DEFAULT_USER.items():
        if k not in u:
            u[k] = list(v) if isinstance(v, list) else v
    u["history"] = normalize_list(u.get("history", []))
    u["favs"] = normalize_list(u.get("favs", []))
    u["pdf_photos"] = list(u.get("pdf_photos", []))
    u["invited_users"] = list(u.get("invited_users", []))
    return u

def reset_modes(u):
    u["support_mode"] = False
    u["translate_mode"] = False
    u["summarize_mode"] = False
    u["pdf_mode"] = False
    u["story_mode"] = False
    u["movie_mode"] = False
    u["wallpaper_mode"] = False
    u["gif_mode"] = False
    u["compress_mode"] = False
    u["state"] = "home"

def is_vip(uid):
    try:
        return float(get_user(uid).get("vip", 0)) > time.time()
    except:
        return False

def translate_text(text, target="en"):
    text = (text or "").strip()
    if not text:
        return text
    has_ar = any('\u0600' <= c <= '\u06FF' for c in text)
    if target == "en" and not has_ar:
        return text
    if target == "ar" and has_ar:
        return text
    try:
        sl = "ar" if target == "en" else "en"
        r = requests.get("https://translate.googleapis.com/translate_a/single", params={"client": "gtx", "sl": sl, "tl": target, "dt": "t", "q": text}, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            data = r.json()
            out = "".join([x[0] for x in data[0] if x and x[0]])
            if out and out.strip().lower() != text.strip().lower():
                return out
    except Exception as e:
        print("google tr err: " + str(e))
    try:
        pair = "ar|en" if target == "en" else "en|ar"
        r = requests.get("https://api.mymemory.translated.net/get", params={"q": text[:500], "langpair": pair}, timeout=10)
        if r.status_code == 200:
            tr = r.json().get("responseData", {}).get("translatedText", "")
            if tr and tr.lower() != text.lower():
                return tr
    except Exception as e:
        print("mymemory err: " + str(e))
    return text

def summarize_text(text):
    text = (text or "").strip()
    if len(text) < 200:
        return text
    sentences = re.split(r'[.!؟\n]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    if len(sentences) <= 3:
        return text
    picked = [sentences[0]]
    by_len = sorted(sentences, key=len, reverse=True)[:2]
    for s in by_len:
        if s not in picked:
            picked.append(s)
    if sentences[-1] not in picked:
        picked.append(sentences[-1])
    return ". ".join(picked) + "."

TEXTS = {
    "ar": {
        "choose_lang_title": "اختر لغتك", "welcome": "اهلا بيك في نزل", "welcome_sub": "نزل فيديوهات وصوتيات من كل المنصات",
        "points": "نقطك", "invites": "دعواتك", "vip_left": "فاضل في VIP", "vip_days": "يوم", "not_vip": "انت مش VIP",
        "send_link": "ابعت لينك دلوقتي", "search_btn": "بحث بالاسم", "download_mp3": "تحميل MP3", "download_video": "تحميل فيديو",
        "quality_720": "جودة 720", "quality_1080": "جودة 1080", "quality_2k": "جودة 2K", "quality_4k": "جودة 4K",
        "pdf_btn": "صور لـ PDF", "fav_btn": "مفضلتي", "history_btn": "سجلي", "points_btn": "نقطي ودعوتي", "vip_btn": "VIP",
        "lang_btn": "اللغة", "support_btn": "الدعم", "admin_btn": "لوحة تحكم", "translate_btn": "ترجمة", "summarize_btn": "تلخيص",
        "search_prompt": "اكتب اسم الاغنية او الفيديو اللي بتدور عليه", "searching": "بدور علي", "search_wait": "استنى ثواني",
        "not_found": "ملقيتش حاجة بالاسم ده، جرب اسم تاني او ابعت لينك على طول", "choose_result": "اختر من النتايج دي", "choose_format": "اختار الصيغة",
        "downloading": "بنحمل دلوقتي، استنى", "download_done": "تم التحميل", "download_failed": "التحميل فشل، جرب تاني او ابعت لينك تاني",
        "support_prompt": "اكتب رسالتك للدعم", "support_sent": "رسالتك اتبعت للدعم", "support_reply_title": "رد الدعم",
        "help_text": "ابعت لينك من يوتيوب او تيك توك او انستا او فيسبوك، او دوس بحث بالاسم", "lang_changed": "تم تغيير اللغة",
        "vip_done": "بقيت VIP لمدة 30 يوم", "vip_congrats": "مبروك، بقيت VIP", "back": "رجوع", "home": "القايمة الرئيسية",
        "translate_ask": "ابعت النص اللي عايز تترجمه، لو عربي هترجمه انجليزي، ولو انجليزي هترجمه عربي", "translate_done": "الترجمة",
        "summarize_ask": "ابعت النص اللي عايز تلخصه", "summarize_done": "التلخيص",
        "pdf_ask": "ابعت الصور وانا هحولها PDF، ولما تخلص دوس انهاء", "pdf_done": "تم تحويل الصور لـ PDF", "pdf_added": "تم اضافة الصورة", "pdf_no_photos": "ابعت صور الاول",
        "converting_mp3": "بحولها اغنية دلوقتي، استنى", "no_link_mp3": "ابعت لينك الفيديو الاول", "history_empty": "سجلك فاضي لسه", "fav_empty": "مفضلتك فاضية لسه",
        "no_wm_btn": "بدون علامة مائية", "playlist_btn": "تحميل قايمة تشغيل", "story_btn": "ستوري انستا", "gif_btn": "فيديو لـ GIF",
        "compress_btn": "ضغط فيديو", "extract_btn": "استخراج صوت من فيديو", "movies_btn": "افلام ومسلسلات", "wallpaper_btn": "خلفيات HD",
        "explore_btn": "اكسبلور ترند", "choose_quality": "اختار الجودة اللي عايز تحمل بيها", "quality_set": "تمام، الجودة بقت",
        "choose_video_action": "ابعت فيديو واختار هتعمل بيه ايه:", "send_video_first": "ابعت فيديو من موبايلك الاول",
    },
    "en": {
        "choose_lang_title": "Choose your language", "welcome": "Welcome to Nezel", "welcome_sub": "Download videos and audios from all platforms",
        "points": "Points", "invites": "Invites", "vip_left": "VIP left", "vip_days": "days", "not_vip": "You are not VIP",
        "send_link": "Send link now", "search_btn": "Search by name", "download_mp3": "Download MP3", "download_video": "Download Video",
        "quality_720": "Quality 720", "quality_1080": "Quality 1080", "quality_2k": "Quality 2K", "quality_4k": "Quality 4K",
        "pdf_btn": "Images to PDF", "fav_btn": "My Favorites", "history_btn": "My History", "points_btn": "My Points", "vip_btn": "VIP",
        "lang_btn": "Language", "support_btn": "Support", "admin_btn": "Admin Panel", "translate_btn": "Translate", "summarize_btn": "Summarize",
        "search_prompt": "Type the song or video name you want", "searching": "Searching for", "search_wait": "Please wait",
        "not_found": "Nothing found with this name, try another name or send link directly", "choose_result": "Choose from results", "choose_format": "Choose format",
        "downloading": "Downloading now, please wait", "download_done": "Download done", "download_failed": "Download failed, try again",
        "support_prompt": "Write your message to support", "support_sent": "Your message sent to support", "support_reply_title": "Support reply",
        "help_text": "Send a link from YouTube, TikTok, Instagram or Facebook, or tap Search", "lang_changed": "Language changed",
        "vip_done": "You are now VIP for 30 days", "vip_congrats": "Congrats, you are VIP", "back": "Back", "home": "Main Menu",
        "translate_ask": "Send text to translate, Arabic -> English, English -> Arabic", "translate_done": "Translation",
        "summarize_ask": "Send text to summarize", "summarize_done": "Summary",
        "pdf_ask": "Send photos and I will make PDF, press Finish when done", "pdf_done": "PDF created", "pdf_added": "Photo added", "pdf_no_photos": "Send photos first",
        "converting_mp3": "Converting to MP3, wait", "no_link_mp3": "Send video link first", "history_empty": "Your history is empty", "fav_empty": "Your favorites is empty",
        "no_wm_btn": "No Watermark", "playlist_btn": "Playlist Download", "story_btn": "Insta Story", "gif_btn": "Video to GIF",
        "compress_btn": "Compress Video", "extract_btn": "Extract Audio", "movies_btn": "Movies & Series", "wallpaper_btn": "HD Wallpapers",
        "explore_btn": "Trending Explore", "choose_quality": "Choose quality", "quality_set": "Quality set to",
        "choose_video_action": "Send a video and choose:", "send_video_first": "Send a video first",
    }
}

def T(uid, key):
    u = get_user(uid)
    lang = u.get("lang") or "ar"
    if lang not in TEXTS:
        lang = "ar"
    return TEXTS[lang].get(key, key)

def lang_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("العربية 🇪🇬", callback_data="set_lang_ar")],
        [InlineKeyboardButton("English 🇬🇧", callback_data="set_lang_en")],
    ])

def quality_keyboard(uid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 720", callback_data="set_q_720"), InlineKeyboardButton("🎬 1080", callback_data="set_q_1080")],
        [InlineKeyboardButton("🎬 2K", callback_data="set_q_2k"), InlineKeyboardButton("🎬 4K", callback_data="set_q_4k")],
        [InlineKeyboardButton(f"⬅️ {T(uid, 'back')}", callback_data="home")],
    ])

def main_keyboard(uid):
    u = get_user(uid)
    if is_vip(uid):
        days = int((float(u.get("vip", 0)) - time.time()) // 86400) + 1
        vip_txt = f"👑 {T(uid, 'vip_btn')} | {T(uid, 'vip_left')} {max(1, days)} {T(uid, 'vip_days')}"
    else:
        vip_txt = f"👑 {T(uid, 'vip_btn')}"
    kb = [
        [InlineKeyboardButton(f"🎵 {T(uid, 'download_mp3')}", callback_data="mode_mp3"), InlineKeyboardButton(f"📥 {T(uid, 'download_video')}", callback_data="mode_video")],
        [InlineKeyboardButton(f"🎬 {T(uid, 'quality_720')}", callback_data="set_q_720"), InlineKeyboardButton(f"🎬 {T(uid, 'quality_1080')}", callback_data="set_q_1080")],
        [InlineKeyboardButton("🎬 2K", callback_data="set_q_2k"), InlineKeyboardButton("🎬 4K", callback_data="set_q_4k")],
        [InlineKeyboardButton(f"✨ {T(uid, 'no_wm_btn')}", callback_data="mode_nowm"), InlineKeyboardButton(f"📃 {T(uid, 'playlist_btn')}", callback_data="mode_playlist")],
        [InlineKeyboardButton(f"📸 {T(uid, 'story_btn')}", callback_data="mode_story"), InlineKeyboardButton(f"🔥 {T(uid, 'explore_btn')}", callback_data="mode_explore")],
        [InlineKeyboardButton(f"🎞️ {T(uid, 'gif_btn')}", callback_data="mode_gif"), InlineKeyboardButton(f"🗜️ {T(uid, 'compress_btn')}", callback_data="mode_compress")],
        [InlineKeyboardButton(f"🎧 {T(uid, 'extract_btn')}", callback_data="mode_extract"), InlineKeyboardButton(f"🎬 {T(uid, 'movies_btn')}", callback_data="mode_movies")],
        [InlineKeyboardButton(f"🖼️ {T(uid, 'wallpaper_btn')}", callback_data="mode_wallpaper"), InlineKeyboardButton(f"🔍 {T(uid, 'search_btn')}", callback_data="search")],
        [InlineKeyboardButton(f"🖼️ {T(uid, 'pdf_btn')}", callback_data="pdf_menu"), InlineKeyboardButton(f"🌐 {T(uid, 'translate_btn')}", callback_data="tr_menu")],
        [InlineKeyboardButton(f"📝 {T(uid, 'summarize_btn')}", callback_data="sum_menu"), InlineKeyboardButton(f"⭐ {T(uid, 'fav_btn')}", callback_data="fav_info")],
        [InlineKeyboardButton(f"📂 {T(uid, 'history_btn')}", callback_data="history_info"), InlineKeyboardButton(f"🎁 {T(uid, 'points_btn')}", callback_data="points_info")],
        [InlineKeyboardButton(f"{vip_txt}", callback_data="vip_info"), InlineKeyboardButton(f"🌐 {T(uid, 'lang_btn')}", callback_data="lang")],
        [InlineKeyboardButton(f"📞 {T(uid, 'support_btn')}", callback_data="support")],
    ]
    if int(uid) == ADMIN_ID and ADMIN_ID != 0:
        kb.append([InlineKeyboardButton(f"👑 {T(uid, 'admin_btn')}", callback_data="admin_info")])
    return InlineKeyboardMarkup(kb)

def show_main_menu_text(uid, name):
    u = get_user(uid)
    points = u.get("points", 0)
    invites = u.get("invites", 0)
    if is_vip(uid):
        days = int((float(u.get("vip", 0)) - time.time()) // 86400) + 1
        vip_line = f"👑 {T(uid, 'vip_left')} {max(1, days)} {T(uid, 'vip_days')}"
    else:
        vip_line = f"👑 {T(uid, 'not_vip')}"
    return "\n".join([
        f"✨ {T(uid, 'welcome')} {name} 👑", "", T(uid, 'welcome_sub'), "────────────────",
        f"🎁 {T(uid, 'points')}: {points} / 100", f"👥 {T(uid, 'invites')}: {invites} / 50", vip_line,
        f"🎬 الجودة الحالية: {u.get('quality','720')}", "────────────────", f"👇 {T(uid, 'send_link')}"
    ])

def compress_video_file(in_path, out_path, crf=28):
    if not shutil.which("ffmpeg"):
        return False, "ffmpeg not found"
    cmd = ["ffmpeg", "-y", "-i", in_path, "-vcodec", "libx264", "-crf", str(crf), "-preset", "veryfast", "-acodec", "aac", "-b:a", "128k", "-movflags", "+faststart", out_path]
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=180)
        if res.returncode != 0:
            print("ffmpeg err: " + res.stderr.decode(errors="ignore")[-500:])
            return False, "ffmpeg failed"
        if not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
            return False, "output too small"
        return True, "ok"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, str(e)

def save_history(u, url, title=""):
    url = (url or "").strip()
    if not url:
        return
    hist = normalize_list(u.get("history", []))
    hist = [x for x in hist if x["url"] != url]
    hist.append({"url": url, "title": (title or url)[:80], "time": int(time.time())})
    u["history"] = hist[-30:]
    save_data()

def add_fav(u, url, title=""):
    url = (url or "").strip()
    if not url:
        return
    favs = normalize_list(u.get("favs", []))
    favs = [x for x in favs if x["url"] != url]
    favs.append({"url": url, "title": (title or url)[:80], "time": int(time.time())})
    u["favs"] = favs[-30:]
    save_data()

def search_movies(query):
    results = []
    try:
        r = requests.get("https://api.tvmaze.com/search/shows", params={"q": query}, timeout=15)
        if r.status_code == 200 and r.json():
            for item in r.json()[:5]:
                s = item.get("show", {})
                summary = re.sub(r'<[^>]+>', '', s.get("summary", "") or "")[:180]
                results.append({"name": s.get("name", ""), "summary": summary or f"{s.get('premiered','')} - {s.get('status','')}", "url": s.get("url", "")})
            if results:
                return results
    except Exception as e:
        print(f"tvmaze err: {e}")
    try:
        r = requests.get("https://ar.wikipedia.org/w/api.php", params={"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": 5}, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            for item in r.json().get("query", {}).get("search", [])[:5]:
                title = item.get("title", "")
                snippet = re.sub(r'<[^>]+>', '', item.get("snippet", "") or "")[:180]
                results.append({"name": title, "summary": snippet, "url": f"https://ar.wikipedia.org/wiki/{title.replace(' ', '_')}"})
            if results:
                return results
    except Exception as e:
        print(f"wiki movies err: {e}")
    return results

def get_wallpapers(query="nature"):
    try:
        r = requests.get("https://picsum.photos/v2/list", params={"page": 1, "limit": 5}, timeout=15)
        if r.status_code == 200:
            return [f"https://picsum.photos/id/{x['id']}/1080/1920" for x in r.json()]
    except Exception as e:
        print(f"wallpaper err: {e}")
    return ["https://picsum.photos/1080/1920", "https://picsum.photos/1080/1920?random=1", "https://picsum.photos/1080/1920?random=2"]

def get_trending():
    try:
        r = requests.get("https://www.tikwm.com/api/feed/list", params={"region": "EG", "count": 10}, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json().get("data", {})
        videos = data.get("videos", []) if isinstance(data, dict) else []
        res = []
        for v in videos[:5]:
            vid = v.get("video_id") or v.get("id") or ""
            title = v.get("title") or v.get("desc") or "ترند"
            author = v.get("author", {}).get("unique_id", "tiktok") if isinstance(v.get("author"), dict) else "tiktok"
            if vid:
                res.append({"id": str(vid), "title": title[:50], "author": author, "url": f"https://www.tiktok.com/@{author}/video/{vid}"})
        if res:
            return res
    except Exception as e:
        print(f"trend err: {e}")
    return []

def do_search(query):
    try:
        opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True, "socket_timeout": 30}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch5:{query}", download=False)
            entries = info.get("entries", []) if info else []
            results = []
            for e in entries:
                if not e:
                    continue
                vid = e.get("id", "")
                title = e.get("title", query)
                if vid and len(vid) == 11:
                    results.append({"id": vid, "title": title})
            if results:
                return results
    except Exception as e:
        print("ytsearch failed: " + str(e))
    return []

def format_for_quality(quality="720", want_audio=False):
    if want_audio:
        return "bestaudio/best"
    q = str(quality).lower()
    h = {"720": 720, "1080": 1080, "2k": 1440, "4k": 2160}.get(q, 720)
    return f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"

def download_with_ytdlp(url, base, want_audio=False, quality="720"):
    try:
        for f in glob.glob(base + ".*"):
            try: os.remove(f)
            except: pass
        fmt = format_for_quality(quality, want_audio)
        opts = {
            "format": fmt, "outtmpl": base + ".%(ext)s", "quiet": True, "no_warnings": True,
            "nocheckcertificate": True, "socket_timeout": 90, "cookiefile": None,
            "extractor_args": {"youtube": {"player_client": [["android", "ios", "web", "tv", "mweb"]], "player_skip": ["configs"]}},
            "http_headers": {"User-Agent": "Mozilla/5.0"},
        }
        if want_audio:
            opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        files = [f for f in glob.glob(base + ".*") if not f.endswith(".part")]
        return files
    except Exception as e:
        print("download failed: " + str(e))
        return []

async def send_downloaded(q_or_msg, files, want_audio, kb):
    # q_or_msg has reply_video / reply_audio / reply_photo
    try:
        for fp in files:
            if fp.endswith((".jpg", ".jpeg", ".png", ".webp")):
                with open(fp, "rb") as f:
                    await q_or_msg.reply_photo(f)
            else:
                with open(fp, "rb") as f:
                    if want_audio:
                        await q_or_msg.reply_audio(f, reply_markup=kb)
                    else:
                        await q_or_msg.reply_video(f, reply_markup=kb)
            try: os.remove(fp)
            except: pass
        return True
    except Exception as e:
        print(f"send err: {e}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = get_user(uid)
    if context.args and context.args[0].startswith("inv_"):
        inviter = context.args[0].replace("inv_", "")
        if inviter != str(uid) and not u.get("invited_by") and inviter.isdigit():
            u["invited_by"] = inviter
            inv = get_user(int(inviter))
            if str(uid) not in inv.get("invited_users", []):
                inv["invited_users"].append(str(uid))
                try: inv["points"] = int(inv.get("points", 0)) + 5
                except: inv["points"] = 5
                try: inv["invites"] = int(inv.get("invites", 0)) + 1
                except: inv["invites"] = 1
                save_data()
                try: await context.bot.send_message(chat_id=int(inviter), text="🎉 حد دخل من لينكك! +5 نقاط")
                except: pass
    reset_modes(u)
    save_data()
    await update.message.reply_text("اختر لغتك\n\nChoose your language", reply_markup=lang_keyboard())

async def vip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Use: /vip 123456"); return
    if uid != ADMIN_ID and ADMIN_ID != 0:
        await update.message.reply_text("Not allowed"); return
    try:
        target = str(context.args[0]).strip()
        if not target.isdigit():
            await update.message.reply_text("ID must be numbers"); return
        tu = get_user(target)
        tu["vip"] = time.time() + 30 * 86400
        save_data()
        await update.message.reply_text(T(uid, "vip_done"))
        try: await context.bot.send_message(chat_id=int(target), text=T(int(target), "vip_congrats"))
        except: pass
    except Exception as e:
        await update.message.reply_text("Error: " + str(e))

async def reply_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_ID or ADMIN_ID == 0: return
    if len(context.args) < 2:
        await update.message.reply_text("Use: /reply 123456 your message"); return
    target = context.args[0]
    if not target.isdigit():
        await update.message.reply_text("ID wrong"); return
    msg = " ".join(context.args[1:])
    try:
        await context.bot.send_message(chat_id=int(target), text=f"{T(int(target), 'support_reply_title')}\n\n{msg}")
        await update.message.reply_text("Sent")
    except Exception as e:
        await update.message.reply_text("Error: " + str(e))

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = get_user(uid)
    data = q.data or ""
    if data == "set_lang_ar":
        u["lang"] = "ar"; reset_modes(u); save_data()
        await q.message.reply_text(T(uid, "lang_changed"))
        await q.message.reply_text(show_main_menu_text(uid, q.from_user.first_name or ""), reply_markup=main_keyboard(uid))
        return
    if data == "set_lang_en":
        u["lang"] = "en"; reset_modes(u); save_data()
        await q.message.reply_text(T(uid, "lang_changed"))
        await q.message.reply_text(show_main_menu_text(uid, q.from_user.first_name or ""), reply_markup=main_keyboard(uid))
        return
    if not u.get("lang"):
        await q.message.reply_text("اختر لغتك\n\nChoose your language", reply_markup=lang_keyboard())
        return
    if data.startswith("set_q_"):
        qq = data.replace("set_q_", "").lower()
        u["quality"] = qq; save_data()
        await q.message.reply_text(f"✅ {T(uid, 'quality_set')} {qq}\n\nابعت لينك دلوقتي وهيتحمل بالجودة دي")
        return
    if data == "mode_mp3":
        reset_modes(u); u["download_mode"] = "audio"; save_data()
        await q.message.reply_text("🎵 تمام، ابعت اللينك وهحوله MP3 على طول"); return
    if data == "mode_video":
        reset_modes(u); u["download_mode"] = "video"; save_data()
        await q.message.reply_text(f"📥 تمام، اختار الجودة:", reply_markup=quality_keyboard(uid)); return
    if data == "mode_nowm":
        reset_modes(u); u["download_mode"] = "nowm"; save_data()
        await q.message.reply_text("✨ تمام، ابعت لينك تيك توك وهجيبهولك من غير علامة مائية"); return
    if data == "mode_playlist":
        reset_modes(u); u["download_mode"] = "playlist"; save_data()
        await q.message.reply_text("📃 ابعت لينك قايمة التشغيل"); return
    if data == "mode_story":
        reset_modes(u); u["story_mode"] = True; u["state"] = "story"; save_data()
        await q.message.reply_text("📸 ابعت لينك الستوري من انستا على طول\nانسخ لينك الستوري من انستا وابعته هنا"); return
    if data == "mode_explore":
        await q.message.reply_text("🔥 بدور على الترند...")
        trends = get_trending()
        if not trends:
            await q.message.reply_text(T(uid, "not_found")); return
        btns = [[InlineKeyboardButton(f"🎵 {t['title'][:35]}", callback_data=f"pick_tiktok_{t['id']}")] for t in trends]
        btns.append([InlineKeyboardButton(f"⬅️ {T(uid, 'back')}", callback_data="home")])
        await q.message.reply_text("🔥 ترند تيك توك دلوقتي:", reply_markup=InlineKeyboardMarkup(btns)); return
    if data == "mode_gif":
        reset_modes(u); u["gif_mode"] = True; save_data()
        await q.message.reply_text("🎞️ ابعت فيديو من موبايلك وهحوله GIF"); return
    if data == "mode_compress":
        reset_modes(u); u["compress_mode"] = True; save_data()
        await q.message.reply_text("🗜️ ابعت فيديو من موبايلك وهضغطهولك عشان يتبعت بسهولة"); return
    if data == "mode_extract":
        reset_modes(u); u["state"] = "extract"; save_data()
        await q.message.reply_text("🎧 ابعت فيديو من موبايلك وهطلعلك الصوت بتاعه MP3"); return
    if data == "mode_movies":
        reset_modes(u); u["movie_mode"] = True; u["state"] = "movies"; save_data()
        await q.message.reply_text("🎬 اكتب اسم الفيلم او المسلسل اللي بتدور عليه بالعربي او الانجليزي"); return
    if data == "mode_wallpaper":
        reset_modes(u); u["wallpaper_mode"] = True; u["state"] = "wallpaper"; save_data()
        await q.message.reply_text("🖼️ اكتب نوع الخلفية اللي عايزها: طبيعة، سيارات، انمي..."); return
    if data == "search":
        reset_modes(u); u["state"] = "search"; save_data()
        await q.message.reply_text(f"🔍 {T(uid, 'search_prompt')}"); return
    if data == "lang":
        await q.message.reply_text("اختر لغتك\n\nChoose your language", reply_markup=lang_keyboard()); return
    if data == "support":
        reset_modes(u); u["state"] = "support"; u["support_mode"] = True; save_data()
        await q.message.reply_text(f"📞 {T(uid, 'support_prompt')}"); return
    if data == "tr_menu":
        reset_modes(u); u["translate_mode"] = True; save_data()
        await q.message.reply_text(T(uid, "translate_ask")); return
    if data == "sum_menu":
        reset_modes(u); u["summarize_mode"] = True; save_data()
        await q.message.reply_text(T(uid, "summarize_ask")); return
    if data == "pdf_menu":
        reset_modes(u); u["pdf_mode"] = True; u["pdf_photos"] = []; save_data()
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ انهاء وتحويل", callback_data="pdf_finish")]])
        await q.message.reply_text(T(uid, "pdf_ask"), reply_markup=kb); return
    if data == "pdf_finish":
        if not u.get("pdf_photos"):
            await q.message.reply_text(T(uid, "pdf_no_photos")); return
        await q.message.reply_text(T(uid, "downloading"))
        try:
            images = []
            for file_id in u["pdf_photos"]:
                try:
                    tg_file = await context.bot.get_file(file_id)
                    bio = io.BytesIO()
                    await tg_file.download_to_memory(bio)
                    bio.seek(0)
                    images.append(Image.open(bio).convert("RGB"))
                except Exception as e:
                    print(f"pdf img err: {e}")
                    continue
            if not images:
                await q.message.reply_text(T(uid, "download_failed")); return
            pdf_path = f"/tmp/{uid}_{int(time.time()*1000)}.pdf"
            images[0].save(pdf_path, save_all=True, append_images=images[1:])
            with open(pdf_path, "rb") as f:
                await q.message.reply_document(f, filename="Nezel.pdf", caption=T(uid, "pdf_done"))
            try: os.remove(pdf_path)
            except: pass
            u["pdf_photos"] = []; u["pdf_mode"] = False; save_data()
        except Exception as e:
            print("pdf err: " + str(e))
            await q.message.reply_text(T(uid, "download_failed"))
        return
    if data in ("help_mp3", "help_video", "help"):
        await q.message.reply_text(T(uid, "help_text")); return
    if data == "vip_info":
        if is_vip(uid):
            days = int((float(u.get("vip", 0)) - time.time()) // 86400) + 1
            await q.message.reply_text(f"👑 انت VIP 👑\n\nفاضل في VIP {max(1, days)} يوم\n\n⚡ تحميل اسرع\n🎵 جودة 1080 كاملة\n🚫 من غير اعلانات\n\nشكرا انك معانا ❤️")
        else:
            kb_vip = InlineKeyboardMarkup([[InlineKeyboardButton("📞 كلم الادمن للاشتراك", url="https://t.me/ccccbcv")], [InlineKeyboardButton("⬅️ رجوع", callback_data="home")]])
            await q.message.reply_text(f"👑 VIP - نزل\n\nانت لسه مش VIP\n\n✨ مميزات VIP لمدة شهر:\n⚡ تحميل اسرع من غير انتظار\n🎵 جودة 1080 كاملة\n🚫 من غير اعلانات\n⭐ اولوية في الدعم\n\n💰 السعر: 50 جنيه / شهر\n\n📌 عشان تشترك:\n1- حول 50 جنيه\n2- دوس على زرار كلم الادمن تحت\n3- ابعتله الاي دي ده:\n🆔 {uid}\n\nوهيفعلك VIP في نفس اليوم 👑\n\n🎁 نقطك: {u.get('points', 0)} من 100\n👥 دعواتك: {u.get('invites', 0)} من 50", reply_markup=kb_vip)
        return
    if data == "points_info":
        link = f"https://t.me/{context.bot.username}?start=inv_{uid}"
        await q.message.reply_text(f"🎁 {T(uid, 'points')}: {u.get('points', 0)} / 100\n👥 {T(uid, 'invites')}: {u.get('invites', 0)} / 50\n\n🔗 لينك دعوتك:\n{link}"); return
    if data == "history_info":
        hist = normalize_list(u.get("history", []))
        if not hist:
            await q.message.reply_text(T(uid, "history_empty")); return
        # آخر 10 ب index حقيقي
        start_idx = max(0, len(hist) - 10)
        btns = [[InlineKeyboardButton(f"▶️ {hist[i]['title'][:30]}", callback_data=f"hist_{i}")] for i in range(start_idx, len(hist))]
        btns.append([InlineKeyboardButton("🗑️ مسح السجل", callback_data="hist_clear")])
        btns.append([InlineKeyboardButton(f"⬅️ {T(uid, 'back')}", callback_data="home")])
        await q.message.reply_text(f"📂 {T(uid, 'history_btn')} - دوس على اي واحد عشان تحمله تاني:", reply_markup=InlineKeyboardMarkup(btns)); return
    if data == "hist_clear":
        u["history"] = []; save_data()
        await q.message.reply_text("🗑️ تم مسح السجل"); return
    if data.startswith("hist_"):
        try:
            idx = int(data.replace("hist_", ""))
            hist = normalize_list(u.get("history", []))
            if idx < 0 or idx >= len(hist):
                await q.message.reply_text(T(uid, "download_failed")); return
            url = hist[idx]["url"]
            await q.message.reply_text(T(uid, "downloading"))
            base = "/tmp/" + str(uid) + "_" + str(int(time.time()*1000))
            files = download_with_ytdlp(url, base, want_audio=False, quality=u.get("quality", "720"))
            if files:
                await send_downloaded(q.message, files, False, None)
            else:
                await q.message.reply_text(T(uid, "download_failed"))
        except Exception as e:
            print(f"hist dl err: {e}")
            await q.message.reply_text(T(uid, "download_failed"))
        return
    if data == "fav_info":
        favs = normalize_list(u.get("favs", []))
        if not favs:
            await q.message.reply_text(T(uid, "fav_empty")); return
        start_idx = max(0, len(favs) - 10)
        btns = [[InlineKeyboardButton(f"⭐ {favs[i]['title'][:30]}", callback_data=f"favdl_{i}")] for i in range(start_idx, len(favs))]
        btns.append([InlineKeyboardButton(f"⬅️ {T(uid, 'back')}", callback_data="home")])
        await q.message.reply_text(f"⭐ {T(uid, 'fav_btn')} - دوس عشان تحمل:", reply_markup=InlineKeyboardMarkup(btns)); return
    if data.startswith("favdl_"):
        try:
            idx = int(data.replace("favdl_", ""))
            favs = normalize_list(u.get("favs", []))
            if idx < 0 or idx >= len(favs):
                await q.message.reply_text(T(uid, "download_failed")); return
            url = favs[idx]["url"]
            await q.message.reply_text(T(uid, "downloading"))
            base = "/tmp/" + str(uid) + "_" + str(int(time.time()*1000))
            files = download_with_ytdlp(url, base, want_audio=False, quality=u.get("quality", "720"))
            if files:
                await send_downloaded(q.message, files, False, None)
            else:
                await q.message.reply_text(T(uid, "download_failed"))
        except Exception as e:
            print(f"fav dl err: {e}")
            await q.message.reply_text(T(uid, "download_failed"))
        return
    if data.startswith("favadd_"):
        if u.get("last_link"):
            add_fav(u, u.get("last_link"), u.get("last_link"))
            await q.message.reply_text("⭐ اتضاف للمفضلة")
        return
    if data == "admin_info":
        if int(uid) != ADMIN_ID:
            await q.message.reply_text(T(uid, "help_text")); return
        total = len(DATA["users"])
        vip_count = sum(1 for x in DATA["users"].values() if isinstance(x, dict) and float(x.get("vip", 0) or 0) > time.time())
        kb_admin = InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 تفعيل VIP", callback_data="admin_addvip"), InlineKeyboardButton("❌ الغاء VIP", callback_data="admin_delvip")],
            [InlineKeyboardButton("📊 احصائيات", callback_data="admin_stats")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="home")],
        ])
        await q.message.reply_text(f"👑 لوحة تحكم الادمن\n\n👥 عدد المستخدمين: {total}\n💎 عدد الـ VIP: {vip_count}", reply_markup=kb_admin); return
    if data == "admin_addvip":
        if int(uid) != ADMIN_ID: return
        reset_modes(u); u["state"] = "admin_addvip"; save_data()
        await q.message.reply_text("💎 ابعت الاي دي بتاع المستخدم اللي عايز تفعله VIP"); return
    if data == "admin_delvip":
        if int(uid) != ADMIN_ID: return
        reset_modes(u); u["state"] = "admin_delvip"; save_data()
        await q.message.reply_text("❌ ابعت الاي دي بتاع المستخدم اللي عايز تلغي منه VIP"); return
    if data == "admin_stats":
        if int(uid) != ADMIN_ID: return
        total = len(DATA["users"])
        vip_count = sum(1 for x in DATA["users"].values() if isinstance(x, dict) and float(x.get("vip", 0) or 0) > time.time())
        total_points = 0
        for x in DATA["users"].values():
            if isinstance(x, dict):
                try: total_points += int(x.get("points", 0) or 0)
                except: pass
        await q.message.reply_text(f"📊 احصائيات البوت\n\n👥 المستخدمين: {total}\n💎 VIP: {vip_count}\n🎁 مجموع النقط: {total_points}"); return
    if data == "home":
        await q.message.reply_text(show_main_menu_text(uid, q.from_user.first_name or ""), reply_markup=main_keyboard(uid)); return
    if data == "convert_mp3_last":
        url = u.get("last_link", "")
        if not url:
            await q.message.reply_text(T(uid, "no_link_mp3")); return
        await q.message.reply_text(T(uid, "converting_mp3"))
        base = "/tmp/" + str(uid) + "_" + str(int(time.time()*1000)) + "_mp3"
        files = download_with_ytdlp(url, base, want_audio=True, quality=u.get("quality", "720"))
        if not files:
            await q.message.reply_text(T(uid, "download_failed")); return
        await send_downloaded(q.message, files, True, None); return

async def handle_dl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try: await q.answer()
    except: pass
    uid = q.from_user.id
    u = get_user(uid)
    data = q.data or ""
    if data.startswith("dl_tiktok_"):
        vid = data.replace("dl_tiktok_", "")
        await q.message.reply_text(T(uid, "downloading"))
        url = f"https://www.tiktok.com/@tiktok/video/{vid}"
        base = "/tmp/" + str(uid) + "_" + str(int(time.time()*1000))
        files = download_with_ytdlp(url, base, want_audio=False, quality=u.get("quality", "720"))
        if not files:
            await q.message.reply_text(T(uid, "download_failed")); return
        await send_downloaded(q.message, files, False, None); return
    want_audio = False
    quality = u.get("quality", "720")
    vid = ""
    if data.startswith("dl_audio_"):
        vid = data.replace("dl_audio_", ""); want_audio = True
    elif data.startswith("dl_1080_"):
        vid = data.replace("dl_1080_", ""); quality = "1080"
    elif data.startswith("dl_720_"):
        vid = data.replace("dl_720_", ""); quality = "720"
    elif data.startswith("dl_2k_"):
        vid = data.replace("dl_2k_", ""); quality = "2k"
    elif data.startswith("dl_4k_"):
        vid = data.replace("dl_4k_", ""); quality = "4k"
    elif data.startswith("dl_video_"):
        vid = data.replace("dl_video_", ""); quality = u.get("quality", "720")
    else:
        return
    u["quality"] = quality; save_data()
    await q.message.reply_text(T(uid, "downloading"))
    try:
        base = "/tmp/" + str(uid) + "_" + str(int(time.time()*1000))
        yt_url = "https://www.youtube.com/watch?v=" + vid
        files = download_with_ytdlp(yt_url, base, want_audio=want_audio, quality=quality)
        if not files:
            await q.message.reply_text(T(uid, "download_failed")); return
        await send_downloaded(q.message, files, want_audio, None)
    except Exception as e:
        await q.message.reply_text(f"{T(uid, 'download_failed')}\n{str(e)}")

async def handle_choose_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data or ""
    if data.startswith("pick_tiktok_"):
        vid = data.replace("pick_tiktok_", "")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🎵 {T(uid, 'download_mp3')}", callback_data=f"dl_audio_{vid}")],
            [InlineKeyboardButton(f"📥 {T(uid, 'download_video')} - 720", callback_data=f"dl_tiktok_{vid}")],
            [InlineKeyboardButton(f"⬅️ {T(uid, 'back')}", callback_data="home")],
        ])
        await q.message.reply_text(f"{T(uid, 'choose_format')}", reply_markup=kb); return
    if not data.startswith("pick_"):
        return
    vid = data.replace("pick_", "")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🎵 {T(uid, 'download_mp3')}", callback_data=f"dl_audio_{vid}")],
        [InlineKeyboardButton(f"📥 {T(uid, 'download_video')} - 720", callback_data=f"dl_720_{vid}")],
        [InlineKeyboardButton(f"📥 {T(uid, 'download_video')} - 1080", callback_data=f"dl_1080_{vid}")],
        [InlineKeyboardButton(f"📥 {T(uid, 'download_video')} - 2K", callback_data=f"dl_2k_{vid}")],
        [InlineKeyboardButton(f"📥 {T(uid, 'download_video')} - 4K", callback_data=f"dl_4k_{vid}")],
        [InlineKeyboardButton(f"⬅️ {T(uid, 'back')}", callback_data="home")],
    ])
    await q.message.reply_text(f"{T(uid, 'choose_format')}", reply_markup=kb)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = get_user(uid)
    user = update.effective_user
    # فيديو من الموبايل
    is_video_msg = bool(update.message.video or (update.message.document and update.message.document.mime_type and "video" in update.message.document.mime_type))
    if is_video_msg:
        if u.get("gif_mode") or u.get("compress_mode") or u.get("state") == "extract":
            try:
                await update.message.reply_text("⏳ بحول الفيديو...")
                file_id = update.message.video.file_id if update.message.video else update.message.document.file_id
                f = await context.bot.get_file(file_id)
                ts = int(time.time()*1000)
                in_path = f"/tmp/{uid}_{ts}_in.mp4"
                await f.download_to_drive(in_path)
                if u.get("gif_mode"):
                    out_path = f"/tmp/{uid}_{ts}_out.gif"
                    res = subprocess.run(["ffmpeg", "-y", "-i", in_path, "-vf", "fps=10,scale=480:-1:flags=lanczos", out_path], capture_output=True, timeout=90)
                    if not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
                        await update.message.reply_text("الـ ffmpeg مش شغال على السيرفر، جرب تاني او كلم الادمن")
                    else:
                        with open(out_path, "rb") as ff:
                            await update.message.reply_document(ff, filename="Nezel.gif")
                        try: os.remove(out_path)
                        except: pass
                elif u.get("compress_mode"):
                    out_path = f"/tmp/{uid}_{ts}_out.mp4"
                    ok, msg = compress_video_file(in_path, out_path, crf=28)
                    if not ok:
                        ok2, msg2 = compress_video_file(in_path, out_path, crf=32)
                        if not ok2:
                            await update.message.reply_text(f"الضغط فشل: {msg2} - اتأكد ان ffmpeg متثبت على السيرفر")
                        else:
                            ok = True
                    if ok:
                        with open(out_path, "rb") as ff:
                            await update.message.reply_video(ff, caption="🗜️ تم ضغط الفيديو")
                        try: os.remove(out_path)
                        except: pass
                else:
                    out_path = f"/tmp/{uid}_{ts}_out.mp3"
                    res = subprocess.run(["ffmpeg", "-y", "-i", in_path, "-vn", "-ab", "192k", out_path], capture_output=True, timeout=90)
                    if not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
                        await update.message.reply_text("استخراج الصوت فشل")
                    else:
                        with open(out_path, "rb") as ff:
                            await update.message.reply_audio(ff, title="Nezel Audio")
                        try: os.remove(out_path)
                        except: pass
                try: os.remove(in_path)
                except: pass
                reset_modes(u); save_data()
                return
            except Exception as e:
                await update.message.reply_text(f"فشل: {e}")
                reset_modes(u); save_data()
                return
        else:
            await update.message.reply_text(f"🎬 {T(uid, 'choose_video_action')}\n\nدوس على زرار GIF او ضغط او استخراج صوت من القايمة، وبعدين ابعت الفيديو تاني", reply_markup=main_keyboard(uid))
            return
    # صورة - مع كابشن فيه لينك
    if update.message.photo:
        caption = (update.message.caption or "").strip()
        cap_url = extract_url(caption)
        if cap_url and not u.get("pdf_mode"):
            text = caption
        elif u.get("pdf_mode"):
            file_id = update.message.photo[-1].file_id
            u["pdf_photos"].append(file_id)
            save_data()
            await update.message.reply_text(f"{T(uid, 'pdf_added')} {len(u['pdf_photos'])} ✅")
            return
        else:
            return
        # لو الصورة معاها كابشن لينك، كمل لتحت كأنها رسالة لينك
        if not cap_url:
            return
    else:
        text = (update.message.text or update.message.caption or "").strip()
    if not text:
        return
    if not u.get("lang"):
        await update.message.reply_text("اختر لغتك\n\nChoose your language", reply_markup=lang_keyboard())
        return
    if u.get("state") == "admin_addvip" and int(uid) == ADMIN_ID:
        target = text.strip()
        if not target.isdigit():
            await update.message.reply_text("ابعت اي دي ارقام بس"); return
        tu = get_user(target)
        tu["vip"] = time.time() + 30 * 86400
        u["state"] = "home"; save_data()
        await update.message.reply_text(f"✅ تم تفعيل VIP للمستخدم {target} لمدة 30 يوم")
        try: await context.bot.send_message(chat_id=int(target), text=T(int(target), "vip_congrats"))
        except: pass
        await update.message.reply_text(show_main_menu_text(uid, user.first_name or ""), reply_markup=main_keyboard(uid))
        return
    if u.get("state") == "admin_delvip" and int(uid) == ADMIN_ID:
        target = text.strip()
        if not target.isdigit():
            await update.message.reply_text("ابعت اي دي ارقام بس"); return
        tu = get_user(target)
        tu["vip"] = 0
        u["state"] = "home"; save_data()
        await update.message.reply_text(f"❌ تم الغاء VIP من المستخدم {target}")
        await update.message.reply_text(show_main_menu_text(uid, user.first_name or ""), reply_markup=main_keyboard(uid))
        return
    if u.get("support_mode") or u.get("state") == "support":
        u["support_mode"] = False; u["state"] = "home"; save_data()
        await update.message.reply_text(f"✅ {T(uid, 'support_sent')}")
        if ADMIN_ID != 0:
            try:
                name = user.first_name or ""
                username = user.username
                username_link = f'<a href="https://t.me/{username}">@{username}</a>' if username else "مفيش يوزر"
                msg_text = (f"📩 <b>رسالة دعم جديدة</b>\n━━━━━━━━━━━━━━\n👤 الاسم: <a href=\"tg://user?id={uid}\">{html.escape(name)}</a>\n🆔 الاي دي: <a href=\"tg://user?id={uid}\">{uid}</a>\n🔗 يوزر: {username_link}\n━━━━━━━━━━━━━━\n💬 الرسالة:\n{html.escape(text)}\n━━━━━━━━━━━━━━\nللرد اكتب:\n<code>/reply {uid} رسالتك</code>")
                await context.bot.send_message(chat_id=ADMIN_ID, text=msg_text, parse_mode=ParseMode.HTML)
            except Exception as e:
                print("Support forward failed: " + str(e))
        await update.message.reply_text(show_main_menu_text(uid, user.first_name or ""), reply_markup=main_keyboard(uid))
        return
    if u.get("translate_mode"):
        u["translate_mode"] = False; u["state"] = "home"; save_data()
        has_ar = any('\u0600' <= c <= '\u06FF' for c in text)
        target = "en" if has_ar else "ar"
        tr = translate_text(text, target)
        await update.message.reply_text(f"🌐 {T(uid, 'translate_done')}:\n{tr}")
        await update.message.reply_text(show_main_menu_text(uid, user.first_name or ""), reply_markup=main_keyboard(uid))
        return
    if u.get("summarize_mode"):
        u["summarize_mode"] = False; u["state"] = "home"; save_data()
        summ = summarize_text(text)
        await update.message.reply_text(f"📝 {T(uid, 'summarize_done')}:\n{summ}")
        await update.message.reply_text(show_main_menu_text(uid, user.first_name or ""), reply_markup=main_keyboard(uid))
        return
    if u.get("state") == "story" or u.get("story_mode"):
        reset_modes(u); save_data()
        url = extract_url(text)
        if url and "instagram.com" in url:
            await update.message.reply_text("📸 بحمل الستوري...")
            base = "/tmp/" + str(uid) + "_" + str(int(time.time()*1000))
            files = download_with_ytdlp(url, base, want_audio=False, quality=u.get("quality", "720"))
            if files:
                await send_downloaded(update.message, files, False, None)
            else:
                await update.message.reply_text("مش عارف اجيب الستوري، انستا قافل الستوري من غير تسجيل دخول، ابعت لينك ريل او بوست بدل الستوري")
        else:
            await update.message.reply_text("📸 ابعت لينك الستوري مش اليوزر، انسخ لينك الستوري من انستا وابعته هنا")
        return
    if u.get("state") == "movies" or u.get("movie_mode"):
        reset_modes(u); save_data()
        await update.message.reply_text("🎬 بدور...")
        res = search_movies(text)
        if not res:
            await update.message.reply_text(T(uid, "not_found")); return
        out = "🎬 لقيت دول:\n\n"
        for r in res:
            out += f"🎬 {r['name']}\n{r['summary'][:150]}\n{r['url']}\n\n"
        await update.message.reply_text(out); return
    if u.get("state") == "wallpaper" or u.get("wallpaper_mode"):
        reset_modes(u); save_data()
        await update.message.reply_text("🖼️ بجيبلك خلفيات...")
        walls = get_wallpapers(text)
        for w in walls[:3]:
            try: await update.message.reply_photo(w, caption="🖼️ خلفية HD من نزل")
            except Exception as e: print(f"wall send err: {e}")
        return
    if u.get("state") == "search":
        u["state"] = "home"; save_data()
        msg = await update.message.reply_text(f"🔍 {T(uid, 'searching')}: {text}\n{T(uid, 'search_wait')}...")
        results = do_search(text)
        if not results:
            await msg.edit_text(T(uid, "not_found")); return
        buttons = []
        for r in results:
            title = r["title"]
            if len(title) > 35: title = title[:35] + "..."
            buttons.append([InlineKeyboardButton(f"🎵 {title}", callback_data=f"pick_{r['id']}")])
        buttons.append([InlineKeyboardButton(f"⬅️ {T(uid, 'back')}", callback_data="home")])
        await msg.edit_text(f"{T(uid, 'choose_result')}:", reply_markup=InlineKeyboardMarkup(buttons))
        return
    url = extract_url(text)
    if url and any(x in url for x in ["youtube.com", "youtu.be", "tiktok.com", "instagram.com", "facebook.com", "fb.watch"]):
        u["last_link"] = url
        save_history(u, url, url)
        await update.message.reply_text(T(uid, "downloading"))
        try:
            base = "/tmp/" + str(uid) + "_" + str(int(time.time()*1000))
            files = download_with_ytdlp(url, base, want_audio=False, quality=u.get("quality", "720"))
            if files:
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"🎵 {T(uid, 'download_mp3')}", callback_data="convert_mp3_last")],
                    [InlineKeyboardButton("⭐ اضافة للمفضلة", callback_data="favadd_")],
                ])
                await send_downloaded(update.message, files, False, kb)
            else:
                await update.message.reply_text(T(uid, "download_failed"))
        except Exception as e:
            await update.message.reply_text(f"{T(uid, 'download_failed')}\n{str(e)}")
        return
    await update.message.reply_text(show_main_menu_text(uid, user.first_name or ""), reply_markup=main_keyboard(uid))

def main():
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN missing"); return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("vip", vip_cmd))
    app.add_handler(CommandHandler("reply", reply_cmd))
    app.add_handler(CallbackQueryHandler(handle_dl, pattern="^dl_"))
    app.add_handler(CallbackQueryHandler(handle_choose_result, pattern="^pick_"))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_message))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_message))
    app.add_handler(MessageHandler(filters.CAPTION, handle_message))
    print("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
