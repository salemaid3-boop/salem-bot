import os, json, time, threading, glob, sys, traceback, re, requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 1159182662
ADMIN_USERNAME = "@SALEM"
PAY_NUMBER = "01015414353"
PAY_METHOD = "فودافون كاش"

if not TOKEN:
    print("ERROR: BOT_TOKEN مش موجود في Variables")
    sys.exit(1)

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
DB_FILE = "nezel_db.json"
DB_LOCK = threading.Lock()

VIP_PRICE = "50 جنيه"
VIP_DAYS = 30
POINTS_FOR_VIP = 100
INVITES_FOR_VIP = 50
POINTS_PER_INVITE = 5

# سيرفرات Piped - لو واحد وقع التاني يشتغل
PIPED_INSTANCES = [
    "https://piped.video",
    "https://piped.privacyredirect.com",
    "https://piped.adminforge.de",
    "https://inv.nadeko.net",
    "https://piped.mha.fi",
]

try:
    from PIL import Image
    HAS_PIL = True
except:
    HAS_PIL = False

try:
    import yt_dlp
    HAS_YTDLP = True
except:
    HAS_YTDLP = False

try:
    from flask import Flask
    app = Flask(__name__)
    @app.route('/')
    def home():
        return "Nezel Bot is Running!"
    def run_flask():
        port = int(os.environ.get("PORT", 10000))
        app.run(host="0.0.0.0", port=port)
    threading.Thread(target=run_flask, daemon=True).start()
except Exception as e:
    print(f"Flask error: {e}")

def default_db():
    return {"users": {}, "fav": {}, "history": {}, "points": {}, "vip": {}, "invites": {}, "mode": {}, "lang": {}, "last_dl": {}}

def load_db():
    with DB_LOCK:
        if not os.path.exists(DB_FILE):
            return default_db()
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            for k in default_db().keys():
                if k not in d:
                    d[k] = {}
            if isinstance(d["vip"], list):
                new_vip = {}
                for u in d["vip"]:
                    new_vip[str(u)] = time.time() + VIP_DAYS*86400
                d["vip"] = new_vip
            return d
        except:
            return default_db()

def save_db(d):
    with DB_LOCK:
        try:
            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Save DB error: {e}")

def is_admin(uid):
    return str(uid) == str(ADMIN_ID)

def get_lang(uid):
    db = load_db()
    return db["lang"].get(str(uid), "ar")

def set_lang(uid, lang):
    db = load_db()
    db["lang"][str(uid)] = lang
    save_db(db)

def get_mode(uid):
    db = load_db()
    return db["mode"].get(str(uid), "video")

def set_mode(uid, mode):
    db = load_db()
    db["mode"][str(uid)] = mode
    save_db(db)

def T(uid, ar, en):
    lang = get_lang(uid)
    return ar if lang == "ar" else en

def get_points(uid, db=None):
    if db is None: db = load_db()
    return db["points"].get(str(uid), 0)

def get_invites(uid, db=None):
    if db is None: db = load_db()
    return db["invites"].get(str(uid), 0)

def is_vip(uid, db=None):
    if db is None: db = load_db()
    exp = db["vip"].get(str(uid), 0)
    if exp and exp > time.time():
        return True
    if exp and exp <= time.time():
        db["vip"].pop(str(uid), None)
        save_db(db)
    return False

def vip_left_days(uid, db=None):
    if db is None: db = load_db()
    exp = db["vip"].get(str(uid), 0)
    if not exp: return 0
    return max(int((exp - time.time()) / 86400) + 1, 0)

def make_vip_auto(uid, db, reason=""):
    if db["vip"].get(str(uid), 0) > time.time():
        return False
    db["vip"][str(uid)] = time.time() + VIP_DAYS*86400
    save_db(db)
    try:
        bot.send_message(int(uid), f"🎉 مبروك يا بطل!\n\n👑 بقيت VIP\n\n{reason}\n📅 الاشتراك: {VIP_DAYS} يوم\n💎 تحميل بدون حدود\n⚡ اولوية في التحميل\n\nاستمتع يا وحش 🔥")
    except: pass
    return True

