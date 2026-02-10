#!/usr/bin/env python3
"""
PDF Bot Pro - Ultimate Version 2.1
يدعم: نصوص | صورة واحدة | مجموعة صور (Album) | TXT | DOCX → PDF
مع قوالب متعددة وأزرار تفاعلية ودعم 6 لغات
متوافق مع bothost.ru
"""

import os
import sys
import json
import logging
import time
import asyncio
from datetime import datetime
from pathlib import Path
from deep_translator import GoogleTranslator

from dotenv import load_dotenv
load_dotenv()
from subscription_checker import check_membership

from telegram import Update, ChatMember, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, grey, white, black
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

# حدود المدخلات
MAX_TEXT_LENGTH = 50000
MAX_ALBUM_IMAGES = 20

# المسار الأساسي للمشروع
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PDF_DIR = os.path.join(BASE_DIR, "temp_files")
DATA_DIR = os.path.join(BASE_DIR, "data")

os.makedirs(PDF_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============ نظام إدارة الطلبات المتزامنة ============
MAX_CONCURRENT_REQUESTS = 10
request_semaphore = None  # يتم إنشاؤه داخل main()

async def acquire_request_slot():
    """الحصول على مكان في طابور التنفيذ"""
    if request_semaphore:
        await request_semaphore.acquire()

async def release_request_slot():
    """تحرير مكان في طابور التنفيذ"""
    if request_semaphore:
        request_semaphore.release()

# ============ تخزين البيانات (JSON) ============
STATS_FILE = os.path.join(DATA_DIR, "user_stats.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "user_settings.json")

def _load_json(filepath):
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {filepath}: {e}")
    return {}

def _save_json(filepath, data):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving {filepath}: {e}")

# ============ إحصائيات المستخدمين ============
user_stats = _load_json(STATS_FILE)

def update_stats(user_id, action_type):
    uid = str(user_id)
    if uid not in user_stats:
        user_stats[uid] = {
            'pdfs': 0, 'texts': 0, 'images': 0, 'files': 0,
            'joined': datetime.now().isoformat()
        }
    user_stats[uid][action_type] = user_stats[uid].get(action_type, 0) + 1
    _save_json(STATS_FILE, user_stats)

def get_stats(user_id):
    return user_stats.get(
        str(user_id),
        {'pdfs': 0, 'texts': 0, 'images': 0, 'files': 0}
    )

# ============ اللغات (6 لغات) ============
TRANSLATIONS = {
    "ar": {
        "welcome": "👋 مرحباً {name}!\n\n🤖 **بوت PDF الذكي Pro**\n\n📤 أرسل: نص | صور | ملف TXT | ملف Word\n\n🎨 اختر القالب والجودة من الإعدادات",
        "received": "📥 **تم استلام طلبك!**\n⏳ جاري المعالجة...",
        "processing": "🔄 جاري تحويل النص إلى PDF...\n⏱️ يرجى الانتظار",
        "processing_album": "🔄 جاري معالجة {count} صور...\n⏱️ يرجى الانتظار",
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
        "watermark": "© PDF Bot Pro | {channel}",
        "footer": "تم الإنشاء: {date}",
        "settings": "⚙️ **الإعدادات**\n\nاختر ما تريد تعديله:",
        "template_select": "🎨 اختر قالب التصميم:",
        "quality_select": "📊 اختر جودة PDF:",
        "template_changed": "✅ تم تغيير القالب إلى: {template}",
        "quality_changed": "✅ تم تغيير الجودة إلى: {quality}",
        "stats": "📊 **إحصائياتك**\n\n📄 ملفات PDF: {pdfs}\n📝 نصوص: {texts}\n🖼️ صور: {images}\n📁 ملفات: {files}",
        "help": "📖 **المساعدة**\n\n/start - بدء البوت\n/settings - الإعدادات\n/stats - إحصائياتك\n/help - المساعدة\n\n📤 **يمكنك إرسال:**\n• نص عادي\n• صورة أو مجموعة صور\n• ملف TXT\n• ملف Word (.docx)",
        "file_received": "� **تم استلام الملف!**\n📁 {filename}\n⏳ جاري التحويل...",
        "docx_not_supported": "⚠️ دعم ملفات Word غير متوفر، يرجى تثبيت python-docx",
        "classic": "🎨 كلاسيكي",
        "modern": "✨ عصري",
        "dark": "🌙 داكن",
        "high": "🔷 عالية",
        "medium": "🔶 متوسطة",
        "low": "🔸 منخفضة",
        "text_too_long": "❌ **النص طويل جداً**\nالحد الأقصى: {max} حرف",
        "album_too_large": "❌ **عدد الصور كثير جداً**\nالحد الأقصى: {max} صورة"
    },
    "en": {
        "welcome": "👋 Hello {name}!\n\n🤖 **AI PDF Bot Pro**\n\n📤 Send: Text | Photos | TXT file | Word file\n\n🎨 Choose template and quality in settings",
        "received": "📥 **Request received!**\n⏳ Processing...",
        "processing": "🔄 Converting text to PDF...\n⏱️ Please wait",
        "processing_album": "🔄 Processing {count} images...\n⏱️ Please wait",
        "processing_step1": "📝 Analyzing content...",
        "processing_step2": "🎨 Applying design...",
        "processing_step3": "📄 Creating PDF file...",
        "uploading": "📤 Uploading file to you...",
        "success": "✅ **Success!**\n📄 PDF file is ready to download",
        "success_album": "✅ **Success!**\n📄 {count} images in one PDF",
        "error": "❌ **Error occurred**\n{error}\n\n🔄 Please try again",
        "not_member": "🔒 **Subscription required**\n\n📢 Join {channel} first\n✅ Then come back and send /start",
        "title": "PDF Document",
        "title_album": "Image Album",
        "watermark": "© PDF Bot Pro | {channel}",
        "footer": "Generated: {date}",
        "settings": "⚙️ **Settings**\n\nChoose what to modify:",
        "template_select": "🎨 Choose design template:",
        "quality_select": "📊 Choose PDF quality:",
        "template_changed": "✅ Template changed to: {template}",
        "quality_changed": "✅ Quality changed to: {quality}",
        "stats": "📊 **Your Statistics**\n\n📄 PDFs: {pdfs}\n📝 Texts: {texts}\n🖼️ Images: {images}\n📁 Files: {files}",
        "help": "📖 **Help**\n\n/start - Start bot\n/settings - Settings\n/stats - Your stats\n/help - Help\n\n📤 **You can send:**\n• Plain text\n• Photo or album\n• TXT file\n• Word file (.docx)",
        "file_received": "� **File received!**\n📁 {filename}\n⏳ Converting...",
        "docx_not_supported": "⚠️ Word file support not available, please install python-docx",
        "classic": "🎨 Classic",
        "modern": "✨ Modern",
        "dark": "🌙 Dark",
        "high": "🔷 High",
        "medium": "🔶 Medium",
        "low": "🔸 Low",
        "text_too_long": "❌ **Text is too long**\nMax: {max} characters",
        "album_too_large": "❌ **Too many images**\nMax: {max} images"
    },
    "ru": {
        "welcome": "👋 Привет {name}!\n\n🤖 **AI PDF Бот Pro**\n\n📤 Отправьте: Текст | Фото | TXT | Word\n\n🎨 Выберите шаблон и качество в настройках",
        "received": "📥 **Запрос получен!**\n⏳ Обработка...",
        "processing": "⏳ Создание PDF...",
        "processing_album": "⏳ Обработка {count} изображений...",
        "processing_step1": "📝 Анализ содержимого...",
        "processing_step2": "🎨 Применение дизайна...",
        "processing_step3": "📄 Создание PDF файла...",
        "uploading": "📤 Загрузка файла...",
        "success": "📄 PDF создан успешно!",
        "success_album": "📄 {count} изображений в одном PDF",
        "error": "❌ Ошибка: {error}",
        "not_member": "⚠️ Сначала подпишитесь на {channel}",
        "title": "PDF Документ",
        "title_album": "Фотоальбом",
        "watermark": "© PDF Bot Pro | {channel}",
        "footer": "Создано: {date}",
        "settings": "⚙️ **Настройки**\n\nВыберите что изменить:",
        "template_select": "🎨 Выберите шаблон:",
        "quality_select": "📊 Выберите качество PDF:",
        "template_changed": "✅ Шаблон изменен на: {template}",
        "quality_changed": "✅ Качество изменено на: {quality}",
        "stats": "📊 **Ваша статистика**\n\n📄 PDF файлов: {pdfs}\n📝 Текстов: {texts}\n🖼️ Изображений: {images}\n📁 Файлов: {files}",
        "help": "📖 **Помощь**\n\n/start - Запуск\n/settings - Настройки\n/stats - Статистика\n/help - Помощь",
        "file_received": "📁 Файл получен, обработка...",
        "docx_not_supported": "⚠️ Поддержка Word недоступна",
        "classic": "🎨 Классика",
        "modern": "✨ Модерн",
        "dark": "🌙 Тёмный",
        "high": "🔷 Высокое",
        "medium": "🔶 Среднее",
        "low": "🔸 Низкое",
        "text_too_long": "❌ **Текст слишком длинный**\nМакс: {max} символов",
        "album_too_large": "❌ **Слишком много изображений**\nМакс: {max} изображений"
    },
    "tr": {
        "welcome": "👋 Merhaba {name}!\n\n🤖 **AI PDF Bot Pro**\n\n📤 Gönder: Metin | Fotoğraf | TXT | Word\n\n🎨 Ayarlardan şablon ve kalite seçin",
        "received": "📥 **İstek alındı!**\n⏳ İşleniyor...",
        "processing": "⏳ PDF oluşturuluyor...",
        "processing_album": "⏳ {count} resim işleniyor...",
        "processing_step1": "📝 İçerik analiz ediliyor...",
        "processing_step2": "🎨 Tasarım uygulanıyor...",
        "processing_step3": "📄 PDF dosyası oluşturuluyor...",
        "uploading": "📤 Dosya yükleniyor...",
        "success": "📄 PDF başarıyla oluşturuldu!",
        "success_album": "📄 {count} resim tek PDF'de",
        "error": "❌ Hata: {error}",
        "not_member": "⚠️ Önce {channel} kanalına katılın",
        "title": "PDF Belgesi",
        "title_album": "Fotoğraf Albümü",
        "watermark": "© PDF Bot Pro | {channel}",
        "footer": "Oluşturuldu: {date}",
        "settings": "⚙️ **Ayarlar**\n\nDeğiştirmek istediğinizi seçin:",
        "template_select": "🎨 Tasarım şablonu seçin:",
        "quality_select": "📊 PDF kalitesi seçin:",
        "template_changed": "✅ Şablon değiştirildi: {template}",
        "quality_changed": "✅ Kalite değiştirildi: {quality}",
        "stats": "📊 **İstatistikleriniz**\n\n📄 PDF: {pdfs}\n📝 Metin: {texts}\n🖼️ Resim: {images}\n📁 Dosya: {files}",
        "help": "📖 **Yardım**\n\n/start - Başlat\n/settings - Ayarlar\n/stats - İstatistik\n/help - Yardım",
        "file_received": "📁 Dosya alındı, işleniyor...",
        "docx_not_supported": "⚠️ Word desteği mevcut değil",
        "classic": "🎨 Klasik",
        "modern": "✨ Modern",
        "dark": "🌙 Karanlık",
        "high": "🔷 Yüksek",
        "medium": "🔶 Orta",
        "low": "🔸 Düşük",
        "text_too_long": "❌ **Metin çok uzun**\nMaks: {max} karakter",
        "album_too_large": "❌ **Çok fazla resim**\nMaks: {max} resim"
    },
    "fr": {
        "welcome": "👋 Bonjour {name}!\n\n🤖 **AI PDF Bot Pro**\n\n📤 Envoyez: Texte | Photos | TXT | Word\n\n🎨 Choisissez le modèle dans les paramètres",
        "received": "📥 **Reçu!**\n⏳ Traitement en cours...",
        "processing": "⏳ Création du PDF...",
        "processing_album": "⏳ Traitement de {count} images...",
        "processing_step1": "📝 Analyse du contenu...",
        "processing_step2": "🎨 Application du design...",
        "processing_step3": "📄 Création du fichier PDF...",
        "uploading": "📤 Téléchargement du fichier...",
        "success": "📄 PDF créé avec succès!",
        "success_album": "📄 {count} images dans un PDF",
        "error": "❌ Erreur: {error}",
        "not_member": "⚠️ Rejoignez {channel} d'abord",
        "title": "Document PDF",
        "title_album": "Album Photo",
        "watermark": "© PDF Bot Pro | {channel}",
        "footer": "Créé le: {date}",
        "settings": "⚙️ **Paramètres**\n\nChoisissez ce que vous voulez modifier:",
        "template_select": "🎨 Choisissez le modèle:",
        "quality_select": "📊 Choisissez la qualité PDF:",
        "template_changed": "✅ Modèle changé en: {template}",
        "quality_changed": "✅ Qualité changée en: {quality}",
        "stats": "📊 **Vos Statistiques**\n\n📄 PDFs: {pdfs}\n📝 Textes: {texts}\n🖼️ Images: {images}\n📁 Fichiers: {files}",
        "help": "📖 **Aide**\n\n/start - Démarrer\n/settings - Paramètres\n/stats - Statistiques\n/help - Aide",
        "file_received": "📁 Fichier reçu, traitement...",
        "docx_not_supported": "⚠️ Support Word non disponible",
        "classic": "🎨 Classique",
        "modern": "✨ Moderne",
        "dark": "🌙 Sombre",
        "high": "🔷 Haute",
        "medium": "🔶 Moyenne",
        "low": "🔸 Basse",
        "text_too_long": "❌ **Texte trop long**\nMax: {max} caractères",
        "album_too_large": "❌ **Trop d'images**\nMax: {max} images"
    },
    "es": {
        "welcome": "👋 ¡Hola {name}!\n\n🤖 **AI PDF Bot Pro**\n\n📤 Envía: Texto | Fotos | TXT | Word\n\n🎨 Elige plantilla y calidad en ajustes",
        "received": "📥 **¡Solicitud recibida!**\n⏳ Procesando...",
        "processing": "⏳ Creando PDF...",
        "processing_album": "⏳ Procesando {count} imágenes...",
        "processing_step1": "📝 Analizando contenido...",
        "processing_step2": "🎨 Aplicando diseño...",
        "processing_step3": "📄 Creando archivo PDF...",
        "uploading": "📤 Subiendo archivo...",
        "success": "📄 ¡PDF creado con éxito!",
        "success_album": "📄 {count} imágenes en un PDF",
        "error": "❌ Error: {error}",
        "not_member": "⚠️ Únete a {channel} primero",
        "title": "Documento PDF",
        "title_album": "Álbum de Fotos",
        "watermark": "© PDF Bot Pro | {channel}",
        "footer": "Creado: {date}",
        "settings": "⚙️ **Ajustes**\n\nElige qué modificar:",
        "template_select": "🎨 Elige plantilla:",
        "quality_select": "📊 Elige calidad PDF:",
        "template_changed": "✅ Plantilla cambiada a: {template}",
        "quality_changed": "✅ Calidad cambiada a: {quality}",
        "stats": "📊 **Tus Estadísticas**\n\n📄 PDFs: {pdfs}\n📝 Textos: {texts}\n🖼️ Imágenes: {images}\n📁 Archivos: {files}",
        "help": "📖 **Ayuda**\n\n/start - Iniciar\n/settings - Ajustes\n/stats - Estadísticas\n/help - Ayuda",
        "file_received": "📁 Archivo recibido, procesando...",
        "docx_not_supported": "⚠️ Soporte Word no disponible",
        "classic": "🎨 Clásico",
        "modern": "✨ Moderno",
        "dark": "🌙 Oscuro",
        "high": "🔷 Alta",
        "medium": "🔶 Media",
        "low": "🔸 Baja",
        "text_too_long": "❌ **Texto demasiado largo**\nMáx: {max} caracteres",
        "album_too_large": "❌ **Demasiadas imágenes**\nMáx: {max} imágenes"
    }
}

# ============ إعدادات المستخدم ============
user_settings = _load_json(SETTINGS_FILE)

def get_user_settings(user_id):
    uid = str(user_id)
    if uid not in user_settings:
        user_settings[uid] = {'template': 'modern', 'quality': 'high'}
        _save_json(SETTINGS_FILE, user_settings)
    return user_settings[uid]

def set_user_setting(user_id, key, value):
    uid = str(user_id)
    if uid not in user_settings:
        user_settings[uid] = {'template': 'modern', 'quality': 'high'}
    user_settings[uid][key] = value
    _save_json(SETTINGS_FILE, user_settings)

# ============ القوالب ============
TEMPLATES = {
    'classic': {
        'bg_color': '#FFFFFF',
        'header_color': '#333333',
        'text_color': '#000000',
        'accent_color': '#666666',
        'watermark_color': '#CCCCCC',
        'footer_color': '#888888'
    },
    'modern': {
        'bg_color': '#F8F9FA',
        'header_color': '#2196F3',
        'text_color': '#212529',
        'accent_color': '#1976D2',
        'watermark_color': '#90CAF9',
        'footer_color': '#6C757D'
    },
    'dark': {
        'bg_color': '#1A1A2E',
        'header_color': '#E94560',
        'text_color': '#EAEAEA',
        'accent_color': '#0F3460',
        'watermark_color': '#3D5A80',
        'footer_color': '#888888'
    }
}

QUALITY_SETTINGS = {
    'high': {'dpi': 300, 'compression': 0},
    'medium': {'dpi': 150, 'compression': 50},
    'low': {'dpi': 72, 'compression': 80}
}

class TranslationManager:
    def __init__(self):
        self.cache_dir = Path("translations")
        self.cache_dir.mkdir(exist_ok=True)
        self.loaded_translations = {}

    def get_translation(self, lang, key, default_text):
        if lang in TRANSLATIONS:
            return TRANSLATIONS[lang].get(key, default_text)
        
        # Load from cache if not loaded
        if lang not in self.loaded_translations:
            self._load_from_cache(lang)
        
        # Check cache
        if lang in self.loaded_translations and key in self.loaded_translations[lang]:
            return self.loaded_translations[lang][key]
        
        # Translate and cache
        return self._translate_and_cache(lang, key, default_text)

    def _load_from_cache(self, lang):
        cache_file = self.cache_dir / f"{lang}.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    self.loaded_translations[lang] = json.load(f)
            except Exception as e:
                logger.error(f"Error loading translation cache for {lang}: {e}")
                self.loaded_translations[lang] = {}
        else:
            self.loaded_translations[lang] = {}

    def _translate_and_cache(self, lang, key, text):
        try:
            # Skip translation for placeholders or specific keys if needed
            # For now, simple translation
            translated = GoogleTranslator(source='auto', target=lang).translate(text)
            
            if lang not in self.loaded_translations:
                self.loaded_translations[lang] = {}
                
            self.loaded_translations[lang][key] = translated
            
            # Save to file
            cache_file = self.cache_dir / f"{lang}.json"
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.loaded_translations[lang], f, ensure_ascii=False, indent=2)
                
            return translated
        except Exception as e:
            logger.error(f"Translation error for {lang}: {e}")
            return text

translation_manager = TranslationManager()

class Localization:
    def __init__(self, lang):
        self.lang = lang
    
    def get(self, key, **kwargs):
        # Get default English text first
        default_text = TRANSLATIONS['en'].get(key, key)
        
        if self.lang == 'en':
            text = default_text
        else:
            text = translation_manager.get_translation(self.lang, key, default_text)
            
        return text.format(**kwargs) if kwargs else text
    
    def format_date(self):
        return datetime.now().strftime('%Y-%m-%d %H:%M')

# ============ الخطوط ============
class FontManager:
    def __init__(self):
        # البحث عن الخط العربي في مجلد Noto_Sans_Arabic
        arabic_font_path = os.path.join(BASE_DIR, "Noto_Sans_Arabic", "static", "NotoSansArabic-Regular.ttf")
        
        # البحث عن DejaVuSans من reportlab
        default_font_path = None
        try:
            import reportlab
            rl_fonts_dir = os.path.join(os.path.dirname(reportlab.__file__), 'fonts')
            candidate = os.path.join(rl_fonts_dir, 'DejaVuSans.ttf')
            if os.path.exists(candidate):
                default_font_path = candidate
        except Exception:
            pass
        
        self.loaded_fonts = {}
        
        # تسجيل الخط العربي
        if os.path.exists(arabic_font_path):
            try:
                pdfmetrics.registerFont(TTFont('Font_ar', arabic_font_path))
                self.loaded_fonts['ar'] = 'Font_ar'
                logger.info(f"✅ تحميل الخط العربي: NotoSansArabic-Regular.ttf")
            except Exception as e:
                logger.warning(f"⚠️ فشل تحميل الخط العربي: {e}")
                self.loaded_fonts['ar'] = 'Helvetica'
        else:
            logger.warning(f"⚠️ الخط العربي غير موجود: {arabic_font_path}")
            self.loaded_fonts['ar'] = 'Helvetica'
        
        # تسجيل الخط الافتراضي لباقي اللغات
        if default_font_path and os.path.exists(default_font_path):
            try:
                pdfmetrics.registerFont(TTFont('Font_default', default_font_path))
                for lang in ['en', 'ru', 'tr', 'fr', 'es']:
                    self.loaded_fonts[lang] = 'Font_default'
                logger.info(f"✅ تحميل خط DejaVuSans من reportlab")
            except Exception as e:
                logger.warning(f"⚠️ فشل تحميل DejaVuSans: {e}")
                for lang in ['en', 'ru', 'tr', 'fr', 'es']:
                    self.loaded_fonts[lang] = 'Helvetica'
        else:
            logger.warning("⚠️ DejaVuSans غير موجود، استخدام Helvetica")
            for lang in ['en', 'ru', 'tr', 'fr', 'es']:
                self.loaded_fonts[lang] = 'Helvetica'
    
    def get_font(self, lang):
        return self.loaded_fonts.get(lang, self.loaded_fonts.get('en', 'Helvetica'))

font_manager = FontManager()

# ============ فحص العضوية ============
# Removed: Logic moved to subscription_checker.py

# ============ تنظيف الملفات ============
async def cleanup_file_async(filepath, delay=120):
    """حذف ملف مؤقت بعد فترة"""
    await asyncio.sleep(delay)
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"🗑️ Deleted: {filepath}")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

