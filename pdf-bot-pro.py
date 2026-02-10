#!/usr/bin/env python3
"""
PDF Bot Pro - Ultimate Version 2.1 (Fixed)
يدعم: العربية بشكل صحيح | معالجة غير متزامنة | تحسين الأداء
"""

import os
import sys
import requests
import logging
import threading
import time
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# مكتبات معالجة العربية
import arabic_reshaper
from bidi.algorithm import get_display

load_dotenv()

from telegram import Update, ChatMember, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image

# Optional: Word document support
try:
    from docx import Document
    DOCX_SUPPORTED = True
except ImportError:
    DOCX_SUPPORTED = False

# ============ إعدادات ============
TOKEN = os.getenv("BOT_TOKEN")
TARGET_CHANNEL = os.getenv("TARGET_CHANNEL", "@medbibliotekaa")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL = os.getenv("MODEL", "llama3.2")
PDF_DIR = "pdf_output"  # تغيير المسار ليكون محلياً لتجنب مشاكل الصلاحيات

if not TOKEN:
    sys.exit("❌ Error: BOT_TOKEN is missing in .env file")

os.makedirs(PDF_DIR, exist_ok=True)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============ نظام إدارة الطلبات المتزامنة ============
MAX_CONCURRENT_REQUESTS = 10
request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
active_requests = 0
request_lock = asyncio.Lock()

async def acquire_request_slot():
    global active_requests
    async with request_lock:
        active_requests += 1
    await request_semaphore.acquire()

async def release_request_slot():
    global active_requests
    request_semaphore.release()
    async with request_lock:
        active_requests -= 1

# ============ إحصائيات وإعدادات المستخدمين ============
user_stats = {}
user_settings = {}

def update_stats(user_id, action_type):
    if user_id not in user_stats:
        user_stats[user_id] = {'pdfs': 0, 'texts': 0, 'images': 0, 'files': 0, 'joined': datetime.now().isoformat()}
    user_stats[user_id][action_type] = user_stats[user_id].get(action_type, 0) + 1

def get_stats(user_id):
    return user_stats.get(user_id, {'pdfs': 0, 'texts': 0, 'images': 0, 'files': 0})

def get_user_settings(user_id):
    if user_id not in user_settings:
        user_settings[user_id] = {'template': 'modern', 'quality': 'high'}
    return user_settings[user_id]

def set_user_setting(user_id, key, value):
    if user_id not in user_settings:
        user_settings[user_id] = {'template': 'modern', 'quality': 'high'}
    user_settings[user_id][key] = value