def add_point(uid):
    db = load_db()
    db["points"][str(uid)] = db["points"].get(str(uid), 0) + 1
    if db["points"][str(uid)] >= POINTS_FOR_VIP and not is_vip(uid, db):
        make_vip_auto(uid, db, "🏆 جمعت 100 نقطة - تستاهل تبقى VIP ببلاش!")
    else:
        save_db(db)

def save_history(uid, link):
    db = load_db()
    h = db["history"].get(str(uid), [])
    h.insert(0, link[:80])
    db["history"][str(uid)] = h[:20]
    db["last_dl"][str(uid)] = link[:300]
    save_db(db)

def home_kb(uid):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("📥 ┊ تحميل فيديو", callback_data="mode_video"), InlineKeyboardButton("🎵 ┊ تحميل MP3", callback_data="mode_mp3"))
    kb.add(InlineKeyboardButton("🎬 ┊ جودة 720", callback_data="mode_q720"), InlineKeyboardButton("🎬 ┊ جودة 1080", callback_data="mode_q1080"))
    kb.add(InlineKeyboardButton("🔍 ┊ بحث بالاسم", callback_data="mode_search"), InlineKeyboardButton("🖼️ ┊ صور لـ PDF", callback_data="mode_pdf"))
    kb.add(InlineKeyboardButton("⭐ ┊ مفضلتي", callback_data="show_fav"), InlineKeyboardButton("📂 ┊ سجلي", callback_data="show_history"))
    kb.add(InlineKeyboardButton("🎁 ┊ نقطي ودعوتي", callback_data="my_points"), InlineKeyboardButton("👑 ┊ VIP", callback_data="vip_info"))
    kb.add(InlineKeyboardButton("🌐 ┊ اللغة / Language", callback_data="lang_menu"), InlineKeyboardButton("📞 ┊ الدعم", callback_data="support"))
    if is_admin(uid):
        kb.add(InlineKeyboardButton("👑 ┊ لوحة تحكم", callback_data="admin_panel"))
    return kb

def welcome_text(user, db=None):
    uid = str(user.id)
    if db is None: db = load_db()
    name = user.first_name or "صديقي"
    pts = get_points(uid, db)
    inv = get_invites(uid, db)
    vip_txt = f"👑 VIP - فاضل {vip_left_days(uid, db)} يوم" if is_vip(uid, db) else "❌ مش VIP"
    lang = db["lang"].get(uid, "ar")
    if lang == "en":
        return f"✨ Welcome {name} to Nezel 👑\n\n━━━━━━━━━━━━━━\n📥 TikTok • YouTube • Insta • FB • X\n🎵 MP3 • 🔍 Search • 🖼️ PDF\n━━━━━━━━━━━━━━\n🎁 Points: {pts} / 100\n👥 Invites: {inv} / 50\n👑 {vip_txt}\n━━━━━━━━━━━━━━\n👇 Send link now"
    return f"✨ اهلا {name} في Nezel 👑\n\n━━━━━━━━━━━━━━\n📥 بيحمل من: تيك توك • يوتيوب • انستا • فيسبوك • X\n🎵 MP3 • 🔍 بحث بالاسم • 🖼️ صور لـ PDF\n━━━━━━━━━━━━━━\n🎁 نقطك: {pts} / 100\n👥 دعواتك: {inv} / 50\n👑 {vip_txt}\n━━━━━━━━━━━━━━\n👇 ابعت اللينك على طول"

def fav_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("⭐ ضيف للمفضلة", callback_data="fav_add"))
    return kb

def safe_edit(call, text, reply_markup=None):
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=reply_markup)
    except:
        try:
            bot.send_message(call.message.chat.id, text, reply_markup=reply_markup)
        except: pass

