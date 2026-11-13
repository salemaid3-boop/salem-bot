import os, json, re, time, glob, requests
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
except:
    ADMIN_ID = 0
DATA_FILE = "users.json"
PIPED_INSTANCES = ["https://piped.video", "https://piped.privacyredirect.com", "https://piped.adminforge.de", "https://piped.mha.fi"]

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
        print(f"save failed: {e}")

DATA = load_data()

def get_user(uid):
    uid = str(uid)
    if uid not in DATA["users"] or not isinstance(DATA["users"][uid], dict):
        DATA["users"][uid] = {"lang": "ar", "vip": 0, "state": "home", "support_mode": False}
        save_data()
    u = DATA["users"][uid]
    if u.get("lang") not in ["ar", "en"]:
        u["lang"] = "ar"
    if "vip" not in u:
        u["vip"] = 0
    if "state" not in u:
        u["state"] = "home"
    if "support_mode" not in u:
        u["support_mode"] = False
    return u

def is_vip(uid):
    u = get_user(uid)
    try:
        return float(u.get("vip", 0)) > time.time()
    except:
        return False

TEXTS = {
    "ar": {
        "welcome": "👋 اهلا بيك في بوت التحميل\nاختار من تحت:",
        "vip_status": "👑 VIP - فاضل {d} يوم",
        "not_vip": "❌ مش VIP",
        "search_prompt": "🔍 اكتب اسم الاغنية او الفيديو:",
        "searching": "🔍 بدور على: {q} استنى...",
        "not_found": "❌ ملقيتش حاجة بالاسم ده، جرب اسم تاني",
        "downloading": "⏳ بحمل... استنى شوية",
        "choose_lang": "🌐 اختار اللغة / Choose Language:",
        "support_prompt": "✍️ اكتب رسالتك للدعم:",
        "support_sent": "✅ رسالتك وصلت للدعم، هنرد عليك قريب",
        "support_reply": "💬 رد الدعم:\n\n{msg}",
        "help": "📖 ابعت لينك فيديو من يوتيوب / تيك توك / انستا / فيس بوك، او دوس بحث ودور بالاسم",
        "choose_format": "🎵 {title}\nاختار:",
    },
    "en": {
        "welcome": "👋 Welcome to Download Bot\nChoose:",
        "vip_status": "👑 VIP - {d} days left",
        "not_vip": "❌ Not VIP",
        "search_prompt": "🔍 Type song or video name:",
        "searching": "🔍 Searching for: {q} wait...",
        "not_found": "❌ Nothing found, try another name",
        "downloading": "⏳ Downloading... wait",
        "choose_lang": "🌐 Choose Language:",
        "support_prompt": "✍️ Write your message to support:",
        "support_sent": "✅ Your message sent to support",
        "support_reply": "💬 Support reply:\n\n{msg}",
        "help": "📖 Send a video link from YouTube / TikTok / Insta / Facebook, or tap Search",
        "choose_format": "🎵 {title}\nChoose:",
    }
}

def T(uid, key, **kwargs):
    u = get_user(uid)
    lang = u.get("lang", "ar")
    if lang not in TEXTS:
        lang = "ar"
    txt = TEXTS[lang].get(key, key)
    try:
        return txt.format(**kwargs)
    except:
        return txt

def main_keyboard(uid):
    u = get_user(uid)
    lang = u.get("lang", "ar")
    if is_vip(uid):
        days = int((float(u.get("vip", 0)) - time.time()) // 86400) + 1
        vip_txt = T(uid, "vip_status", d=days)
    else:
        vip_txt = T(uid, "not_vip")
    if lang == "ar":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 بحث", callback_data="search"), InlineKeyboardButton("🎵 تحميل", callback_data="help")],
            [InlineKeyboardButton("🌐 اللغة", callback_data="lang"), InlineKeyboardButton("🛠 الدعم", callback_data="support")],
            [InlineKeyboardButton(vip_txt, callback_data="vip_info")]
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Search", callback_data="search"), InlineKeyboardButton("🎵 Download", callback_data="help")],
        [InlineKeyboardButton("🌐 Language", callback_data="lang"), InlineKeyboardButton("🛠 Support", callback_data="support")],
        [InlineKeyboardButton(vip_txt, callback_data="vip_info")]
    ])