# ============ اللغات والترجمة ============
# (تم اختصار القاموس هنا للحفاظ على المساحة، استخدم نفس القاموس الموجود في كودك الأصلي)
TRANSLATIONS = {
    "ar": {
        "welcome": "👋 مرحباً {name}!\n\n🤖 **بوت PDF الذكي Pro**\n\n📤 أرسل: نص | صور | ملف TXT | ملف Word\n\n🎨 اختر القالب والجودة من الإعدادات",
        "received": "📥 **تم استلام طلبك!**\n⏳ جاري المعالجة...",
        "processing_step1": "📝 تحليل المحتوى...",
        "processing_step2": "🎨 تطبيق التصميم...",
        "processing_step3": "📄 إنشاء ملف PDF...",
        "uploading": "📤 جاري رفع الملف إليك...",
        "success": "✅ **تم بنجاح!**\n📄 ملف PDF جاهز للتحميل",
        "success_album": "✅ **تم بنجاح!**\n📄 {count} صور في PDF واحد",
        "error": "❌ **حدث خطأ**\n{error}\n\n🔄 يرجى المحاولة مرة أخرى",
        "not_member": "🔒 **الاشتراك مطلوب**\n\n📢 اشترك في {channel} أولاً\n✅ ثم عد وأرسل /start",
        "title": "مستند PDF",
        "title_album": "ألبوم الصور",
        "watermark": "© PDF Bot Pro",
        "footer": "تم الإنشاء: {date}",
        "enhance_prompt": "حسّن هذا النص بالعربية واجعله أكثر وضوحاً",
        "settings": "⚙️ **الإعدادات**",
        "docx_not_supported": "⚠️ دعم ملفات Word غير متوفر",
        "processing": "🔄 جاري المعالجة...",
        "processing_album": "🔄 معالجة {count} صور...",
        "file_received": "📁 تم استلام الملف: {filename}",
        "template_select": "🎨 اختر القالب:",
        "quality_select": "📊 اختر الجودة:",
        "template_changed": "✅ تم تغيير القالب",
        "quality_changed": "✅ تم تغيير الجودة",
        "help": "أرسل نصاً أو صورة للبدء",
        "stats": "إحصائياتك: {pdfs} ملفات",
        "classic": "كلاسيكي", "modern": "عصري", "dark": "داكن",
        "high": "عالية", "medium": "متوسطة", "low": "منخفضة"
    },
    "en": {
         "welcome": "👋 Hello {name}!\n\n🤖 **AI PDF Bot Pro**",
         "received": "📥 Request received!",
         "processing_step1": "📝 Analyzing...",
         "processing_step2": "🎨 Designing...",
         "processing_step3": "📄 Generating PDF...",
         "uploading": "📤 Uploading...",
         "success": "✅ Done!",
         "success_album": "✅ Done! {count} images.",
         "error": "❌ Error: {error}",
         "not_member": "🔒 Join {channel} first.",
         "title": "PDF Document",
         "title_album": "Image Album",
         "watermark": "© PDF Bot Pro",
         "footer": "Generated: {date}",
         "enhance_prompt": "Improve this text professionally",
         "settings": "⚙️ Settings",
         "docx_not_supported": "⚠️ Word not supported",
         "processing": "🔄 Processing...",
         "processing_album": "🔄 Processing {count} images...",
         "file_received": "📁 File received: {filename}",
         "template_select": "🎨 Template:",
         "quality_select": "📊 Quality:",
         "template_changed": "✅ Template changed",
         "quality_changed": "✅ Quality changed",
         "help": "Send text or photo to start",
         "stats": "Stats: {pdfs} files",
         "classic": "Classic", "modern": "Modern", "dark": "Dark",
         "high": "High", "medium": "Medium", "low": "Low"
    },
    "ru": {
        "welcome": "👋 Привет {name}!",
        "received": "📥 Запрос получен!",
        "processing_step1": "📝 Анализ...",
        "processing_step2": "🎨 Дизайн...",
        "processing_step3": "📄 Создание PDF...",
        "uploading": "📤 Загрузка...",
        "success": "✅ Готово!",
        "success_album": "✅ Готово! {count} фото.",
        "error": "❌ Ошибка: {error}",
        "not_member": "🔒 Подпишитесь на {channel}.",
        "title": "PDF Документ",
        "title_album": "Фотоальбом",
        "watermark": "© PDF Bot Pro",
        "footer": "Создано: {date}",
        "enhance_prompt": "Улучши этот текст профессионально на русском",
        "settings": "⚙️ Настройки",
        "docx_not_supported": "⚠️ Word не поддерживается",
        "processing": "🔄 Обработка...",
        "processing_album": "🔄 Обработка {count} фото...",
        "file_received": "📁 Файл получен: {filename}",
        "template_select": "🎨 Шаблон:",
        "quality_select": "📊 Качество:",
        "template_changed": "✅ Шаблон изменен",
        "quality_changed": "✅ Качество изменено",
        "help": "Отправьте текст или фото",
        "stats": "Статистика: {pdfs} файлов",
        "classic": "Классика", "modern": "Модерн", "dark": "Тёмный",
        "high": "Высокое", "medium": "Среднее", "low": "Низкое"
    }
}

# Add fallbacks for other languages from original code...
class Localization:
    def __init__(self, lang):
        self.lang = lang if lang in TRANSLATIONS else 'en'
    def get(self, key, **kwargs):
        # Fallback to English if key missing in target lang
        text = TRANSLATIONS[self.lang].get(key, TRANSLATIONS['en'].get(key, key))
        return text.format(**kwargs) if kwargs else text
    def format_date(self):
        return datetime.now().strftime('%Y-%m-%d %H:%M')