# ===== محرك يوتيوب الجديد - من غير yt-dlp =====
def extract_youtube_id(url_or_text):
    # بيطلع الـ ID من اي لينك يوتيوب
    m = re.search(r'(?:v=|/shorts/|/embed/|youtu\.be/|/live/)([A-Za-z0-9_-]{11})', url_or_text)
    if m:
        return m.group(1)
    return None

def is_youtube_url(url):
    return "youtube.com" in url or "youtu.be" in url

def piped_search(query):
    # بحث يوتيوب من Piped - بيرجع اول فيديو
    for inst in PIPED_INSTANCES:
        try:
            r = requests.get(f"{inst}/api/v1/search", params={"q": query, "filter": "videos"}, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                data = r.json()
                if data:
                    first = data[0]
                    return {"id": first.get("url", "").split("v=")[-1].split("/watch?v=")[-1], "title": first.get("title", ""), "url": first.get("url", "")}
        except Exception as e:
            print(f"Piped search {inst} failed: {e}")
            continue
    return None

def piped_download(video_id, base, want_audio=False, max_height=None):
    # تحميل من Piped - بيرجع اسم الملف
    last_err = ""
    for inst in PIPED_INSTANCES:
        try:
            r = requests.get(f"{inst}/api/v1/streams/{video_id}", timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                continue
            data = r.json()
            download_url = None
            ext = ".mp4"
            if want_audio:
                # اختار احسن صوت
                audios = data.get("audioStreams", [])
                if not audios:
                    continue
                # رتب بالجودة
                audios = sorted(audios, key=lambda x: x.get("bitrate", 0), reverse=True)
                download_url = audios[0].get("url")
                ext = ".m4a" if "m4a" in audios[0].get("mimeType", "") else ".mp3"
                if "webm" in audios[0].get("mimeType", ""):
                    ext = ".webm"
            else:
                # فيديو + صوت مع بعض لو موجود
                vids = data.get("videoStreams", [])
                # دور على فيديو فيه صوت - itag 18, 22
                best = None
                for v in vids:
                    if v.get("itag") in [18, 22] or (v.get("videoOnly") == False and "mp4" in v.get("mimeType", "")):
                        if max_height and v.get("quality", ""):
                            try:
                                q = int(v.get("quality", "0").replace("p", ""))
                                if q > max_height:
                                    continue
                            except: pass
                        best = v
                        break
                if not best and vids:
                    # خد اي فيديو mp4
                    for v in vids:
                        if "mp4" in v.get("mimeType", "") and not v.get("videoOnly"):
                            best = v
                            break
                if not best:
                    # اخر حل: خد اول فيديو
                    if vids:
                        best = vids[0]
                    else:
                        continue
                download_url = best.get("url")
                ext = ".mp4"
            if not download_url:
                continue
            # نزل الملف
            out_file = base + ext
            with requests.get(download_url, stream=True, timeout=60, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                if resp.status_code != 200:
                    continue
                total = 0
                with open(out_file, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            total += len(chunk)
                            if total > 48*1024*1024:
                                break
            if os.path.exists(out_file) and os.path.getsize(out_file) > 1000:
                return out_file
        except Exception as e:
            last_err = str(e)
            print(f"Piped download {inst} failed: {e}")
            continue
    raise Exception(last_err or "Piped كله واقع، جرب تاني بعد دقيقة")

def ytdlp_download(url, base, fmt, is_audio=False):
    # ده للتيك توك والانستا والفيس - لسه شغال على yt-dlp
    tries = []
    if is_audio:
        tries.append({'format': 'bestaudio/best', 'outtmpl': base + ".%(ext)s", 'noplaylist': True, 'quiet': True, 'no_warnings': True})
    else:
        tries.append({'format': fmt, 'outtmpl': base + ".%(ext)s", 'noplaylist': True, 'quiet': True, 'no_warnings': True, 'merge_output_format': 'mp4'})
        tries.append({'format': 'best', 'outtmpl': base + ".%(ext)s", 'noplaylist': True, 'quiet': True})
    last_err = ""
    for opts in tries:
        try:
            for f in glob.glob(base + "*"):
                try: os.remove(f)
                except: pass
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            files = [f for f in os.listdir(".") if f.startswith(base) and not f.endswith(".part")]
            if files:
                return files
        except Exception as e:
            last_err = str(e)
            continue
    raise Exception(last_err)

def cleanup_base(base):
    for f in glob.glob(base + "*"):
        try: os.remove(f)
        except: pass

@bot.message_handler(commands=['start'])
def start(message):
    uid = str(message.from_user.id)
    db = load_db()
    is_new = uid not in db["users"]
    if is_new:
        db["users"][uid] = {"name": message.from_user.first_name, "username": message.from_user.username, "time": time.time()}
        save_db(db)
        parts = message.text.split()
        if len(parts) > 1:
            inviter = parts[1].strip()
            db2 = load_db()
            if inviter != uid and inviter in db2["users"]:
                db2["points"][inviter] = db2["points"].get(inviter, 0) + POINTS_PER_INVITE
                db2["invites"][inviter] = db2["invites"].get(inviter, 0) + 1
                inv_count = db2["invites"][inviter]
                save_db(db2)
                if inv_count >= INVITES_FOR_VIP and not is_vip(inviter, db2):
                    db3 = load_db()
                    make_vip_auto(inviter, db3, f"🔥 جبت {INVITES_FOR_VIP} شخص بدعوتك - تستاهل VIP ببلاش!")
                else:
                    try:
                        bot.send_message(int(inviter), f"🎁 حد دخل بدعوتك!\n\n+{POINTS_PER_INVITE} نقط ✨\n🎁 نقطك: {db2['points'][inviter]} / 100\n👥 دعواتك: {inv_count} / 50\n\nلو وصلت 50 دعوة هتبقى VIP ببلاش 👑")
                    except: pass
    bot.reply_to(message, welcome_text(message.from_user), reply_markup=home_kb(uid))

@bot.message_handler(commands=['admin'])
def admin_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "مش ليك يا صاحبي")
        return
    db = load_db()
    vips = len([u for u, e in db["vip"].items() if e > time.time()])
    msg = f"👑 لوحة الادمن\n\n━━━━━━━━━━━━━━\n👥 المستخدمين: {len(db['users'])}\n👑 VIP: {vips}\n━━━━━━━━━━━━━━\n📢 /broadcast + رسالتك\n👑 /vip الايدي = VIP شهر\n❌ /unvip الايدي = الغاء VIP"
    bot.reply_to(message, msg)

@bot.message_handler(commands=['broadcast'])
def broadcast(message):
    if not is_admin(message.from_user.id): return
    txt = message.text.replace("/broadcast", "").strip()
    if not txt:
        bot.reply_to(message, "اكتب الرسالة بعد /broadcast")
        return
    db = load_db()
    ok = 0
    for u in list(db["users"].keys()):
        try:
            bot.send_message(int(u), "📢 رسالة من الادمن:\n\n" + txt)
            ok += 1
            time.sleep(0.05)
        except: pass
    bot.reply_to(message, f"اتبعتت لـ {ok}")

@bot.message_handler(commands=['vip'])
def make_vip(message):
    if not is_admin(message.from_user.id): return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "اكتب /vip + الايدي")
        return
    db = load_db()
    db["vip"][parts[1]] = time.time() + VIP_DAYS*86400
    save_db(db)
    bot.reply_to(message, f"بقى VIP 👑 لمدة {VIP_DAYS} يوم")
    try:
        bot.send_message(int(parts[1]), f"🎉 مبروك! بقيت VIP 👑\n\n📅 لمدة {VIP_DAYS} يوم\n💎 تحميل بدون حدود - شامل كل حاجة\n⚡ اولوية في التحميل\n💳 دفعت: {VIP_PRICE}")
    except: pass

@bot.message_handler(commands=['unvip'])
def remove_vip(message):
    if not is_admin(message.from_user.id): return
    parts = message.text.split()
    if len(parts) < 2: return
    db = load_db()
    db["vip"].pop(parts[1], None)
    save_db(db)
    bot.reply_to(message, "اتشال منه VIP ❌")

@bot.callback_query_handler(func=lambda c: True)
def callbacks(call):
    uid = str(call.from_user.id)
    data = call.data
    try:
        if data.startswith("mode_"):
            m = data.replace("mode_", "")
            set_mode(uid, m)
            bot.answer_callback_query(call.id, "تمام ✅")
            if m == "search":
                bot.send_message(call.message.chat.id, T(uid, "🔍 اكتب اسم الاغنية او الفيديو اللي بتدور عليه", "🔍 Type song or video name"))
            elif m == "pdf":
                bot.send_message(call.message.chat.id, T(uid, "🖼️ ابعت الصور ورا بعض، وبعدين اكتب done عشان احولهم PDF", "🖼️ Send images then done for PDF"))
            else:
                bot.send_message(call.message.chat.id, T(uid, "✅ تمام يا وحش، ابعت اللينك دلوقتي 👇", "✅ OK, send link now 👇"))
        elif data == "lang_menu":
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("🇪🇬 عربي", callback_data="lang_ar"), InlineKeyboardButton("🇺🇸 English", callback_data="lang_en"))
            kb.add(InlineKeyboardButton("🔙 رجوع", callback_data="back_home"))
            safe_edit(call, T(uid, "🌐 اختار اللغة:", "🌐 Choose language:"), kb)
        elif data == "lang_ar":
            set_lang(uid, "ar")
            bot.answer_callback_query(call.id, "عربي 🇪🇬")
            safe_edit(call, welcome_text(call.from_user), home_kb(uid))
        elif data == "lang_en":
            set_lang(uid, "en")
            bot.answer_callback_query(call.id, "English 🇺🇸")
            safe_edit(call, welcome_text(call.from_user), home_kb(uid))
        elif data == "back_home":
            safe_edit(call, welcome_text(call.from_user), home_kb(uid))
        elif data == "show_fav":
            db = load_db()
            lst = db["fav"].get(uid, [])
            if not lst:
                bot.send_message(call.message.chat.id, T(uid, "⭐ المفضلة فاضية لسه", "⭐ Fav is empty"))
            else:
                bot.send_message(call.message.chat.id, "⭐ مفضلتك:\n" + "\n".join(lst))
        elif data == "show_history":
            db = load_db()
            h = db["history"].get(uid, [])
            if not h:
                bot.send_message(call.message.chat.id, T(uid, "📂 لسه محملتش حاجة", "📂 No downloads yet"))
            else:
                bot.send_message(call.message.chat.id, "📂 سجلك:\n" + "\n".join(h[:10]))
        elif data == "my_points":
            db = load_db()
            pts = db["points"].get(uid, 0)
            inv = db["invites"].get(uid, 0)
            bot_username = bot.get_me().username
            link = f"https://t.me/{bot_username}?start={uid}"
            msg = f"🎁 نقطك ودعواتك\n\n━━━━━━━━━━━━━━\n🎁 نقطك: {pts} / {POINTS_FOR_VIP}\n👥 دعواتك: {inv} / {INVITES_FOR_VIP}\n━━━━━━━━━━━━━━\n💡 كل واحد يدخل بدعوتك = +{POINTS_PER_INVITE} نقط\n👑 100 نقطة = VIP ببلاش\n👑 50 دعوة = VIP ببلاش\n━━━━━━━━━━━━━━\n🔗 لينك دعوتك:\n{link}\n\n📤 ابعته لصحابك واكسب 👑"
            bot.send_message(call.message.chat.id, msg)
        elif data == "vip_info":
            db = load_db()
            if is_vip(uid, db):
                days = vip_left_days(uid, db)
                bot.send_message(call.message.chat.id, f"👑 انت VIP\n\n━━━━━━━━━━━━━━\n✅ تحميل بدون حدود\n⚡ اولوية في التحميل\n📅 فاضلك: {days} يوم\n━━━━━━━━━━━━━━\nاستمتع يا وحش 🔥")
            else:
                pts = db["points"].get(uid, 0)
                inv = db["invites"].get(uid, 0)
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton(f"💳 اشترك VIP - {VIP_PRICE} / شهر", callback_data="vip_buy"))
                kb.add(InlineKeyboardButton("🎁 ابعت دعوة واكسب نقط", callback_data="my_points"))
                kb.add(InlineKeyboardButton("🔙 رجوع", callback_data="back_home"))
                bot.send_message(call.message.chat.id, f"👑 اشتراك VIP\n\n━━━━━━━━━━━━━━\n💰 السعر: {VIP_PRICE} / شهر\n✅ شامل كل حاجة\n💎 تحميل بدون حدود\n⚡ اولوية في التحميل\n━━━━━━━━━━━━━━\n🎁 نقطك: {pts} / {POINTS_FOR_VIP}\n👥 دعواتك: {inv} / {INVITES_FOR_VIP}\n━━━━━━━━━━━━━━\n💡 3 طرق تبقى VIP:\n1️⃣ تدفع {VIP_PRICE} - دوس على الزرار تحت\n2️⃣ تجمع {POINTS_FOR_VIP} نقطة\n3️⃣ تجيب {INVITES_FOR_VIP} شخص بدعوتك\n━━━━━━━━━━━━━━\n💳 الدفع: {PAY_METHOD}: {PAY_NUMBER}\n📸 ابعت سكرين شوت بعد الدفع للادمن", reply_markup=kb)
        elif data == "vip_buy":
            name = call.from_user.first_name or "بدون اسم"
            username = "@" + call.from_user.username if call.from_user.username else "مفيش يوزر"
            try:
                bot.send_message(ADMIN_ID, f"🔥 حد عايز يشترك VIP\n\n━━━━━━━━━━━━━━\n👤 الاسم: {name}\n📱 اليوزر: {username}\n🆔 الايدي: {uid}\n💰 السعر: {VIP_PRICE} / شهر\n💳 المفروض يدفع على: {PAY_NUMBER}\n━━━━━━━━━━━━━━\nعشان تخليه VIP اكتب:\n/vip {uid}")
                bot.send_message(call.message.chat.id, f"✅ تمام، بعت طلبك للادمن\n\n💰 الاشتراك: {VIP_PRICE} / شهر\n💳 ادفع على {PAY_METHOD}: {PAY_NUMBER}\n📸 ابعت سكرين شوت الدفع للادمن {ADMIN_USERNAME}\n\nالادمن هيكلمك اول ما يشوفه 👑")
            except:
                bot.send_message(call.message.chat.id, f"كلم الادمن: {ADMIN_USERNAME}")
        elif data == "support":
            bot.send_message(call.message.chat.id, f"📞 الدعم:\n\nكلم الادمن: {ADMIN_USERNAME}\n💳 فودافون كاش: {PAY_NUMBER}\nهنرد عليك في اسرع وقت ❤️")
        elif data == "admin_panel":
            if not is_admin(uid):
                bot.answer_callback_query(call.id, "مش ليك")
                return
            db = load_db()
            vips = len([u for u, e in db["vip"].items() if e > time.time()])
            msg = f"👑 لوحة تحكم\n\n━━━━━━━━━━━━━━\n👥 المستخدمين: {len(db['users'])}\n👑 VIP: {vips}\n━━━━━━━━━━━━━━\n📢 /broadcast رسالتك\n👑 /vip الايدي = VIP شهر\n❌ /unvip الايدي = الغاء VIP"
            bot.send_message(call.message.chat.id, msg)
        elif data == "fav_add":
            db = load_db()
            link = db.get("last_dl", {}).get(uid, "")
            if not link:
                h = db["history"].get(uid, [])
                link = h[0] if h else ""
            if not link:
                bot.answer_callback_query(call.id, "مفيش حاجة تتحفظ")
                return
            lst = db["fav"].get(uid, [])
            if link not in lst:
                lst.append(link)
                db["fav"][uid] = lst
                save_db(db)
                bot.answer_callback_query(call.id, "اتضاف ⭐")
            else:
                bot.answer_callback_query(call.id, "موجود قبل كده")
    except Exception as e:
        print(f"Callback error {data}: {e}")
        try: bot.answer_callback_query(call.id, "حصل مشكلة، جرب تاني")
        except: pass

