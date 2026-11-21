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
import asyncio
from datetime import date
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
BACKUP_FILE = "users_backup.json"
URL_RE = re.compile(r'https?://[^\s<>"]+')
MAX_TG_SIZE = 49 * 1024 * 1024
DOWNLOAD_SEM = asyncio.Semaphore(2)
CANCEL_FLAGS = {}
ACTIVE_MSGS = {}

def extract_url(text):
    m = URL_RE.search(text or "")
    return m.group(0).rstrip(").,") if m else ""

def platform_of(url):
    u = (url or "").lower()
    if "tiktok.com" in u or "vt.tiktok" in u: return "tiktok"
    if "instagram.com" in u: return "instagram"
    if "facebook.com" in u or "fb.watch" in u: return "facebook"
    if "youtube.com" in u or "youtu.be" in u: return "youtube"
    return "other"

def load_data():
    for path in [DATA_FILE, BACKUP_FILE]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    if isinstance(d, dict) and "users" in d:
                        if "stats" not in d: d["stats"] = {"total": 0, "by_platform": {}, "today": str(date.today()), "today_count": 0}
                        if "banned" not in d: d["banned"] = []
                        return d
            except Exception as e:
                print(f"load {path} err: {e}")
    return {"users": {}, "stats": {"total": 0, "by_platform": {}, "today": str(date.today()), "today_count": 0}, "banned": []}

def save_data():
    try:
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(DATA, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_FILE)
        shutil.copyfile(DATA_FILE, BACKUP_FILE)
    except Exception as e:
        print("save failed: " + str(e))

DATA = load_data()

DEFAULT_USER = {
    "lang": None, "vip": 0, "state": "home",
    "support_mode": False, "translate_mode": False, "summarize_mode": False, "pdf_mode": False,
    "points": 0, "invites": 0, "invited_by": None, "invited_users": [],
    "last_link": "", "pdf_photos": [], "history": [], "favs": [],
    "quality": "720", "download_mode": "video", "story_mode": False, "movie_mode": False, "wallpaper_mode": False,
    "gif_mode": False, "compress_mode": False, "banned": False, "last_dl_at": 0,
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
    return u

def is_banned(uid):
    return str(uid) in DATA.get("banned", []) or bool(get_user(uid).get("banned"))

def reset_modes(u):
    u["support_mode"] = False; u["translate_mode"] = False; u["summarize_mode"] = False; u["pdf_mode"] = False
    u["story_mode"] = False; u["movie_mode"] = False; u["wallpaper_mode"] = False
    u["gif_mode"] = False; u["compress_mode"] = False; u["state"] = "home"

def is_vip(uid):
    try: return float(get_user(uid).get("vip", 0)) > time.time()
    except: return False

def bump_stats(platform):
    s = DATA.get("stats", {})
    today = str(date.today())
    if s.get("today") != today:
        s["today"] = today; s["today_count"] = 0
    s["total"] = int(s.get("total", 0)) + 1
    s["today_count"] = int(s.get("today_count", 0)) + 1
    bp = s.get("by_platform", {})
    bp[platform] = int(bp.get(platform, 0)) + 1
    s["by_platform"] = bp
    DATA["stats"] = s
    save_data()

def cleanup_tmp():
    try:
        now = time.time()
        for f in glob.glob("/tmp/*"):
            try:
                if now - os.path.getmtime(f) > 3600:
                    os.remove(f)
            except: pass
    except: pass

def translate_text(text, target="en"):
    text = (text or "").strip()
    if not text: return text
    has_ar = any('\u0600' <= c <= '\u06FF' for c in text)
    if target == "en" and not has_ar: return text
    if target == "ar" and has_ar: return text
    try:
        sl = "ar" if target == "en" else "en"
        r = requests.get("https://translate.googleapis.com/translate_a/single", params={"client": "gtx", "sl": sl, "tl": target, "dt": "t", "q": text}, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            data = r.json()
            out = "".join([x[0] for x in data[0] if x and x[0]])
            if out and out.strip().lower() != text.strip().lower(): return out
    except Exception as e: print("google tr err: " + str(e))
    try:
        pair = "ar|en" if target == "en" else "en|ar"
        r = requests.get("https://api.mymemory.translated.net/get", params={"q": text[:500], "langpair": pair}, timeout=10)
        if r.status_code == 200:
            tr = r.json().get("responseData", {}).get("translatedText", "")
            if tr and tr.lower() != text.lower(): return tr
    except Exception as e: print("mymemory err: " + str(e))
    return text

def summarize_text(text):
    text = (text or "").strip()
    if len(text) < 200: return text
    sentences = re.split(r'[.!؟\n]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    if len(sentences) <= 3: return text
    picked = [sentences[0]]
    for s in sorted(sentences, key=len, reverse=True)[:2]:
        if s not in picked: picked.append(s)
    if sentences[-1] not in picked: picked.append(sentences[-1])
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
        "translate_ask": "ابعت النص اللي عايز تترجمه", "translate_done": "الترجمة",
        "summarize_ask": "ابعت النص اللي عايز تلخصه", "summarize_done": "التلخيص",
        "pdf_ask": "ابعت الصور وانا هحولها PDF، ولما تخلص دوس انهاء", "pdf_done": "تم تحويل الصور لـ PDF", "pdf_added": "تم اضافة الصورة", "pdf_no_photos": "ابعت صور الاول",
        "converting_mp3": "بحولها اغنية دلوقتي، استنى", "no_link_mp3": "ابعت لينك الفيديو الاول", "history_empty": "سجلك فاضي لسه", "fav_empty": "مفضلتك فاضية لسه",
        "no_wm_btn": "بدون علامة مائية", "playlist_btn": "تحميل قايمة تشغيل", "story_btn": "ستوري انستا", "gif_btn": "فيديو لـ GIF",
        "compress_btn": "ضغط فيديو", "extract_btn": "استخراج صوت من فيديو", "movies_btn": "افلام ومسلسلات", "wallpaper_btn": "خلفيات HD",
        "explore_btn": "اكسبلور ترند", "choose_quality": "اختار الجودة", "quality_set": "تمام، الجودة بقت",
        "choose_video_action": "ابعت فيديو واختار هتعمل بيه ايه:", "send_video_first": "ابعت فيديو من موبايلك الاول",
        "cancel": "❌ إلغاء", "cancelled": "تم الإلغاء ✅", "too_big": "الفيديو كبير جدا (اكتر من 49 ميجا) حتى بعد الضغط، جرب جودة اقل",
        "rate_limit": "استنى ثواني قبل ما تبعت لينك تاني ⏳", "banned_msg": "انت محظور من البوت 🚫",
        "queue_wait": "في تحميلات قبلك، انت في الطابور...",
    },
    "en": {
        "choose_lang_title": "Choose your language", "welcome": "Welcome to Nezel", "welcome_sub": "Download videos and audios from all platforms",
        "points": "Points", "invites": "Invites", "vip_left": "VIP left", "vip_days": "days", "not_vip": "You are not VIP",
        "send_link": "Send link now", "search_btn": "Search by name", "download_mp3": "Download MP3", "download_video": "Download Video",
        "quality_720": "Quality 720", "quality_1080": "Quality 1080", "quality_2k": "Quality 2K", "quality_4k": "Quality 4K",
        "pdf_btn": "Images to PDF", "fav_btn": "My Favorites", "history_btn": "My History", "points_btn": "My Points", "vip_btn": "VIP",
        "lang_btn": "Language", "support_btn": "Support", "admin_btn": "Admin Panel", "translate_btn": "Translate", "summarize_btn": "Summarize",
        "search_prompt": "Type the song or video name you want", "searching": "Searching for", "search_wait": "Please wait",
        "not_found": "Nothing found", "choose_result": "Choose from results", "choose_format": "Choose format",
        "downloading": "Downloading now, please wait", "download_done": "Download done", "download_failed": "Download failed, try again",
        "support_prompt": "Write your message to support", "support_sent": "Your message sent to support", "support_reply_title": "Support reply",
        "help_text": "Send a link from YouTube, TikTok, Instagram or Facebook", "lang_changed": "Language changed",
        "vip_done": "You are now VIP for 30 days", "vip_congrats": "Congrats, you are VIP", "back": "Back", "home": "Main Menu",
        "translate_ask": "Send text to translate", "translate_done": "Translation",
        "summarize_ask": "Send text to summarize", "summarize_done": "Summary",
        "pdf_ask": "Send photos and I will make PDF", "pdf_done": "PDF created", "pdf_added": "Photo added", "pdf_no_photos": "Send photos first",
        "converting_mp3": "Converting to MP3, wait", "no_link_mp3": "Send video link first", "history_empty": "Your history is empty", "fav_empty": "Your favorites is empty",
        "no_wm_btn": "No Watermark", "playlist_btn": "Playlist Download", "story_btn": "Insta Story", "gif_btn": "Video to GIF",
        "compress_btn": "Compress Video", "extract_btn": "Extract Audio", "movies_btn": "Movies & Series", "wallpaper_btn": "HD Wallpapers",
        "explore_btn": "Trending Explore", "choose_quality": "Choose quality", "quality_set": "Quality set to",
        "choose_video_action": "Send a video and choose:", "send_video_first": "Send a video first",
        "cancel": "❌ Cancel", "cancelled": "Cancelled ✅", "too_big": "Video is too big even after compression, try lower quality",
        "rate_limit": "Wait a few seconds before sending another link ⏳", "banned_msg": "You are banned 🚫",
        "queue_wait": "There are downloads before you, you are in queue...",
    }
}

def T(uid, key):
    u = get_user(uid)
    lang = u.get("lang") or "ar"
    if lang not in TEXTS: lang = "ar"
    return TEXTS[lang].get(key, key)

def lang_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("العربية 🇪🇬", callback_data="set_lang_ar")],[InlineKeyboardButton("English 🇬🇧", callback_data="set_lang_en")]])