# ============ إنشاء PDF من نص (مع لف أسطر وهوامش مضبوطة) ============
def create_pdf_text(content, chat_id, lang, user_id):
    """إنشاء PDF من نص مع لف أسطر وهوامش مضبوطة"""
    loc = Localization(lang)
    font_name = font_manager.get_font(lang)
    settings = get_user_settings(user_id)
    template = TEMPLATES[settings['template']]

    filename = f"doc_{chat_id}_{int(time.time())}.pdf"
    filepath = os.path.join(PDF_DIR, filename)

    c = canvas.Canvas(filepath, pagesize=A4)
    width, height = A4

    # الهوامش
    LEFT_MARGIN = 60
    RIGHT_MARGIN = 60
    TOP_MARGIN = 120    # بداية النص تحت الهيدر
    BOTTOM_MARGIN = 70  # فوق الفوتر

    base_font = font_name if font_name != 'Helvetica' else "Helvetica"
    font_size = 11
    line_height = 16
    max_text_width = width - LEFT_MARGIN - RIGHT_MARGIN

    def draw_page_frame():
        """رسم الخلفية + الهيدر + الووترمارك + الفوتر لكل صفحة"""
        # خلفية
        c.setFillColor(HexColor(template['bg_color']))
        c.rect(0, 0, width, height, fill=True, stroke=False)

        # علامة مائية + اسم الطبيب
        c.saveState()
        c.setFillColor(HexColor(template['watermark_color']))
        c.setFont("Helvetica-Bold", 46)
        c.translate(width / 2, height / 2)
        c.rotate(45)
        c.drawCentredString(0, 0, loc.get('watermark', channel=TARGET_CHANNEL))
        russian_font = font_manager.get_font('ru')
        try:
            c.setFont(russian_font, 26)
        except Exception:
            c.setFont("Helvetica", 26)
        c.drawCentredString(0, -55, "Dr Mohammed Dashir")
        c.restoreState()

        # شريط علوي
        if settings['template'] in ['modern', 'dark']:
            c.setFillColor(HexColor(template['accent_color']))
            c.rect(0, height - 8, width, 8, fill=True, stroke=False)

        # Header
        c.setFillColor(HexColor(template['header_color']))
        c.setFont("Helvetica-Bold", 20)
        c.drawString(LEFT_MARGIN, height - 50, loc.get('title'))
        c.setFont("Helvetica", 10)
        c.setFillColor(HexColor(template['footer_color']))
        c.drawString(LEFT_MARGIN, height - 70, loc.format_date())
        c.setStrokeColor(HexColor(template['accent_color']))
        c.setLineWidth(1.5)
        c.line(LEFT_MARGIN, height - 80, width - RIGHT_MARGIN, height - 80)

        # Footer
        c.setFillColor(HexColor(template['footer_color']))
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(width / 2, 35, "© All Rights Reserved - Dr Mohammed Dashir")
        c.setFont("Helvetica", 8)
        c.drawCentredString(
            width / 2,
            22,
            f"{TARGET_CHANNEL} • " + loc.get('footer', date=loc.format_date())
        )

        # شريط سفلي
        if settings['template'] in ['modern', 'dark']:
            c.setFillColor(HexColor(template['accent_color']))
            c.rect(0, 0, width, 5, fill=True, stroke=False)

        # إعداد خط النص
        c.setFont(base_font, font_size)
        c.setFillColor(HexColor(template['text_color']))

    # أول صفحة
    draw_page_frame()
    y = height - TOP_MARGIN

    for raw_line in content.split("\n"):
        if not raw_line.strip():
            y -= line_height
            if y < BOTTOM_MARGIN:
                c.showPage()
                draw_page_frame()
                y = height - TOP_MARGIN
            continue

        words = raw_line.split()
        current = ""

        for word in words:
            test = (current + " " + word) if current else word
            text_width = c.stringWidth(test, base_font, font_size)

            if text_width <= max_text_width:
                current = test
            else:
                if y < BOTTOM_MARGIN:
                    c.showPage()
                    draw_page_frame()
                    y = height - TOP_MARGIN
                c.drawString(LEFT_MARGIN, y, current)
                y -= line_height
                current = word

        if current:
            if y < BOTTOM_MARGIN:
                c.showPage()
                draw_page_frame()
                y = height - TOP_MARGIN
            c.drawString(LEFT_MARGIN, y, current)
            y -= line_height

    c.save()
    return filepath

