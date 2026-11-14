import os, json, time, re, html, subprocess, glob, requests, io
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

BOT_TOKEN = os.environ.get("BOT_TOKEN", "PUT_YOUR_TOKEN_HERE")
# حط الاي دي بتاعك هنا - جيبه من @userinfobot
ADMIN_ID = int(os.environ.get("ADMIN_ID", "1159182662"))
SUPPORT_EMAIL = "salemaid5340@gmail.com"
DATA_FILE = "data.json"
POINTS_PER_INVITE = 5

# ---------- DATA ----------
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                if "users" in d: return d
        except: pass
    return {"users": {}}
def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(DATA, f, ensure_ascii=False, indent=2)
    except Exception as e: print(f"save err: {e}")
DATA = load_data()

DEFAULT_USER = {"points":0,"invites":0,"invited_by":None,"vip":False,"lang":"ar","last_link":"","pdf_photos":[],"translate_mode":False,"summarize_mode":False,"support_mode":False,"pdf_mode":False,"invited_users":[]}
def get_user(uid):
    uid = str(uid)
    if uid not in DATA["users"]:
        DATA["users"][uid] = dict(DEFAULT_USER); save_data()
    u = DATA["users"][uid]
    for k,v in DEFAULT_USER.items():
        if k not in u: u[k]=v
    return u

# ---------- LANG ----------
LANGS = {
 "ar": {"welcome":"أهلاً","welcome_sub":"بوتك لتحميل الفيديوهات والترجمة والتلخيص","points":"نقاطك","invites":"دعواتك","send_link":"ابعت لينك الفيديو عشان أحمله","download_failed":"فشل التحميل، جرب لينك تاني 😔","downloading":"بنحمل دلوقتي، استنى ثواني... ⏳","invalid_link":"اللينك مش شغال، ابعت لينك صحيح","vip_line":"👑 انت VIP - كل حاجة مفتوحة ليك","support_sent":"تم ارسال رسالتك للدعم ✅ هنرد عليك قريب","support_ask":"اكتب رسالتك للدعم وهنرد عليك قريب 📩","translate_ask":"ابعت النص اللي عايز تترجمه","summarize_ask":"ابعت النص اللي عايز تلخصه","pdf_ask":"ابعت الصور وانا هحولها PDF، ولما تخلص دوس انهاء","pdf_done":"تم تحويل الصور لـ PDF ✅","no_link_mp3":"ابعت لينك الفيديو الاول، وبعدين دوس تحويل لـ MP3 🎵","converting_mp3":"بحولها اغنية دلوقتي... 🎵⏳"},
 "en": {"welcome":"Welcome","welcome_sub":"Your bot for downloads, translate & summarize","points":"Your Points","invites":"Your Invites","send_link":"Send video link to download","download_failed":"Download failed, try another link 😔","downloading":"Downloading now, wait... ⏳","invalid_link":"Invalid link","vip_line":"👑 You are VIP","support_sent":"Your message sent to support ✅","support_ask":"Write your message to support 📩","translate_ask":"Send text to translate","summarize_ask":"Send text to summarize","pdf_ask":"Send photos and I will make PDF, press Finish when done","pdf_done":"PDF created ✅","no_link_mp3":"Send video link first, then press Convert to MP3 🎵","converting_mp3":"Converting to song now... 🎵⏳"}
}
def T(uid, key):
    u = get_user(uid)
    return LANGS.get(u.get("lang","ar"), LANGS["ar"]).get(key, key)

def safe_url(url):
    return url.startswith("http") and any(x in url for x in ["tiktok.com","youtube.com","youtu.be","instagram.com","facebook.com","fb.watch","twitter.com","x.com"])

# ---------- TRANSLATE FIXED ----------
def translate_text(text, target="en"):
    text = text.strip()
    if not text: return text
    try:
        sl = "ar" if target == "en" else "en"
        r = requests.get("https://translate.googleapis.com/translate_a/single", params={"client":"gtx","sl":sl,"tl":target,"dt":"t","q":text}, timeout=10, headers={"User-Agent":"Mozilla/5.0"})
        if r.status_code == 200:
            data = r.json()
            out = "".join([x[0] for x in data[0] if x[0]])
            if out and out.strip().lower() != text.strip().lower(): return out
    except Exception as e: print(f"google tr err: {e}")
    try:
        r = requests.get("https://api.mymemory.translated.net/get", params={"q":text[:500],"langpair":"ar|en" if target=="en" else "en|ar"}, timeout=10)
        if r.status_code == 200:
            tr = r.json().get("responseData", {}).get("translatedText","")
            if tr and tr.lower() != text.lower(): return tr
    except Exception as e: print(f"mymemory err: {e}")
    return text