def quality_keyboard(uid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 720", callback_data="set_q_720"), InlineKeyboardButton("🎬 1080", callback_data="set_q_1080")],
        [InlineKeyboardButton("🎬 2K", callback_data="set_q_2k"), InlineKeyboardButton("🎬 4K", callback_data="set_q_4k")],
        [InlineKeyboardButton(f"⬅️ {T(uid, 'back')}", callback_data="home")],
    ])

def cancel_keyboard(uid):
    return InlineKeyboardMarkup([[InlineKeyboardButton(T(uid, "cancel"), callback_data=f"cancel_{uid}")]])

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
    points = u.get("points", 0); invites = u.get("invites", 0)
    if is_vip(uid):
        days = int((float(u.get("vip", 0)) - time.time()) // 86400) + 1
        vip_line = f"👑 {T(uid, 'vip_left')} {max(1, days)} {T(uid, 'vip_days')}"
    else:
        vip_line = f"👑 {T(uid, 'not_vip')}"
    return "\n".join([f"✨ {T(uid, 'welcome')} {name} 👑", "", T(uid, 'welcome_sub'), "────────────────", f"🎁 {T(uid, 'points')}: {points} / 100", f"👥 {T(uid, 'invites')}: {invites} / 50", vip_line, f"🎬 الجودة الحالية: {u.get('quality','720')}", "────────────────", f"👇 {T(uid, 'send_link')}"])

def compress_video_file(in_path, out_path, crf=28):
    if not shutil.which("ffmpeg"): return False, "ffmpeg not found"
    cmd = ["ffmpeg", "-y", "-i", in_path, "-vcodec", "libx264", "-crf", str(crf), "-preset", "veryfast", "-acodec", "aac", "-b:a", "128k", "-movflags", "+faststart", out_path]
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=180)
        if res.returncode != 0: return False, "ffmpeg failed"
        if not os.path.exists(out_path) or os.path.getsize(out_path) < 1000: return False, "output too small"
        return True, "ok"
    except Exception as e: return False, str(e)

async def ensure_size_ok(path, uid):
    try:
        if not path or not os.path.exists(path): return None
        if os.path.getsize(path) <= MAX_TG_SIZE: return path
        if not path.endswith(".mp4"): return None
        for crf in [30, 34, 38]:
            out = path.replace(".mp4", f"_c{crf}.mp4")
            ok, _ = compress_video_file(path, out, crf=crf)
            if ok and os.path.getsize(out) <= MAX_TG_SIZE:
                try: os.remove(path)
                except: pass
                return out
            try:
                if os.path.exists(out): os.remove(out)
            except: pass
        return None
    except: return None

def save_history(u, url, title=""):
    url = (url or "").strip()
    if not url: return
    hist = normalize_list(u.get("history", []))
    hist = [x for x in hist if x["url"] != url]
    hist.append({"url": url, "title": (title or url)[:80], "time": int(time.time())})
    u["history"] = hist[-30:]; save_data()

def add_fav(u, url, title=""):
    url = (url or "").strip()
    if not url: return
    favs = normalize_list(u.get("favs", []))
    favs = [x for x in favs if x["url"] != url]
    favs.append({"url": url, "title": (title or url)[:80], "time": int(time.time())})
    u["favs"] = favs[-30:]; save_data()

