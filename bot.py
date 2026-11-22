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
import copy
import requests
import yt_dlp
import subprocess
import shutil
import asyncio
import random
from pathlib import Path
from datetime import datetime, date
from PIL import Image, ImageDraw, ImageFont
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ParseMode

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")  # (مش مستخدم لسه - الداتا بتتحفظ في users.json)
FORCE_SUB_CHANNEL = os.getenv("FORCE_SUB_CHANNEL", "")  # مثال: @NezelBotChannel من غير https
COOKIES_FILE = os.getenv("COOKIES_FILE", "")  # اختياري: ملف cookies.txt ليوتيوب/انستا (بيحل مشكلة "confirm you're not a bot")
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "1159182662") or 0)
except:
    ADMIN_ID = 0

DATA_FILE = "users.json"
BACKUP_FILE = "users_backup.json"
URL_RE = re.compile(r'https?://[^\s<>"]+')
MAX_TG_SIZE = 49 * 1024 * 1024
TG_DL_LIMIT = 20 * 1024 * 1024  # حد تليجرام لتنزيل ملفات من المستخدمين للبوت
UP = {"read_timeout": 180, "write_timeout": 180}  # مهلة رفع الملفات الكبيرة
CANCEL_FLAGS = {}
TREND_URLS = {}
MODE_LABELS = {"audio": "MP3", "video": "فيديو", "nowm": "بدون علامة", "playlist": "قايمة"}

_DOWNLOAD_SEM = None
def get_sem():
    # بيتعمل وقت الاستخدام عشان يتربط بالـ event loop الصح
    global _DOWNLOAD_SEM
    if _DOWNLOAD_SEM is None:
        _DOWNLOAD_SEM = asyncio.Semaphore(2)
    return _DOWNLOAD_SEM

async def arun(cmd, timeout=120):
    """تشغيل أمر (ffmpeg مثلا) من غير ما نوقف البوت كله"""
    def _run():
        try:
            return subprocess.run(cmd, capture_output=True, timeout=timeout)
        except Exception as e:
            print("cmd err:", e)
            return None
    return await asyncio.to_thread(_run)

def extract_url(text):
    m = URL_RE.search(text or "")
    return m.group(0).rstrip(").,") if m else ""

def extract_all_urls(text):
    return [u.rstrip(").,") for u in URL_RE.findall(text or "")]

def platform_of(url):
    u = (url or "").lower()
    if "tiktok.com" in u or "vt.tiktok" in u: return "tiktok"
    if "instagram.com" in u: return "instagram"
    if "facebook.com" in u or "fb.watch" in u: return "facebook"
    if "youtube.com" in u or "youtu.be" in u: return "youtube"
    if "pinterest." in u: return "pinterest"
    if "reddit.com" in u or "redd.it" in u: return "reddit"
    if "twitch.tv" in u: return "twitch"
    if "soundcloud.com" in u: return "soundcloud"
    if "t.me/" in u: return "telegram"
    return "other"

# ===== Persistence =====
def load_data():
    for path in [DATA_FILE, BACKUP_FILE]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    if isinstance(d, dict) and "users" in d:
                        if "stats" not in d: d["stats"] = {"total": 0, "by_platform": {}, "today": str(date.today()), "today_count": 0}
                        if "banned" not in d: d["banned"] = []
                        if "follows" not in d: d["follows"] = {}
                        if "quiz" not in d: d["quiz"] = {"date": "", "q": "", "a": ""}
                        return d
            except Exception as e:
                print(f"load {path} err: {e}")
    return {"users": {}, "stats": {"total": 0, "by_platform": {}, "today": str(date.today()), "today_count": 0}, "banned": [], "follows": {}, "quiz": {"date": "", "q": "", "a": ""}}

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
    "meme_mode": False, "meme_photo": None, "merge_videos": [], "trim_mode": False, "trim_video": None,
    "cover_mode": False, "caption_mode": False, "follow_mode": False, "pdf2img_mode": False,
    "cut_mode": False, "story_convert_mode": False, "remove_music_mode": False, "lyrics_mode": False,
    "quiz_date": "",
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
        # deepcopy: عشان القوايم (invited_users, pdf_photos...) متتشاركش بين كل اليوزرز
        DATA["users"][uid] = copy.deepcopy(DEFAULT_USER)
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
    for k in ["support_mode","translate_mode","summarize_mode","pdf_mode","story_mode","movie_mode","wallpaper_mode","gif_mode","compress_mode","meme_mode","trim_mode","cover_mode","caption_mode","follow_mode","pdf2img_mode","cut_mode","story_convert_mode","remove_music_mode","lyrics_mode"]:
        u[k] = False
    u["state"] = "home"

def is_vip(uid):
    try: return float(get_user(uid).get("vip", 0)) > time.time()
    except: return False

async def check_force_sub(bot, uid):
    if not FORCE_SUB_CHANNEL: return True
    try:
        m = await bot.get_chat_member(FORCE_SUB_CHANNEL, uid)
        return m.status in ["member","administrator","creator"]
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
                if os.path.isfile(f) and now - os.path.getmtime(f) > 3600:
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

# ===== NEW HELPERS =====
def clean_title(t):
    t = re.sub(r'[\(\[\{].*?[\)\]\}]', ' ', t or "")
    t = re.sub(r'(?i)\b(official|video|audio|lyrics|lyric|clip|hd|4k|mv)\b', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()

def get_lyrics(title):
    try:
        q = clean_title(title) or title
        r = requests.get("https://lrclib.net/api/search", params={"q": q}, timeout=15)
        if r.status_code == 200 and r.json():
            item = r.json()[0]
            return item.get("plainLyrics") or item.get("syncedLyrics") or ""
    except Exception as e: print("lyrics err", e)
    return ""

def get_title(url):
    """بيجيب اسم الاغنية/الفيديو من اللينك (عشان نبحث عن الكلمات)"""
    try:
        opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True, "socket_timeout": 30}
        if COOKIES_FILE and os.path.exists(COOKIES_FILE): opts["cookiefile"] = COOKIES_FILE
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False) or {}
        t = info.get("track"); a = info.get("artist")
        if t: return f"{a} {t}" if a else t
        return info.get("title", "") or ""
    except Exception as e:
        print("title err", e); return ""

