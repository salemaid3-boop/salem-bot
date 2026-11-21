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
    "last_link": "", "pdf_photos": [], "history": [], "favs": []
}

def get_user(uid):
    uid = str(uid)
    if uid not in DATA["users"] or not isinstance(DATA["users"][uid], dict):
        DATA["users"][uid] = dict(DEFAULT_USER)
        save_data()
    u = DATA["users"][uid]
    for k, v in DEFAULT_USER.items():
        if k not in u:
            u[k] = list(v) if isinstance(v, list) else v
    return u

def reset_modes(u):
    u["support_mode"] = False
    u["translate_mode"] = False
    u["summarize_mode"] = False
    u["pdf_mode"] = False
    u["state"] = "home"

def is_vip(uid):
    try:
        return float(get_user(uid).get("vip", 0)) > time.time()
    except:
        return False

# ================= TRANSLATE - متظبط 100% =================
def translate_text(text, target="en"):
    text = text.strip()
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

# ================= SUMMARIZE - تلخيص حقيقي =================
def summarize_text(text):
    text = text.strip()
    if len(text) < 200:
        return text
    sentences = re.split(r'[.!؟\n]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    if len(sentences) <= 3:
        return text
    picked = []
    picked.append(sentences[0])
    by_len = sorted(sentences, key=len, reverse=True)[:2]
    for s in by_len:
        if s not in picked:
            picked.append(s)
    if sentences[-1] not in picked:
        picked.append(sentences[-1])
    return ". ".join(picked) + "."

TEXTS = {
    "ar": {
        "choose_lang_title": "اختر لغتك",
        "welcome": "اهلا بيك في نزل",
        "welcome_sub": "نزل فيديوهات وصوتيات من كل المنصات",
        "points": "نقطك",
        "invites": "دعواتك",
        "vip_left": "فاضل في VIP",
        "vip_days": "يوم",
        "not_vip": "انت مش VIP",
        "send_link": "ابعت لينك دلوقتي",
        "search_btn": "بحث بالاسم",
        "download_mp3": "تحميل MP3",
        "download_video": "تحميل فيديو",
        "quality_720": "جودة 720",
        "quality_1080": "جودة 1080",
        "pdf_btn": "صور لـ PDF",
        "fav_btn": "مفضلتي",
        "history_btn": "سجلي",
        "points_btn": "نقطي ودعوتي",
        "vip_btn": "VIP",
        "lang_btn": "اللغة",
        "support_btn": "الدعم",
        "admin_btn": "لوحة تحكم",
        "translate_btn": "ترجمة",
        "summarize_btn": "تلخيص",
        "search_prompt": "اكتب اسم الاغنية او الفيديو اللي بتدور عليه",
        "searching": "بدور علي",
        "search_wait": "استنى ثواني",
        "not_found": "ملقيتش حاجة بالاسم ده، جرب اسم تاني او ابعت لينك على طول",
        "choose_result": "اختر من النتايج دي",
        "choose_format": "اختار الصيغة",
        "downloading": "بنحمل دلوقتي، استنى",
        "download_done": "تم التحميل",
        "download_failed": "التحميل فشل، جرب تاني او ابعت لينك تاني",
        "support_prompt": "اكتب رسالتك للدعم",
        "support_sent": "رسالتك اتبعت للدعم",
        "support_reply_title": "رد الدعم",
        "help_text": "ابعت لينك من يوتيوب او تيك توك او انستا او فيسبوك، او دوس بحث بالاسم",
        "lang_changed": "تم تغيير اللغة",
        "vip_done": "بقيت VIP لمدة 30 يوم",
        "vip_congrats": "مبروك، بقيت VIP",
        "back": "رجوع",
        "home": "القايمة الرئيسية",
        "translate_ask": "ابعت النص اللي عايز تترجمه، لو عربي هترجمه انجليزي، ولو انجليزي هترجمه عربي",
        "translate_done": "الترجمة",
        "summarize_ask": "ابعت النص اللي عايز تلخصه",
        "summarize_done": "التلخيص",
        "pdf_ask": "ابعت الصور وانا هحولها PDF، ولما تخلص دوس انهاء",
        "pdf_done": "تم تحويل الصور لـ PDF",
        "pdf_added": "تم اضافة الصورة",
        "pdf_no_photos": "ابعت صور الاول",
        "converting_mp3": "بحولها اغنية دلوقتي، استنى",
        "no_link_mp3": "ابعت لينك الفيديو الاول",
        "history_empty": "سجلك فاضي لسه",
        "fav_empty": "مفضلتك فاضية لسه",
    },
    "en": {
        "choose_lang_title": "Choose your language",
        "welcome": "Welcome to Nezel",
        "welcome_sub": "Download videos and audios from all platforms",
        "points": "Points",
        "invites": "Invites",
        "vip_left": "VIP left",
        "vip_days": "days",
        "not_vip": "You are not VIP",
        "send_link": "Send link now",
        "search_btn": "Search by name",
        "download_mp3": "Download MP3",
        "download_video": "Download Video",
        "quality_720": "Quality 720",
        "quality_1080": "Quality 1080",
        "pdf_btn": "Images to PDF",
        "fav_btn": "My Favorites",
        "history_btn": "My History",
        "points_btn": "My Points",
        "vip_btn": "VIP",
        "lang_btn": "Language",
        "support_btn": "Support",
        "admin_btn": "Admin Panel",
        "translate_btn": "Translate",
        "summarize_btn": "Summarize",
        "search_prompt": "Type the song or video name you want",
        "searching": "Searching for",
        "search_wait": "Please wait",
        "not_found": "Nothing found with this name, try another name or send link directly",
        "choose_result": "Choose from results",
        "choose_format": "Choose format",
        "downloading": "Downloading now, please wait",
        "download_done": "Download done",
        "download_failed": "Download failed, try again",
        "support_prompt": "Write your message to support",
        "support_sent": "Your message sent to support",
        "support_reply_title": "Support reply",
        "help_text": "Send a link from YouTube, TikTok, Instagram or Facebook, or tap Search",
        "lang_changed": "Language changed",
        "vip_done": "You are now VIP for 30 days",
        "vip_congrats": "Congrats, you are VIP",
        "back": "Back",
        "home": "Main Menu",
        "translate_ask": "Send text to translate, Arabic -> English, English -> Arabic",
        "translate_done": "Translation",
        "summarize_ask": "Send text to summarize",
        "summarize_done": "Summary",
        "pdf_ask": "Send photos and I will make PDF, press Finish when done",
        "pdf_done": "PDF created",
        "pdf_added": "Photo added",
        "pdf_no_photos": "Send photos first",
        "converting_mp3": "Converting to MP3, wait",
        "no_link_mp3": "Send video link first",
        "history_empty": "Your history is empty",
        "fav_empty": "Your favorites is empty",
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

def main_keyboard(uid):
    u = get_user(uid)
    if is_vip(uid):
        days = int((float(u.get("vip", 0)) - time.time()) // 86400) + 1
        vip_txt = f"👑 {T(uid, 'vip_btn')} | {T(uid, 'vip_left')} {max(1, days)} {T(uid, 'vip_days')}"
    else:
        vip_txt = f"👑 {T(uid, 'vip_btn')}"
    kb = [
        [InlineKeyboardButton(f"🎵 {T(uid, 'download_mp3')}", callback_data="help_mp3"), InlineKeyboardButton(f"📥 {T(uid, 'download_video')}", callback_data="help_video")],
        [InlineKeyboardButton(f"🎬 {T(uid, 'quality_1080')}", callback_data="help_video"), InlineKeyboardButton(f"🎬 {T(uid, 'quality_720')}", callback_data="help_video")],
        [InlineKeyboardButton(f"🔍 {T(uid, 'search_btn')}", callback_data="search"), InlineKeyboardButton(f"🖼️ {T(uid, 'pdf_btn')}", callback_data="pdf_menu")],
        [InlineKeyboardButton(f"🌐 {T(uid, 'translate_btn')}", callback_data="tr_menu"), InlineKeyboardButton(f"📝 {T(uid, 'summarize_btn')}", callback_data="sum_menu")],
        [InlineKeyboardButton(f"⭐ {T(uid, 'fav_btn')}", callback_data="fav_info"), InlineKeyboardButton(f"📂 {T(uid, 'history_btn')}", callback_data="history_info")],
        [InlineKeyboardButton(f"🎁 {T(uid, 'points_btn')}", callback_data="points_info"), InlineKeyboardButton(f"{vip_txt}", callback_data="vip_info")],
        [InlineKeyboardButton(f"🌐 {T(uid, 'lang_btn')}", callback_data="lang"), InlineKeyboardButton(f"📞 {T(uid, 'support_btn')}", callback_data="support")],
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
    lines = []
    lines.append(f"✨ {T(uid, 'welcome')} {name} 👑")
    lines.append("")
    lines.append(T(uid, 'welcome_sub'))
    lines.append("────────────────")
    lines.append(f"🎁 {T(uid, 'points')}: {points} / 100")
    lines.append(f"👥 {T(uid, 'invites')}: {invites} / 50")
    lines.append(vip_line)
    lines.append("────────────────")
    lines.append(f"👇 {T(uid, 'send_link')}")
    return "\n".join(lines)

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

def download_with_ytdlp(url, base, want_audio=False, quality="720"):
    try:
        for f in glob.glob(base + ".*"):
            try:
                os.remove(f)
            except:
                pass
        if want_audio:
            fmt = "bestaudio/best"
        else:
            if quality == "1080":
                fmt = "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
            else:
                fmt = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
        opts = {
            "format": fmt,
            "outtmpl": base + ".%(ext)s",
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "socket_timeout": 90,
            "cookiefile": "/etc/secrets/cookies.txt" if os.path.exists("/etc/secrets/cookies.txt") else ("cookies.txt" if os.path.exists("cookies.txt") else None),
            "extractor_args": {"youtube": {"player_client": [["android", "ios", "web", "tv", "mweb"]], "player_skip": [ "configs"]}},
            "http_headers": {"User-Agent": "Mozilla/5.0"},
        }
        if want_audio:
            opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        files = glob.glob(base + ".*")
        files = [f for f in files if not f.endswith(".part")]
        return files
    except Exception as e:
        print("download failed: " + str(e))
        return []

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
                inv["points"] = inv.get("points", 0) + 5
                inv["invites"] = inv.get("invites", 0) + 1
                save_data()
                try:
                    await context.bot.send_message(chat_id=int(inviter), text="🎉 حد دخل من لينكك! +5 نقاط")
                except:
                    pass
    reset_modes(u)
    save_data()
    await update.message.reply_text("اختر لغتك\n\nChoose your language", reply_markup=lang_keyboard())
    return

async def vip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Use: /vip 123456")
        return
    if uid != ADMIN_ID and ADMIN_ID != 0:
        await update.message.reply_text("Not allowed")
        return
    try:
        target = str(context.args[0]).strip()
        if not target.isdigit():
            await update.message.reply_text("ID must be numbers")
            return
        tu = get_user(target)
        tu["vip"] = time.time() + 30 * 86400
        save_data()
        await update.message.reply_text(T(uid, "vip_done"))
        try:
            await context.bot.send_message(chat_id=int(target), text=T(int(target), "vip_congrats"))
        except:
            pass
    except Exception as e:
        await update.message.reply_text("Error: " + str(e))

async def reply_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_ID or ADMIN_ID == 0:
        return
    if len(context.args) < 2:
        await update.message.reply_text("Use: /reply 123456 your message")
        return
    target = context.args[0]
    if not target.isdigit():
        await update.message.reply_text("ID wrong")
        return
    msg = " ".join(context.args[1:])
    try:
        full = f"{T(int(target), 'support_reply_title')}\n\n{msg}"
        await context.bot.send_message(chat_id=int(target), text=full)
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
        u["lang"] = "ar"
        reset_modes(u)
        save_data()
        name = q.from_user.first_name or ""
        await q.message.reply_text(T(uid, "lang_changed"))
        await q.message.reply_text(show_main_menu_text(uid, name), reply_markup=main_keyboard(uid))
        return
    if data == "set_lang_en":
        u["lang"] = "en"
        reset_modes(u)
        save_data()
        name = q.from_user.first_name or ""
        await q.message.reply_text(T(uid, "lang_changed"))
        await q.message.reply_text(show_main_menu_text(uid, name), reply_markup=main_keyboard(uid))
        return
    if not u.get("lang"):
        await q.message.reply_text("اختر لغتك\n\nChoose your language", reply_markup=lang_keyboard())
        return
    if data == "search":
        reset_modes(u); u["state"] = "search"; save_data()
        await q.message.reply_text(f"🔍 {T(uid, 'search_prompt')}")
    elif data == "lang":
        await q.message.reply_text("اختر لغتك\n\nChoose your language", reply_markup=lang_keyboard())
    elif data == "support":
        reset_modes(u); u["state"] = "support"; u["support_mode"] = True; save_data()
        await q.message.reply_text(f"📞 {T(uid, 'support_prompt')}")
    elif data == "tr_menu":
        reset_modes(u); u["translate_mode"] = True; save_data()
        await q.message.reply_text(T(uid, "translate_ask"))
    elif data == "sum_menu":
        reset_modes(u); u["summarize_mode"] = True; save_data()
        await q.message.reply_text(T(uid, "summarize_ask"))
    elif data == "pdf_menu":
        reset_modes(u); u["pdf_mode"] = True; u["pdf_photos"] = []; save_data()
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ انهاء وتحويل", callback_data="pdf_finish")]])
        await q.message.reply_text(T(uid, "pdf_ask"), reply_markup=kb)
    elif data == "pdf_finish":
        if not u.get("pdf_photos"):
            await q.message.reply_text(T(uid, "pdf_no_photos")); return
        await q.message.reply_text(T(uid, "downloading"))
        try:
            images = []
            for file_id in u["pdf_photos"]:
                tg_file = await context.bot.get_file(file_id)
                bio = io.BytesIO()
                await tg_file.download_to_memory(bio)
                bio.seek(0)
                img = Image.open(bio).convert("RGB")
                images.append(img)
            pdf_path = f"/tmp/{uid}_{int(time.time())}.pdf"
            images[0].save(pdf_path, save_all=True, append_images=images[1:])
            with open(pdf_path, "rb") as f:
                await q.message.reply_document(f, filename="Nezel.pdf", caption=T(uid, "pdf_done"))
            try:
                os.remove(pdf_path)
            except:
                pass
        except Exception as e:
            print("pdf err: " + str(e))
            await q.message.reply_text(T(uid, "download_failed"))
    elif data == "help_mp3" or data == "help_video" or data == "help":
        await q.message.reply_text(T(uid, "help_text"))
    elif data == "vip_info":
        if is_vip(uid):
            days = int((float(u.get("vip", 0)) - time.time()) // 86400) + 1
            await q.message.reply_text(f"👑 انت VIP 👑\n\nفاضل في VIP {max(1, days)} يوم\n\n⚡ تحميل اسرع\n🎵 جودة 1080 كاملة\n🚫 من غير اعلانات\n\nشكرا انك معانا ❤️")
        else:
            kb_vip = InlineKeyboardMarkup([[InlineKeyboardButton("📞 كلم الادمن للاشتراك", url="https://t.me/ccccbcv")], [InlineKeyboardButton("⬅️ رجوع", callback_data="home")]])
            await q.message.reply_text(f"👑 VIP - نزل\n\nانت لسه مش VIP\n\n✨ مميزات VIP لمدة شهر:\n⚡ تحميل اسرع من غير انتظار\n🎵 جودة 1080 كاملة\n🚫 من غير اعلانات\n⭐ اولوية في الدعم\n\n💰 السعر: 50 جنيه / شهر\n\n📌 عشان تشترك:\n1- حول 50 جنيه\n2- دوس على زرار كلم الادمن تحت\n3- ابعتله الاي دي ده:\n🆔 {uid}\n\nوهيفعلك VIP في نفس اليوم 👑\n\n🎁 نقطك: {u.get('points', 0)} من 100\n👥 دعواتك: {u.get('invites', 0)} من 50", reply_markup=kb_vip)
    elif data == "points_info":
        link = f"https://t.me/{context.bot.username}?start=inv_{uid}"
        await q.message.reply_text(f"🎁 {T(uid, 'points')}: {u.get('points', 0)} / 100\n👥 {T(uid, 'invites')}: {u.get('invites', 0)} / 50\n\n🔗 لينك دعوتك:\n{link}")
    elif data == "history_info":
        hist = u.get("history", [])
        if not hist:
            await q.message.reply_text(T(uid, "history_empty")); return
        txt = "\n".join(hist[-10:])
        await q.message.reply_text(f"📂 {T(uid, 'history_btn')}:\n{txt}")
    elif data == "fav_info":
        favs = u.get("favs", [])
        if not favs:
            await q.message.reply_text(T(uid, "fav_empty")); return
        txt = "\n".join(favs[-10:])
        await q.message.reply_text(f"⭐ {T(uid, 'fav_btn')}:\n{txt}")
    elif data == "admin_info":
        if int(uid) != ADMIN_ID:
            await q.message.reply_text(T(uid, "help_text")); return
        total = len(DATA["users"])
        vip_count = sum(1 for x in DATA["users"].values() if isinstance(x, dict) and float(x.get("vip", 0)) > time.time())
        kb_admin = InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 تفعيل VIP", callback_data="admin_addvip"), InlineKeyboardButton("❌ الغاء VIP", callback_data="admin_delvip")],
            [InlineKeyboardButton("📊 احصائيات", callback_data="admin_stats")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="home")],
        ])
        await q.message.reply_text(f"👑 لوحة تحكم الادمن\n\n👥 عدد المستخدمين: {total}\n💎 عدد الـ VIP: {vip_count}", reply_markup=kb_admin)
    elif data == "admin_addvip":
        if int(uid) != ADMIN_ID: return
        reset_modes(u); u["state"] = "admin_addvip"; save_data()
        await q.message.reply_text("💎 ابعت الاي دي بتاع المستخدم اللي عايز تفعله VIP")
    elif data == "admin_delvip":
        if int(uid) != ADMIN_ID: return
        reset_modes(u); u["state"] = "admin_delvip"; save_data()
        await q.message.reply_text("❌ ابعت الاي دي بتاع المستخدم اللي عايز تلغي منه VIP")
    elif data == "admin_stats":
        if int(uid) != ADMIN_ID: return
        total = len(DATA["users"])
        vip_count = sum(1 for x in DATA["users"].values() if isinstance(x, dict) and float(x.get("vip", 0)) > time.time())
        total_points = sum(int(x.get("points", 0)) for x in DATA["users"].values() if isinstance(x, dict))
        await q.message.reply_text(f"📊 احصائيات البوت\n\n👥 المستخدمين: {total}\n💎 VIP: {vip_count}\n🎁 مجموع النقط: {total_points}")
    elif data == "home":
        name = q.from_user.first_name or ""
        await q.message.reply_text(show_main_menu_text(uid, name), reply_markup=main_keyboard(uid))
    elif data == "convert_mp3_last":
        url = u.get("last_link", "")
        if not url:
            await q.message.reply_text(T(uid, "no_link_mp3")); return
        await q.message.reply_text(T(uid, "converting_mp3"))
        base = "/tmp/" + str(uid) + "_" + str(int(time.time())) + "_mp3"
        files = download_with_ytdlp(url, base, want_audio=True, quality="720")
        if not files:
            await q.message.reply_text(T(uid, "download_failed")); return
        with open(files[0], "rb") as f:
            await q.message.reply_audio(f, title="Nezel Audio")
        try:
            os.remove(files[0])
        except:
            pass

async def handle_dl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data or ""
    want_audio = False
    quality = "720"
    vid = ""
    if data.startswith("dl_audio_"):
        vid = data.replace("dl_audio_", ""); want_audio = True
    elif data.startswith("dl_1080_"):
        vid = data.replace("dl_1080_", ""); quality = "1080"
    elif data.startswith("dl_720_"):
        vid = data.replace("dl_720_", ""); quality = "720"
    elif data.startswith("dl_video_"):
        vid = data.replace("dl_video_", ""); quality = "720"
    else:
        return
    await q.message.reply_text(T(uid, "downloading"))
    try:
        base = "/tmp/" + str(uid) + "_" + str(int(time.time()))
        yt_url = "https://www.youtube.com/watch?v=" + vid
        files = download_with_ytdlp(yt_url, base, want_audio=want_audio, quality=quality)
        if not files:
            await q.message.reply_text(T(uid, "download_failed")); return
        with open(files[0], "rb") as f:
            if want_audio:
                await q.message.reply_audio(f)
            else:
                await q.message.reply_video(f)
        try:
            os.remove(files[0])
        except:
            pass
    except Exception as e:
        await q.message.reply_text(f"{T(uid, 'download_failed')}\n{str(e)}")

async def handle_choose_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data or ""
    if not data.startswith("pick_"):
        return
    vid = data.replace("pick_", "")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🎵 {T(uid, 'download_mp3')}", callback_data=f"dl_audio_{vid}")],
        [InlineKeyboardButton(f"📥 {T(uid, 'download_video')} - 720", callback_data=f"dl_720_{vid}")],
        [InlineKeyboardButton(f"📥 {T(uid, 'download_video')} - 1080", callback_data=f"dl_1080_{vid}")],
        [InlineKeyboardButton(f"⬅️ {T(uid, 'back')}", callback_data="home")],
    ])
    await q.message.reply_text(f"{T(uid, 'choose_format')}", reply_markup=kb)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = get_user(uid)
    user = update.effective_user
    if update.message.photo:
        if u.get("pdf_mode"):
            file_id = update.message.photo[-1].file_id
            u["pdf_photos"].append(file_id)
            save_data()
            await update.message.reply_text(f"{T(uid, 'pdf_added')} {len(u['pdf_photos'])} ✅")
        return
    text = (update.message.text or "").strip()
    if not text:
        return
    if not u.get("lang"):
        await update.message.reply_text("اختر لغتك\n\nChoose your language", reply_markup=lang_keyboard())
        return
            # تفعيل / الغاء VIP من الادمن
    if u.get("state") == "admin_addvip" and int(uid) == ADMIN_ID:
        target = text.strip()
        if not target.isdigit():
            await update.message.reply_text("ابعت اي دي ارقام بس")
            return
        tu = get_user(target)
        tu["vip"] = time.time() + 30 * 86400
        u["state"] = "home"
        save_data()
        await update.message.reply_text(f"✅ تم تفعيل VIP للمستخدم {target} لمدة 30 يوم")
        try:
            await context.bot.send_message(chat_id=int(target), text=T(int(target), "vip_congrats"))
        except:
            pass
        name2 = user.first_name or ""
        await update.message.reply_text(show_main_menu_text(uid, name2), reply_markup=main_keyboard(uid))
        return
    if u.get("state") == "admin_delvip" and int(uid) == ADMIN_ID:
        target = text.strip()
        if not target.isdigit():
            await update.message.reply_text("ابعت اي دي ارقام بس")
            return
        tu = get_user(target)
        tu["vip"] = 0
        u["state"] = "home"
        save_data()
        await update.message.reply_text(f"❌ تم الغاء VIP من المستخدم {target}")
        name2 = user.first_name or ""
        await update.message.reply_text(show_main_menu_text(uid, name2), reply_markup=main_keyboard(uid))
        return
    if u.get("support_mode") or u.get("state") == "support":
        u["support_mode"] = False; u["state"] = "home"; save_data()
        await update.message.reply_text(f"✅ {T(uid, 'support_sent')}")
        if ADMIN_ID != 0:
            try:
                name = user.first_name or ""
                username = user.username
                username_link = f'<a href="https://t.me/{username}">@{username}</a>' if username else "مفيش يوزر"
                msg_text = (
                    f"📩 <b>رسالة دعم جديدة</b>\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"👤 الاسم: <a href=\"tg://user?id={uid}\">{html.escape(name)}</a>\n"
                    f"🆔 الاي دي: <a href=\"tg://user?id={uid}\">{uid}</a>\n"
                    f"🔗 يوزر: {username_link}\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"💬 الرسالة:\n{html.escape(text)}\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"للرد اكتب:\n<code>/reply {uid} رسالتك</code>"
                )
                await context.bot.send_message(chat_id=ADMIN_ID, text=msg_text, parse_mode=ParseMode.HTML)
            except Exception as e:
                print("Support forward failed: " + str(e))
        name2 = user.first_name or ""
        await update.message.reply_text(show_main_menu_text(uid, name2), reply_markup=main_keyboard(uid))
        return
    if u.get("translate_mode"):
        u["translate_mode"] = False; u["state"] = "home"; save_data()
        has_ar = any('\u0600' <= c <= '\u06FF' for c in text)
        target = "en" if has_ar else "ar"
        tr = translate_text(text, target)
        await update.message.reply_text(f"🌐 {T(uid, 'translate_done')}:\n{tr}")
        name2 = user.first_name or ""
        await update.message.reply_text(show_main_menu_text(uid, name2), reply_markup=main_keyboard(uid))
        return
    if u.get("summarize_mode"):
        u["summarize_mode"] = False; u["state"] = "home"; save_data()
        summ = summarize_text(text)
        await update.message.reply_text(f"📝 {T(uid, 'summarize_done')}:\n{summ}")
        name2 = user.first_name or ""
        await update.message.reply_text(show_main_menu_text(uid, name2), reply_markup=main_keyboard(uid))
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
            if len(title) > 35:
                title = title[:35] + "..."
            buttons.append([InlineKeyboardButton(f"🎵 {title}", callback_data=f"pick_{r['id']}")])
        buttons.append([InlineKeyboardButton(f"⬅️ {T(uid, 'back')}", callback_data="home")])
        kb = InlineKeyboardMarkup(buttons)
        await msg.edit_text(f"{T(uid, 'choose_result')}:", reply_markup=kb)
        return
    if "http" in text and any(x in text for x in ["youtube.com", "youtu.be", "tiktok.com", "instagram.com", "facebook.com", "fb.watch"]):
        u["last_link"] = text
        hist = u.get("history", [])
        hist.append(text[:100])
        u["history"] = hist[-20:]
        save_data()
        await update.message.reply_text(T(uid, "downloading"))
        try:
            base = "/tmp/" + str(uid) + "_" + str(int(time.time()))
            files = download_with_ytdlp(text, base, want_audio=False, quality="720")
            if files:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"🎵 {T(uid, 'download_mp3')}", callback_data="convert_mp3_last")]])
                with open(files[0], "rb") as f:
                    await update.message.reply_video(f, reply_markup=kb)
                try:
                    os.remove(files[0])
                except:
                    pass
            else:
                await update.message.reply_text(T(uid, "download_failed"))
        except Exception as e:
            await update.message.reply_text(f"{T(uid, 'download_failed')}\n{str(e)}")
        return
    name = user.first_name or ""
    await update.message.reply_text(show_main_menu_text(uid, name), reply_markup=main_keyboard(uid))

def main():
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN missing")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("vip", vip_cmd))
    app.add_handler(CommandHandler("reply", reply_cmd))
    app.add_handler(CallbackQueryHandler(handle_dl, pattern="^dl_"))
    app.add_handler(CallbackQueryHandler(handle_choose_result, pattern="^pick_"))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_message))
    print("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