def search_movies(query):
    results = []
    try:
        r = requests.get("https://api.tvmaze.com/search/shows", params={"q": query}, timeout=15)
        if r.status_code == 200 and r.json():
            for item in r.json()[:5]:
                s = item.get("show", {})
                summary = re.sub(r'<[^>]+>', '', s.get("summary", "") or "")[:180]
                results.append({"name": s.get("name", ""), "summary": summary or f"{s.get('premiered','')} - {s.get('status','')}", "url": s.get("url", "")})
            if results: return results
    except Exception as e: print(f"tvmaze err: {e}")
    try:
        r = requests.get("https://ar.wikipedia.org/w/api.php", params={"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": 5}, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            for item in r.json().get("query", {}).get("search", [])[:5]:
                title = item.get("title", "")
                snippet = re.sub(r'<[^>]+>', '', item.get("snippet", "") or "")[:180]
                results.append({"name": title, "summary": snippet, "url": f"https://ar.wikipedia.org/wiki/{title.replace(' ', '_')}"})
            if results: return results
    except Exception as e: print(f"wiki err: {e}")
    return results

def get_wallpapers(query="nature"):
    try:
        r = requests.get("https://picsum.photos/v2/list", params={"page": 1, "limit": 5}, timeout=15)
        if r.status_code == 200: return [f"https://picsum.photos/id/{x['id']}/1080/1920" for x in r.json()]
    except Exception as e: print(f"wallpaper err: {e}")
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
            if vid: res.append({"id": str(vid), "title": title[:50], "author": author, "url": f"https://www.tiktok.com/@{author}/video/{vid}"})
        if res: return res
    except Exception as e: print(f"trend err: {e}")
    return []

def do_search(query):
    try:
        opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True, "socket_timeout": 30}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch5:{query}", download=False)
            entries = info.get("entries", []) if info else []
            results = []
            for e in entries:
                if not e: continue
                vid = e.get("id", ""); title = e.get("title", query)
                if vid and len(vid) == 11: results.append({"id": vid, "title": title})
            if results: return results
    except Exception as e: print("ytsearch failed: " + str(e))
    return []

def format_for_quality(quality="720", want_audio=False):
    if want_audio: return "bestaudio/best"
    q = str(quality).lower()
    h = {"720": 720, "1080": 1080, "2k": 1440, "4k": 2160}.get(q, 720)
    return f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"