def summarize_text(text):
    # تلخيص حقيقي: بياخد اول واهم الجمل مش قص وخلاص
    text = text.strip()
    sentences = re.split(r'[.!؟\n]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    if len(sentences) <= 3: return text
    # خد اول جملتين + اطول جملتين + اخر جملة
    picked = []
    picked.append(sentences[0])
    sorted_by_len = sorted(sentences, key=len, reverse=True)[:2]
    for s in sorted_by_len:
        if s not in picked: picked.append(s)
    if sentences[-1] not in picked: picked.append(sentences[-1])
    return ". ".join(picked) + "."

# ---------- DOWNLOAD ----------
def download_with_ytdlp(url, base, want_audio=False, quality="720"):
    try:
        for f in glob.glob(base+".*"):
            try: os.remove(f)
            except: pass
        cmd = ["yt-dlp","--no-playlist","--no-warnings","-o",base+".%(ext)s"]
        if want_audio:
            cmd += ["-x","--audio-format","mp3","--audio-quality","0"]
        else:
            h = {"1080":"bv*[height<=1080]+ba/b[height<=1080]/b","720":"bv*[height<=720]+ba/b[height<=720]/b"}.get(quality,"bv*[height<=720]+ba/b[height<=720]/b")
            cmd += ["-f",h,"--merge-output-format","mp4","--remux-video","mp4"]
        cmd += [url]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        print(f"YTDLP ERR: {r.stderr[-800:]}")
        files = [f for f in glob.glob(base+".*") if not f.endswith(".part")]
        if files: return files
        if want_audio:
            subprocess.run(["yt-dlp","--no-playlist","-f","mp4/best","-o",base+".mp4",url], capture_output=True, text=True, timeout=120)
            vid = base+".mp4"
            if os.path.exists(vid):
                mp3 = base+".mp3"
                subprocess.run(["ffmpeg","-y","-i",vid,"-vn","-ab","192k",mp3], capture_output=True, text=True, timeout=60)
                try: os.remove(vid)
                except: pass
                if os.path.exists(mp3): return [mp3]
        return []
    except Exception as e:
        print(f"download err: {e}"); return []

# ---------- MENUS ----------
def main_kb(uid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 تحميل فيديو | Download", callback_data="dl_menu")],
        [InlineKeyboardButton("🌐 ترجمة | Translate", callback_data="tr_menu"), InlineKeyboardButton("📝 تلخيص | Summarize", callback_data="sum_menu")],
        [InlineKeyboardButton("📄 تحويل PDF | PDF", callback_data="pdf_menu"), InlineKeyboardButton("🎵 تحويل لـ MP3", callback_data="convert_mp3")],
        [InlineKeyboardButton("👥 دعوة اصحابك +5 | Invite", callback_data="invite"), InlineKeyboardButton("👑 VIP", callback_data="vip")],
        [InlineKeyboardButton("🌍 اللغة | Language", callback_data="lang"), InlineKeyboardButton("📩 الدعم | Support", callback_data="support")],
    ])

def show_main_menu_text(uid, name):
    u = get_user(uid)
    points = u["points"]; invites = u["invites"]
    filled = min(10, int(points/10))
    p_bar = "🟩"*filled + "⬜"*(10-filled)
    vip_line = f"\n{T(uid,'vip_line')}" if u["vip"] else ""
    return f"✨ {T(uid,'welcome')} {html.escape(name)} 👑\n\n{T(uid,'welcome_sub')}\n━━━━━━━━━━━━━━\n🎁 {T(uid,'points')}: {points} من 100\n{p_bar}\n👥 {T(uid,'invites')}: {invites} من 50\n{vip_line}\n━━━━━━━━━━━━━━\n👇 {T(uid,'send_link')}"