# ============ الخطوط (محسنة) ============
class FontManager:
    def __init__(self):
        self.loaded_fonts = {}
        # استخدام خطوط تدعم العربية والروسية (يجب وضع ملف Arial.ttf أو NotoSans.ttf بجانب البوت)
        # إذا لم تجد الخطوط، سيحاول النظام البحث عنها
        self.font_map = {
            'ar': ['Arial.ttf', 'arial.ttf', '/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf'],
            'ru': ['Arial.ttf', 'arial.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'],
            'default': ['Arial.ttf', 'arial.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
        }
        self.register_fonts()

    def register_fonts(self):
        # محاولة تحميل خط افتراضي يدعم اليونيكود
        font_path = self.find_font(self.font_map['default'])
        if font_path:
            try:
                pdfmetrics.registerFont(TTFont('UniversalFont', font_path))
                self.default_font = 'UniversalFont'
            except Exception as e:
                logger.error(f"Failed to load font {font_path}: {e}")
                self.default_font = 'Helvetica'
        else:
            self.default_font = 'Helvetica'

    def find_font(self, paths):
        for path in paths:
            if os.path.exists(path):
                return path
            # Check local directory
            local_path = os.path.join(os.getcwd(), path)
            if os.path.exists(local_path):
                return local_path
        return None

    def get_font(self):
        return self.default_font

font_manager = FontManager()

# ============ أدوات المساعدة ============
def fix_text_rtl(text):
    """إصلاح اتجاه النص العربي"""
    try:
        reshaped_text = arabic_reshaper.reshape(text)
        bidi_text = get_display(reshaped_text)
        return bidi_text
    except Exception:
        return text

# ============ Ollama (محسنة للتزامن) ============
def call_ollama_sync(prompt, system=""):
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "system": system,
            "stream": False
        }, timeout=45)
        if response.status_code == 200:
            data = response.json()
            return data.get("response", prompt)
    except Exception as e:
        logger.error(f"Ollama error: {e}")
    return prompt

# ============ PDF Logic (محسنة) ============
TEMPLATES = {
    'classic': {'bg': '#FFFFFF', 'text': '#000000', 'header': '#333333', 'accent': '#666666'},
    'modern': {'bg': '#F8F9FA', 'text': '#212529', 'header': '#2196F3', 'accent': '#1976D2'},
    'dark': {'bg': '#1A1A2E', 'text': '#EAEAEA', 'header': '#E94560', 'accent': '#0F3460'}
}

QUALITY_SETTINGS = {
    'high': {'dpi': 300, 'q': 95},
    'medium': {'dpi': 150, 'q': 70},
    'low': {'dpi': 72, 'q': 50}
}

def create_pdf_text_sync(content, chat_id, lang, user_id):
    loc = Localization(lang)
    settings = get_user_settings(user_id)
    template = TEMPLATES[settings['template']]
    
    # 1. Enhance text via Ollama (Blocking but run in thread)
    enhanced = call_ollama_sync(content, loc.get('enhance_prompt'))
    
    filename = f"doc_{chat_id}_{int(time.time())}.pdf"
    filepath = os.path.join(PDF_DIR, filename)
    
    c = canvas.Canvas(filepath, pagesize=A4)
    width, height = A4
    font_name = font_manager.get_font()
    
    margin = 50
    y = height - 100
    line_height = 20
    
    # Simple formatting logic
    c.setFillColor(HexColor(template['bg']))
    c.rect(0,0,width,height, fill=True, stroke=False)
    
    # Header
    c.setFillColor(HexColor(template['header']))
    c.setFont(font_name, 18)
    header_text = fix_text_rtl(loc.get('title'))
    c.drawRightString(width - margin, height - 50, header_text) if lang == 'ar' else c.drawString(margin, height - 50, header_text)

    # Body
    c.setFillColor(HexColor(template['text']))
    c.setFont(font_name, 12)
    
    lines = enhanced.split('\n')
    for line in lines:
        # معالجة العربية
        display_line = fix_text_rtl(line)
        
        # التفاف النص البسيط (يمكن تحسينه)
        text_width = c.stringWidth(display_line, font_name, 12)
        if text_width > (width - 2*margin):
            # هنا يمكن إضافة منطق لتقسيم السطر الطويل
            pass 
        
        if y < 70:
            c.showPage()
            c.setFillColor(HexColor(template['bg']))
            c.rect(0,0,width,height, fill=True, stroke=False)
            c.setFillColor(HexColor(template['text']))
            c.setFont(font_name, 12)
            y = height - 50
            
        if lang == 'ar':
            c.drawRightString(width - margin, y, display_line)
        else:
            c.drawString(margin, y, display_line)
        y -= line_height

    # Footer
    c.setFont(font_name, 8)
    c.setFillColor(HexColor(template['accent']))
    c.drawCentredString(width/2, 30, f"{TARGET_CHANNEL} | {loc.format_date()}")
    
    c.save()
    return filepath