def get_tiktok_id_from_url(url):
    try:
        r = requests.get(url, allow_redirects=True, timeout=15, headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"})
        final = r.url
        m = re.search(r'/video/(\d+)', final)
        if m: return m.group(1), final
        return None, final
    except Exception:
        return None, url

def download_tiktok_via_api(url, base, want_audio=False):
    try:
        vid, final_url = get_tiktok_id_from_url(url)
        for try_url in [url, final_url]:
            if not try_url: continue
            r = requests.get("https://www.tikwm.com/api/", params={"url": try_url, "hd": 1}, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200: continue
            data = r.json().get("data", {})
            if not data: continue
            if want_audio:
                audio_url = None
                if isinstance(data.get("music_info"), dict):
                    audio_url = data["music_info"].get("play")
                if not audio_url:
                    audio_url = data.get("music")
                if audio_url:
                    ar = requests.get(audio_url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
                    if ar.status_code == 200 and len(ar.content) > 5000:
                        out = base + ".mp3"
                        with open(out, "wb") as f: f.write(ar.content)
                        return [out], data.get("cover")
                continue
            video_url = data.get("play") or data.get("wmplay") or data.get("hdplay")
            if not video_url: continue
            vr = requests.get(video_url, timeout=60, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.tiktok.com/"})
            if vr.status_code == 200 and len(vr.content) > 10000:
                out = base + ".mp4"
                with open(out, "wb") as f: f.write(vr.content)
                thumb = data.get("cover") or data.get("origin_cover")
                return [out], thumb
        return [], None
    except Exception as e:
        print("tikwm err: " + str(e))
        return [], None

def download_with_ytdlp(url, base, want_audio=False, quality="720", progress_cb=None):
    plat = platform_of(url)
    if plat == "tiktok":
        files, thumb = download_tiktok_via_api(url, base, want_audio=want_audio)
        if files:
            return files, thumb
        print("tikwm failed, fallback to yt-dlp")
    try:
        for f in glob.glob(base + ".*"):
            try: os.remove(f)
            except: pass
        fmt = format_for_quality(quality, want_audio)
        def hook(d):
            if progress_cb and d.get("status") == "downloading":
                try:
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    dl = d.get("downloaded_bytes", 0)
                    if total > 0:
                        pct = int(dl * 100 / total)
                        progress_cb(pct)
                except: pass
        opts = {
            "format": fmt, "outtmpl": base + ".%(ext)s",
            "quiet": True, "no_warnings": True, "nocheckcertificate": True,
            "socket_timeout": 90, "retries": 3, "noplaylist": True,
            "progress_hooks": [hook] if progress_cb else [],
            "http_headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
        }
        if want_audio:
            opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            thumb = info.get("thumbnail") if isinstance(info, dict) else None
        files = [f for f in glob.glob(base + ".*") if not f.endswith(".part")]
        if not files and plat == "tiktok":
            return download_tiktok_via_api(url, base, want_audio=want_audio)
        return files, thumb
    except Exception as e:
        print("download failed: " + str(e))
        if plat == "tiktok":
            return download_tiktok_via_api(url, base, want_audio=want_audio)
        return [], None

def download_playlist(url, uid, quality="720"):
    try:
        opts = {"quiet": True, "extract_flat": True, "skip_download": True, "socket_timeout": 30}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            entries = info.get("entries", []) if info else []
            urls = []
            for e in entries[:5]:
                if not e: continue
                vid = e.get("id") or e.get("url")
                if vid:
                    if "youtube" in url: urls.append(f"https://www.youtube.com/watch?v={vid}")
                    else: urls.append(e.get("webpage_url") or vid)
            return urls
    except Exception as e:
        print(f"playlist err: {e}")
        return []

async def send_downloaded(msg_obj, files, want_audio, kb, thumb_url=None):
    try:
        thumb_path = None
        if thumb_url:
            try:
                r = requests.get(thumb_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code == 200 and len(r.content) > 1000:
                    thumb_path = f"/tmp/thumb_{int(time.time()*1000)}.jpg"
                    with open(thumb_path, "wb") as f: f.write(r.content)
            except: pass
        for fp in files:
            if not fp or not os.path.exists(fp): continue
            if fp.endswith((".jpg", ".jpeg", ".png", ".webp")):
                with open(fp, "rb") as f: await msg_obj.reply_photo(f)
            else:
                with open(fp, "rb") as f:
                    if want_audio: await msg_obj.reply_audio(f, reply_markup=kb)
                    else:
                        try:
                            if thumb_path and os.path.exists(thumb_path):
                                await msg_obj.reply_video(f, reply_markup=kb, thumbnail=open(thumb_path, "rb"))
                            else:
                                await msg_obj.reply_video(f, reply_markup=kb)
                        except:
                            with open(fp, "rb") as f2: await msg_obj.reply_video(f2, reply_markup=kb)
            try: os.remove(fp)
            except: pass
        if thumb_path:
            try: os.remove(thumb_path)
            except: pass
        return True
    except Exception as e:
        print(f"send err: {e}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_banned(uid):
        await update.message.reply_text(T(uid, "banned_msg")); return
    u = get_user(uid)
    if context.args and context.args[0].startswith("inv_"):
        inviter = context.args[0].replace("inv_", "")
        if inviter != str(uid) and not u.get("invited_by") and inviter.isdigit():
            u["invited_by"] = inviter
            inv = get_user(int(inviter))
            if str(uid) not in inv.get("invited_users", []):
                inv["invited_users"].append(str(uid))
                inv["points"] = int(inv.get("points", 0)) + 5
                inv["invites"] = int(inv.get("invites", 0)) + 1
                save_data()
                try: await context.bot.send_message(chat_id=int(inviter), text="🎉 حد دخل من لينكك! +5 نقاط")
                except: pass
    reset_modes(u); save_data()
    await update.message.reply_text("اختر لغتك\n\nChoose your language", reply_markup=lang_keyboard())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📖 أوامر البوت:\n\n/start - القايمة الرئيسية\n/help - المساعدة\n/stats - إحصائياتك\n/vip 123 - تفعيل VIP (أدمن)\n/reply 123 رسالة - رد على دعم (أدمن)\n/broadcast رسالة - رسالة للكل (أدمن)\n/ban 123 - حظر (أدمن)\n/unban 123 - فك حظر (أدمن)\n\nابعت لينك من تيك توك / انستا / فيس / يوتيوب وهيتحمل على طول")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    s = DATA.get("stats", {})
    bp = s.get("by_platform", {})
    lines = "\n".join([f"{k}: {v}" for k, v in bp.items()]) if bp else "لسه مفيش تحميلات"
    await update.message.reply_text(f"📊 إحصائيات البوت:\n\n👥 المستخدمين: {len(DATA['users'])}\n📥 تحميل كلي: {s.get('total',0)}\n📥 النهاردة: {s.get('today_count',0)}\n\n🎬 بالمنصة:\n{lines}")

async def vip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args: await update.message.reply_text("Use: /vip 123456"); return
    if uid != ADMIN_ID and ADMIN_ID != 0: await update.message.reply_text("Not allowed"); return
    try:
        target = str(context.args[0]).strip()
        if not target.isdigit(): await update.message.reply_text("ID must be numbers"); return
        tu = get_user(target); tu["vip"] = time.time() + 30 * 86400; save_data()
        await update.message.reply_text(T(uid, "vip_done"))
        try: await context.bot.send_message(chat_id=int(target), text=T(int(target), "vip_congrats"))
        except: pass
    except Exception as e: await update.message.reply_text("Error: " + str(e))

async def reply_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_ID or ADMIN_ID == 0: return
    if len(context.args) < 2: await update.message.reply_text("Use: /reply 123456 your message"); return
    target = context.args[0]
    if not target.isdigit(): await update.message.reply_text("ID wrong"); return
    msg = " ".join(context.args[1:])
    try:
        await context.bot.send_message(chat_id=int(target), text=f"{T(int(target), 'support_reply_title')}\n\n{msg}")
        await update.message.reply_text("Sent")
    except Exception as e: await update.message.reply_text("Error: " + str(e))

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_ID or ADMIN_ID == 0: return
    if not context.args: await update.message.reply_text("Use: /broadcast your message"); return
    msg = " ".join(context.args)
    sent = 0; failed = 0
    await update.message.reply_text(f"📣 ببعت لـ {len(DATA['users'])} واحد...")
    for tid in list(DATA["users"].keys()):
        if str(tid) in DATA.get("banned", []): continue
        try:
            await context.bot.send_message(chat_id=int(tid), text=f"📣 رسالة من الأدمن:\n\n{msg}")
            sent += 1; await asyncio.sleep(0.05)
        except: failed += 1
    await update.message.reply_text(f"✅ اتبعت لـ {sent}، فشل {failed}")

async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_ID or ADMIN_ID == 0: return
    if not context.args: await update.message.reply_text("Use: /ban 123"); return
    target = str(context.args[0]).strip()
    if target not in DATA.get("banned", []): DATA["banned"].append(target)
    tu = get_user(target); tu["banned"] = True; save_data()
    await update.message.reply_text(f"🚫 تم حظر {target}")

async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_ID or ADMIN_ID == 0: return
    if not context.args: await update.message.reply_text("Use: /unban 123"); return
    target = str(context.args[0]).strip()
    if target in DATA.get("banned", []): DATA["banned"].remove(target)
    tu = get_user(target); tu["banned"] = False; save_data()
    await update.message.reply_text(f"✅ تم فك حظر {target}")

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if is_banned(uid): await q.message.reply_text(T(uid, "banned_msg")); return
    u = get_user(uid)
    data = q.data or ""
    if data.startswith("cancel_"):
        target = data.replace("cancel_", "")
        CANCEL_FLAGS[target] = True
        await q.message.reply_text(T(uid, "cancelled")); return
    if data == "set_lang_ar":
        u["lang"] = "ar"; reset_modes(u); save_data()
        await q.message.reply_text(T(uid, "lang_changed"))
        await q.message.reply_text(show_main_menu_text(uid, q.from_user.first_name or ""), reply_markup=main_keyboard(uid)); return
    if data == "set_lang_en":
        u["lang"] = "en"; reset_modes(u); save_data()
        await q.message.reply_text(T(uid, "lang_changed"))
        await q.message.reply_text(show_main_menu_text(uid, q.from_user.first_name or ""), reply_markup=main_keyboard(uid)); return
    if not u.get("lang"):
        await q.message.reply_text("اختر لغتك\n\nChoose your language", reply_markup=lang_keyboard()); return
    if data.startswith("set_q_"):
        qq = data.replace("set_q_", "").lower(); u["quality"] = qq; save_data()
        await q.message.reply_text(f"✅ {T(uid, 'quality_set')} {qq}\n\nابعت لينك دلوقتي وهيتحمل بالجودة دي"); return
    if data == "mode_mp3": reset_modes(u); u["download_mode"] = "audio"; save_data(); await q.message.reply_text("🎵 تمام، ابعت اللينك وهحوله MP3 على طول"); return
    if data == "mode_video": reset_modes(u); u["download_mode"] = "video"; save_data(); await q.message.reply_text(f"📥 تمام، اختار الجودة:", reply_markup=quality_keyboard(uid)); return
    if data == "mode_nowm": reset_modes(u); u["download_mode"] = "nowm"; save_data(); await q.message.reply_text("✨ تمام، ابعت لينك تيك توك وهجيبهولك من غير علامة مائية"); return
    if data == "mode_playlist": reset_modes(u); u["download_mode"] = "playlist"; save_data(); await q.message.reply_text("📃 ابعت لينك قايمة التشغيل، هجيب أول 5 فيديوهات"); return
    if data == "mode_story": reset_modes(u); u["story_mode"] = True; u["state"] = "story"; save_data(); await q.message.reply_text("📸 ابعت لينك الستوري من انستا على طول"); return
    if data == "mode_explore":
        await q.message.reply_text("🔥 بدور على الترند...")
        trends = get_trending()
        if not trends: await q.message.reply_text(T(uid, "not_found")); return
        btns = [[InlineKeyboardButton(f"🎵 {t['title'][:35]}", callback_data=f"pick_tiktok_{t['id']}")] for t in trends]
        btns.append([InlineKeyboardButton(f"⬅️ {T(uid, 'back')}", callback_data="home")])
        await q.message.reply_text("🔥 ترند تيك توك دلوقتي:", reply_markup=InlineKeyboardMarkup(btns)); return
    if data == "mode_gif": reset_modes(u); u["gif_mode"] = True; save_data(); await q.message.reply_text("🎞️ ابعت فيديو من موبايلك وهحوله GIF"); return
    if data == "mode_compress": reset_modes(u); u["compress_mode"] = True; save_data(); await q.message.reply_text("🗜️ ابعت فيديو من موبايلك وهضغطهولك"); return
    if data == "mode_extract": reset_modes(u); u["state"] = "extract"; save_data(); await q.message.reply_text("🎧 ابعت فيديو من موبايلك وهطلعلك الصوت بتاعه MP3"); return
    if data == "mode_movies": reset_modes(u); u["movie_mode"] = True; u["state"] = "movies"; save_data(); await q.message.reply_text("🎬 اكتب اسم الفيلم او المسلسل"); return
    if data == "mode_wallpaper": reset_modes(u); u["wallpaper_mode"] = True; u["state"] = "wallpaper"; save_data(); await q.message.reply_text("🖼️ اكتب نوع الخلفية: طبيعة، سيارات، انمي..."); return
    if data == "search": reset_modes(u); u["state"] = "search"; save_data(); await q.message.reply_text(f"🔍 {T(uid, 'search_prompt')}"); return
    if data == "lang": await q.message.reply_text("اختر لغتك\n\nChoose your language", reply_markup=lang_keyboard()); return
    if data == "support": reset_modes(u); u["state"] = "support"; u["support_mode"] = True; save_data(); await q.message.reply_text(f"📞 {T(uid, 'support_prompt')}"); return
    if data == "tr_menu": reset_modes(u); u["translate_mode"] = True; save_data(); await q.message.reply_text(T(uid, "translate_ask")); return
    if data == "sum_menu": reset_modes(u); u["summarize_mode"] = True; save_data(); await q.message.reply_text(T(uid, "summarize_ask")); return
    if data == "pdf_menu":
        reset_modes(u); u["pdf_mode"] = True; u["pdf_photos"] = []; save_data()
        await q.message.reply_text(T(uid, "pdf_ask"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ انهاء وتحويل", callback_data="pdf_finish")]])); return
    if data == "pdf_finish":
        if not u.get("pdf_photos"): await q.message.reply_text(T(uid, "pdf_no_photos")); return
        await q.message.reply_text(T(uid, "downloading"))
        try:
            images = []
            for file_id in u["pdf_photos"]:
                try:
                    tg_file = await context.bot.get_file(file_id); bio = io.BytesIO(); await tg_file.download_to_memory(bio); bio.seek(0); images.append(Image.open(bio).convert("RGB"))
                except: continue
            if not images: await q.message.reply_text(T(uid, "download_failed")); return
            pdf_path = f"/tmp/{uid}_{int(time.time()*1000)}.pdf"
            images[0].save(pdf_path, save_all=True, append_images=images[1:])
            with open(pdf_path, "rb") as f: await q.message.reply_document(f, filename="Nezel.pdf", caption=T(uid, "pdf_done"))
            try: os.remove(pdf_path)
            except: pass
            u["pdf_photos"] = []; u["pdf_mode"] = False; save_data()
        except Exception as e: print("pdf err: " + str(e)); await q.message.reply_text(T(uid, "download_failed"))
        return
    if data in ("help_mp3", "help_video", "help"): await q.message.reply_text(T(uid, "help_text")); return
    if data == "vip_info":
        if is_vip(uid):
            days = int((float(u.get("vip", 0)) - time.time()) // 86400) + 1
            await q.message.reply_text(f"👑 انت VIP 👑\n\nفاضل في VIP {max(1, days)} يوم")
        else:
            kb_vip = InlineKeyboardMarkup([[InlineKeyboardButton("📞 كلم الادمن للاشتراك", url="https://t.me/ccccbcv")], [InlineKeyboardButton("⬅️ رجوع", callback_data="home")]])
            await q.message.reply_text(f"👑 VIP - نزل\n\nانت لسه مش VIP\n\n💰 السعر: 50 جنيه / شهر\n\n🆔 {uid}", reply_markup=kb_vip)
        return
    if data == "points_info":
        link = f"https://t.me/{context.bot.username}?start=inv_{uid}"
        await q.message.reply_text(f"🎁 {T(uid, 'points')}: {u.get('points', 0)} / 100\n👥 {T(uid, 'invites')}: {u.get('invites', 0)} / 50\n\n🔗 لينك دعوتك:\n{link}"); return
    if data == "history_info":
        hist = normalize_list(u.get("history", []))
        if not hist: await q.message.reply_text(T(uid, "history_empty")); return
        start_idx = max(0, len(hist) - 10)
        btns = [[InlineKeyboardButton(f"▶️ {hist[i]['title'][:30]}", callback_data=f"hist_{i}")] for i in range(start_idx, len(hist))]
        btns.append([InlineKeyboardButton("🗑️ مسح السجل", callback_data="hist_clear")])
        btns.append([InlineKeyboardButton(f"⬅️ {T(uid, 'back')}", callback_data="home")])
        await q.message.reply_text(f"📂 {T(uid, 'history_btn')}:", reply_markup=InlineKeyboardMarkup(btns)); return
    if data == "hist_clear": u["history"] = []; save_data(); await q.message.reply_text("🗑️ تم مسح السجل"); return
    if data.startswith("hist_"):
        try:
            idx = int(data.replace("hist_", "")); hist = normalize_list(u.get("history", []))
            if idx < 0 or idx >= len(hist): await q.message.reply_text(T(uid, "download_failed")); return
            url = hist[idx]["url"]; await q.message.reply_text(T(uid, "downloading"))
            base = "/tmp/" + str(uid) + "_" + str(int(time.time()*1000))
            files, thumb = download_with_ytdlp(url, base, want_audio=False, quality=u.get("quality", "720"))
            if files: await send_downloaded(q.message, files, False, None, thumb)
            else: await q.message.reply_text(T(uid, "download_failed"))
        except: await q.message.reply_text(T(uid, "download_failed"))
        return
    if data == "fav_info":
        favs = normalize_list(u.get("favs", []))
        if not favs: await q.message.reply_text(T(uid, "fav_empty")); return
        start_idx = max(0, len(favs) - 10)
        btns = [[InlineKeyboardButton(f"⭐ {favs[i]['title'][:30]}", callback_data=f"favdl_{i}")] for i in range(start_idx, len(favs))]
        btns.append([InlineKeyboardButton(f"⬅️ {T(uid, 'back')}", callback_data="home")])
        await q.message.reply_text(f"⭐ {T(uid, 'fav_btn')}:", reply_markup=InlineKeyboardMarkup(btns)); return
    if data.startswith("favdl_"):
        try:
            idx = int(data.replace("favdl_", "")); favs = normalize_list(u.get("favs", []))
            if idx < 0 or idx >= len(favs): await q.message.reply_text(T(uid, "download_failed")); return
            url = favs[idx]["url"]; await q.message.reply_text(T(uid, "downloading"))
            base = "/tmp/" + str(uid) + "_" + str(int(time.time()*1000))
            files, thumb = download_with_ytdlp(url, base, want_audio=False, quality=u.get("quality", "720"))
            if files: await send_downloaded(q.message, files, False, None, thumb)
            else: await q.message.reply_text(T(uid, "download_failed"))
        except: await q.message.reply_text(T(uid, "download_failed"))
        return
    if data.startswith("favadd_"):
        if u.get("last_link"): add_fav(u, u.get("last_link"), u.get("last_link")); await q.message.reply_text("⭐ اتضاف للمفضلة")
        return
    if data == "admin_info":
        if int(uid) != ADMIN_ID: await q.message.reply_text(T(uid, "help_text")); return
        s = DATA.get("stats", {})
        total = len(DATA["users"]); vip_count = sum(1 for x in DATA["users"].values() if isinstance(x, dict) and float(x.get("vip", 0) or 0) > time.time())
        kb_admin = InlineKeyboardMarkup([[InlineKeyboardButton("💎 تفعيل VIP", callback_data="admin_addvip"), InlineKeyboardButton("❌ الغاء VIP", callback_data="admin_delvip")],[InlineKeyboardButton("📊 احصائيات", callback_data="admin_stats")],[InlineKeyboardButton("📣 Broadcast", callback_data="admin_broadcast")],[InlineKeyboardButton("⬅️ رجوع", callback_data="home")]])
        await q.message.reply_text(f"👑 لوحة تحكم الادمن\n\n👥 المستخدمين: {total}\n💎 VIP: {vip_count}\n📥 تحميل كلي: {s.get('total',0)}\n📥 النهاردة: {s.get('today_count',0)}\n🚫 محظورين: {len(DATA.get('banned',[]))}", reply_markup=kb_admin); return
    if data == "admin_addvip":
        if int(uid) != ADMIN_ID: return
        reset_modes(u); u["state"] = "admin_addvip"; save_data(); await q.message.reply_text("💎 ابعت الاي دي"); return
    if data == "admin_delvip":
        if int(uid) != ADMIN_ID: return
        reset_modes(u); u["state"] = "admin_delvip"; save_data(); await q.message.reply_text("❌ ابعت الاي دي"); return
    if data == "admin_broadcast":
        if int(uid) != ADMIN_ID: return
        reset_modes(u); u["state"] = "broadcast"; save_data(); await q.message.reply_text("📣 اكتب الرسالة اللي عايز تبعتها للكل"); return
    if data == "admin_stats":
        if int(uid) != ADMIN_ID: return
        s = DATA.get("stats", {})
        await q.message.reply_text(f"📊 احصائيات\n\n👥 {len(DATA['users'])}\n💎 VIP: {sum(1 for x in DATA['users'].values() if isinstance(x, dict) and float(x.get('vip',0) or 0) > time.time())}\n📥 كلي: {s.get('total',0)}\n📥 النهاردة: {s.get('today_count',0)}\n🎬 {s.get('by_platform',{})}"); return
    if data == "home": await q.message.reply_text(show_main_menu_text(uid, q.from_user.first_name or ""), reply_markup=main_keyboard(uid)); return
    if data == "convert_mp3_last":
        url = u.get("last_link", "")
        if not url: await q.message.reply_text(T(uid, "no_link_mp3")); return
        await q.message.reply_text(T(uid, "converting_mp3"))
        base = "/tmp/" + str(uid) + "_" + str(int(time.time()*1000)) + "_mp3"
        files, _ = download_with_ytdlp(url, base, want_audio=True, quality=u.get("quality", "720"))
        if not files: await q.message.reply_text(T(uid, "download_failed")); return
        await send_downloaded(q.message, files, True, None); return

async def handle_dl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try: await q.answer()
    except: pass
    uid = q.from_user.id
    if is_banned(uid): await q.message.reply_text(T(uid, "banned_msg")); return
    u = get_user(uid); data = q.data or ""
    if data.startswith("dl_tiktok_"):
        vid = data.replace("dl_tiktok_", ""); await q.message.reply_text(T(uid, "downloading"))
        url = f"https://www.tiktok.com/@tiktok/video/{vid}"
        base = "/tmp/" + str(uid) + "_" + str(int(time.time()*1000))
        files, thumb = download_with_ytdlp(url, base, want_audio=False, quality=u.get("quality", "720"))
        if not files: await q.message.reply_text(T(uid, "download_failed")); return
        await send_downloaded(q.message, files, False, None, thumb); return
    want_audio = False; quality = u.get("quality", "720"); vid = ""
    if data.startswith("dl_audio_"): vid = data.replace("dl_audio_", ""); want_audio = True
    elif data.startswith("dl_1080_"): vid = data.replace("dl_1080_", ""); quality = "1080"
    elif data.startswith("dl_720_"): vid = data.replace("dl_720_", ""); quality = "720"
    elif data.startswith("dl_2k_"): vid = data.replace("dl_2k_", ""); quality = "2k"
    elif data.startswith("dl_4k_"): vid = data.replace("dl_4k_", ""); quality = "4k"
    elif data.startswith("dl_video_"): vid = data.replace("dl_video_", ""); quality = u.get("quality", "720")
    else: return
    u["quality"] = quality; save_data()
    await q.message.reply_text(T(uid, "downloading"))
    try:
        base = "/tmp/" + str(uid) + "_" + str(int(time.time()*1000))
        files, thumb = download_with_ytdlp("https://www.youtube.com/watch?v=" + vid, base, want_audio=want_audio, quality=quality)
        if not files: await q.message.reply_text(T(uid, "download_failed")); return
        await send_downloaded(q.message, files, want_audio, None, thumb)
    except Exception as e: await q.message.reply_text(f"{T(uid, 'download_failed')}\n{str(e)}")

async def handle_choose_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); uid = q.from_user.id; data = q.data or ""
    if data.startswith("pick_tiktok_"):
        vid = data.replace("pick_tiktok_", "")
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"🎵 {T(uid, 'download_mp3')}", callback_data=f"dl_audio_{vid}")],[InlineKeyboardButton(f"📥 {T(uid, 'download_video')} - 720", callback_data=f"dl_tiktok_{vid}")],[InlineKeyboardButton(f"⬅️ {T(uid, 'back')}", callback_data="home")]])
        await q.message.reply_text(f"{T(uid, 'choose_format')}", reply_markup=kb); return
    if not data.startswith("pick_"): return
    vid = data.replace("pick_", "")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"🎵 {T(uid, 'download_mp3')}", callback_data=f"dl_audio_{vid}")],[InlineKeyboardButton(f"📥 {T(uid, 'download_video')} - 720", callback_data=f"dl_720_{vid}")],[InlineKeyboardButton(f"📥 {T(uid, 'download_video')} - 1080", callback_data=f"dl_1080_{vid}")],[InlineKeyboardButton(f"📥 {T(uid, 'download_video')} - 2K", callback_data=f"dl_2k_{vid}")],[InlineKeyboardButton(f"📥 {T(uid, 'download_video')} - 4K", callback_data=f"dl_4k_{vid}")],[InlineKeyboardButton(f"⬅️ {T(uid, 'back')}", callback_data="home")]])
    await q.message.reply_text(f"{T(uid, 'choose_format')}", reply_markup=kb)