def make_meme(image_path, top_text, out_path):
    try:
        img = Image.open(image_path).convert("RGB")
        w, h = img.size
        draw = ImageDraw.Draw(img)
        txt = (top_text or "")[:80]
        try:  # عشان العربي يتكتب صح (اختياري: pip install arabic-reshaper python-bidi)
            import arabic_reshaper
            from bidi.algorithm import get_display
            txt = get_display(arabic_reshaper.reshape(txt))
        except Exception:
            pass
        bar = int(h * 0.15)
        size = max(14, min(int(w * 0.08), int(bar * 0.7)))
        font = None
        while size >= 14:
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
            except Exception:
                font = None
                break
            if draw.textlength(txt, font=font) <= w * 0.94: break
            size -= 2
        draw.rectangle([0, 0, w, bar], fill=(0, 0, 0))
        draw.rectangle([0, h - bar, w, h], fill=(0, 0, 0))
        if font is None:
            draw.text((10, max(0, bar // 4)), txt, fill="white")
        else:
            draw.text((w // 2, bar // 2), txt, font=font, fill="white", anchor="mm")
        img.save(out_path)
        return True
    except Exception as e:
        print("meme err", e); return False

def make_caption(title):
    base = (title or "فيديو جامد").strip()
    tags = ["#نزل", "#Nezel", "#ترند", "#فيديو", "#تيك_توك", "#يوتيوب", "#explore", "#viral", "#مصر", "#funny"]
    caption = f"{base} 🔥\n\nحمله من بوت نزل 👇\n\n" + " ".join(tags)
    return caption

QUIZ_LIST = [
    ("ايه عاصمة مصر؟", "القاهرة"),
    ("كام لون في قوس قزح؟", "7"),
    ("ايه اكبر كوكب؟", "المشتري"),
    ("مين غنى اغنية انت عمري؟", "ام كلثوم"),
    ("كام يوم في السنة؟", "365"),
]

def norm_ar(s):
    s = (s or "").strip().lower()
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي")):
        s = s.replace(a, b)
    return s

def get_today_quiz():
    today = str(date.today())
    qd = DATA.get("quiz", {})
    if qd.get("date") != today:
        q, a = random.choice(QUIZ_LIST)
        DATA["quiz"] = {"date": today, "q": q, "a": a}
        save_data()
        return q, a
    return qd.get("q",""), qd.get("a","")

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
        "force_sub": "لازم تشترك في القناة الاول عشان تستخدم البوت 👇",
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
        "force_sub": "You must join the channel first 👇",
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
        # NEW
        [InlineKeyboardButton("✂️ قص أحلى حتة", callback_data="mode_cut"), InlineKeyboardButton("📱 تحويل لستوري", callback_data="mode_story_convert")],
        [InlineKeyboardButton("😂 اعملي ميم", callback_data="mode_meme"), InlineKeyboardButton("🔔 تنبيه جديد", callback_data="mode_follow")],
        [InlineKeyboardButton("🎤 بحث بالصوت", callback_data="mode_voice"), InlineKeyboardButton("🎁 مسابقة يومية", callback_data="mode_quiz")],
        [InlineKeyboardButton("🏆 لوحة الشرف", callback_data="mode_leader"), InlineKeyboardButton("🖼️ اعملي غلاف", callback_data="mode_cover")],
        [InlineKeyboardButton("✍️ كابشن وهاشتاجات", callback_data="mode_caption"), InlineKeyboardButton("🎼 شيل الموسيقى", callback_data="mode_nomusic")],
        [InlineKeyboardButton("🔗 دمج فيديوهين", callback_data="mode_merge"), InlineKeyboardButton("✂️ تقطيع فيديو", callback_data="mode_trim")],
        [InlineKeyboardButton("📄 PDF لصور", callback_data="mode_pdf2img"), InlineKeyboardButton("🎤 صوت + كلمات", callback_data="mode_lyrics")],
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
    mode_label = MODE_LABELS.get(u.get("download_mode", "video"), "فيديو")
    return "\n".join([f"✨ {T(uid, 'welcome')} {name} 👑", "", T(uid, 'welcome_sub'), "────────────────", f"🎁 {T(uid, 'points')}: {points} / 100", f"👥 {T(uid, 'invites')}: {invites} / 50", vip_line, f"🎬 الجودة الحالية: {u.get('quality','720')} | الوضع: {mode_label}", "────────────────", f"👇 {T(uid, 'send_link')} - ممكن تبعت اكتر من لينك مرة واحدة"])

def compress_video_file(in_path, out_path, crf=28):
    if not shutil.which("ffmpeg"): return False, "ffmpeg not found"
    cmd = ["ffmpeg", "-y", "-i", in_path, "-vcodec", "libx264", "-crf", str(crf), "-preset", "veryfast", "-acodec", "aac", "-b:a", "128k", "-movflags", "+faststart", out_path]
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=180)
        if res.returncode != 0: return False, "ffmpeg failed"
        if not os.path.exists(out_path) or os.path.getsize(out_path) < 1000: return False, "output too small"
        return True, "ok"
    except Exception as e: return False, str(e)

def convert_to_story(in_path, out_path):
    if not shutil.which("ffmpeg"): return False
    cmd = ["ffmpeg","-y","-i",in_path,"-vf","scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2","-c:a","copy",out_path]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=180)
        return r.returncode==0 and os.path.exists(out_path)
    except: return False

def cut_best_part(in_path, out_path):
    # بيقص من 0 لـ 30 ثانية (أول 30 ثانية)
    if not shutil.which("ffmpeg"): return False
    cmd = ["ffmpeg","-y","-i",in_path,"-ss","0","-t","30","-c","copy",out_path]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        return r.returncode==0 and os.path.exists(out_path)
    except: return False

def _ensure_size_ok_sync(path):
    try:
        if not path or not os.path.exists(path): return None
        if os.path.getsize(path) <= MAX_TG_SIZE: return path
        stem, ext = os.path.splitext(path)
        if ext.lower() not in (".mp4", ".mkv", ".webm", ".mov"):
            try: os.remove(path)
            except: pass
            return None
        for crf in [30, 34, 38]:
            out = f"{stem}_c{crf}.mp4"
            ok, _ = compress_video_file(path, out, crf=crf)
            if ok and os.path.getsize(out) <= MAX_TG_SIZE:
                try: os.remove(path)
                except: pass
                return out
            try:
                if os.path.exists(out): os.remove(out)
            except: pass
        try: os.remove(path)
        except: pass
        return None
    except Exception:
        return None

async def ensure_size_ok(path, uid):
    return await asyncio.to_thread(_ensure_size_ok_sync, path)

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
    """بيترجم الكلمة للانجليزي ويدور بيها، ولو فشل بيرجع لصور عشوائية"""
    urls = []
    try:
        kw = translate_text(query or "", "en")
        kw = re.sub(r'[^a-zA-Z0-9]+', ',', kw).strip(",") or "nature"
        kw = ",".join(kw.split(",")[:3])
        urls += [f"https://loremflickr.com/1080/1920/{kw}?lock={random.randint(1, 99999)}" for _ in range(3)]
    except Exception as e: print(f"wallpaper kw err: {e}")
    try:
        r = requests.get("https://picsum.photos/v2/list", params={"page": random.randint(1, 20), "limit": 5}, timeout=15)
        if r.status_code == 200: urls += [f"https://picsum.photos/id/{x['id']}/1080/1920" for x in r.json()]
    except Exception as e: print(f"wallpaper err: {e}")
    if not urls:
        urls = ["https://picsum.photos/1080/1920", "https://picsum.photos/1080/1920?random=1", "https://picsum.photos/1080/1920?random=2"]
    return urls

def get_trending():
    # ترند: tikwm + fallback يوتيوب ترند
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
    # fallback: بحث ترند يوتيوب
    try:
        res2 = do_search("trending egypt " + str(date.today().year))
        return [{"id": r["id"], "title": r["title"], "author": "youtube", "url": f"https://www.youtube.com/watch?v={r['id']}"} for r in res2[:5]]
    except: return []

def do_search(query):
    try:
        opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True, "socket_timeout": 30}
        if COOKIES_FILE and os.path.exists(COOKIES_FILE): opts["cookiefile"] = COOKIES_FILE
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
    return (f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best")

def get_tiktok_id_from_url(url):
    try:
        r = requests.get(url, allow_redirects=True, timeout=15, headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"})
        final = r.url
        m = re.search(r'/video/(\d+)', final)
        if m: return m.group(1), final
        return None, final
    except:
        return None, url

def download_tiktok_via_api(url, base, want_audio=False):
    try:
        vid, final_url = get_tiktok_id_from_url(url)
        for try_url in [url, final_url]:
            if not try_url: continue
            r = requests.get("https://www.tikwm.com/api/", params={"url": try_url, "hd": 1}, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200: continue
            j = r.json()
            data = j.get("data", {})
            if not data: continue
            if want_audio:
                audio_url = data.get("music") or (data.get("music_info", {}).get("play") if isinstance(data.get("music_info"), dict) else None)
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

def download_with_ytdlp(url, base, want_audio=False, quality="720", progress_cb=None, cancel_check=None):
    plat = platform_of(url)
    if plat == "tiktok":
        files, thumb = download_tiktok_via_api(url, base, want_audio=want_audio)
        if files: return files, thumb
        print("tikwm failed, fallback to yt-dlp")
    try:
        for f in glob.glob(base + ".*"):
            try: os.remove(f)
            except: pass
        fmt = format_for_quality(quality, want_audio)
        def hook(d):
            if cancel_check and cancel_check():
                raise Exception("cancelled")
            if progress_cb and d.get("status") == "downloading":
                try:
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    dl = d.get("downloaded_bytes", 0)
                    if total > 0: progress_cb(int(dl * 100 / total))
                except Exception: pass
        opts = {
            "format": fmt, "outtmpl": base + ".%(ext)s",
            "quiet": True, "no_warnings": True, "nocheckcertificate": True,
            "socket_timeout": 90, "retries": 3, "noplaylist": True,
            "progress_hooks": [hook],
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            }
        }
        # (اتشال extractor_args القديم: كان قايمة جوا قايمة وده غلط ومكن يبوظ يوتيوب خالص)
        if not want_audio:
            opts["merge_output_format"] = "mp4"  # عشان الملف يطلع mp4 دايما
        if COOKIES_FILE and os.path.exists(COOKIES_FILE):
            opts["cookiefile"] = COOKIES_FILE
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
        if cancel_check and cancel_check():
            return [], None
        if plat == "tiktok":
            return download_tiktok_via_api(url, base, want_audio=want_audio)
        return [], None

def download_playlist(url, uid, quality="720"):
    try:
        opts = {"quiet": True, "extract_flat": True, "skip_download": True, "socket_timeout": 30}
        if COOKIES_FILE and os.path.exists(COOKIES_FILE): opts["cookiefile"] = COOKIES_FILE
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

def _fetch_thumb(thumb_url):
    try:
        if not thumb_url: return None
        r = requests.get(thumb_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        # تليجرام بيقبل صورة مصغرة اقل من 200 كيلو
        if r.status_code == 200 and 1000 < len(r.content) < 200 * 1024:
            p = f"/tmp/thumb_{int(time.time()*1000)}.jpg"
            with open(p, "wb") as f: f.write(r.content)
            return p
    except Exception: pass
    return None

async def send_downloaded(msg_obj, files, want_audio, kb, thumb_url=None):
    thumb_path = await asyncio.to_thread(_fetch_thumb, thumb_url)
    ok = True
    try:
        for fp in files:
            try:
                if fp.endswith((".jpg", ".jpeg", ".png", ".webp")):
                    with open(fp, "rb") as f: await msg_obj.reply_photo(f, **UP)
                elif want_audio or fp.endswith((".mp3", ".m4a", ".opus")):
                    with open(fp, "rb") as f: await msg_obj.reply_audio(f, reply_markup=kb, **UP)
                else:
                    with open(fp, "rb") as f:
                        try:
                            await msg_obj.reply_video(f, reply_markup=kb, thumbnail=(Path(thumb_path) if thumb_path else None), supports_streaming=True, **UP)
                        except Exception as e1:
                            print(f"video send err: {e1}")
                            f.seek(0)  # لازم نرجع اول الملف قبل ما نبعته تاني
                            await msg_obj.reply_document(f, reply_markup=kb, **UP)
            except Exception as e:
                print(f"send err: {e}")
                ok = False
    finally:
        for fp in files:
            try: os.remove(fp)
            except: pass
        if thumb_path:
            try: os.remove(thumb_path)
            except: pass
    return ok

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    is_new = str(uid) not in DATA["users"]  # لازم قبل أي get_user
    if is_banned(uid):
        await update.message.reply_text(T(uid, "banned_msg")); return
    u = get_user(uid)
    # اشتراك اجباري
    if FORCE_SUB_CHANNEL and not await check_force_sub(context.bot, uid):
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{FORCE_SUB_CHANNEL.replace('@','')}")],[InlineKeyboardButton("✅ اشتركت", callback_data="check_sub")]])
        await update.message.reply_text(T(uid, "force_sub"), reply_markup=kb); return
    if context.args and context.args[0].startswith("inv_"):
        inviter = context.args[0].replace("inv_", "")
        # الدعوة بتتحسب بس لو اليوزر جديد فعلا
        if is_new and inviter != str(uid) and not u.get("invited_by") and inviter.isdigit():
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
    reset_modes(u); save_data()
    await update.message.reply_text("اختر لغتك\n\nChoose your language", reply_markup=lang_keyboard())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text("📖 أوامر البوت:\n\n/start - القايمة الرئيسية\n/help - المساعدة\n/stats - إحصائيات البوت\n/vip 123 - تفعيل VIP (أدمن)\n/reply 123 رسالة - رد على دعم (أدمن)\n/broadcast رسالة - رسالة للكل (أدمن)\n/ban 123 - حظر (أدمن)\n/unban 123 - فك حظر (أدمن)\n\nابعت لينك من تيك توك / انستا / فيس / يوتيوب / Pinterest / Reddit / Twitch / SoundCloud وهيتحمل على طول\nممكن تبعت اكتر من لينك مرة واحدة")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    s = DATA.get("stats", {})
    bp = s.get('by_platform', {})
    if bp:
        bp_txt = "\n".join([f"{k}: {v}" for k,v in bp.items()])
        await update.message.reply_text(f"📊 إحصائيات البوت:\n\n👥 المستخدمين: {len(DATA['users'])}\n📥 تحميل كلي: {s.get('total',0)}\n📥 النهاردة: {s.get('today_count',0)}\n\n🎬 بالمنصة:\n{bp_txt}")
    else:
        await update.message.reply_text(f"📊 إحصائيات البوت:\n\n👥 المستخدمين: {len(DATA['users'])}\n📥 تحميل كلي: {s.get('total',0)}\n📥 النهاردة: {s.get('today_count',0)}\n\n📊 لسه مفيش تحميلات")

async def vip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    # كان "and" وده بيخلي اي حد يفعل VIP لو ADMIN_ID = 0
    if uid != ADMIN_ID or ADMIN_ID == 0: await update.message.reply_text("Not allowed"); return
    if not context.args: await update.message.reply_text("Use: /vip 123456"); return
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
    parts = (update.message.text or "").split(None, 1)  # عشان السطور الجديدة متضيعش
    msg = parts[1] if len(parts) > 1 else ""
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
    if data == "check_sub":
        if await check_force_sub(context.bot, uid):
            await q.message.reply_text("✅ تمام، اهلا بيك")
            await q.message.reply_text(show_main_menu_text(uid, q.from_user.first_name or ""), reply_markup=main_keyboard(uid))
        else:
            await q.message.reply_text(T(uid, "force_sub"))
        return
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
    # NEW MODES
    if data == "mode_cut": reset_modes(u); u["cut_mode"]=True; u["state"]="cut"; save_data(); await q.message.reply_text("✂️ ابعت فيديو من موبايلك (لحد 20 ميجا) وهقصلك أول 30 ثانية منه"); return
    if data == "mode_story_convert": reset_modes(u); u["story_convert_mode"]=True; u["state"]="story_convert"; save_data(); await q.message.reply_text("📱 ابعت فيديو (لحد 20 ميجا) وهحوله لمقاس ستوري 1080x1920"); return
    if data == "mode_meme": reset_modes(u); u["meme_mode"]=True; u["state"]="meme_photo"; save_data(); await q.message.reply_text("😂 ابعت صورة وبعدها اكتب النص اللي عايزه على الميم"); return
    if data == "mode_follow": reset_modes(u); u["follow_mode"]=True; u["state"]="follow"; save_data(); await q.message.reply_text("🔔 اكتب يوزر التيك توك من غير @ - مثال: ahmed123"); return
    if data == "mode_voice": reset_modes(u); u["state"]="voice"; save_data(); await q.message.reply_text("🎤 ابعت فويس بالنص اللي عايز تدور عليه"); return
    if data == "mode_quiz":
        if u.get("quiz_date") == str(date.today()):
            await q.message.reply_text("🎁 جاوبت على مسابقة النهاردة، تعالى بكرة"); return
        qq, aa = get_today_quiz(); u["state"]="quiz"; save_data(); await q.message.reply_text(f"🎁 مسابقة اليوم:\n\n{qq}\n\nاكتب اجابتك"); return
    if data == "mode_leader":
        users_sorted = sorted(DATA["users"].items(), key=lambda x: int(x[1].get("invites",0)) if isinstance(x[1], dict) else 0, reverse=True)[:10]
        txt = "🏆 لوحة الشرف - اكتر ناس دعوا صحابهم:\n\n"
        for i,(tid,uu) in enumerate(users_sorted,1):
            txt += f"{i}. ID ***{str(tid)[-4:]} - {uu.get('invites',0)} دعوة - {uu.get('points',0)} نقطة\n"
        await q.message.reply_text(txt); return
    if data == "mode_cover": reset_modes(u); u["cover_mode"]=True; u["state"]="cover"; save_data(); await q.message.reply_text("🖼️ ابعت فيديو (لحد 20 ميجا) وهعملك غلاف ليه"); return
    if data == "mode_caption": reset_modes(u); u["caption_mode"]=True; u["state"]="caption"; save_data(); await q.message.reply_text("✍️ ابعت لينك الفيديو او اكتب عنوانه وهعملك كابشن وهاشتاجات"); return
    if data == "mode_nomusic": reset_modes(u); u["remove_music_mode"]=True; u["state"]="nomusic"; save_data(); await q.message.reply_text("🎼 ابعت فيديو (لحد 20 ميجا) وهقلل الترددات العالية بتاعة الموسيقى (مش فصل كامل)"); return
    if data == "mode_merge": reset_modes(u); u["state"]="merge"; u["merge_videos"]=[]; save_data(); await q.message.reply_text("🔗 ابعت اول فيديو وبعدين التاني (كل واحد لحد 20 ميجا)"); return
    if data == "mode_trim": reset_modes(u); u["trim_mode"]=True; u["state"]="trim_video"; save_data(); await q.message.reply_text("✂️ ابعت الفيديو وبعدين اكتب الوقت - مثال: من 0:10 لـ 0:30"); return
    if data == "mode_pdf2img": reset_modes(u); u["pdf2img_mode"]=True; u["state"]="pdf2img"; save_data(); await q.message.reply_text("📄 ابعت ملف PDF وهحوله لصور (أول 3 صفحات)"); return
    if data == "mode_lyrics": reset_modes(u); u["lyrics_mode"]=True; u["state"]="lyrics"; save_data(); await q.message.reply_text("🎤 ابعت لينك الاغنية او اسمها وهجيب الصوت + كلماتها"); return
    if data == "mode_mp3": reset_modes(u); u["download_mode"] = "audio"; save_data(); await q.message.reply_text("🎵 تمام، ابعت اللينك وهحوله MP3 على طول"); return
    if data == "mode_video": reset_modes(u); u["download_mode"] = "video"; save_data(); await q.message.reply_text(f"📥 تمام، اختار الجودة:", reply_markup=quality_keyboard(uid)); return
    if data == "mode_nowm": reset_modes(u); u["download_mode"] = "nowm"; save_data(); await q.message.reply_text("✨ تمام، ابعت لينك تيك توك وهجيبهولك من غير علامة مائية"); return
    if data == "mode_playlist": reset_modes(u); u["download_mode"] = "playlist"; save_data(); await q.message.reply_text("📃 ابعت لينك قايمة التشغيل، هجيب أول 5 فيديوهات"); return
    if data == "mode_story": reset_modes(u); u["story_mode"] = True; u["state"] = "story"; save_data(); await q.message.reply_text("📸 ابعت لينك الستوري من انستا على طول"); return
    if data == "mode_explore":
        await q.message.reply_text("🔥 بدور على الترند...")
        trends = await asyncio.to_thread(get_trending)
        if not trends: await q.message.reply_text(T(uid, "not_found")); return
        btns = []
        for t in trends:
            if t["author"] == "youtube":
                cb_data = f"pick_{t['id']}"  # نتيجة يوتيوب مش تيك توك
            else:
                TREND_URLS[t["id"]] = t["url"]
                cb_data = f"pick_tiktok_{t['id']}"
            btns.append([InlineKeyboardButton(f"🎵 {t['title'][:35]}", callback_data=cb_data)])
        btns.append([InlineKeyboardButton(f"⬅️ {T(uid, 'back')}", callback_data="home")])
        await q.message.reply_text("🔥 ترند دلوقتي:", reply_markup=InlineKeyboardMarkup(btns)); return
    if data == "mode_gif": reset_modes(u); u["gif_mode"] = True; save_data(); await q.message.reply_text("🎞️ ابعت فيديو من موبايلك (لحد 20 ميجا) وهحوله GIF"); return
    if data == "mode_compress": reset_modes(u); u["compress_mode"] = True; save_data(); await q.message.reply_text("🗜️ ابعت فيديو من موبايلك (لحد 20 ميجا) وهضغطهولك"); return
    if data == "mode_extract": reset_modes(u); u["state"] = "extract"; save_data(); await q.message.reply_text("🎧 ابعت فيديو من موبايلك (لحد 20 ميجا) وهطلعلك الصوت بتاعه MP3"); return
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
            with open(pdf_path, "rb") as f: await q.message.reply_document(f, filename="Nezel.pdf", caption=T(uid, "pdf_done"), **UP)
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
            url = hist[idx]["url"]
            await do_download_flow(q.message, uid, url, quality=u.get("quality", "720"))
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
            url = favs[idx]["url"]
            await do_download_flow(q.message, uid, url, quality=u.get("quality", "720"))
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
        await do_download_flow(q.message, uid, url, want_audio=True, quality=u.get("quality", "720")); return

async def handle_dl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try: await q.answer()
    except: pass
    uid = q.from_user.id
    if is_banned(uid): await q.message.reply_text(T(uid, "banned_msg")); return
    u = get_user(uid); data = q.data or ""
    want_audio = False; quality = u.get("quality", "720"); url = ""
    if data.startswith("dl_tiktok_") or data.startswith("dl_ttaudio_"):
        want_audio = data.startswith("dl_ttaudio_")
        vid = data.split("_", 2)[2]
        url = TREND_URLS.get(vid) or f"https://www.tiktok.com/@tiktok/video/{vid}"
    else:
        vid = ""
        for pre, qual, aud in (("dl_audio_", None, True), ("dl_1080_", "1080", False), ("dl_720_", "720", False), ("dl_2k_", "2k", False), ("dl_4k_", "4k", False), ("dl_video_", None, False)):
            if data.startswith(pre):
                vid = data[len(pre):]; want_audio = aud
                if qual: quality = qual; u["quality"] = qual; save_data()
                break
        if not vid: return
        url = "https://www.youtube.com/watch?v=" + vid
    # بنستخدم نفس مسار التحميل (حجم + إلغاء + احصائيات + رسايل خطأ)
    await do_download_flow(q.message, uid, url, want_audio=want_audio, quality=quality)

async def handle_choose_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); uid = q.from_user.id; data = q.data or ""
    if data.startswith("pick_tiktok_"):
        vid = data.replace("pick_tiktok_", "")
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"🎵 {T(uid, 'download_mp3')}", callback_data=f"dl_ttaudio_{vid}")],[InlineKeyboardButton(f"📥 {T(uid, 'download_video')} - 720", callback_data=f"dl_tiktok_{vid}")],[InlineKeyboardButton(f"⬅️ {T(uid, 'back')}", callback_data="home")]])
        await q.message.reply_text(f"{T(uid, 'choose_format')}", reply_markup=kb); return
    if not data.startswith("pick_"): return
    vid = data.replace("pick_", "")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"🎵 {T(uid, 'download_mp3')}", callback_data=f"dl_audio_{vid}")],[InlineKeyboardButton(f"📥 {T(uid, 'download_video')} - 720", callback_data=f"dl_720_{vid}")],[InlineKeyboardButton(f"📥 {T(uid, 'download_video')} - 1080", callback_data=f"dl_1080_{vid}")],[InlineKeyboardButton(f"📥 {T(uid, 'download_video')} - 2K", callback_data=f"dl_2k_{vid}")],[InlineKeyboardButton(f"📥 {T(uid, 'download_video')} - 4K", callback_data=f"dl_4k_{vid}")],[InlineKeyboardButton(f"⬅️ {T(uid, 'back')}", callback_data="home")]])
    await q.message.reply_text(f"{T(uid, 'choose_format')}", reply_markup=kb)

