import os, json, time, glob, re, threading, html, asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

def _keep_alive():
    port = int(os.environ.get("PORT", 10000))
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"Bot is running")
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0", port), H).serve_forever()
threading.Thread(target=_keep_alive, daemon=True).start()

import requests, yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = 1159182662  # انت بس
SUPPORT_EMAIL = "your-email@gmail.com"  # <-- غيره لايميلك
DATA_FILE = "users.json"
DATA_LOCK = threading.Lock()
RATE = {}  # uid -> last_time

ALLOWED_DOMAINS = ["youtube.com","youtu.be","tiktok.com","instagram.com","facebook.com","fb.watch","fb.gg","x.com","twitter.com","soundcloud.com","vm.tiktok.com"]
MAX_SIZE_FREE = 50*1024*1024
MAX_SIZE_VIP = 200*1024*1024

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE,"r",encoding="utf-8") as f:
                d=json.load(f)
                if isinstance(d,dict) and "users" in d: return d
        except: pass
    return {"users":{}}
DATA = load_data()

def save_data():
    with DATA_LOCK:
        try:
            tmp = DATA_FILE+".tmp"
            with open(tmp,"w",encoding="utf-8") as f: json.dump(DATA,f,ensure_ascii=False,indent=2)
            os.replace(tmp, DATA_FILE)
        except Exception as e: print(f"save failed: {e}")

def get_user(uid):
    uid=str(uid)
    if uid not in DATA["users"] or not isinstance(DATA["users"][uid],dict):
        DATA["users"][uid]={"lang":None,"vip":0,"state":"home","support_mode":False,"points":0,"invites":0,"invited_by":None,"history":[],"fav":[],"last_active":time.time(),"pdf_photos":[],"translate_mode":False,"summarize_mode":False}
        save_data()
    u=DATA["users"][uid]
    for k,v in {"lang":None,"vip":0,"state":"home","support_mode":False,"points":0,"invites":0,"invited_by":None,"history":[],"fav":[],"last_active":time.time(),"pdf_photos":[],"translate_mode":False,"summarize_mode":False}.items():
        if k not in u: u[k]=v
    return u

def is_vip(uid):
    try: return float(get_user(uid).get("vip",0)) > time.time()
    except: return False

def is_admin(uid): return int(uid)==ADMIN_ID

def rate_limited(uid):
    now=time.time()
    if now - RATE.get(str(uid),0) < 5: return True
    RATE[str(uid)]=now; return False

def safe_url(url):
    try:
        host=urlparse(url).netloc.lower().replace("www.","")
        return any(host==d or host.endswith("."+d) for d in ALLOWED_DOMAINS)
    except: return False

def clean_text(s, max_len=500):
    s=re.sub(r'[<>&]', '', str(s or ""))
    return s[:max_len]