# ============ ألبوم الصور ============
def create_pdf_album(image_paths, chat_id, lang, user_id, caption=""):
    loc = Localization(lang)
    settings = get_user_settings(user_id)
    template = TEMPLATES[settings['template']]
    quality = QUALITY_SETTINGS[settings['quality']]

    filename = f"album_{chat_id}_{int(time.time())}.pdf"
    filepath = os.path.join(PDF_DIR, filename)

    c = canvas.Canvas(filepath, pagesize=A4)
    width, height = A4

    for i, img_path in enumerate(image_paths):
        if i > 0:
            c.showPage()

        c.setFillColor(HexColor(template['bg_color']))
        c.rect(0, 0, width, height, fill=True, stroke=False)

        c.saveState()
        c.setFillColor(HexColor(template['watermark_color']))
        c.setFont("Helvetica-Bold", 45)
        c.translate(width / 2, height / 2)
        c.rotate(45)
        c.drawCentredString(0, 0, loc.get('watermark', channel=TARGET_CHANNEL))
        russian_font = font_manager.get_font('ru')
        try:
            c.setFont(russian_font, 28)
        except Exception:
            c.setFont("Helvetica", 28)
        c.drawCentredString(0, -50, "Dr Mohammed Dashir")
        c.restoreState()

        if settings['template'] in ['modern', 'dark']:
            c.setFillColor(HexColor(template['accent_color']))
            c.rect(0, height - 6, width, 6, fill=True, stroke=False)

        c.setFillColor(HexColor(template['header_color']))
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, height - 40, f"{loc.get('title_album')} - {i+1}/{len(image_paths)}")
        c.setFont("Helvetica", 9)
        c.setFillColor(HexColor(template['footer_color']))
        c.drawString(50, height - 55, loc.format_date())
        c.setStrokeColor(HexColor(template['accent_color']))
        c.line(50, height - 60, width - 50, height - 60)

        try:
            img = Image.open(img_path)
            if quality['compression'] > 0:
                img = img.convert('RGB')
                temp_path = img_path + "_compressed.jpg"
                img.save(temp_path, 'JPEG', quality=100 - quality['compression'])
                img_path = temp_path

            img_w, img_h = img.size
            aspect = img_h / img_w
            margin = 50
            max_w = width - (margin * 2)
            max_h = height - 120
            new_w = max_w
            new_h = new_w * aspect
            if new_h > max_h:
                new_h = max_h
                new_w = new_h / aspect
            x_pos = (width - new_w) / 2
            y_pos = ((height - 70) - new_h) / 2
            c.drawImage(img_path, x_pos, y_pos, width=new_w, height=new_h)
        except Exception as e:
            c.setFont("Helvetica", 11)
            c.drawString(50, height / 2, f"[Error: {e}]")

        c.setFillColor(HexColor(template['footer_color']))
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(width / 2, 28, "© All Rights Reserved - Dr Mohammed Dashir")
        c.setFont("Helvetica", 8)
        c.drawCentredString(
            width / 2,
            16,
            f"{TARGET_CHANNEL} • " + loc.get('footer', date=loc.format_date())
        )

        if settings['template'] in ['modern', 'dark']:
            c.setFillColor(HexColor(template['accent_color']))
            c.rect(0, 0, width, 4, fill=True, stroke=False)

    c.save()
    logger.info(f"📄 Album: {filepath} ({len(image_paths)} images)")
    return filepath