async def do_download_flow(message, uid, url, want_audio=False, quality="720", is_playlist=False, check_rate=True):
    u = get_user(uid)
    now = time.time()
    if check_rate and now - float(u.get("last_dl_at", 0)) < 3 and not is_vip(uid):
        await message.reply_text(T(uid, "rate_limit")); return False
    u["last_dl_at"] = now; save_data()
    key = str(uid)
    CANCEL_FLAGS[key] = False
    plat = platform_of(url)
    loop = asyncio.get_running_loop()
    sem = get_sem()
    queued = sem.locked()
    status_msg = await message.reply_text(f"⏳ {T(uid, 'downloading')} 0%" + (f"\n{T(uid, 'queue_wait')}" if queued else ""), reply_markup=cancel_keyboard(uid))
    last_pct = [0]
    def cb(pct):  # بيتنادى من thread التحميل
        if pct - last_pct[0] >= 20:
            last_pct[0] = pct
            try: asyncio.run_coroutine_threadsafe(status_msg.edit_text(f"⏳ {T(uid, 'downloading')} {pct}%", reply_markup=cancel_keyboard(uid)), loop)
            except Exception: pass
    def cancelled():
        return bool(CANCEL_FLAGS.get(key))
    async with sem:
        if cancelled():
            await status_msg.edit_text(T(uid, "cancelled")); return False
        if is_playlist:
            urls = await asyncio.to_thread(download_playlist, url, uid, quality)
            if not urls: await status_msg.edit_text(T(uid, "download_failed")); return False
            await status_msg.edit_text(f"📃 لقيت {len(urls)} فيديوهات، بحملهم...", reply_markup=cancel_keyboard(uid))
            for idx, pu in enumerate(urls):
                if cancelled(): break
                base = "/tmp/" + str(uid) + "_" + str(int(time.time()*1000)) + f"_{idx}"
                files, thumb = await asyncio.to_thread(download_with_ytdlp, pu, base, want_audio, quality, None, cancelled)
                fixed_files = []
                for fp in files:
                    fixed = await ensure_size_ok(fp, uid)
                    if not fixed: await message.reply_text(T(uid, "too_big")); continue
                    fixed_files.append(fixed)
                if fixed_files:
                    await send_downloaded(message, fixed_files, want_audio, None, thumb)
            await status_msg.edit_text(T(uid, "cancelled") if cancelled() else "✅ خلصت القايمة")
            bump_stats(plat); return True
        base = "/tmp/" + str(uid) + "_" + str(int(time.time()*1000))
        files, thumb = await asyncio.to_thread(download_with_ytdlp, url, base, want_audio, quality, cb, cancelled)
        if cancelled():
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
        sent_ok = await send_downloaded(message, ok_files, want_audio, kb, thumb)
        if not sent_ok:
            await message.reply_text(T(uid, "download_failed"))
            return False
        bump_stats(plat)
        cleanup_tmp()
        return True