@bot.message_handler(commands=['done'])
def done_pdf(message):
    uid = str(message.from_user.id)
    if not HAS_PIL:
        bot.reply_to(message, "نزل Pillow الاول: pip install Pillow")
        return
    files = sorted(glob.glob(f"pdf_{uid}_*.jpg"))
    if not files:
        bot.reply_to(message, "مبعتش صور لسه")
        return
    try:
        imgs = [Image.open(f).convert("RGB") for f in files]
        out = f"pdf_{uid}.pdf"
        imgs[0].save(out, save_all=True, append_images=imgs[1:])
        with open(out, "rb") as doc:
            bot.send_document(message.chat.id, doc, caption="اتفضل الـ PDF 🖼️")
        for f in files:
            try: os.remove(f)
            except: pass
        try: os.remove(out)
        except: pass
    except Exception as e:
        bot.reply_to(message, "مشكلة: " + str(e))

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    uid = str(message.from_user.id)
    if get_mode(uid) != "pdf":
        bot.reply_to(message, "دوس على زرار صور لـ PDF الاول من /start")
        return
    try:
        fid = message.photo[-1].file_id
        info = bot.get_file(fid)
        data = bot.download_file(info.file_path)
        n = len(glob.glob(f"pdf_{uid}_*.jpg"))
        with open(f"pdf_{uid}_{n}.jpg", "wb") as f:
            f.write(data)
        bot.reply_to(message, "اتحفظت ✅ - ابعت اللي بعدها او اكتب done")
    except Exception as e:
        bot.reply_to(message, "مشكلة: " + str(e))