TEXTS={
 "ar":{"choose_lang_title":"اختر لغتك","welcome":"اهلا بيك في نزل","welcome_sub":"نزل فيديوهات وصوتيات من كل المنصات","points":"نقطك","invites":"دعواتك","vip_left":"فاضل في VIP","vip_days":"يوم","not_vip":"انت مش VIP","send_link":"ابعت لينك دلوقتي","search_btn":"بحث بالاسم","download_mp3":"تحميل MP3","download_video":"تحميل فيديو","quality_720":"جودة 720","quality_1080":"جودة 1080","quality_2k":"جودة 2K ✨","quality_4k":"جودة 4K 👑","pdf_btn":"صور لـ PDF","fav_btn":"مفضلتي","history_btn":"سجلي","points_btn":"نقطي ودعوتي","vip_btn":"VIP","lang_btn":"اللغة","support_btn":"الدعم","admin_btn":"لوحة تحكم","summarize_btn":"تلخيص 🎙️","translate_btn":"ترجمة AI 🌐","search_prompt":"اكتب اسم الاغنية او الفيديو اللي بتدور عليه","searching":"بدور علي","not_found":"ملقيتش حاجة، جرب اسم تاني او ابعت لينك","choose_result":"اختر من النتايج دي","choose_format":"اختار الصيغة","downloading":"بنحمل دلوقتي، استنى ثواني... ⏳","download_done":"تم التحميل ✅","download_failed":"التحميل فشل، جرب تاني او ابعت لينك تاني","support_prompt":"اكتب رسالتك للدعم","support_sent":"رسالتك اتبعت للدعم ✅","support_reply_title":"رد الدعم 💬","help_text":"ابعت لينك من يوتيوب او تيك توك او انستا او فيسبوك، او دوس بحث بالاسم","lang_changed":"تم تغيير اللغة ✅","vip_done":"بقيت VIP لمدة 30 يوم 👑","vip_congrats":"مبروك، بقيت VIP 👑","back":"رجوع","home":"القايمة الرئيسية","idle":"وحشتنا! 👋\nدوس ابدأ عشان تكمل","translate_prompt":"ابعت النص اللي عايز تترجمه","translate_done":"الترجمة:","summarize_prompt":"ابعت لينك الفيديو اللي عايز تلخصه","summarizing":"بفرغ الفيديو وبجهز التلخيص... 🎙️","pdf_prompt":"ابعت الصور، ولما تخلص دوس انشاء PDF","pdf_done":"تم انشاء الـ PDF ✅","points_title":"نقاطي ودعوتي 🎁","invite_link":"لينك دعوتك:","admin_title":"لوحة تحكم 👑","users_count":"عدد المستخدمين:","not_admin":"مش مسموح ليك تدخل هنا ⛔","too_big":"الفيديو كبير اوي على النسخة المجانية، خد VIP عشان تحمله","rate_msg":"استنى 5 ثواني وحاول تاني ⏳","invalid_link":"اللينك ده مش مدعوم، ابعت لينك من المنصات المدعومة بس"},
 "en":{"choose_lang_title":"Choose your language","welcome":"Welcome to Nezel","welcome_sub":"Download videos and audios from all platforms","points":"Points","invites":"Invites","vip_left":"VIP left","vip_days":"days","not_vip":"You are not VIP","send_link":"Send link now","search_btn":"Search by name","download_mp3":"Download MP3","download_video":"Download Video","quality_720":"Quality 720","quality_1080":"Quality 1080","quality_2k":"Quality 2K ✨","quality_4k":"Quality 4K 👑","pdf_btn":"Images to PDF","fav_btn":"My Favorites","history_btn":"My History","points_btn":"My Points","vip_btn":"VIP","lang_btn":"Language","support_btn":"Support","admin_btn":"Admin Panel","summarize_btn":"Summarize 🎙️","translate_btn":"AI Translate 🌐","search_prompt":"Type song or video name","searching":"Searching for","not_found":"Nothing found, try another name","choose_result":"Choose from results","choose_format":"Choose format","downloading":"Downloading now... ⏳","download_done":"Download done ✅","download_failed":"Download failed, try again","support_prompt":"Write your message to support","support_sent":"Your message sent ✅","support_reply_title":"Support reply 💬","help_text":"Send link from YouTube, TikTok, Instagram or Facebook","lang_changed":"Language changed ✅","vip_done":"You are VIP for 30 days 👑","vip_congrats":"Congrats, you are VIP 👑","back":"Back","home":"Main Menu","idle":"Missed you! 👋\nTap Start to continue","translate_prompt":"Send text to translate","translate_done":"Translation:","summarize_prompt":"Send video link to summarize","summarizing":"Transcribing video... 🎙️","pdf_prompt":"Send photos, then tap Create PDF","pdf_done":"PDF created ✅","points_title":"My Points & Invites 🎁","invite_link":"Your invite link:","admin_title":"Admin Panel 👑","users_count":"Users:","not_admin":"Not allowed ⛔","too_big":"Video too big for free version, get VIP","rate_msg":"Wait 5 seconds and try again ⏳","invalid_link":"This link is not supported"}
}
def T(uid,key):
    u=get_user(uid); lang=u.get("lang") or "ar"
    if lang not in TEXTS: lang="ar"
    return TEXTS[lang].get(key,key)

def lang_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton("العربية 🇪🇬",callback_data="set_lang_ar")],[InlineKeyboardButton("English 🇬🇧",callback_data="set_lang_en")]])
def back_kb(uid): return InlineKeyboardMarkup([[InlineKeyboardButton(f"⬅️ {T(uid,'back')}",callback_data="home")]])