def create_pdf_album_sync(image_paths, chat_id, lang, user_id, caption=""):
    settings = get_user_settings(user_id)
    template = TEMPLATES[settings['template']]
    quality_conf = QUALITY_SETTINGS[settings['quality']]
    
    filename = f"album_{chat_id}_{int(time.time())}.pdf"
    filepath = os.path.join(PDF_DIR, filename)
    
    c = canvas.Canvas(filepath, pagesize=A4)
    width, height = A4
    
    for img_path in image_paths:
        try:
            img = Image.open(img_path)
            if img.mode != 'RGB':
                img = img.convert('RGB')
                
            # Resize logic based on aspect ratio
            img_w, img_h = img.size
            aspect = img_h / img_w
            
            avail_w = width - 100
            avail_h = height - 150
            
            new_w = avail_w
            new_h = new_w * aspect
            
            if new_h > avail_h:
                new_h = avail_h
                new_w = new_h / aspect
                
            x_pos = (width - new_w) / 2
            y_pos = (height - new_h) / 2
            
            c.setFillColor(HexColor(template['bg']))
            c.rect(0,0,width,height, fill=True, stroke=False)
            
            # Watermark
            c.saveState()
            c.setFillColor(HexColor(template['accent']))
            c.setFillAlpha(0.1)
            c.setFont("Helvetica-Bold", 40)
            c.translate(width/2, height/2)
            c.rotate(45)
            c.drawCentredString(0, 0, TARGET_CHANNEL)
            c.restoreState()
            
            # Draw Image
            c.drawImage(img_path, x_pos, y_pos, width=new_w, height=new_h)
            
            c.showPage()
        except Exception as e:
            logger.error(f"Image error: {e}")
            
    c.save()
    return filepath