@bot.message_handler(func=lambda m: True)
def handle_link(message):
    if not message.text: return
    text = message.text.strip()
    uid = str(message.from_user.id)
    mode = get_mode(uid)

    if text.lower() in ["done", "تم", "خلصت", "/done", "تم ✅", "done ✅"]:
        return done_pdf(message)

    is_link = text.startswith("http")

    # البحث بالاسم - من Piped مش من yt-dlp
    if mode == "search" and not is_link:
        bot.reply_to(message, "🔍 بدور على: " + text + " استنى...")
        try:
            res = piped_search(text)
            if not res or not res.get("id"):
                bot.reply_to(message, "ملقيتش حاجة بالاسم ده")
                return
            base = f"search_{uid}_{int(time.time())}"
            out = piped_download(res["id"], base, want_audio=True)
            if os.path.getsize(out) > 45*1024*1024:
                bot.reply_to(message, "الملف كبير اوي على تيليجرام")
                cleanup_base(base); return
            with open(out, "rb") as a:
                bot.send_audio(message.chat.id, a, caption=f"لقيتهالك 😎\n{res.get('title','')}", reply_markup=fav_kb())
            cleanup_base(base)
            add_point(uid)
            save_history(uid, text)
        except Exception as e:
            bot.reply_to(message, "مشكلة في البحث: " + str(e)[:300])
        return

    if not is_link:
        bot.reply_to(message, T(uid, "ابعت لينك صحيح يا صاحبي، واختار النوع من /start الاول", "Send valid link, choose from /start first"))
        return

    # لو يوتيوب - استخدم Piped
    if is_youtube_url(text):
        vid = extract_youtube_id(text)
        if not vid:
            bot.reply_to(message, "لينك يوتيوب مش مظبوط")
            return
        if mode == "mp3":
            bot.reply_to(message, "🎵 تمام، بحوّل لـ MP3 ⏳")
            base = f"audio_{uid}_{int(time.time())}"
            try:
                out = piped_download(vid, base, want_audio=True)
                if os.path.getsize(out) > 45*1024*1024:
                    bot.reply_to(message, "الملف كبير اوي على تيليجرام")
                    cleanup_base(base); return
                with open(out, "rb") as a:
                    bot.send_audio(message.chat.id, a, caption="اتفضل الـ MP3 يا وحش 🔥", reply_markup=fav_kb())
                cleanup_base(base)
                add_point(uid)
                save_history(uid, text)
            except Exception as e:
                bot.reply_to(message, "الخطأ الحقيقي MP3: " + str(e)[:300])
        else:
            max_h = 720 if mode == "q720" else 1080 if mode == "q1080" else None
            bot.reply_to(message, "📥 تمام، بحمل الفيديو ⏳")
            base = f"video_{uid}_{int(time.time())}"
            try:
                out = piped_download(vid, base, want_audio=False, max_height=max_h)
                if os.path.getsize(out) > 45*1024*1024:
                    bot.reply_to(message, "الفيديو كبير اوي على تيليجرام، جرب جودة 720")
                    cleanup_base(base); return
                with open(out, "rb") as v:
                    bot.send_video(message.chat.id, v, caption="اتفضل الفيديو يا وحش 🔥", reply_markup=fav_kb())
                cleanup_base(base)
                add_point(uid)
                save_history(uid, text)
            except Exception as e:
                bot.reply_to(message, "الخطأ الحقيقي: " + str(e)[:300])
        return

    # تيك توك / انستا / فيس - لسه yt-dlp
    if mode == "mp3":
        bot.reply_to(message, "🎵 تمام، بحوّل لـ MP3 ⏳")
        base = f"audio_{uid}_{int(time.time())}"
        try:
            files = ytdlp_download(text, base, "bestaudio/best", is_audio=True)
            if files:
                if os.path.getsize(files[0]) > 45*1024*1024:
                    bot.reply_to(message, "الملف كبير اوي على تيليجرام")
                    cleanup_base(base); return
                with open(files[0], "rb") as a:
                    bot.send_audio(message.chat.id, a, caption="اتفضل الـ MP3 يا وحش 🔥", reply_markup=fav_kb())
                cleanup_base(base)
                add_point(uid)
                save_history(uid, text)
            else:
                bot.reply_to(message, "مش عارف احول اللينك ده")
        except Exception as e:
            bot.reply_to(message, "الخطأ الحقيقي MP3: " + str(e)[:300])
    else:
        if mode == "q720":
            fmt = "best[height<=720][ext=mp4]/best[height<=720]/18/22/mp4/best"
        elif mode == "q1080":
            fmt = "best[height<=1080][ext=mp4]/best[height<=1080]/22/18/mp4/best"
        else:
            fmt = "18/22/mp4/best[ext=mp4]/best"
        bot.reply_to(message, "📥 تمام، بحمل الفيديو ⏳")
        base = f"video_{uid}_{int(time.time())}"
        try:
            files = ytdlp_download(text, base, fmt, is_audio=False)
            if files:
                if os.path.getsize(files[0]) > 45*1024*1024:
                    bot.reply_to(message, "الفيديو كبير اوي على تيليجرام، جرب جودة 720")
                    cleanup_base(base); return
                with open(files[0], "rb") as v:
                    if files[0].endswith(".mp4"):
                        bot.send_video(message.chat.id, v, caption="اتفضل الفيديو يا وحش 🔥", reply_markup=fav_kb())
                    else:
                        bot.send_document(message.chat.id, v, caption="اتفضل الفيديو يا وحش 🔥", reply_markup=fav_kb())
                cleanup_base(base)
                add_point(uid)
                save_history(uid, text)
            else:
                bot.reply_to(message, "مش عارف احمل اللينك ده")
        except Exception as e:
            bot.reply_to(message, "الخطأ الحقيقي: " + str(e)[:300])

print("البوت هيشتغل دلوقتي...")
while True:
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=True)
    except Exception as e:
        print("اعادة تشغيل بعد خطأ: " + str(e))
        traceback.print_exc()
        time.sleep(5)
