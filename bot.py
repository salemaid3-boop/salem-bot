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
    HTTPServer(("0.0.0.0", port), H).serve_forever()

threading.Thread(target=_keep_alive, daemon=True).start()
import json
import time
import glob
import requests
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
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
        except:
            pass
    return {"users": {}}

def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(DATA, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("save failed: " + str(e))

DATA = load_data()

def get_user(uid):
    uid = str(uid)
    if uid not in DATA["users"] or not isinstance(DATA["users"][uid], dict):
        DATA["users"][uid] = {"lang": None, "vip": 0, "state": "home", "support_mode": False, "points": 0, "invites": 0}
        save_data()
    u = DATA["users"][uid]
    if "lang" not in u:
        u["lang"] = None
    if "vip" not in u:
        u["vip"] = 0
    if "state" not in u:
        u["state"] = "home"
    if "support_mode" not in u:
        u["support_mode"] = False
    if "points" not in u:
        u["points"] = 0
    if "invites" not in u:
        u["invites"] = 0
    return u

def is_vip(uid):
    try:
        return float(get_user(uid).get("vip", 0)) > time.time()
    except:
        return False

# كل رسالة عربي في سطر لوحده، وانجليزي في سطر لوحده، عشان متتشقلبش
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
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🎵 {T(uid, 'download_mp3')}", callback_data="help_mp3"), InlineKeyboardButton(f"📥 {T(uid, 'download_video')}", callback_data="help_video")],
        [InlineKeyboardButton(f"🎬 {T(uid, 'quality_1080')}", callback_data="help_video"), InlineKeyboardButton(f"🎬 {T(uid, 'quality_720')}", callback_data="help_video")],
        [InlineKeyboardButton(f"🔍 {T(uid, 'search_btn')}", callback_data="search"), InlineKeyboardButton(f"🖼️ {T(uid, 'pdf_btn')}", callback_data="pdf_info")],
        [InlineKeyboardButton(f"⭐ {T(uid, 'fav_btn')}", callback_data="fav_info"), InlineKeyboardButton(f"📂 {T(uid, 'history_btn')}", callback_data="history_info")],
        [InlineKeyboardButton(f"🎁 {T(uid, 'points_btn')}", callback_data="points_info"), InlineKeyboardButton(f"{vip_txt}", callback_data="vip_info")],
        [InlineKeyboardButton(f"🌐 {T(uid, 'lang_btn')}", callback_data="lang"), InlineKeyboardButton(f"📞 {T(uid, 'support_btn')}", callback_data="support")],
        [InlineKeyboardButton(f"👑 {T(uid, 'admin_btn')}", callback_data="admin_info")],
    ])

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
    try:
        r = requests.get("https://inv.nadeko.net/api/v1/search", params={"q": query, "type": "video"}, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            data = r.json()
            results = []
            for item in data[:5]:
                vid = item.get("videoId", "")
                title = item.get("title", query)
                if vid:
                    results.append({"id": vid, "title": title})
            if results:
                return results
    except Exception as e:
        print("invidious failed: " + str(e))
    return []

def download_with_ytdlp(url, base, want_audio=False, quality="720"):
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
        "extractor_args": {"youtube": {"player_client": ["android", "ios"]}},
        "merge_output_format": "mp4",
        "http_headers": {"User-Agent": "Mozilla/5.0"},
    }
    if want_audio:
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    files = glob.glob(base + ".*")
    files = [f for f in files if not f.endswith(".part")]
    return files

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = get_user(uid)
    u["state"] = "home"
    u["support_mode"] = False
    save_data()
    # اللغة اول حاجة كل مرة، مش اول مرة بس
    text = "اختر لغتك\n\nChoose your language"
    await update.message.reply_text(text, reply_markup=lang_keyboard())
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
        u["state"] = "home"
        u["support_mode"] = False
        save_data()
        name = q.from_user.first_name or ""
        await q.message.reply_text(T(uid, "lang_changed"))
        await q.message.reply_text(show_main_menu_text(uid, name), reply_markup=main_keyboard(uid))
        return
    if data == "set_lang_en":
        u["lang"] = "en"
        u["state"] = "home"
        u["support_mode"] = False
        save_data()
        name = q.from_user.first_name or ""
        await q.message.reply_text(T(uid, "lang_changed"))
        await q.message.reply_text(show_main_menu_text(uid, name), reply_markup=main_keyboard(uid))
        return
    if not u.get("lang"):
        await q.message.reply_text("اختر لغتك\n\nChoose your language", reply_markup=lang_keyboard())
        return
    if data == "search":
        u["state"] = "search"
        u["support_mode"] = False
        save_data()
        await q.message.reply_text(f"🔍 {T(uid, 'search_prompt')}")
    elif data == "lang":
        await q.message.reply_text("اختر لغتك\n\nChoose your language", reply_markup=lang_keyboard())
    elif data == "support":
        u["state"] = "support"
        u["support_mode"] = True
        save_data()
        await q.message.reply_text(f"📞 {T(uid, 'support_prompt')}")
    elif data == "help_mp3" or data == "help_video" or data == "help":
        await q.message.reply_text(T(uid, "help_text"))
    elif data == "vip_info":
        if is_vip(uid):
            days = int((float(u.get("vip", 0)) - time.time()) // 86400) + 1
            await q.message.reply_text(f"👑 {T(uid, 'vip_left')} {max(1, days)} {T(uid, 'vip_days')}")
        else:
            await q.message.reply_text(T(uid, "not_vip"))
    elif data == "points_info":
        await q.message.reply_text(f"🎁 {T(uid, 'points')}: {u.get('points', 0)} / 100\n👥 {T(uid, 'invites')}: {u.get('invites', 0)} / 50")
    elif data in ["pdf_info", "fav_info", "history_info", "admin_info"]:
        await q.message.reply_text(T(uid, "help_text"))
    elif data == "home":
        name = q.from_user.first_name or ""
        u["state"] = "home"
        u["support_mode"] = False
        save_data()
        await q.message.reply_text(show_main_menu_text(uid, name), reply_markup=main_keyboard(uid))

async def handle_dl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data or ""
    want_audio = False
    quality = "720"
    vid = ""
    if data.startswith("dl_audio_"):
        vid = data.replace("dl_audio_", "")
        want_audio = True
    elif data.startswith("dl_1080_"):
        vid = data.replace("dl_1080_", "")
        quality = "1080"
    elif data.startswith("dl_720_"):
        vid = data.replace("dl_720_", "")
        quality = "720"
    elif data.startswith("dl_video_"):
        vid = data.replace("dl_video_", "")
        quality = "720"
    else:
        return
    await q.message.reply_text(T(uid, "downloading"))
    try:
        base = "/tmp/" + str(uid) + "_" + str(int(time.time()))
        yt_url = "https://www.youtube.com/watch?v=" + vid
        files = download_with_ytdlp(yt_url, base, want_audio=want_audio, quality=quality)
        if not files:
            await q.message.reply_text(T(uid, "download_failed"))
            return
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
    text = (update.message.text or "").strip()
    if not text:
        return
    if not u.get("lang"):
        await update.message.reply_text("اختر لغتك\n\nChoose your language", reply_markup=lang_keyboard())
        return
    if u.get("support_mode") or u.get("state") == "support":
        u["support_mode"] = False
        u["state"] = "home"
        save_data()
        await update.message.reply_text(f"✅ {T(uid, 'support_sent')}")
        if ADMIN_ID != 0:
            try:
                name = update.effective_user.first_name or ""
                msg_text = "رسالة دعم جديدة\n"
                msg_text += f"الاسم: {name}\n"
                msg_text += f"الايدي: {uid}\n"
                msg_text += "----------------\n"
                msg_text += f"{text}\n"
                msg_text += "----------------\n"
                msg_text += f"للرد اكتب: /reply {uid} رسالتك"
                await context.bot.send_message(chat_id=ADMIN_ID, text=msg_text)
            except Exception as e:
                print("Support forward failed: " + str(e))
        name2 = update.effective_user.first_name or ""
        await update.message.reply_text(show_main_menu_text(uid, name2), reply_markup=main_keyboard(uid))
        return
    if u.get("state") == "search":
        u["state"] = "home"
        save_data()
        msg = await update.message.reply_text(f"🔍 {T(uid, 'searching')}: {text}\n{T(uid, 'search_wait')}...")
        results = do_search(text)
        if not results:
            await msg.edit_text(T(uid, "not_found"))
            return
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
        await update.message.reply_text(T(uid, "downloading"))
        try:
            base = "/tmp/" + str(uid) + "_" + str(int(time.time()))
            files = download_with_ytdlp(text, base, want_audio=False, quality="720")
            if files:
                with open(files[0], "rb") as f:
                    await update.message.reply_video(f)
                try:
                    os.remove(files[0])
                except:
                    pass
            else:
                await update.message.reply_text(T(uid, "download_failed"))
        except Exception as e:
            await update.message.reply_text(f"{T(uid, 'download_failed')}\n{str(e)}")
        return
    name = update.effective_user.first_name or ""
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
    print("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