def piped_search(query):
    import urllib.parse
    try:
        q = urllib.parse.quote(query)
        yt_url = f"https://www.youtube.com/results?search_query={q}"
        proxy_url = f"https://api.allorigins.win/raw?url={urllib.parse.quote(yt_url)}"
        r = requests.get(proxy_url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and "videoId" in r.text:
            ids = re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', r.text)
            seen = set()
            uniq = []
            for vid in ids:
                if vid not in seen:
                    seen.add(vid)
                    uniq.append(vid)
            if uniq:
                return {"id": uniq[0], "title": query, "url": f"/watch?v={uniq[0]}"}
    except Exception as e:
        print(f"AllOrigins failed: {e}")
    try:
        q = urllib.parse.quote(f"site:youtube.com {query}")
        r = requests.get(f"https://html.duckduckgo.com/html/?q={q}", timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            m = re.findall(r'watch\?v=([A-Za-z0-9_-]{11})', r.text)
            if m:
                return {"id": m[0], "title": query, "url": f"/watch?v={m[0]}"}
    except Exception as e:
        print(f"DuckDuckGo failed: {e}")
    try:
        r = requests.get("https://yt.lemnoslife.com/noKey/search", params={"part": "snippet", "q": query, "maxResults": 1}, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            items = r.json().get("items", [])
            if items:
                vid = items[0].get("id", {}).get("videoId", "")
                if vid:
                    return {"id": vid, "title": items[0].get("snippet", {}).get("title", query), "url": f"/watch?v={vid}"}
    except Exception as e:
        print(f"LemnosLife failed: {e}")
    for inst in PIPED_INSTANCES:
        try:
            r = requests.get(f"{inst}/api/v1/search", params={"q": query, "filter": "all"}, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else data.get("items", [])
                if items:
                    first = items[0]
                    url = first.get("url", "")
                    vid = ""
                    if "v=" in url:
                        vid = url.split("v=")[-1].split("&")[0]
                    elif first.get("videoId"):
                        vid = first.get("videoId")
                    if vid and len(vid) == 11:
                        return {"id": vid, "title": first.get("title", query), "url": url}
        except:
            continue
    return None

def ytdlp_download(url, base, fmt, is_audio=False):
    opts = {"format": fmt, "outtmpl": base + ".%(ext)s", "quiet": True, "no_warnings": True, "nocheckcertificate": True, "socket_timeout": 60, "http_headers": {"User-Agent": "Mozilla/5.0"}}
    if is_audio:
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    files = glob.glob(base + ".*")
    return files

def piped_download(video_id, base, want_audio=False):
    yt_url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        r = requests.post("https://api.cobalt.tools/", json={"url": yt_url, "isAudioOnly": want_audio, "downloadMode": "auto", "filenameStyle": "basic"}, timeout=30, headers={"Accept": "application/json", "Content-Type": "application/json"})
        if r.status_code == 200:
            dl_url = r.json().get("url", "")
            if dl_url:
                ext = ".m4a" if want_audio else ".mp4"
                out = base + ext
                with requests.get(dl_url, stream=True, timeout=60, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                    if resp.status_code == 200:
                        with open(out, "wb") as f:
                            for chunk in resp.iter_content(8192):
                                if chunk:
                                    f.write(chunk)
                        if os.path.exists(out) and os.path.getsize(out) > 1000:
                            return out
    except Exception as e:
        print(f"Cobalt failed: {e}")
    for inst in PIPED_INSTANCES:
        try:
            r = requests.get(f"{inst}/api/v1/streams/{video_id}", timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                continue
            data = r.json()
            dl = None
            ext = ".mp4"
            if want_audio:
                audios = data.get("audioStreams", [])
                if not audios:
                    continue
                audios = sorted(audios, key=lambda x: x.get("bitrate", 0), reverse=True)
                dl = audios[0].get("url")
                ext = ".m4a"
            else:
                vids = data.get("videoStreams", [])
                if not vids:
                    continue
                dl = vids[0].get("url")
                ext = ".mp4"
            if not dl:
                continue
            out = base + ext
            with requests.get(dl, stream=True, timeout=60, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                if resp.status_code != 200:
                    continue
                with open(out, "wb") as f:
                    for chunk in resp.iter_content(8192):
                        if chunk:
                            f.write(chunk)
            if os.path.exists(out) and os.path.getsize(out) > 1000:
                return out
        except:
            continue
    fmt = "bestaudio/best" if want_audio else "18/22/mp4/best"
    files = ytdlp_download(yt_url, base, fmt, is_audio=want_audio)
    if files:
        return files[0]
    raise Exception("Download failed")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = get_user(uid)
    u["state"] = "home"
    u["support_mode"] = False
    save_data()
    await update.message.reply_text(T(uid, "welcome"), reply_markup=main_keyboard(uid))

async def vip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = get_user(uid)
    if not context.args:
        await update.message.reply_text("ابعت الايدي بعد /vip - مثال: /vip 123456" if u.get("lang") == "ar" else "Send ID after /vip")
        return
    if uid != ADMIN_ID and ADMIN_ID != 0:
        await update.message.reply_text("مش مسموح" if u.get("lang") == "ar" else "Not allowed")
        return
    try:
        target = str(context.args[0])
        tu = get_user(target)
        tu["vip"] = time.time() + 30 * 86400
        save_data()
        await update.message.reply_text("✅ بقى VIP لمدة 30 يوم")
        try:
            await context.bot.send_message(chat_id=int(target), text="🎉 مبروك! بقيت VIP")
        except:
            pass
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = get_user(uid)
    data = q.data or ""
    if data == "search":
        u["state"] = "search"
        save_data()
        await q.message.reply_text(T(uid, "search_prompt"))
    elif data == "help":
        await q.message.reply_text(T(uid, "help"))
    elif data == "lang":
        u["state"] = "home"
        save_data()
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🇪🇬 عربي", callback_data="set_lang_ar"), InlineKeyboardButton("🇺🇸 English", callback_data="set_lang_en")]])
        await q.message.reply_text(T(uid, "choose_lang"), reply_markup=kb)
    elif data == "set_lang_ar":
        u["lang"] = "ar"
        u["state"] = "home"
        save_data()
        await q.message.reply_text("✅ اتغيرت للعربي", reply_markup=main_keyboard(uid))
    elif data == "set_lang_en":
        u["lang"] = "en"
        u["state"] = "home"
        save_data()
        await q.message.reply_text("✅ Changed to English", reply_markup=main_keyboard(uid))
    elif data == "support":
        u["state"] = "support"
        u["support_mode"] = True
        save_data()
        await q.message.reply_text(T(uid, "support_prompt"))
    elif data == "vip_info":
        if is_vip(uid):
            days = int((float(u.get("vip", 0)) - time.time()) // 86400) + 1
            await q.message.reply_text(T(uid, "vip_status", d=days))
        else:
            await q.message.reply_text(T(uid, "not_vip"))

async def handle_dl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data or ""
    if data.startswith("dl_audio_"):
        vid = data.replace("dl_audio_", "")
        want_audio = True
    elif data.startswith("dl_video_"):
        vid = data.replace("dl_video_", "")
        want_audio = False
    else:
        return
    await q.message.reply_text(T(uid, "downloading"))
    try:
        base = f"/tmp/{uid}_{int(time.time())}"
        out = piped_download(vid, base, want_audio=want_audio)
        if want_audio:
            with open(out, "rb") as f:
                await q.message.reply_audio(f)
        else:
            with open(out, "rb") as f:
                await q.message.reply_video(f)
        try:
            os.remove(out)
        except:
            pass
    except Exception as e:
        await q.message.reply_text(f"❌ فشل: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = get_user(uid)
    text = (update.message.text or "").strip()
    if not text:
        return
    if u.get("support_mode") or u.get("state") == "support":
        u["support_mode"] = False
        u["state"] = "home"
        save_data()
        await update.message.reply_text(T(uid, "support_sent"))
        if ADMIN_ID != 0:
            try:
                await context.bot.send_message(chat_id=ADMIN_ID, text=f"📩 رسالة دعم جديدة\nمن: {update.effective_user.first_name} ({uid})\n\n{text}\n\nللرد: /reply {uid} رسالتك")
            except Exception as e:
                print(f"Support forward failed: {e}")
        return
    if u.get("state") == "search":
        u["state"] = "home"
        save_data()
        msg = await update.message.reply_text(T(uid, "searching", q=text))
        res = piped_search(text)
        if not res:
            await msg.edit_text(T(uid, "not_found"))
            return
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎵 MP3", callback_data=f"dl_audio_{res['id']}"), InlineKeyboardButton("🎬 فيديو", callback_data=f"dl_video_{res['id']}")]])
        await msg.edit_text(T(uid, "choose_format", title=res.get("title", text)), reply_markup=kb)
        return
    if "http" in text and any(x in text for x in ["youtube.com", "youtu.be", "tiktok.com", "instagram.com", "facebook.com", "fb.watch"]):
        await update.message.reply_text(T(uid, "downloading"))
        try:
            base = f"/tmp/{uid}_{int(time.time())}"
            files = ytdlp_download(text, base, "bestaudio/best", is_audio=True)
            if files:
                with open(files[0], "rb") as f:
                    await update.message.reply_audio(f, title="Audio")
                try:
                    os.remove(files[0])
                except:
                    pass
            else:
                await update.message.reply_text("❌ فشل التحميل")
        except Exception as e:
            await update.message.reply_text(f"❌ فشل التحميل: {e}")
        return
    await update.message.reply_text(T(uid, "welcome"), reply_markup=main_keyboard(uid))

async def reply_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_ID or ADMIN_ID == 0:
        return
    if len(context.args) < 2:
        await update.message.reply_text("استخدم: /reply 123456 رسالتك")
        return
    target = context.args[0]
    msg = " ".join(context.args[1:])
    try:
        await context.bot.send_message(chat_id=int(target), text=T(int(target), "support_reply", msg=msg))
        await update.message.reply_text("✅ اتبعت")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

def main():
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN missing")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("vip", vip_cmd))
    app.add_handler(CommandHandler("reply", reply_cmd))
    app.add_handler(CallbackQueryHandler(handle_dl, pattern="^dl_"))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