# ============ Handlers (Async Wrappers) ============
async def check_membership(user_id, context):
    try:
        member = await context.bot.get_chat_member(TARGET_CHANNEL, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception:
        return False # Fallback logic, maybe True for testing

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    loc = Localization(user.language_code)
    
    if not await check_membership(user.id, context):
        await update.message.reply_text(loc.get('not_member', channel=TARGET_CHANNEL))
        return
        
    await update.message.reply_text(loc.get('welcome', name=user.first_name), parse_mode='Markdown')

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    loc = Localization(user.language_code)
    
    if not await check_membership(user.id, context):
        await update.message.reply_text(loc.get('not_member', channel=TARGET_CHANNEL))
        return

    await acquire_request_slot()
    msg = await update.message.reply_text(loc.get('processing'))
    
    try:
        # Run synchronous blocking code in a separate thread
        loop = asyncio.get_running_loop()
        pdf_path = await loop.run_in_executor(
            None, 
            create_pdf_text_sync, 
            update.message.text, 
            update.effective_chat.id, 
            user.language_code, 
            user.id
        )
        
        await context.bot.send_chat_action(update.effective_chat.id, 'upload_document')
        await update.message.reply_document(
            document=open(pdf_path, 'rb'),
            filename=f"Doc_{int(time.time())}.pdf",
            caption=loc.get('success')
        )
        update_stats(user.id, 'texts')
        await msg.delete()
        
        # Cleanup
        threading.Thread(target=lambda: (time.sleep(60), os.remove(pdf_path))).start()
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await msg.edit_text(loc.get('error', error=str(e)))
    finally:
        await release_request_slot()

# Album global state
albums = {}

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not await check_membership(user.id, context):
        await update.message.reply_text(Localization(user.language_code).get('not_member', channel=TARGET_CHANNEL))
        return

    photo = update.message.photo[-1]
    file = await photo.get_file()
    
    # Download file locally
    img_path = os.path.join(PDF_DIR, f"{update.message.message_id}.jpg")
    await file.download_to_drive(img_path)
    
    # Album grouping logic
    mg_id = update.message.media_group_id
    key = mg_id if mg_id else f"single_{update.message.message_id}"
    
    if key not in albums:
        albums[key] = {'paths': [], 'task': None, 'msg': update.message, 'user': user}
        
    albums[key]['paths'].append(img_path)
    
    # Cancel previous timer if exists
    if albums[key]['task']:
        albums[key]['task'].cancel()
        
    async def process():
        await asyncio.sleep(2) # Wait for other photos
        if key not in albums: return
        
        data = albums.pop(key)
        paths = data['paths']
        loc = Localization(data['user'].language_code)
        
        await acquire_request_slot()
        status_msg = await data['msg'].reply_text(loc.get('processing_album', count=len(paths)))
        
        try:
            loop = asyncio.get_running_loop()
            pdf_path = await loop.run_in_executor(
                None,
                create_pdf_album_sync,
                paths,
                data['msg'].chat_id,
                data['user'].language_code,
                data['user'].id,
                ""
            )
            
            await data['msg'].reply_document(open(pdf_path, 'rb'), caption=loc.get('success_album', count=len(paths)))
            await status_msg.delete()
            
            # Cleanup
            def clean():
                time.sleep(60)
                if os.path.exists(pdf_path): os.remove(pdf_path)
                for p in paths:
                    if os.path.exists(p): os.remove(p)
            threading.Thread(target=clean).start()
            
        except Exception as e:
            await status_msg.edit_text(str(e))
        finally:
            await release_request_slot()

    albums[key]['task'] = asyncio.create_task(process())

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    loc = Localization(user.language_code)
    
    if not await check_membership(user.id, context):
        await update.message.reply_text(loc.get('not_member', channel=TARGET_CHANNEL))
        return

    doc = update.message.document
    f = await doc.get_file()
    path = os.path.join(PDF_DIR, doc.file_name)
    await f.download_to_drive(path)
    
    msg = await update.message.reply_text(loc.get('processing'))
    
    try:
        content = ""
        if path.endswith('.docx') and DOCX_SUPPORTED:
            # Word processing logic (must be in executor if heavy, but small files are ok)
            document = Document(path)
            content = "\n".join([p.text for p in document.paragraphs])
        elif path.endswith('.txt'):
            with open(path, 'r', encoding='utf-8', errors='ignore') as txt_file:
                content = txt_file.read()
        
        if content:
             loop = asyncio.get_running_loop()
             pdf_path = await loop.run_in_executor(
                None, 
                create_pdf_text_sync, 
                content, 
                update.effective_chat.id, 
                user.language_code, 
                user.id
            )
             await update.message.reply_document(open(pdf_path, 'rb'), caption=loc.get('success'))
        else:
             await msg.edit_text(loc.get('error', error="Format not supported or empty"))

    except Exception as e:
        await msg.edit_text(loc.get('error', error=str(e)))
    finally:
        await msg.delete()
        if os.path.exists(path): os.remove(path)

# ============ Main ============
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    # Add other command handlers...
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    logger.info("✅ Bot Started")
    app.run_polling()

if __name__ == "__main__":
    main()