# ---------- HANDLERS ----------
async def start(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = get_user(uid)
    args = context.args
    if args and args[0].startswith("inv_"):
        inviter = args[0].replace("inv_","")
        # FIX: منع تكرار النقاط ودعوة النفس
        if inviter != str(uid) and not u["invited_by"] and inviter not in u.get("invited_users",[]):
            u["invited_by"] = inviter
            if inviter.isdigit():
                inv = get_user(int(inviter))
                if str(uid) not in inv.get("invited_users",[]):
                    inv["invited_users"].append(str(uid))
                    inv["points"] += POINTS_PER_INVITE; inv["invites"] += 1
                    if inv["invites"] >= 10: inv["vip"] = True
                    save_data()
                    try: await context.bot.send_message(chat_id=int(inviter), text=f"🎉 حد دخل من لينكك! +{POINTS_PER_INVITE} نقاط")
                    except: pass
    name = update.effective_user.first_name or "صديقي"
    await update.message.reply_text(show_main_menu_text(uid, name), reply_markup=main_kb(uid), parse_mode=ParseMode.HTML)

def reset_modes(u):
    u["translate_mode"]=False; u["summarize_mode"]=False; u["support_mode"]=False; u["pdf_mode"]=False

async def handle_callback(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); uid = q.from_user.id; u = get_user(uid); data = q.data
    name = q.from_user.first_name or "صديقي"
    if data == "main":
        await q.edit_message_text(show_main_menu_text(uid, name), reply_markup=main_kb(uid), parse_mode=ParseMode.HTML)
    elif data == "lang":
        u["lang"] = "en" if u["lang"]=="ar" else "ar"; save_data()
        await q.edit_message_text(show_main_menu_text(uid, name), reply_markup=main_kb(uid), parse_mode=ParseMode.HTML)
    elif data == "tr_menu":
        reset_modes(u); u["translate_mode"]=True; save_data(); await q.message.reply_text(T(uid,"translate_ask"))
    elif data == "sum_menu":
        reset_modes(u); u["summarize_mode"]=True; save_data(); await q.message.reply_text(T(uid,"summarize_ask"))
    elif data == "support":
        reset_modes(u); u["support_mode"]=True; save_data()
        await q.message.reply_text(f"{T(uid,'support_ask')}\n\n📧 او كلمنا على الايميل:\n{SUPPORT_EMAIL}")
    elif data == "invite":
        link = f"https://t.me/{context.bot.username}?start=inv_{uid}"
        await q.message.reply_text(f"🔗 لينك الدعوة بتاعك:\n{link}\n\nكل واحد يدخل من لينكك هتاخد +{POINTS_PER_INVITE} نقاط 🎁")
    elif data == "vip":
        await q.message.reply_text("👑 VIP: ادعو 10 اصحاب عشان تاخد VIP، او كلم الدعم.")
    elif data == "pdf_menu":
        reset_modes(u); u["pdf_mode"]=True; u["pdf_photos"]=[]; save_data()
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ انهاء وتحويل", callback_data="pdf_finish")]])
        await q.message.reply_text(T(uid,"pdf_ask"), reply_markup=kb)
    elif data == "pdf_finish":
        if not u.get("pdf_photos"):
            await q.message.reply_text("ابعت صور الاول 📸"); return
        await q.message.reply_text("بحول الصور لـ PDF... ⏳")
        try:
            images = []
            for file_id in u["pdf_photos"]:
                tg_file = await context.bot.get_file(file_id)
                bio = io.BytesIO(); await tg_file.download_to_memory(bio); bio.seek(0)
                img = Image.open(bio).convert("RGB"); images.append(img)
            pdf_path = f"/tmp/{uid}_{int(time.time())}.pdf"
            images[0].save(pdf_path, save_all=True, append_images=images[1:])
            with open(pdf_path,"rb") as f: await q.message.reply_document(f, filename="Nezel.pdf", caption=T(uid,"pdf_done"))
            try: os.remove(pdf_path)
            except: pass
        except Exception as e:
            print(f"pdf err: {e}"); await q.message.reply_text("حصل مشكلة في تحويل الـ PDF 😔")
        u["pdf_photos"]=[]; u["pdf_mode"]=False; save_data()
    elif data == "convert_mp3":
        await handle_convert_mp3(update, context)
    elif data == "dl_menu":
        await q.message.reply_text("ابعت لينك الفيديو من تيك توك / يوتيوب / انستا / فيس 📥")

async def handle_convert_mp3(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; uid = q.from_user.id; u = get_user(uid)
    url = u.get("last_link","")
    if not url or "http" not in url:
        await q.message.reply_text(T(uid,"no_link_mp3")); return
    await q.message.reply_text(T(uid,"converting_mp3"))
    try:
        # FIX: Cobalt الجديد
        try:
            r = requests.post("https://api.cobalt.tools/api/json", json={"url":url,"downloadMode":"audio","audioFormat":"mp3"}, headers={"Accept":"application/json","Content-Type":"application/json"}, timeout=30)
            if r.status_code == 200:
                audio_url = r.json().get("url")
                if audio_url:
                    ar = requests.get(audio_url, timeout=60, headers={"User-Agent":"Mozilla/5.0"})
                    if ar.status_code == 200 and len(ar.content) > 1000:
                        path = f"/tmp/{uid}_{int(time.time())}.mp3"
                        with open(path,"wb") as f: f.write(ar.content)
                        with open(path,"rb") as f: await q.message.reply_audio(f, title="Nezel Audio 🎵")
                        try: os.remove(path)
                        except: pass
                        return
        except Exception as e: print(f"cobalt err: {e}")
        base = f"/tmp/{uid}_{int(time.time())}_mp3"
        files = download_with_ytdlp(url, base, want_audio=True, quality="720")
        if files and os.path.exists(files[0]):
            with open(files[0],"rb") as f: await q.message.reply_audio(f, title="Nezel Audio 🎵")
            try: os.remove(files[0])
            except: pass
            return
        await q.message.reply_text(T(uid,"download_failed"))
    except Exception as e:
        print(f"mp3 convert err: {e}"); await q.message.reply_text(T(uid,"download_failed"))

async def handle_message(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id; u = get_user(uid); user = update.effective_user
    text = (update.message.text or "").strip()

    # FIX: /reply للادمن
    if text.startswith("/reply") and uid == ADMIN_ID:
        try:
            parts = text.split(" ", 2); target = int(parts[1]); msg = parts[2]
            await context.bot.send_message(chat_id=target, text=f"📩 رد الدعم:\n\n{msg}")
            await update.message.reply_text("تم الرد ✅")
        except: await update.message.reply_text("استخدم: /reply الاي_دي الرسالة")
        return

    # FIX: PDF - حفظ الصور بجد
    if update.message.photo:
        if u.get("pdf_mode"):
            file_id = update.message.photo[-1].file_id
            u["pdf_photos"].append(file_id); save_data()
            await update.message.reply_text(f"تم اضافة الصورة {len(u['pdf_photos'])} ✅ كمل او دوس انهاء")
        return

    if not text: return

    # الدعم - الاي دي قابل للضغط يدخلك على صفحته
    if u.get("support_mode"):
        u["support_mode"]=False; save_data()
        await update.message.reply_text(T(uid,"support_sent"))
        if ADMIN_ID != 0:
            username_link = f'<a href="https://t.me/{user.username}">@{user.username}</a>' if user.username else "مفيش يوزر"
            msg_to_admin = (
                f"📩 <b>رسالة دعم جديدة</b>\n━━━━━━━━━━━━━━\n"
                f"👤 الاسم: <a href=\"tg://user?id={uid}\">{html.escape(user.first_name or 'مستخدم')}</a>\n"
                f"🆔 الاي دي: <a href=\"tg://user?id={uid}\">{uid}</a>\n"
                f"🔗 يوزر: {username_link}\n━━━━━━━━━━━━━━\n💬 الرسالة:\n{text}\n━━━━━━━━━━━━━━\nللرد اكتب:\n<code>/reply {uid} رسالتك</code>"
            )
            try: await context.bot.send_message(chat_id=ADMIN_ID, text=msg_to_admin, parse_mode=ParseMode.HTML)
            except Exception as e: print(f"support forward err: {e}")
        return

    if u.get("translate_mode"):
        u["translate_mode"]=False; save_data()
        is_ar = any('\u0600' <= c <= '\u06FF' for c in text)
        tr = translate_text(text, "en" if is_ar else "ar")
        await update.message.reply_text(f"🌐 الترجمة:\n{tr}"); return

    if u.get("summarize_mode"):
        u["summarize_mode"]=False; save_data()
        await update.message.reply_text(f"📝 التلخيص:\n{summarize_text(text)}"); return

    if "http" in text:
        if not safe_url(text):
            await update.message.reply_text(T(uid,"invalid_link")); return
        u["last_link"]=text; save_data()
        await update.message.reply_text(T(uid,"downloading"))
        base = f"/tmp/{uid}_{int(time.time())}"
        files = download_with_ytdlp(text, base, want_audio=False, quality="720")
        if not files:
            await update.message.reply_text(T(uid,"download_failed")); return
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎵 تحويل لـ MP3", callback_data="convert_mp3")],[InlineKeyboardButton("🏠 الرئيسية", callback_data="main")]])
        try:
            with open(files[0],"rb") as f: await update.message.reply_video(f, caption="تم التحميل ✅", reply_markup=kb)
        except:
            with open(files[0],"rb") as f: await update.message.reply_document(f, reply_markup=kb)
        try: os.remove(files[0])
        except: pass
        return

    await update.message.reply_text(show_main_menu_text(uid, user.first_name or "صديقي"), reply_markup=main_kb(uid), parse_mode=ParseMode.HTML)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))
    # FIX: Flask بدون reloader عشان ميعملش Conflict
    from flask import Flask
    import threading
    flask_app = Flask(__name__)
    @flask_app.route("/")
    def home(): return "Bot is running!"
    threading.Thread(target=lambda: flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)), use_reloader=False), daemon=True).start()
    app.run_polling()

if __name__ == "__main__":
    main()