def transcribe_wav(wav):
    try:
        import whisper  # اختياري: pip install openai-whisper (تقيل)
        m = whisper.load_model("tiny")
        return (m.transcribe(wav).get("text", "") or "").strip()
    except Exception as e:
        print("whisper err:", e)
        return ""

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user: return
    uid = update.effective_user.id
    if is_banned(uid): return
    u = get_user(uid)
    if u.get("state") != "voice":
        return
    await update.message.reply_text("🎤 سمعتك، بدور على اللي قولته...")
    try:
        vf = await context.bot.get_file(update.message.voice.file_id)
        ts = int(time.time() * 1000)
        path = f"/tmp/{uid}_{ts}_voice.ogg"
        await vf.download_to_drive(path)
        wav = path.replace(".ogg", ".wav")
        await arun(["ffmpeg", "-y", "-i", path, wav], 30)
        text = await asyncio.to_thread(transcribe_wav, wav)
        for p in (path, wav):
            try: os.remove(p)
            except: pass
        if not text:
            await update.message.reply_text("🎤 مش عرفت اسمع كويس، اكتب الاسم كتابة وهادور عليه")
            u["state"] = "search"; save_data(); return
        u["state"] = "home"; save_data()
        await update.message.reply_text(f"🎤 سمعت: {text}\nبدور...")
        results = await asyncio.to_thread(do_search, text)
        if not results:
            await update.message.reply_text(T(uid, "not_found")); return
        buttons = [[InlineKeyboardButton(f"🎵 {r['title'][:35]}", callback_data=f"pick_{r['id']}")] for r in results]
        buttons.append([InlineKeyboardButton(f"⬅️ {T(uid, 'back')}", callback_data="home")])
        await update.message.reply_text(T(uid, "choose_result"), reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        await update.message.reply_text(f"فشل الفويس: {e}")

def _cleanup_glob(pattern):
    for p in glob.glob(pattern):
        try: os.remove(p)
        except: pass

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # الرسايل المتعدلة / بوستات القنوات مفيهاش update.message
    if not update.message or not update.effective_user: return
    uid = update.effective_user.id
    if is_banned(uid): await update.message.reply_text(T(uid, "banned_msg")); return
    u = get_user(uid); user = update.effective_user

    # ===== PDF -> صور =====
    if update.message.document and update.message.document.mime_type == "application/pdf" and u.get("state") == "pdf2img":
        try:
            await update.message.reply_text("⏳ بحول PDF لصور...")
            f = await context.bot.get_file(update.message.document.file_id)
            pdf_path = f"/tmp/{uid}_{int(time.time()*1000)}_in.pdf"
            await f.download_to_drive(pdf_path)
            try:
                import fitz
            except ImportError:
                await update.message.reply_text("⚠️ تحويل PDF مش متاح على السيرفر ده، ضيف PyMuPDF في requirements.txt")
                reset_modes(u); save_data(); return
            doc = fitz.open(pdf_path)
            total = len(doc)
            for i in range(min(3, total)):
                pix = doc[i].get_pixmap(dpi=150)
                img_path = f"/tmp/{uid}_{int(time.time()*1000)}_p{i}.png"
                pix.save(img_path)
                with open(img_path, "rb") as ff: await update.message.reply_photo(ff, caption=f"📄 صفحة {i+1} من {total}", **UP)
                try: os.remove(img_path)
                except: pass
            doc.close()
            try: os.remove(pdf_path)
            except: pass
            if total > 3: await update.message.reply_text("ℹ️ بعتلك أول 3 صفحات بس")
            reset_modes(u); save_data(); return
        except Exception as e:
            await update.message.reply_text(f"فشل: {e}"); return

    # ===== ادوات الفيديو =====
    is_video_msg = bool(update.message.video or (update.message.document and update.message.document.mime_type and "video" in update.message.document.mime_type))
    if is_video_msg:
        vobj = update.message.video or update.message.document
        state = u.get("state")
        video_tool = bool(u.get("gif_mode") or u.get("compress_mode") or state in ["merge", "extract", "cut", "story_convert", "nomusic", "trim_video", "cover", "trim"])
        if not video_tool:
            await update.message.reply_text(f"🎬 {T(uid, 'choose_video_action')}", reply_markup=main_keyboard(uid)); return
        if (vobj.file_size or 0) > TG_DL_LIMIT:
            await update.message.reply_text("⚠️ تليجرام بيسمح للبوتات تنزل ملفات لحد 20 ميجا بس، ابعت فيديو أصغر")
            return
        ts = int(time.time() * 1000)
        in_path = f"/tmp/{uid}_{ts}_in.mp4"
        try:
            f = await context.bot.get_file(vobj.file_id)
            await f.download_to_drive(in_path)
            # --- دمج ---
            if state == "merge":
                u["merge_videos"].append(in_path); save_data()
                if len(u["merge_videos"]) < 2:
                    await update.message.reply_text("✅ اول فيديو وصل، ابعت التاني"); return
                await update.message.reply_text("⏳ بدمج الفيديوهين...")
                vids = list(u["merge_videos"])[:2]
                list_path = f"/tmp/{uid}_{ts}_list.txt"
                with open(list_path, "w") as lf:
                    for pp in vids: lf.write(f"file '{pp}'\n")
                out = f"/tmp/{uid}_{ts}_merged.mp4"
                await arun(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", out], 120)
                if not (os.path.exists(out) and os.path.getsize(out) > 1000):
                    # لو الفيديوهين مختلفين في الكودك/المقاس بنعيد الترميز
                    await arun(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-c:a", "aac", "-movflags", "+faststart", out], 240)
                if os.path.exists(out) and os.path.getsize(out) > 1000:
                    with open(out, "rb") as ff: await update.message.reply_video(ff, caption="🔗 تم الدمج", **UP)
                else:
                    await update.message.reply_text("الدمج فشل")
                for pp in list(u["merge_videos"]) + [list_path, out]:
                    try: os.remove(pp)
                    except: pass
                u["merge_videos"] = []; reset_modes(u); save_data(); return
            # --- تقطيع: بنحفظ الفيديو ونستنى الوقت ---
            if state in ("trim_video", "trim") or u.get("trim_mode"):
                u["trim_video"] = in_path; u["state"] = "trim_wait_time"; save_data()
                await update.message.reply_text("✂️ الفيديو وصل، اكتب الوقت - مثال: من 0:10 لـ 0:30"); return
            await update.message.reply_text("⏳ بحول الفيديو...")
            if u.get("gif_mode"):
                out_path = f"/tmp/{uid}_{ts}_out.gif"
                await arun(["ffmpeg", "-y", "-i", in_path, "-vf", "fps=10,scale=480:-1:flags=lanczos", out_path], 90)
                if not os.path.exists(out_path) or os.path.getsize(out_path) < 1000: await update.message.reply_text("الـ ffmpeg مش شغال على السيرفر")
                else:
                    with open(out_path, "rb") as ff: await update.message.reply_document(ff, filename="Nezel.gif", **UP)
            elif u.get("compress_mode"):
                out_path = f"/tmp/{uid}_{ts}_out.mp4"
                ok, _ = await asyncio.to_thread(compress_video_file, in_path, out_path, 28)
                if not ok:
                    ok, _ = await asyncio.to_thread(compress_video_file, in_path, out_path, 32)
                if ok:
                    with open(out_path, "rb") as ff: await update.message.reply_video(ff, caption="🗜️ تم ضغط الفيديو", **UP)
                else:
                    await update.message.reply_text("الضغط فشل")
            elif state == "cut" or u.get("cut_mode"):
                out_path = f"/tmp/{uid}_{ts}_cut.mp4"
                if await asyncio.to_thread(cut_best_part, in_path, out_path):
                    with open(out_path, "rb") as ff: await update.message.reply_video(ff, caption="✂️ أول 30 ثانية", **UP)
                else: await update.message.reply_text("القص فشل")
            elif state == "story_convert" or u.get("story_convert_mode"):
                out_path = f"/tmp/{uid}_{ts}_story.mp4"
                if await asyncio.to_thread(convert_to_story, in_path, out_path):
                    with open(out_path, "rb") as ff: await update.message.reply_video(ff, caption="📱 جاهز للستوري 1080x1920", **UP)
                else: await update.message.reply_text("التحويل فشل")
            elif state == "nomusic":
                out_path = f"/tmp/{uid}_{ts}_nomusic.mp4"
                await arun(["ffmpeg", "-y", "-i", in_path, "-af", "lowpass=f=3000", out_path], 120)
                if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                    with open(out_path, "rb") as ff: await update.message.reply_video(ff, caption="🎼 قللت الترددات العالية (ده مش فصل حقيقي للموسيقى)", **UP)
                else: await update.message.reply_text("فشل")
            elif state == "cover" or u.get("cover_mode"):
                out_img = f"/tmp/{uid}_{ts}_cover.jpg"
                await arun(["ffmpeg", "-y", "-i", in_path, "-ss", "1", "-vframes", "1", out_img], 30)
                if os.path.exists(out_img):
                    with open(out_img, "rb") as ff: await update.message.reply_photo(ff, caption="🖼️ غلاف الفيديو", **UP)
                else: await update.message.reply_text("فشل الغلاف")
            else:
                out_path = f"/tmp/{uid}_{ts}_out.mp3"
                await arun(["ffmpeg", "-y", "-i", in_path, "-vn", "-ab", "192k", out_path], 90)
                if not os.path.exists(out_path) or os.path.getsize(out_path) < 1000: await update.message.reply_text("استخراج الصوت فشل")
                else:
                    with open(out_path, "rb") as ff: await update.message.reply_audio(ff, title="Nezel Audio", **UP)
            _cleanup_glob(f"/tmp/{uid}_{ts}_*")
            reset_modes(u); save_data(); return
        except Exception as e:
            _cleanup_glob(f"/tmp/{uid}_{ts}_*")
            await update.message.reply_text(f"فشل: {e}"); reset_modes(u); save_data(); return

    # ===== صور =====
    if update.message.photo:
        caption = (update.message.caption or "").strip(); cap_url = extract_url(caption)
        if u.get("state") == "meme_photo" or u.get("meme_mode"):
            u["meme_photo"] = update.message.photo[-1].file_id; u["state"] = "meme_text"; save_data()
            await update.message.reply_text("😂 الصورة وصلت، اكتب النص اللي عايزه على الميم"); return
        if cap_url and not u.get("pdf_mode"):
            text = caption
        elif u.get("pdf_mode"):
            u["pdf_photos"].append(update.message.photo[-1].file_id); save_data()
            await update.message.reply_text(f"{T(uid, 'pdf_added')} {len(u['pdf_photos'])} ✅"); return
        else: return
        if not cap_url: return
    else:
        text = (update.message.text or update.message.caption or "").strip()
    if not text: return
    if not u.get("lang"):
        await update.message.reply_text("اختر لغتك\n\nChoose your language", reply_markup=lang_keyboard()); return

    # ===== تقطيع - انتظار الوقت =====
    if u.get("state") == "trim_wait_time":
        m = re.findall(r'(\d+):(\d+)', text)
        in_path = u.get("trim_video")
        if len(m) < 2:
            await update.message.reply_text("اكتب زي كده: من 0:10 لـ 0:30"); return
        if not in_path or not os.path.exists(in_path):
            await update.message.reply_text("الفيديو مبقاش موجود، ابعته تاني")
            reset_modes(u); save_data(); return
        s = int(m[0][0]) * 60 + int(m[0][1]); e = int(m[1][0]) * 60 + int(m[1][1])
        if e <= s:
            await update.message.reply_text("وقت النهاية لازم يكون اكبر من البداية، اكتب تاني: من 0:10 لـ 0:30"); return
        out = f"/tmp/{uid}_{int(time.time()*1000)}_trim_out.mp4"
        # بنعيد الترميز عشان القص يبقى دقيق (copy كان بيقص على اقرب keyframe)
        await arun(["ffmpeg", "-y", "-ss", str(s), "-i", in_path, "-t", str(e - s), "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-c:a", "aac", "-movflags", "+faststart", out], 120)
        if os.path.exists(out) and os.path.getsize(out) > 1000:
            with open(out, "rb") as ff: await update.message.reply_video(ff, caption=f"✂️ من {s} لـ {e} ثانية", **UP)
        else:
            await update.message.reply_text("القص فشل")
        for pp in (out, in_path):
            try: os.remove(pp)
            except: pass
        reset_modes(u); save_data(); return

    if u.get("state") == "meme_text" and u.get("meme_photo"):
        try:
            f = await context.bot.get_file(u["meme_photo"]); p = f"/tmp/{uid}_meme.jpg"; await f.download_to_drive(p)
            out = f"/tmp/{uid}_meme_out.jpg"
            if await asyncio.to_thread(make_meme, p, text, out):
                with open(out, "rb") as ff: await update.message.reply_photo(ff, caption="😂 الميم جاهز", **UP)
            else: await update.message.reply_text("فشل الميم")
            _cleanup_glob(f"/tmp/{uid}_meme*.jpg")
            reset_modes(u); save_data(); return
        except Exception as e: await update.message.reply_text(f"فشل: {e}"); return

    if u.get("state") == "follow":
        username = text.replace("@", "").strip()
        follows = DATA.get("follows", {})
        if username not in follows: follows[username] = []
        if uid not in follows[username]: follows[username].append(uid)
        DATA["follows"] = follows; save_data()
        await update.message.reply_text(f"🔔 تمام، هبعتلك لما @{username} ينزل جديد"); reset_modes(u); save_data(); return

    if u.get("state") == "quiz":
        qq, aa = get_today_quiz()
        today = str(date.today())
        if u.get("quiz_date") == today:
            await update.message.reply_text("🎁 جاوبت على مسابقة النهاردة، تعالى بكرة")
        else:
            u["quiz_date"] = today  # محاولة واحدة في اليوم
            ua = norm_ar(text); ca = norm_ar(aa)
            if ua == ca or (len(ca) >= 2 and ca in ua):
                u["points"] = int(u.get("points", 0)) + 10
                await update.message.reply_text("🎉 صح! +10 نقط")
            else:
                await update.message.reply_text(f"❌ غلط، الصح: {aa}")
        reset_modes(u); save_data(); return

    if u.get("state") == "caption" or u.get("caption_mode"):
        cap = make_caption(text)
        await update.message.reply_text(f"✍️ الكابشن:\n\n{cap}")
        reset_modes(u); save_data(); return

    if u.get("state") == "lyrics" or u.get("lyrics_mode"):
        reset_modes(u); save_data()
        await update.message.reply_text("🎤 بجيب الصوت والكلمات...")
        url = extract_url(text)
        if url:
            title = (await asyncio.to_thread(get_title, url)) or text
        else:
            results = await asyncio.to_thread(do_search, text)
            if not results:
                await update.message.reply_text(T(uid, "not_found")); return
            url = f"https://www.youtube.com/watch?v={results[0]['id']}"
            title = results[0]["title"]
        lyr = await asyncio.to_thread(get_lyrics, title)
        await do_download_flow(update.message, uid, url, want_audio=True, quality="720")
        if lyr: await update.message.reply_text(f"🎤 الكلمات:\n\n{lyr[:3000]}")
        else: await update.message.reply_text("⚠️ ملقيتش كلمات للاغنية دي")
        return

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
        has_ar = any('\u0600' <= c <= '\u06FF' for c in text); target = "en" if has_ar else "ar"; tr = await asyncio.to_thread(translate_text, text, target)
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
            files, thumb = await asyncio.to_thread(download_with_ytdlp, url, base, False, u.get("quality", "720"))
            if files: await send_downloaded(update.message, files, False, None, thumb)
            else: await update.message.reply_text("مش عارف اجيب الستوري، انستا قافل الستوري من غير تسجيل دخول")
        else: await update.message.reply_text("📸 ابعت لينك الستوري مش اليوزر")
        return
    if u.get("state") == "movies" or u.get("movie_mode"):
        reset_modes(u); save_data(); await update.message.reply_text("🎬 بدور...")
        res = await asyncio.to_thread(search_movies, text)
        if not res: await update.message.reply_text(T(uid, "not_found")); return
        out = "🎬 لقيت دول:\n\n"
        for r in res: out += f"🎬 {r['name']}\n{r['summary'][:150]}\n{r['url']}\n\n"
        await update.message.reply_text(out); return
    if u.get("state") == "wallpaper" or u.get("wallpaper_mode"):
        reset_modes(u); save_data(); await update.message.reply_text("🖼️ بجيبلك خلفيات...")
        sent = 0
        for w in await asyncio.to_thread(get_wallpapers, text):
            if sent >= 3: break
            try:
                await update.message.reply_photo(w, caption="🖼️ خلفية HD من نزل"); sent += 1
            except Exception as e: print("wallpaper send err:", e)
        if not sent: await update.message.reply_text(T(uid, "not_found"))
        return
    if u.get("state") == "search":
        u["state"] = "home"; save_data()
        msg = await update.message.reply_text(f"🔍 {T(uid, 'searching')}: {text}\n{T(uid, 'search_wait')}...")
        results = await asyncio.to_thread(do_search, text)
        if not results: await msg.edit_text(T(uid, "not_found")); return
        buttons = []
        for r in results:
            title = r["title"]
            if len(title) > 35: title = title[:35] + "..."
            buttons.append([InlineKeyboardButton(f"🎵 {title}", callback_data=f"pick_{r['id']}")])
        buttons.append([InlineKeyboardButton(f"⬅️ {T(uid, 'back')}", callback_data="home")])
        await msg.edit_text(f"{T(uid, 'choose_result')}:", reply_markup=InlineKeyboardMarkup(buttons)); return

    # ===== تحميل اكتر من لينك =====
    SUPPORTED = ["youtube.com", "youtu.be", "tiktok.com", "instagram.com", "facebook.com", "fb.watch", "pinterest.", "reddit.com", "redd.it", "twitch.tv", "soundcloud.com", "t.me/"]
    urls_all = extract_all_urls(text)
    if len(urls_all) > 1:
        await update.message.reply_text(f"🔗 لقيت {len(urls_all)} لينكات، بحملهم واحد واحد...")
        for uu in urls_all[:5]:
            if any(x in uu for x in SUPPORTED):
                u["last_link"] = uu; save_history(u, uu, uu)
                await do_download_flow(update.message, uid, uu, want_audio=(u.get("download_mode") == "audio"), quality=u.get("quality", "720"), is_playlist=(u.get("download_mode") == "playlist"), check_rate=False)
        if u.get("download_mode") == "playlist": u["download_mode"] = "video"; save_data()
        return
    url = extract_url(text)
    if url and any(x in url for x in SUPPORTED):
        u["last_link"] = url; save_history(u, url, url)
        mode = u.get("download_mode", "video")
        want_audio = (mode == "audio")
        is_playlist = (mode == "playlist")
        if is_playlist:  # وضع القايمة لمرة واحدة، عشان اللينكات العادية متبوظش بعدها
            u["download_mode"] = "video"; save_data()
        await do_download_flow(update.message, uid, url, want_audio=want_audio, quality=u.get("quality", "720"), is_playlist=is_playlist)
        return
    if "http" in text:
        await update.message.reply_text(f"⚠️ اللينك ده مش مدعوم\nاللي شغال: يوتيوب / تيك توك / انستا / فيس / Pinterest / Reddit / Twitch / SoundCloud\nابعت لينك منهم"); return
    await update.message.reply_text(show_main_menu_text(uid, user.first_name or ""), reply_markup=main_keyboard(uid))

async def backup_job(context: ContextTypes.DEFAULT_TYPE):
    # نسخة احتياطية كل 6 ساعات - بيعمل save_data بس
    save_data()
    print("backup done", datetime.now())

async def on_error(update, context: ContextTypes.DEFAULT_TYPE):
    print("ERROR:", repr(context.error))

def main():
    if not BOT_TOKEN: print("ERROR: BOT_TOKEN missing"); return
    app = (Application.builder().token(BOT_TOKEN)
           .concurrent_updates(True)  # من غيرها البوت بيخدم يوزر واحد بس في نفس الوقت
           .connect_timeout(30).read_timeout(60).write_timeout(60).pool_timeout(30)
           .build())
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
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_message))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_message))
    app.add_handler(MessageHandler(filters.CAPTION, handle_message))
    app.add_error_handler(on_error)
    # backup كل 6 ساعات (محتاج: pip install "python-telegram-bot[job-queue]")
    if app.job_queue:
        app.job_queue.run_repeating(backup_job, interval=21600, first=21600)
    else:
        print("WARNING: job_queue مش متسطب - الباك اب الدوري مش شغال")
    print("Bot started - Full version + All New Features")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
