import os, json, time, threading, subprocess, glob, sys, traceback
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

try:
    from PIL import Image
    HAS_PIL = True
except:
    HAS_PIL = False

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
    return {"users": {}, "fav": {}, "history": {}, "points": {}, "vip": {}, "invites": {}, "mode": {}, "lang": {}}

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
    db = load_db()
    lang = db["lang"].get(str(uid), "ar")
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
    left = int((exp - time.time()) / 86400) + 1
    return max(left, 0)

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

@bot.message_handler(commands=['start'])
def start(message):
    uid = str(message.from_user.id)
    db = load_db()
    if uid not in db["users"]:
        db["users"][uid] = {"name": message.from_user.first_name, "username": message.from_user.username, "time": time.time()}
        parts = message.text.split()
        if len(parts) > 1:
            inviter = parts[1].strip()
            if inviter != uid and inviter in db["users"]:
                db["points"][inviter] = db["points"].get(inviter, 0) + POINTS_PER_INVITE
                db["invites"][inviter] = db["invites"].get(inviter, 0) + 1
                inv_count = db["invites"][inviter]
                save_db(db)
                if inv_count >= INVITES_FOR_VIP and not is_vip(inviter, db):
                    db = load_db()
                    make_vip_auto(inviter, db, f"🔥 جبت {INVITES_FOR_VIP} شخص بدعوتك - تستاهل VIP ببلاش!")
                else:
                    try:
                        bot.send_message(int(inviter), f"🎁 حد دخل بدعوتك!\n\n+{POINTS_PER_INVITE} نقط ✨\n🎁 نقطك: {db['points'][inviter]} / 100\n👥 دعواتك: {inv_count} / 50\n\nلو وصلت 50 دعوة هتبقى VIP ببلاش 👑")
                    except: pass
        save_db(db)
    bot.reply_to(message, welcome_text(message.from_user, db), reply_markup=home_kb(uid))

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
                bot.send_message(call.message.chat.id, T(uid, "🖼️ ابعت الصور ورا بعض، وبعدين اكتب /done عشان احولهم PDF", "🖼️ Send images then /done for PDF"))
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
        bot.reply_to(message, "اتحفظت ✅ - ابعت اللي بعدها او اكتب /done")
    except Exception as e:
        bot.reply_to(message, "مشكلة: " + str(e))

def cleanup_base(base):
    for f in glob.glob(base + "*"):
        try: os.remove(f)
        except: pass

@bot.message_handler(func=lambda m: True)
def handle_link(message):
    if not message.text: return
    text = message.text.strip()
    uid = str(message.from_user.id)
    mode = get_mode(uid)
    is_link = text.startswith("http")
    if mode == "search" and not is_link:
        bot.reply_to(message, "🔍 بدور على: " + text + " استنى...")
        try:
            q = "ytsearch1:" + text
            base = f"search_{uid}_{int(time.time())}"
            subprocess.run([sys.executable, "-m", "yt_dlp", "-x", "--audio-format", "mp3", "--no-playlist", "-o", base + ".%(ext)s", q], timeout=180, capture_output=True)
            mp3s = [f for f in os.listdir(".") if f.startswith(base) and f.endswith(".mp3")]
            if mp3s:
                with open(mp3s[0], "rb") as a:
                    bot.send_audio(message.chat.id, a, caption="لقيتهالك 😎", reply_markup=fav_kb())
                cleanup_base(base)
                add_point(uid)
                db = load_db()
                h = db["history"].get(uid, [])
                h.insert(0, text[:80]); db["history"][uid] = h[:20]; save_db(db)
            else:
                bot.reply_to(message, "ملقيتش حاجة بالاسم ده")
        except Exception as e:
            bot.reply_to(message, "مشكلة: " + str(e))
        return
    if not is_link:
        bot.reply_to(message, T(uid, "ابعت لينك صحيح يا صاحبي، واختار النوع من /start الاول", "Send valid link, choose from /start first"))
        return
    db = load_db()
    h = db["history"].get(uid, [])
    h.insert(0, text[:80]); db["history"][uid] = h[:20]; save_db(db)
    if mode == "mp3":
        bot.reply_to(message, T(uid, "🎵 تمام، بحوّل لـ MP3 ⏳", "🎵 Converting to MP3 ⏳"))
        base = f"audio_{uid}_{int(time.time())}"
        try:
            subprocess.run([sys.executable, "-m", "yt_dlp", "-x", "--audio-format", "mp3", "--no-playlist", "-o", base + ".%(ext)s", text], timeout=180, capture_output=True)
            mp3s = [f for f in os.listdir(".") if f.startswith(base) and f.endswith(".mp3")]
            if mp3s:
                with open(mp3s[0], "rb") as a:
                    bot.send_audio(message.chat.id, a, caption="اتفضل الـ MP3 يا وحش 🔥", reply_markup=fav_kb())
                cleanup_base(base)
                add_point(uid)
            else:
                bot.reply_to(message, T(uid, "مش عارف احول اللينك ده", "Can't convert this link"))
        except Exception as e:
            bot.reply_to(message, "مشكلة: " + str(e))
    else:
        if mode == "q720":
            fmt = "best[height<=720][ext=mp4]/best[height<=720]/best"
        elif mode == "q1080":
            fmt = "best[height<=1080][ext=mp4]/best[height<=1080]/best"
        else:
            fmt = "best[ext=mp4]/best"
        bot.reply_to(message, T(uid, "📥 تمام، بحمل الفيديو ⏳", "📥 Downloading video ⏳"))
        base = f"video_{uid}_{int(time.time())}"
        try:
            subprocess.run([sys.executable, "-m", "yt_dlp", "-f", fmt, "--no-playlist", "-o", base + ".%(ext)s", text], timeout=300, capture_output=True)
            vids = [f for f in os.listdir(".") if f.startswith(base) and not f.endswith(".part")]
            if vids:
                with open(vids[0], "rb") as v:
                    if vids[0].endswith(".mp4"):
                        bot.send_video(message.chat.id, v, caption="اتفضل الفيديو يا وحش 🔥", reply_markup=fav_kb())
                    else:
                        bot.send_document(message.chat.id, v, caption="اتفضل الفيديو يا وحش 🔥", reply_markup=fav_kb())
                cleanup_base(base)
                add_point(uid)
            else:
                bot.reply_to(message, T(uid, "مش عارف احمل اللينك ده", "Can't download this link"))
        except Exception as e:
            bot.reply_to(message, "مشكلة: " + str(e))

print("البوت هيشتغل دلوقتي...")
while True:
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=True)
    except Exception as e:
        print("اعادة تشغيل بعد خطأ: " + str(e))
        traceback.print_exc()
        time.sleep(5)