async def do_download_flow(message, uid, url, want_audio=False, quality="720", is_playlist=False):
    u = get_user(uid)
    now = time.time()
    if now - float(u.get("last_dl_at", 0)) < 3 and not is_vip(uid):
        await message.reply_text(T(uid, "rate_limit")); return False
    u["last_dl_at"] = now; save_data()
    CANCEL_FLAGS[str(uid)] = False
    plat = platform_of(url)
    status_msg = await message.reply_text(f"⏳ {T(uid, 'downloading')} 0%\n{T(uid, 'queue_wait')}", reply_markup=cancel_keyboard(uid))
    last_pct = [0]
    def cb(pct):
        if pct - last_pct[0] >= 20:
            last_pct[0] = pct
            try: asyncio.create_task(status_msg.edit_text(f"⏳ {T(uid, 'downloading')} {pct}%", reply_markup=cancel_keyboard(uid)))
            except: pass
    async with DOWNLOAD_SEM:
        if CANCEL_FLAGS.get(str(uid)):
            await status_msg.edit_text(T(uid, "cancelled")); return False
        if is_playlist:
            urls = download_playlist(url, uid, quality)
            if not urls: await status_msg.edit_text(T(uid, "download_failed")); return False
            await status_msg.edit_text(f"📃 لقيت {len(urls)} فيديوهات، بحملهم...")
            for idx, pu in enumerate(urls):
                if CANCEL_FLAGS.get(str(uid)): break
                base = "/tmp/" + str(uid) + "_" + str(int(time.time()*1000)) + f"_{idx}"
                files, thumb = download_with_ytdlp(pu, base, want_audio=want_audio, quality=quality)
                if files:
                    for fp in files:
                        fixed = await ensure_size_ok(fp, uid)
                        if not fixed: await message.reply_text(T(uid, "too_big")); continue
                        await send_downloaded(message, [fixed], want_audio, None, thumb)
            await status_msg.edit_text("✅ خلصت القايمة")
            bump_stats(plat); return True
        base = "/tmp/" + str(uid) + "_" + str(int(time.time()*1000))
        files, thumb = download_with_ytdlp(url, base, want_audio=want_audio, quality=quality, progress_cb=cb)
        if CANCEL_FLAGS.get(str(uid)):
            for f in files:
                try: os.remove(f)
                except: pass
            await status_msg.edit_text(T(uid, "cancelled")); return False
        if not files:
            await status_msg.edit_text(f"{T(uid, 'download_failed')}\nمنصة: {plat} - جرب لينك تاني او جودة اقل")
            if ADMIN_ID != 0:
                try: await message.bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ تحميل فشل\n👤 {uid}\n🔗 {url}\n📱 {plat}")
                except: pass
            return False
        ok_files = []
        for fp in files:
            fixed = await ensure_size_ok(fp, uid)
            if fixed: ok_files.append(fixed)
            else: await message.reply_text(T(uid, "too_big"))
        if not ok_files:
            await status_msg.edit_text(T(uid, "too_big")); return False
        try: await status_msg.delete()
        except: pass
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"🎵 {T(uid, 'download_mp3')}", callback_data="convert_mp3_last")],[InlineKeyboardButton("⭐ اضافة للمفضلة", callback_data="favadd_")]])
        await send_downloaded(message, ok_files, want_audio, kb, thumb)
        bump_stats(plat)
        cleanup_tmp()
        return True

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    uid = update.effective_user.id
    if is_banned(uid): await update.message.reply_text(T(uid, "banned_msg")); return
    u = get_user(uid); user = update.effective_user
    is_video_msg = bool(update.message.video or (update.message.document and update.message.document.mime_type and "video" in update.message.document.mime_type))
    if is_video_msg:
        if u.get("gif_mode") or u.get("compress_mode") or u.get("state") == "extract":
            try:
                await update.message.reply_text("⏳ بحول الفيديو...")
                file_id = update.message.video.file_id if update.message.video else update.message.document.file_id
                f = await context.bot.get_file(file_id); ts = int(time.time()*1000); in_path = f"/tmp/{uid}_{ts}_in.mp4"; await f.download_to_drive(in_path)
                if u.get("gif_mode"):
                    out_path = f"/tmp/{uid}_{ts}_out.gif"
                    subprocess.run(["ffmpeg", "-y", "-i", in_path, "-vf", "fps=10,scale=480:-1:flags=lanczos", out_path], capture_output=True, timeout=90)
                    if not os.path.exists(out_path) or os.path.getsize(out_path) < 1000: await update.message.reply_text("الـ ffmpeg مش شغال على السيرفر")
                    else:
                        with open(out_path, "rb") as ff: await update.message.reply_document(ff, filename="Nezel.gif")
                        try: os.remove(out_path)
                        except: pass
                elif u.get("compress_mode"):
                    out_path = f"/tmp/{uid}_{ts}_out.mp4"; ok, msg = compress_video_file(in_path, out_path, crf=28)
                    if not ok:
                        ok2, _ = compress_video_file(in_path, out_path, crf=32)
                        if not ok2: await update.message.reply_text("الضغط فشل")
                        else: ok = True
                    if ok:
                        with open(out_path, "rb") as ff: await update.message.reply_video(ff, caption="🗜️ تم ضغط الفيديو")
                        try: os.remove(out_path)
                        except: pass
                else:
                    out_path = f"/tmp/{uid}_{ts}_out.mp3"
                    subprocess.run(["ffmpeg", "-y", "-i", in_path, "-vn", "-ab", "192k", out_path], capture_output=True, timeout=90)
                    if not os.path.exists(out_path) or os.path.getsize(out_path) < 1000: await update.message.reply_text("استخراج الصوت فشل")
                    else:
                        with open(out_path, "rb") as ff: await update.message.reply_audio(ff, title="Nezel Audio")
                        try: os.remove(out_path)
                        except: pass
                try: os.remove(in_path)
                except: pass
                reset_modes(u); save_data(); return
            except Exception as e: await update.message.reply_text(f"فشل: {e}"); reset_modes(u); save_data(); return
        else:
            await update.message.reply_text(f"🎬 {T(uid, 'choose_video_action')}", reply_markup=main_keyboard(uid)); return
    if update.message.photo:
        caption = (update.message.caption or "").strip(); cap_url = extract_url(caption)
        if cap_url and not u.get("pdf_mode"):
            text = caption
        elif u.get("pdf_mode"):
            u["pdf_photos"].append(update.message.photo[-1].file_id); save_data()
            await update.message.reply_text(f"{T(uid, 'pdf_added')} {len(u['pdf_photos'])} ✅"); return
        else:
            return
    else:
        text = (update.message.text or update.message.caption or "").strip()
    if not text: return
    if not u.get("lang"):
        await update.message.reply_text("اختر لغتك\n\nChoose your language", reply_markup=lang_keyboard()); return
    if u.get("state") == "broadcast" and int(uid) == ADMIN_ID:
        u["state"] = "home"; save_data()
        sent = 0
        for tid in list(DATA["users"].keys()):
            if str(tid) in DATA.get("banned", []): continue
            try: await context.bot.send_message(chat_id=int(tid), text=f"📣 رسالة من الأدمن:\n\n{text}"); sent += 1; await asyncio.sleep(0.05)
            except: pass
        await update.message.reply_text(f"✅ اتبعت لـ {sent} واحد"); return
    if u.get("state") == "admin_addvip" and int(uid) == ADMIN_ID:
        target = text.strip()
        if not target.isdigit(): await update.message.reply_text("ابعت اي دي ارقام بس"); return
        tu = get_user(target); tu["vip"] = time.time() + 30 * 86400; u["state"] = "home"; save_data()
        await update.message.reply_text(f"✅ تم تفعيل VIP للمستخدم {target} لمدة 30 يوم")
        try: await context.bot.send_message(chat_id=int(target), text=T(int(target), "vip_congrats"))
        except: pass
        await update.message.reply_text(show_main_menu_text(uid, user.first_name or ""), reply_markup=main_keyboard(uid)); return
    if u.get("state") == "admin_delvip" and int(uid) == ADMIN_ID:
        target = text.strip()
        if not target.isdigit(): await update.message.reply_text("ابعت اي دي ارقام بس"); return
        tu = get_user(target); tu["vip"] = 0; u["state"] = "home"; save_data()
        await update.message.reply_text(f"❌ تم الغاء VIP من المستخدم {target}")
        await update.message.reply_text(show_main_menu_text(uid, user.first_name or ""), reply_markup=main_keyboard(uid)); return
    if u.get("support_mode") or u.get("state") == "support":
        u["support_mode"] = False; u["state"] = "home"; save_data()
        await update.message.reply_text(f"✅ {T(uid, 'support_sent')}")
        if ADMIN_ID != 0:
            try:
                name = user.first_name or ""; username = user.username
                username_link = f'<a href="https://t.me/{username}">@{username}</a>' if username else "مفيش يوزر"
                msg_text = (f"📩 <b>رسالة دعم جديدة</b>\n━━━━━━━━━━━━━━\n👤 الاسم: <a href=\"tg://user?id={uid}\">{html.escape(name)}</a>\n🆔 الاي دي: <a href=\"tg://user?id={uid}\">{uid}</a>\n🔗 يوزر: {username_link}\n━━━━━━━━━━━━━━\n💬 الرسالة:\n{html.escape(text)}\n━━━━━━━━━━━━━━\nللرد اكتب:\n<code>/reply {uid} رسالتك</code>")
                await context.bot.send_message(chat_id=ADMIN_ID, text=msg_text, parse_mode=ParseMode.HTML)
            except Exception as e: print("Support forward failed: " + str(e))
        await update.message.reply_text(show_main_menu_text(uid, user.first_name or ""), reply_markup=main_keyboard(uid)); return
    if u.get("translate_mode"):
        u["translate_mode"] = False; u["state"] = "home"; save_data()
        has_ar = any('\u0600' <= c <= '\u06FF' for c in text); target = "en" if has_ar else "ar"; tr = translate_text(text, target)
        await update.message.reply_text(f"🌐 {T(uid, 'translate_done')}:\n{tr}")
        await update.message.reply_text(show_main_menu_text(uid, user.first_name or ""), reply_markup=main_keyboard(uid)); return
    if u.get("summarize_mode"):
        u["summarize_mode"] = False; u["state"] = "home"; save_data()
        await update.message.reply_text(f"📝 {T(uid, 'summarize_done')}:\n{summarize_text(text)}")
        await update.message.reply_text(show_main_menu_text(uid, user.first_name or ""), reply_markup=main_keyboard(uid)); return
    if u.get("state") == "story" or u.get("story_mode"):
        reset_modes(u); save_data(); url = extract_url(text)
        if url and "instagram.com" in url:
            await update.message.reply_text("📸 بحمل الستوري...")
            base = "/tmp/" + str(uid) + "_" + str(int(time.time()*1000))
            files, thumb = download_with_ytdlp(url, base, want_audio=False, quality=u.get("quality", "720"))
            if files: await send_downloaded(update.message, files, False, None, thumb)
            else: await update.message.reply_text("مش عارف اجيب الستوري، انستا قافل الستوري من غير تسجيل دخول")
        else: await update.message.reply_text("📸 ابعت لينك الستوري مش اليوزر")
        return
    if u.get("state") == "movies" or u.get("movie_mode"):
        reset_modes(u); save_data(); await update.message.reply_text("🎬 بدور...")
        res = search_movies(text)
        if not res: await update.message.reply_text(T(uid, "not_found")); return
        out = "🎬 لقيت دول:\n\n"
        for r in res: out += f"🎬 {r['name']}\n{r['summary'][:150]}\n{r['url']}\n\n"
        await update.message.reply_text(out); return
    if u.get("state") == "wallpaper" or u.get("wallpaper_mode"):
        reset_modes(u); save_data(); await update.message.reply_text("🖼️ بجيبلك خلفيات...")
        for w in get_wallpapers(text)[:3]:
            try: await update.message.reply_photo(w, caption="🖼️ خلفية HD من نزل")
            except: pass
        return
    if u.get("state") == "search":
        u["state"] = "home"; save_data()
        msg = await update.message.reply_text(f"🔍 {T(uid, 'searching')}: {text}\n{T(uid, 'search_wait')}...")
        results = do_search(text)
        if not results: await msg.edit_text(T(uid, "not_found")); return
        buttons = []
        for r in results:
            title = r["title"]
            if len(title) > 35: title = title[:35] + "..."
            buttons.append([InlineKeyboardButton(f"🎵 {title}", callback_data=f"pick_{r['id']}")])
        buttons.append([InlineKeyboardButton(f"⬅️ {T(uid, 'back')}", callback_data="home")])
        await msg.edit_text(f"{T(uid, 'choose_result')}:", reply_markup=InlineKeyboardMarkup(buttons)); return
    url = extract_url(text)
    if url and any(x in url for x in ["youtube.com", "youtu.be", "tiktok.com", "instagram.com", "facebook.com", "fb.watch"]):
        u["last_link"] = url; save_history(u, url, url)
        mode = u.get("download_mode", "video")
        want_audio = (mode == "audio")
        is_playlist = (mode == "playlist")
        await do_download_flow(update.message, uid, url, want_audio=want_audio, quality=u.get("quality", "720"), is_playlist=is_playlist)
        return
    if "http" in text:
        await update.message.reply_text(f"⚠️ اللينك ده مش مدعوم\nاللي شغال: يوتيوب / تيك توك / انستا / فيس\nابعت لينك منهم"); return
    await update.message.reply_text(show_main_menu_text(uid, user.first_name or ""), reply_markup=main_keyboard(uid))

def main():
    if not BOT_TOKEN: print("ERROR: BOT_TOKEN missing"); return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("vip", vip_cmd))
    app.add_handler(CommandHandler("reply", reply_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("unban", unban_cmd))
    app.add_handler(CallbackQueryHandler(handle_dl, pattern="^dl_"))
    app.add_handler(CallbackQueryHandler(handle_choose_result, pattern="^pick_"))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_message))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_message))
    app.add_handler(MessageHandler(filters.CAPTION, handle_message))
    print("Bot started - Full version")
    app.run_polling()

if __name__ == "__main__":
    main()