# ============ معالجات البوت ============
albums = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = user.language_code or 'en'
    loc = Localization(lang)

    if not await check_membership(user.id, context, TARGET_CHANNEL):
        logger.info(f"🚫 Blocked user {user.id} - Not a member of {TARGET_CHANNEL}")
        await update.message.reply_text(loc.get('not_member', channel=TARGET_CHANNEL))
        return

    get_user_settings(user.id)
    await update.message.reply_text(
        loc.get('welcome', name=user.first_name),
        parse_mode='Markdown'
    )

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = user.language_code or 'en'
    loc = Localization(lang)

    if not await check_membership(user.id, context, TARGET_CHANNEL):
        await update.message.reply_text(loc.get('not_member', channel=TARGET_CHANNEL))
        return

    keyboard = [
        [InlineKeyboardButton("🎨 " + loc.get('template_select').replace(':', ''), callback_data="menu_template")],
        [InlineKeyboardButton("📊 " + loc.get('quality_select').replace(':', ''), callback_data="menu_quality")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        loc.get('settings'),
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = user.language_code or 'en'
    loc = Localization(lang)

    if not await check_membership(user.id, context, TARGET_CHANNEL):
        await update.message.reply_text(loc.get('not_member', channel=TARGET_CHANNEL))
        return

    stats = get_stats(user.id)
    await update.message.reply_text(
        loc.get('stats', pdfs=stats['pdfs'], texts=stats['texts'],
                images=stats['images'], files=stats['files']),
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = user.language_code or 'en'
    loc = Localization(lang)

    if not await check_membership(user.id, context, TARGET_CHANNEL):
        await update.message.reply_text(loc.get('not_member', channel=TARGET_CHANNEL))
        return

    await update.message.reply_text(loc.get('help'), parse_mode='Markdown')

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    lang = user.language_code or 'en'
    loc = Localization(lang)

    # فحص العضوية عند الضغط على أي زر
    if not await check_membership(user.id, context, TARGET_CHANNEL):
        await query.edit_message_text(loc.get('not_member', channel=TARGET_CHANNEL))
        return

    data = query.data

    if data == "menu_template":
        keyboard = [
            [InlineKeyboardButton(loc.get('classic'), callback_data="template_classic")],
            [InlineKeyboardButton(loc.get('modern'), callback_data="template_modern")],
            [InlineKeyboardButton(loc.get('dark'), callback_data="template_dark")]
        ]
        await query.edit_message_text(
            loc.get('template_select'),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "menu_quality":
        keyboard = [
            [InlineKeyboardButton(loc.get('high'), callback_data="quality_high")],
            [InlineKeyboardButton(loc.get('medium'), callback_data="quality_medium")],
            [InlineKeyboardButton(loc.get('low'), callback_data="quality_low")]
        ]
        await query.edit_message_text(
            loc.get('quality_select'),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("template_"):
        template = data.replace("template_", "")
        set_user_setting(user.id, 'template', template)
        await query.edit_message_text(
            loc.get('template_changed', template=loc.get(template))
        )

    elif data.startswith("quality_"):
        quality = data.replace("quality_", "")
        set_user_setting(user.id, 'quality', quality)
        await query.edit_message_text(
            loc.get('quality_changed', quality=loc.get(quality))
        )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = user.language_code or 'en'
    loc = Localization(lang)
    chat_id = update.effective_chat.id

    if not await check_membership(user.id, context, TARGET_CHANNEL):
        await update.message.reply_text(loc.get('not_member', channel=TARGET_CHANNEL))
        return

    text = update.message.text
    if text.startswith('/'):
        return

    # فحص طول النص
    if len(text) > MAX_TEXT_LENGTH:
        await update.message.reply_text(
            loc.get('text_too_long', max=MAX_TEXT_LENGTH),
            parse_mode='Markdown'
        )
        return

    await acquire_request_slot()
    
    # إظهار حالة الكتابة للمستخدم
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    # رسالة الاستلام
    processing_msg = await update.message.reply_text(loc.get('received'), parse_mode='Markdown')

    try:
        # المرحلة 1: تحليل المحتوى
        await asyncio.sleep(0.5)
        await processing_msg.edit_text(loc.get('processing_step1'), parse_mode='Markdown')
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        
        # المرحلة 2: تطبيق التصميم
        await asyncio.sleep(0.5)
        await processing_msg.edit_text(loc.get('processing_step2'), parse_mode='Markdown')
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        
        # المرحلة 3: إنشاء PDF
        await processing_msg.edit_text(loc.get('processing_step3'), parse_mode='Markdown')
        pdf_path = create_pdf_text(text, str(chat_id), lang, user.id)
        update_stats(user.id, 'texts')
        update_stats(user.id, 'pdfs')

        # المرحلة 4: رفع الملف
        await processing_msg.edit_text(loc.get('uploading'), parse_mode='Markdown')
        await context.bot.send_chat_action(chat_id=chat_id, action="upload_document")
        
        with open(pdf_path, 'rb') as f:
            await update.message.reply_document(
                document=f,
                caption=loc.get('success'),
                filename=f"Document_{int(time.time())}.pdf",
                parse_mode='Markdown'
            )
        await processing_msg.delete()
        asyncio.create_task(cleanup_file_async(pdf_path, 120))
    except Exception as e:
        await processing_msg.edit_text(loc.get('error', error=str(e)), parse_mode='Markdown')
    finally:
        await release_request_slot()

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = user.language_code or 'en'
    loc = Localization(lang)
    chat_id = update.effective_chat.id
    msg_id = update.message.message_id
    user_id = user.id

    if not await check_membership(user_id, context, TARGET_CHANNEL):
        await update.message.reply_text(loc.get('not_member', channel=TARGET_CHANNEL))
        return

    photo = update.message.photo[-1]
    photo_file = await photo.get_file()
    img_path = os.path.join(PDF_DIR, f"img_{chat_id}_{msg_id}.jpg")
    await photo_file.download_to_drive(img_path)

    media_group_id = update.message.media_group_id
    if media_group_id:
        album_key = f"group_{media_group_id}"
        wait_time = 3
    else:
        album_key = f"single_{chat_id}_{user_id}_{msg_id}"
        wait_time = 0.5

    if album_key not in albums:
        albums[album_key] = {
            'images': [],
            'caption': update.message.caption or "",
            'user_id': user_id,
            'chat_id': chat_id,
            'lang': lang,
            'last_msg': update.message,
            'timer_task': None
        }

    albums[album_key]['images'].append((msg_id, img_path))
    albums[album_key]['last_msg'] = update.message
    if update.message.caption:
        albums[album_key]['caption'] = update.message.caption

    # فحص حجم الألبوم
    if len(albums[album_key]['images']) > MAX_ALBUM_IMAGES:
        await update.message.reply_text(
            loc.get('album_too_large', max=MAX_ALBUM_IMAGES),
            parse_mode='Markdown'
        )
        del albums[album_key]
        return

    if albums[album_key]['timer_task'] and not albums[album_key]['timer_task'].done():
        albums[album_key]['timer_task'].cancel()

    async def process_album():
        await asyncio.sleep(wait_time)
        if album_key not in albums:
            return

        album_data = albums[album_key]
        del albums[album_key]

        await acquire_request_slot()
        try:
            album_data['images'].sort(key=lambda x: x[0])
            image_paths = [p for _, p in album_data['images']]
            count = len(image_paths)

            if count == 1:
                processing_msg = await album_data['last_msg'].reply_text(loc.get('processing'))
            else:
                processing_msg = await album_data['last_msg'].reply_text(
                    loc.get('processing_album', count=count)
                )

            try:
                pdf_path = create_pdf_album(
                    image_paths, str(chat_id), album_data['lang'],
                    album_data['user_id'], album_data['caption']
                )
                update_stats(user_id, 'images')
                update_stats(user_id, 'pdfs')

                with open(pdf_path, 'rb') as f:
                    caption = loc.get('success') if count == 1 else loc.get('success_album', count=count)
                    filename = f"Image_{int(time.time())}.pdf" if count == 1 else f"Album_{count}_images.pdf"
                    await album_data['last_msg'].reply_document(
                        document=f,
                        caption=caption,
                        filename=filename
                    )
                await processing_msg.delete()

                for img in image_paths:
                    asyncio.create_task(cleanup_file_async(img, 10))
                asyncio.create_task(cleanup_file_async(pdf_path, 120))
            except Exception as e:
                logger.error(f"Error processing album: {e}")
                await processing_msg.edit_text(loc.get('error', error=str(e)))
        finally:
            await release_request_slot()

    albums[album_key]['timer_task'] = asyncio.create_task(process_album())

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = user.language_code or 'en'
    loc = Localization(lang)
    chat_id = update.effective_chat.id

    if not await check_membership(user.id, context, TARGET_CHANNEL):
        await update.message.reply_text(loc.get('not_member', channel=TARGET_CHANNEL))
        return

    document = update.message.document
    file_name = document.file_name.lower()

    await acquire_request_slot()
    
    # إظهار حالة الكتابة للمستخدم
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    # رسالة استلام الملف مع اسم الملف
    processing_msg = await update.message.reply_text(
        loc.get('file_received', filename=document.file_name), 
        parse_mode='Markdown'
    )

    try:
        file = await document.get_file()
        file_path = os.path.join(PDF_DIR, f"file_{chat_id}_{int(time.time())}_{document.file_name}")
        await file.download_to_drive(file_path)

        # المرحلة 1: تحليل المحتوى
        await processing_msg.edit_text(loc.get('processing_step1'), parse_mode='Markdown')
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        
        content = ""
        if file_name.endswith('.txt'):
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        elif file_name.endswith('.docx'):
            if not DOCX_SUPPORTED:
                await processing_msg.edit_text(loc.get('docx_not_supported'))
                return
            doc = Document(file_path)
            content = '\n'.join([p.text for p in doc.paragraphs])
        else:
            await processing_msg.edit_text(loc.get('error', error="Unsupported file type"), parse_mode='Markdown')
            return

        if content.strip():
            # المرحلة 2: تطبيق التصميم
            await processing_msg.edit_text(loc.get('processing_step2'), parse_mode='Markdown')
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(0.3)
            
            # المرحلة 3: إنشاء PDF
            await processing_msg.edit_text(loc.get('processing_step3'), parse_mode='Markdown')
            pdf_path = create_pdf_text(content, str(chat_id), lang, user.id)
            update_stats(user.id, 'files')
            update_stats(user.id, 'pdfs')

            # المرحلة 4: رفع الملف
            await processing_msg.edit_text(loc.get('uploading'), parse_mode='Markdown')
            await context.bot.send_chat_action(chat_id=chat_id, action="upload_document")
            
            with open(pdf_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    caption=loc.get('success'),
                    filename=f"Converted_{int(time.time())}.pdf",
                    parse_mode='Markdown'
                )
            await processing_msg.delete()
            asyncio.create_task(cleanup_file_async(pdf_path, 120))
        else:
            await processing_msg.edit_text(loc.get('error', error="Empty file"), parse_mode='Markdown')

        asyncio.create_task(cleanup_file_async(file_path, 10))
    except Exception as e:
        await processing_msg.edit_text(loc.get('error', error=str(e)), parse_mode='Markdown')
    finally:
        await release_request_slot()

# ============ التشغيل ============
async def post_init(application):
    """
    تهيئة الموارد التي تتطلب event loop نشط
    """
    global request_semaphore
    
    # إنشاء Semaphore داخل الـ loop النشط
    request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    logger.info("✅ Semaphore initialized in active event loop")
    
    # التأكد من وجود المجلدات
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        logger.info(f"📁 Created data directory: {DATA_DIR}")

def main():
    logger.info("🚀 Starting PDF Bot Pro v2.2...")
    logger.info(f"📁 PDF Directory: {PDF_DIR}")
    logger.info(f"📁 Data Directory: {DATA_DIR}")
    logger.info(f"🎨 Templates: {list(TEMPLATES.keys())}")
    logger.info(f"🌍 Languages: {list(TRANSLATIONS.keys())}")
    
    # استخدام post_init لتهيئة الموارد غير المتزامنة
    application = Application.builder().token(TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(callback_handler))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    logger.info("✅ Bot is running!")
    application.run_polling()

if __name__ == "__main__":
    main()