def main_keyboard(uid):
    u=get_user(uid)
    if is_vip(uid):
        days=int((float(u.get("vip",0))-time.time())//86400)+1
        vip_txt=f"👑 VIP | {max(1,days)} {T(uid,'vip_days')}"
    else: vip_txt=f"👑 {T(uid,'vip_btn')}"
    rows=[
      [InlineKeyboardButton(f"🎵 {T(uid,'download_mp3')}",callback_data="help_mp3"), InlineKeyboardButton(f"📥 {T(uid,'download_video')}",callback_data="help_video")],
      [InlineKeyboardButton(f"🎬 {T(uid,'quality_720')}",callback_data="help_video"), InlineKeyboardButton(f"🎬 {T(uid,'quality_1080')}",callback_data="help_video")],
      [InlineKeyboardButton(f"✨ {T(uid,'quality_2k')}",callback_data="help_video"), InlineKeyboardButton(f"👑 {T(uid,'quality_4k')}",callback_data="help_video")],
      [InlineKeyboardButton(f"🔍 {T(uid,'search_btn')}",callback_data="search"), InlineKeyboardButton(f"🎙️ {T(uid,'summarize_btn')}",callback_data="summarize")],
      [InlineKeyboardButton(f"🌐 {T(uid,'translate_btn')}",callback_data="translate"), InlineKeyboardButton(f"🖼️ {T(uid,'pdf_btn')}",callback_data="pdf_info")],
      [InlineKeyboardButton(f"⭐ {T(uid,'fav_btn')}",callback_data="fav_info"), InlineKeyboardButton(f"📂 {T(uid,'history_btn')}",callback_data="history_info")],
      [InlineKeyboardButton(f"🎁 {T(uid,'points_btn')}",callback_data="points_info"), InlineKeyboardButton(vip_txt,callback_data="vip_info")],
      [InlineKeyboardButton(f"🌐 {T(uid,'lang_btn')}",callback_data="lang"), InlineKeyboardButton(f"📞 {T(uid,'support_btn')}",callback_data="support")],
    ]
    if is_admin(uid):
        rows.append([InlineKeyboardButton(f"👑 {T(uid,'admin_btn')}",callback_data="admin_info")])
    return InlineKeyboardMarkup(rows)

def show_main_menu_text(uid,name):
    u=get_user(uid); points=u.get("points",0); invites=u.get("invites",0)
    if is_vip(uid):
        days=int((float(u.get("vip",0))-time.time())//86400)+1
        vip_line=f"👑 {T(uid,'vip_left')} {max(1,days)} {T(uid,'vip_days')}  •  ━━━━ {min(100, days*3)}%"
    else: vip_line=f"👑 {T(uid,'not_vip')}  •  خد VIP وشيل كل الحدود"
    p_bar="🟩"*int(points//10)+"⬜"*(10-int(points//10))
    return f"✨ {T(uid,'welcome')} {html.escape(name)} 👑\n\n{T(uid,'welcome_sub')}\n━━━━━━━━━━━━━━\n🎁 {T(uid,'points')}: {points} / 100\n{p_bar}\n👥 {T(uid,'invites')}: {invites} / 50\n{vip_line}\n━━━━━━━━━━━━━━\n👇 {T(uid,'send_link')}"

def do_search(query):
    query=clean_text(query,100)
    try:
        opts={"quiet":True,"no_warnings":True,"extract_flat":True,"skip_download":True,"socket_timeout":30}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info=ydl.extract_info(f"ytsearch5:{query}",download=False)
            entries=info.get("entries",[]) if info else []
            res=[]
            for e in entries:
                if e and e.get("id"): res.append({"id":e.get("id"),"title":e.get("title",query),"src":"yt"})
            if res: return res
    except Exception as e: print(f"search err: {e}")
    try:
        r=requests.get("https://inv.nadeko.net/api/v1/search",params={"q":query,"type":"video"},timeout=15,headers={"User-Agent":"Mozilla/5.0"})
        if r.status_code==200:
            res=[]
            for it in r.json()[:5]:
                if it.get("videoId"): res.append({"id":it.get("videoId"),"title":it.get("title",query),"src":"yt"})
            if res: return res
    except Exception as e: print(f"invidious err: {e}")
    return []

def download_with_ytdlp(url,base,want_audio=False,quality="720"):
    if want_audio: fmt="bestaudio/best"
    elif quality=="4K": fmt="bestvideo[height<=2160]+bestaudio/best[height<=2160]/best"
    elif quality=="2K": fmt="bestvideo[height<=1440]+bestaudio/best[height<=1440]/best"
    elif quality=="1080": fmt="bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
    else: fmt="bestvideo[height<=720]+bestaudio/best[height<=720]/best"
    opts={"format":fmt,"outtmpl":base+".%(ext)s","quiet":True,"no_warnings":True,"nocheckcertificate":True,"socket_timeout":90,"max_filesize":MAX_SIZE_VIP,"http_headers":{"User-Agent":"Mozilla/5.0"},"extractor_args":{"youtube":{"player_client":["android","ios"],"player_skip":["configs","web"]}}}
    if want_audio: opts["postprocessors"]=[{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}]
    with yt_dlp.YoutubeDL(opts) as ydl: ydl.download([url])
    files=[f for f in glob.glob(base+".*") if not f.endswith(".part")]
    return files

def translate_text(text,target="en"):
    # ترجمة سريعة مجانية - MyMemory
    try:
        r=requests.get("https://api.mymemory.translated.net/get",params={"q":text[:500],"langpair":"ar|en" if target=="en" else "en|ar"},timeout=10)
        if r.status_code==200: return r.json().get("responseData",{}).get("translatedText",text)
    except: pass
    return text

def summarize_video(url):
    # بيجيب الترجمة التلقائية ويرتبها
    try:
        opts={"quiet":True,"skip_download":True,"writesubtitles":True,"writeautomaticsub":True,"subtitleslangs":["ar","en"],"subtitlesformat":"vtt","socket_timeout":30}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info=ydl.extract_info(url,download=False)
            title=info.get("title","فيديو")
            subs=info.get("automatic_captions") or info.get("subtitles") or {}
            lang="ar" if "ar" in subs else "en" if "en" in subs else list(subs.keys())[0] if subs else None
            if not lang: return f"📝 {title}\n\nالفيديو ده مفيهوش ترجمة تلقائية، جرب فيديو تاني فيه كلام واضح."
            # نجيب ملف الترجمة
            fmt=subs[lang][0].get("url") if subs[lang] else None
            if not fmt: return f"📝 {title}\n\nمش قادر افرغ الفيديو ده."
            txt=requests.get(fmt,timeout=15).text
            lines=[]
            for l in txt.splitlines():
                l=l.strip()
                if not l or "-->" in l or l.startswith("WEBVTT") or l.isdigit(): continue
                l=re.sub(r"<[^>]+>","",l)
                if l not in lines: lines.append(l)
            full=" ".join(lines)[:4000]
            # تلخيص بسيط: اول 8 جمل مرتبة
            sents=re.split(r"[.!؟\n]+",full)
            sents=[s.strip() for s in sents if len(s.strip())>20][:8]
            out=f"🎙️ تلخيص: {title}\n━━━━━━━━━━━━━━\n\n"
            for i,s in enumerate(sents,1): out+=f"{i}. {s}\n\n"
            out+=f"━━━━━━━━━━━━━━\n📝 عدد الكلمات التقريبي: {len(full.split())}"
            return out
    except Exception as e:
        print(f"summarize err: {e}")
        return "مش قادر افرغ الفيديو ده، جرب لينك تاني."

async def check_idle(context):
    # كل دقيقة يشيك مين قعد 5 دقايق
    now=time.time()
    for uid_str,u in list(DATA["users"].items()):
        if u.get("lang") and now - u.get("last_active",now) > 300 and not u.get("idle_sent"):
            u["idle_sent"]=True; save_data()
            try: await context.bot.send_message(chat_id=int(uid_str),text=f"{T(int(uid_str),'idle')}",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ ابدأ",callback_data="home")]]))
            except: pass

async def start(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; u=get_user(uid)
    # نظام الدعوة: /start 123456
    if context.args:
        inviter=context.args[0].strip()
        if inviter.isdigit() and inviter!=str(uid) and not u.get("invited_by"):
            u["invited_by"]=inviter; save_data()
            inv=get_user(inviter); inv["invites"]=inv.get("invites",0)+1; inv["points"]=inv.get("points",0)+10; save_data()
            try: await context.bot.send_message(chat_id=int(inviter),text=f"🎉 حد دخل بدعوتك! +10 نقط\nنقطك بقت: {inv['points']}")
            except: pass
    u["state"]="home"; u["support_mode"]=False; u["idle_sent"]=False; u["last_active"]=time.time(); save_data()
    await update.message.reply_text("اختر لغتك\n\nChoose your language",reply_markup=lang_keyboard())

async def vip_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    if not is_admin(uid): await update.message.reply_text("Not allowed"); return
    if not context.args: await update.message.reply_text("Use: /vip 123456"); return
    target=context.args[0].strip()
    if not target.isdigit(): await update.message.reply_text("ID must be numbers"); return
    tu=get_user(target); tu["vip"]=time.time()+30*86400; save_data()
    await update.message.reply_text(T(uid,"vip_done"))
    try: await context.bot.send_message(chat_id=int(target),text=T(int(target),"vip_congrats"))
    except: pass

async def reply_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    if not is_admin(uid): return
    if len(context.args)<2: await update.message.reply_text("Use: /reply 123456 your message"); return
    target=context.args[0]
    if not target.isdigit(): await update.message.reply_text("ID wrong"); return
    msg=clean_text(" ".join(context.args[1:]),1000)
    try:
        await context.bot.send_message(chat_id=int(target),text=f"{T(int(target),'support_reply_title')}\n\n{msg}")
        await update.message.reply_text("Sent ✅")
    except: await update.message.reply_text("Error sending")

async def handle_button(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); uid=q.from_user.id; u=get_user(uid); u["last_active"]=time.time(); u["idle_sent"]=False; save_data()
    data=q.data or ""
    if data in ["set_lang_ar","set_lang_en"]:
        u["lang"]="ar" if data=="set_lang_ar" else "en"; u["state"]="home"; u["support_mode"]=False; save_data()
        name=q.from_user.first_name or ""
        await q.message.reply_text(T(uid,"lang_changed"))
        await q.message.reply_text(show_main_menu_text(uid,name),reply_markup=main_keyboard(uid)); return
    if not u.get("lang"):
        await q.message.reply_text("اختر لغتك\n\nChoose your language",reply_markup=lang_keyboard()); return
    if data=="search": u["state"]="search"; u["support_mode"]=False; save_data(); await q.message.reply_text(f"🔍 {T(uid,'search_prompt')}")
    elif data=="lang": await q.message.reply_text("اختر لغتك\n\nChoose your language",reply_markup=lang_keyboard())
    elif data=="translate": u["state"]="translate"; save_data(); await q.message.reply_text(f"🌐 {T(uid,'translate_prompt')}\nابعت النص بالعربي هيترجم انجليزي، وبالانجليزي هيترجم عربي.")
    elif data=="summarize": u["state"]="summarize"; save_data(); await q.message.reply_text(f"🎙️ {T(uid,'summarize_prompt')}")
    elif data=="support":
        u["state"]="support"; u["support_mode"]=True; save_data()
        await q.message.reply_text(f"📞 اهلا بيك في الدعم\n📧 ايميلنا: {SUPPORT_EMAIL}\n\nاكتب رسالتك، وابعت الـ ID بتاعك والاستفسار، وهنرد عليك في اقرب وقت.\nالـ ID بتاعك: `{uid}`")
    elif data in ["help_mp3","help_video","help"]: await q.message.reply_text(T(uid,"help_text"))
    elif data=="vip_info":
        if is_vip(uid):
            days=int((float(u.get("vip",0))-time.time())//86400)+1
            await q.message.reply_text(f"👑 ━━━━━━━━━━━━━━\n👑 VIP ACTIVE\n👑 {T(uid,'vip_left')} {max(1,days)} {T(uid,'vip_days')}\n👑 تحميل 4K + بدون حدود\n━━━━━━━━━━━━━━",reply_markup=back_kb(uid))
        else: await q.message.reply_text(f"👑 انت مش VIP\n\nمميزات VIP:\n✅ جودة 4K و 2K\n✅ تحميل لحد 200 ميجا\n✅ بدون حدود\n\nكلم الدعم عشان تشترك: {SUPPORT_EMAIL}",reply_markup=back_kb(uid))
    elif data=="points_info":
        bot_username=(await context.bot.get_me()).username
        link=f"https://t.me/{bot_username}?start={uid}"
        await q.message.reply_text(f"🎁 {T(uid,'points_title')}\n━━━━━━━━━━━━━━\n🎁 {T(uid,'points')}: {u.get('points',0)} / 100\n👥 {T(uid,'invites')}: {u.get('invites',0)} / 50\n\n🔗 {T(uid,'invite_link')}\n{link}\n\nكل صاحب يدخل من لينكك = +10 نقط\n100 نقطة = VIP مجاني 7 ايام",reply_markup=back_kb(uid))
    elif data=="admin_info":
        if not is_admin(uid): await q.message.reply_text(T(uid,"not_admin")); return
        total=len(DATA["users"]); vips=sum(1 for x in DATA["users"].values() if float(x.get("vip",0))>time.time())
        await q.message.reply_text(f"👑 {T(uid,'admin_title')}\n━━━━━━━━━━━━━━\n👥 {T(uid,'users_count')} {total}\n👑 VIP: {vips}\n📧 الدعم: {SUPPORT_EMAIL}\n\nاوامر الادمن:\n/vip <ID> - ادي VIP\n/reply <ID> <رسالة> - رد على حد",reply_markup=back_kb(uid))
    elif data=="pdf_info": u["state"]="pdf"; u["pdf_photos"]=[]; save_data(); await q.message.reply_text(f"🖼️ {T(uid,'pdf_prompt')}\nبعد ما تبعت الصور دوس هنا:",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📄 انشاء PDF",callback_data="make_pdf")],[InlineKeyboardButton(f"⬅️ {T(uid,'back')}",callback_data="home")]]))
    elif data=="make_pdf": await make_pdf(update,context,uid)
    elif data=="fav_info": await q.message.reply_text(f"⭐ مفضلتك فاضية لسه\nابعت لينك ودوس ⭐ عشان تحفظه",reply_markup=back_kb(uid))
    elif data=="history_info":
        hist=u.get("history",[])[-5:]
        if not hist: await q.message.reply_text("📂 سجلك فاضي",reply_markup=back_kb(uid))
        else:
            txt="📂 اخر 5 تحميلات:\n\n"+"\n".join([f"• {h[:50]}" for h in hist])
            await q.message.reply_text(txt,reply_markup=back_kb(uid))
    elif data=="home":
        name=q.from_user.first_name or ""; u["state"]="home"; u["support_mode"]=False; save_data()
        await q.message.reply_text(show_main_menu_text(uid,name),reply_markup=main_keyboard(uid))

async def make_pdf(update,context,uid):
    from PIL import Image
    import io
    q=update.callback_query; u=get_user(uid); photos=u.get("pdf_photos",[])
    if not photos:
        await q.message.reply_text("ابعت صور الاول"); return
    try:
        imgs=[]
        for fid in photos:
            f=await context.bot.get_file(fid); b=await f.download_as_bytearray(); img=Image.open(io.BytesIO(b)).convert("RGB"); imgs.append(img)
        out=io.BytesIO(); imgs[0].save(out,format="PDF",save_all=True,append_images=imgs[1:],resolution=300)
        out.seek(0); await q.message.reply_document(document=out,filename=f"Nezel_{uid}.pdf",caption=f"📄 {T(uid,'pdf_done')} - {len(imgs)} صورة")
        u["pdf_photos"]=[]; u["state"]="home"; save_data()
    except Exception as e: print(f"pdf err: {e}"); await q.message.reply_text(T(uid,"download_failed"))

async def handle_dl(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if rate_limited(uid): await q.message.reply_text(T(uid,"rate_msg")); return
    data=q.data or ""; want_audio=False; quality="720"; vid=""
    if data.startswith("dl_audio_"): vid=data.replace("dl_audio_",""); want_audio=True
    elif data.startswith("dl_4k_"): vid=data.replace("dl_4k_",""); quality="4K"
    elif data.startswith("dl_2k_"): vid=data.replace("dl_2k_",""); quality="2K"
    elif data.startswith("dl_1080_"): vid=data.replace("dl_1080_",""); quality="1080"
    elif data.startswith("dl_720_"): vid=data.replace("dl_720_",""); quality="720"
    elif data.startswith("dl_video_"): vid=data.replace("dl_video_",""); quality="720"
    else: return
    if not re.match(r"^[A-Za-z0-9_-]{6,20}$",vid): await q.message.reply_text(T(uid,"download_failed")); return
    if quality in ["2K","4K"] and not is_vip(uid): await q.message.reply_text("جودة 2K و 4K للـ VIP بس 👑\nكلم الدعم للاشتراك"); return
    await q.message.reply_text(T(uid,"downloading"))
    try:
        base=f"/tmp/{uid}_{int(time.time())}"
        files=download_with_ytdlp(f"https://www.youtube.com/watch?v={vid}",base,want_audio=want_audio,quality=quality)
        if not files: await q.message.reply_text(T(uid,"download_failed")); return
        if os.path.getsize(files[0]) > (MAX_SIZE_VIP if is_vip(uid) else MAX_SIZE_FREE):
            os.remove(files[0]); await q.message.reply_text(T(uid,"too_big")); return
        with open(files[0],"rb") as f:
            if want_audio: await q.message.reply_audio(f)
            else: await q.message.reply_video(f)
        u=get_user(uid); u["history"]=u.get("history",[])[-20:]+[vid]; save_data()
        try: os.remove(files[0])
        except: pass
    except Exception as e: print(f"dl err: {e}"); await q.message.reply_text(T(uid,"download_failed"))

async def handle_choose_result(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); uid=q.from_user.id; data=q.data or ""
    if not data.startswith("pick_"): return
    vid=data.replace("pick_","")
    kb=InlineKeyboardMarkup([
      [InlineKeyboardButton(f"🎵 {T(uid,'download_mp3')}",callback_data=f"dl_audio_{vid}")],
      [InlineKeyboardButton(f"📥 فيديو - 720",callback_data=f"dl_720_{vid}")],
      [InlineKeyboardButton(f"📥 فيديو - 1080",callback_data=f"dl_1080_{vid}")],
      [InlineKeyboardButton(f"✨ فيديو - 2K",callback_data=f"dl_2k_{vid}"), InlineKeyboardButton(f"👑 فيديو - 4K",callback_data=f"dl_4k_{vid}")],
      [InlineKeyboardButton(f"⬅️ {T(uid,'back')}",callback_data="home")],
    ])
    await q.message.reply_text(T(uid,"choose_format"),reply_markup=kb)

async def handle_message(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; u=get_user(uid); u["last_active"]=time.time(); u["idle_sent"]=False; save_data()
    # صور للـ PDF
    if update.message.photo:
        if u.get("state")=="pdf":
            u["pdf_photos"]=u.get("pdf_photos",[])+[update.message.photo[-1].file_id]; save_data()
            await update.message.reply_text(f"تم اضافة الصورة ✅ ({len(u['pdf_photos'])}) - ابعت كمان او دوس انشاء PDF")
            return
        else:
            await update.message.reply_text("دوس على صور لـ PDF الاول عشان ابدأ اجمع صورك"); return
    text=clean_text((update.message.text or "").strip(),1000)
    if not text: return
    if rate_limited(uid) and "http" in text: await update.message.reply_text(T(uid,"rate_msg")); return
    if not u.get("lang"):
        await update.message.reply_text("اختر لغتك\n\nChoose your language",reply_markup=lang_keyboard()); return
    if u.get("support_mode") or u.get("state")=="support":
        u["support_mode"]=False; u["state"]="home"; save_data()
        await update.message.reply_text(f"✅ {T(uid,'support_sent')}\n📧 هيوصلك الرد على الايميل او هنا.")
        if ADMIN_ID:
            try:
                name=update.effective_user.first_name or ""
                await context.bot.send_message(chat_id=ADMIN_ID,text=f"📞 رسالة دعم جديدة\nالاسم: {html.escape(name)}\nالايدي: {uid}\nالايميل: {SUPPORT_EMAIL}\n----------------\n{text}\n----------------\nللرد: /reply {uid} رسالتك")
            except Exception as e: print(f"support fwd err: {e}")
        await update.message.reply_text(show_main_menu_text(uid,update.effective_user.first_name or ""),reply_markup=main_keyboard(uid)); return
    if u.get("state")=="translate":
        u["state"]="home"; save_data()
        # لو عربي يترجم انجليزي والعكس
        is_ar=any("\u0600" <= c <= "\u06FF" for c in text)
        tr=translate_text(text,"en" if is_ar else "ar")
        await update.message.reply_text(f"🌐 {T(uid,'translate_done')}\n\n{tr}"); return
    if u.get("state")=="summarize":
        u["state"]="home"; save_data()
        if not safe_url(text): await update.message.reply_text(T(uid,"invalid_link")); return
        await update.message.reply_text(T(uid,"summarizing"))
        summ=summarize_video(text)
        await update.message.reply_text(summ); return
    if u.get("state")=="search":
        u["state"]="home"; save_data()
        msg=await update.message.reply_text(f"🔍 {T(uid,'searching')}: {text}...")
        results=do_search(text)
        if not results: await msg.edit_text(T(uid,"not_found")); return
        buttons=[]
        for r in results:
            title=r["title"][:35]+"..." if len(r["title"])>35 else r["title"]
            buttons.append([InlineKeyboardButton(f"🎵 {title}",callback_data=f"pick_{r['id']}")])
        buttons.append([InlineKeyboardButton(f"⬅️ {T(uid,'back')}",callback_data="home")])
        await msg.edit_text(f"{T(uid,'choose_result')}:",reply_markup=InlineKeyboardMarkup(buttons)); return
    if "http" in text:
        if not safe_url(text): await update.message.reply_text(T(uid,"invalid_link")); return
        await update.message.reply_text(T(uid,"downloading"))
        try:
            base=f"/tmp/{uid}_{int(time.time())}"
            files=download_with_ytdlp(text,base,want_audio=False,quality="720")
            if files:
                if os.path.getsize(files[0]) > (MAX_SIZE_VIP if is_vip(uid) else MAX_SIZE_FREE):
                    os.remove(files[0]); await update.message.reply_text(T(uid,"too_big")); return
                with open(files[0],"rb") as f: await update.message.reply_video(f)
                try: os.remove(files[0])
                except: pass
                # زرار تحويل لـ MP3 لاي لينك
                await update.message.reply_text("عايز تحوله اغنية؟ 🎵",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎵 تحويل لـ MP3",callback_data="convert_mp3")]]))
            else: await update.message.reply_text(T(uid,"download_failed"))
        except Exception as e: print(f"link dl err: {e}"); await update.message.reply_text(T(uid,"download_failed"))
        return
    await update.message.reply_text(show_main_menu_text(uid,update.effective_user.first_name or ""),reply_markup=main_keyboard(uid))

async def handle_convert_mp3(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    await q.message.reply_text("ابعت لينك الفيديو تاني وهحوله MP3 على طول 🎵\nاو دوس بحث بالاسم واختار MP3")

def main():
    if not BOT_TOKEN: print("ERROR: BOT_TOKEN missing"); return
    app=Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("vip",vip_cmd))
    app.add_handler(CommandHandler("reply",reply_cmd))
    app.add_handler(CallbackQueryHandler(handle_dl,pattern=r"^dl_"))
    app.add_handler(CallbackQueryHandler(handle_choose_result,pattern=r"^pick_"))
    app.add_handler(CallbackQueryHandler(handle_convert_mp3,pattern=r"^convert_mp3"))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.PHOTO,handle_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,handle_message))
    if app.job_queue: app.job_queue.run_repeating(check_idle,interval=60,first=10)
    print("Bot started - SECURE VERSION")
    app.run_polling()

if __name__=="__main__": main()
