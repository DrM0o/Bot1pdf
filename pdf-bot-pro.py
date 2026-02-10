#!/usr/bin/env python3
"""
PDF Bot Pro - Ultimate Version 2.2 (Fixed Channel ID)
ÙŠØ¯Ø¹Ù…: Ù†ØµÙˆØµ | ØµÙˆØ±Ø© ÙˆØ§Ø­Ø¯Ø© | Ù…Ø¬Ù…ÙˆØ¹Ø© ØµÙˆØ± (Album) | TXT | DOCX â†’ PDF
Ù…Ø¹ Ù‚ÙˆØ§Ù„Ø¨ Ù…ØªØ¹Ø¯Ø¯Ø© ÙˆØ£Ø²Ø±Ø§Ø± ØªÙØ§Ø¹Ù„ÙŠØ© ÙˆØ¯Ø¹Ù… 6 Ù„ØºØ§Øª
"""

import os
import sys
import json
import requests
import logging
import threading
import time
import asyncio
import io
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

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

# ============ Ø¥Ø¹Ø¯Ø§Ø¯Ø§Øª Ù‡Ø§Ù…Ø© Ø¬Ø¯Ø§Ù‹ ============
TOKEN = os.getenv("BOT_TOKEN")

# --- ØªØµØ­ÙŠØ­ Ø§Ù„Ø®Ø·Ø£ Ù‡Ù†Ø§: ØªØ¹ÙŠÙŠÙ† Ø§Ù„Ù‚Ù†Ø§Ø© Ø§Ù„ØµØ­ÙŠØ­Ø© Ø¨Ø´ÙƒÙ„ Ø§ÙØªØ±Ø§Ø¶ÙŠ ---
# Ø¥Ø°Ø§ Ù„Ù… ÙŠØ¬Ø¯ Ø§Ù„Ù‚ÙŠÙ…Ø© ÙÙŠ Ù…Ù„Ù .env Ø³ÙŠØ³ØªØ®Ø¯Ù… @medbibliotekaa
TARGET_CHANNEL = "@medbibliotekaa"  # forced to avoid hosting ENV override
# Normalize channel identifier
TARGET_CHANNEL = TARGET_CHANNEL.strip()
if not TARGET_CHANNEL.startswith("@") and not TARGET_CHANNEL.startswith("-100"):
    TARGET_CHANNEL = f"@{TARGET_CHANNEL}"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL = os.getenv("MODEL", "llama3.2")
PDF_DIR = "/tmp/pdf-bot-pro"

os.makedirs(PDF_DIR, exist_ok=True)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logger.info(f"âœ… TARGET_CHANNEL (runtime): {TARGET_CHANNEL}")

# ============ Ù†Ø¸Ø§Ù… Ø¥Ø¯Ø§Ø±Ø© Ø§Ù„Ø·Ù„Ø¨Ø§Øª Ø§Ù„Ù…ØªØ²Ø§Ù…Ù†Ø© ============
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

# ============ Ø¥Ø­ØµØ§Ø¦ÙŠØ§Øª Ø§Ù„Ù…Ø³ØªØ®Ø¯Ù…ÙŠÙ† ============
user_stats = {}

def update_stats(user_id, action_type):
    if user_id not in user_stats:
        user_stats[user_id] = {
            'pdfs': 0, 'texts': 0, 'images': 0, 'files': 0,
            'joined': datetime.now().isoformat()
        }
    user_stats[user_id][action_type] = user_stats[user_id].get(action_type, 0) + 1

def get_stats(user_id):
    return user_stats.get(user_id, {'pdfs': 0, 'texts': 0, 'images': 0, 'files': 0})

# ============ Ø§Ù„Ù„ØºØ§Øª (6 Ù„ØºØ§Øª) ============
TRANSLATIONS = {
    "ar": {
        "welcome": "ðŸ‘‹ Ù…Ø±Ø­Ø¨Ø§Ù‹ {name}!\n\nðŸ¤– **Ø¨ÙˆØª PDF Ø§Ù„Ø°ÙƒÙŠ Pro**\n\nðŸ“¤ Ø£Ø±Ø³Ù„: Ù†Øµ | ØµÙˆØ± | Ù…Ù„Ù TXT | Ù…Ù„Ù Word\n\nðŸŽ¨ Ø§Ø®ØªØ± Ø§Ù„Ù‚Ø§Ù„Ø¨ ÙˆØ§Ù„Ø¬ÙˆØ¯Ø© Ù…Ù† Ø§Ù„Ø¥Ø¹Ø¯Ø§Ø¯Ø§Øª",
        "received": "ðŸ“¥ **ØªÙ… Ø§Ø³ØªÙ„Ø§Ù… Ø·Ù„Ø¨Ùƒ!**\nâ³ Ø¬Ø§Ø±ÙŠ Ø§Ù„Ù…Ø¹Ø§Ù„Ø¬Ø©...",
        "processing": "ðŸ”„ Ø¬Ø§Ø±ÙŠ ØªØ­ÙˆÙŠÙ„ Ø§Ù„Ù†Øµ Ø¥Ù„Ù‰ PDF...\nâ±ï¸ ÙŠØ±Ø¬Ù‰ Ø§Ù„Ø§Ù†ØªØ¸Ø§Ø±",
        "processing_album": "ðŸ”„ Ø¬Ø§Ø±ÙŠ Ù…Ø¹Ø§Ù„Ø¬Ø© {count} ØµÙˆØ±...\nâ±ï¸ ÙŠØ±Ø¬Ù‰ Ø§Ù„Ø§Ù†ØªØ¸Ø§Ø±",
        "processing_step1": "ðŸ“ ØªØ­Ù„ÙŠÙ„ Ø§Ù„Ù…Ø­ØªÙˆÙ‰...",
        "processing_step2": "ðŸŽ¨ ØªØ·Ø¨ÙŠÙ‚ Ø§Ù„ØªØµÙ…ÙŠÙ…...",
        "processing_step3": "ðŸ“„ Ø¥Ù†Ø´Ø§Ø¡ Ù…Ù„Ù PDF...",
        "uploading": "ðŸ“¤ Ø¬Ø§Ø±ÙŠ Ø±ÙØ¹ Ø§Ù„Ù…Ù„Ù Ø¥Ù„ÙŠÙƒ...",
        "success": "âœ… **ØªÙ… Ø¨Ù†Ø¬Ø§Ø­!**\nðŸ“„ Ù…Ù„Ù PDF Ø¬Ø§Ù‡Ø² Ù„Ù„ØªØ­Ù…ÙŠÙ„",
        "success_album": "âœ… **ØªÙ… Ø¨Ù†Ø¬Ø§Ø­!**\nðŸ“„ {count} ØµÙˆØ± ÙÙŠ PDF ÙˆØ§Ø­Ø¯",
        "error": "âŒ **Ø­Ø¯Ø« Ø®Ø·Ø£**\n{error}\n\nðŸ”„ ÙŠØ±Ø¬Ù‰ Ø§Ù„Ù…Ø­Ø§ÙˆÙ„Ø© Ù…Ø±Ø© Ø£Ø®Ø±Ù‰",
        "not_member": "ðŸ”’ **Ø§Ù„Ø§Ø´ØªØ±Ø§Ùƒ Ù…Ø·Ù„ÙˆØ¨**\n\nðŸ“¢ Ø§Ø´ØªØ±Ùƒ ÙÙŠ {channel} Ø£ÙˆÙ„Ø§Ù‹\nâœ… Ø«Ù… Ø¹Ø¯ ÙˆØ£Ø±Ø³Ù„ /start",
        "title": "Ù…Ø³ØªÙ†Ø¯ PDF",
        "title_album": "Ø£Ù„Ø¨ÙˆÙ… Ø§Ù„ØµÙˆØ±",
        "watermark": "Â© PDF Bot Pro | {channel}",
        "footer": "ØªÙ… Ø§Ù„Ø¥Ù†Ø´Ø§Ø¡: {date}",
        "enhance_prompt": "Ø­Ø³Ù‘Ù† Ù‡Ø°Ø§ Ø§Ù„Ù†Øµ Ø¨Ø§Ù„Ø¹Ø±Ø¨ÙŠØ© ÙˆØ§Ø¬Ø¹Ù„Ù‡ Ø£ÙƒØ«Ø± ÙˆØ¶ÙˆØ­Ø§Ù‹",
        "settings": "âš™ï¸ **Ø§Ù„Ø¥Ø¹Ø¯Ø§Ø¯Ø§Øª**\n\nØ§Ø®ØªØ± Ù…Ø§ ØªØ±ÙŠØ¯ ØªØ¹Ø¯ÙŠÙ„Ù‡:",
        "template_select": "ðŸŽ¨ Ø§Ø®ØªØ± Ù‚Ø§Ù„Ø¨ Ø§Ù„ØªØµÙ…ÙŠÙ…:",
        "quality_select": "ðŸ“Š Ø§Ø®ØªØ± Ø¬ÙˆØ¯Ø© PDF:",
        "template_changed": "âœ… ØªÙ… ØªØºÙŠÙŠØ± Ø§Ù„Ù‚Ø§Ù„Ø¨ Ø¥Ù„Ù‰: {template}",
        "quality_changed": "âœ… ØªÙ… ØªØºÙŠÙŠØ± Ø§Ù„Ø¬ÙˆØ¯Ø© Ø¥Ù„Ù‰: {quality}",
        "stats": "ðŸ“Š **Ø¥Ø­ØµØ§Ø¦ÙŠØ§ØªÙƒ**\n\nðŸ“„ Ù…Ù„ÙØ§Øª PDF: {pdfs}\nðŸ“ Ù†ØµÙˆØµ: {texts}\nðŸ–¼ï¸ ØµÙˆØ±: {images}\nðŸ“ Ù…Ù„ÙØ§Øª: {files}",
        "help": "ðŸ“– **Ø§Ù„Ù…Ø³Ø§Ø¹Ø¯Ø©**\n\n/start - Ø¨Ø¯Ø¡ Ø§Ù„Ø¨ÙˆØª\n/settings - Ø§Ù„Ø¥Ø¹Ø¯Ø§Ø¯Ø§Øª\n/stats - Ø¥Ø­ØµØ§Ø¦ÙŠØ§ØªÙƒ\n/help - Ø§Ù„Ù…Ø³Ø§Ø¹Ø¯Ø©\n\nðŸ“¤ **ÙŠÙ…ÙƒÙ†Ùƒ Ø¥Ø±Ø³Ø§Ù„:**\nâ€¢ Ù†Øµ Ø¹Ø§Ø¯ÙŠ\nâ€¢ ØµÙˆØ±Ø© Ø£Ùˆ Ù…Ø¬Ù…ÙˆØ¹Ø© ØµÙˆØ±\nâ€¢ Ù…Ù„Ù TXT\nâ€¢ Ù…Ù„Ù Word (.docx)",
        "file_received": "ðŸ“ **ØªÙ… Ø§Ø³ØªÙ„Ø§Ù… Ø§Ù„Ù…Ù„Ù!**\nðŸ“ {filename}\nâ³ Ø¬Ø§Ø±ÙŠ Ø§Ù„ØªØ­ÙˆÙŠÙ„...",
        "docx_not_supported": "âš ï¸ Ø¯Ø¹Ù… Ù…Ù„ÙØ§Øª Word ØºÙŠØ± Ù…ØªÙˆÙØ±ØŒ ÙŠØ±Ø¬Ù‰ ØªØ«Ø¨ÙŠØª python-docx",
        "classic": "ðŸŽ¨ ÙƒÙ„Ø§Ø³ÙŠÙƒÙŠ",
        "modern": "âœ¨ Ø¹ØµØ±ÙŠ",
        "dark": "ðŸŒ™ Ø¯Ø§ÙƒÙ†",
        "high": "ðŸ”· Ø¹Ø§Ù„ÙŠØ©",
        "medium": "ðŸ”¶ Ù…ØªÙˆØ³Ø·Ø©",
        "low": "ðŸ”¸ Ù…Ù†Ø®ÙØ¶Ø©"
    },
    "en": {
        "welcome": "ðŸ‘‹ Hello {name}!\n\nðŸ¤– **AI PDF Bot Pro**\n\nðŸ“¤ Send: Text | Photos | TXT file | Word file\n\nðŸŽ¨ Choose template and quality in settings",
        "received": "ðŸ“¥ **Request received!**\nâ³ Processing...",
        "processing": "ðŸ”„ Converting text to PDF...\nâ±ï¸ Please wait",
        "processing_album": "ðŸ”„ Processing {count} images...\nâ±ï¸ Please wait",
        "processing_step1": "ðŸ“ Analyzing content...",
        "processing_step2": "ðŸŽ¨ Applying design...",
        "processing_step3": "ðŸ“„ Creating PDF file...",
        "uploading": "ðŸ“¤ Uploading file to you...",
        "success": "âœ… **Success!**\nðŸ“„ PDF file is ready to download",
        "success_album": "âœ… **Success!**\nðŸ“„ {count} images in one PDF",
        "error": "âŒ **Error occurred**\n{error}\n\nðŸ”„ Please try again",
        "not_member": "ðŸ”’ **Subscription required**\n\nðŸ“¢ Join {channel} first\nâœ… Then come back and send /start",
        "title": "PDF Document",
        "title_album": "Image Album",
        "watermark": "Â© PDF Bot Pro | {channel}",
        "footer": "Generated: {date}",
        "enhance_prompt": "Improve this text professionally and make it clearer",
        "settings": "âš™ï¸ **Settings**\n\nChoose what to modify:",
        "template_select": "ðŸŽ¨ Choose design template:",
        "quality_select": "ðŸ“Š Choose PDF quality:",
        "template_changed": "âœ… Template changed to: {template}",
        "quality_changed": "âœ… Quality changed to: {quality}",
        "stats": "ðŸ“Š **Your Statistics**\n\nðŸ“„ PDFs: {pdfs}\nðŸ“ Texts: {texts}\nðŸ–¼ï¸ Images: {images}\nðŸ“ Files: {files}",
        "help": "ðŸ“– **Help**\n\n/start - Start bot\n/settings - Settings\n/stats - Your stats\n/help - Help\n\nðŸ“¤ **You can send:**\nâ€¢ Plain text\nâ€¢ Photo or album\nâ€¢ TXT file\nâ€¢ Word file (.docx)",
        "file_received": "ðŸ“ **File received!**\nðŸ“ {filename}\nâ³ Converting...",
        "docx_not_supported": "âš ï¸ Word file support not available, please install python-docx",
        "classic": "ðŸŽ¨ Classic",
        "modern": "âœ¨ Modern",
        "dark": "ðŸŒ™ Dark",
        "high": "ðŸ”· High",
        "medium": "ðŸ”¶ Medium",
        "low": "ðŸ”¸ Low"
    },
    "ru": {
        "welcome": "ðŸ‘‹ ÐŸÑ€Ð¸Ð²ÐµÑ‚ {name}!\n\nðŸ¤– **AI PDF Ð‘Ð¾Ñ‚ Pro**\n\nðŸ“¤ ÐžÑ‚Ð¿Ñ€Ð°Ð²ÑŒÑ‚Ðµ: Ð¢ÐµÐºÑÑ‚ | Ð¤Ð¾Ñ‚Ð¾ | TXT | Word\n\nðŸŽ¨ Ð’Ñ‹Ð±ÐµÑ€Ð¸Ñ‚Ðµ ÑˆÐ°Ð±Ð»Ð¾Ð½ Ð¸ ÐºÐ°Ñ‡ÐµÑÑ‚Ð²Ð¾ Ð² Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ°Ñ…",
        "received": "ðŸ“¥ **Ð—Ð°Ð¿Ñ€Ð¾Ñ Ð¿Ñ€Ð¸Ð½ÑÑ‚!**\nâ³ ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ°...",
        "processing": "ðŸ”„ ÐšÐ¾Ð½Ð²ÐµÑ€Ñ‚Ð°Ñ†Ð¸Ñ Ñ‚ÐµÐºÑÑ‚Ð° Ð² PDF...\nâ±ï¸ ÐŸÐ¾Ð¶Ð°Ð»ÑƒÐ¹ÑÑ‚Ð°, Ð¿Ð¾Ð´Ð¾Ð¶Ð´Ð¸Ñ‚Ðµ",
        "processing_album": "ðŸ”„ ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° {count} Ð¸Ð·Ð¾Ð±Ñ€Ð°Ð¶ÐµÐ½Ð¸Ð¹...\nâ±ï¸ ÐŸÐ¾Ð¶Ð°Ð»ÑƒÐ¹ÑÑ‚Ð°, Ð¿Ð¾Ð´Ð¾Ð¶Ð´Ð¸Ñ‚Ðµ",
        "processing_step1": "ðŸ“ ÐÐ½Ð°Ð»Ð¸Ð· ÐºÐ¾Ð½Ñ‚ÐµÐ½Ñ‚Ð°...",
        "processing_step2": "ðŸŽ¨ ÐŸÑ€Ð¸Ð¼ÐµÐ½ÐµÐ½Ð¸Ðµ Ð´Ð¸Ð·Ð°Ð¹Ð½Ð°...",
        "processing_step3": "ðŸ“„ Ð¡Ð¾Ð·Ð´Ð°Ð½Ð¸Ðµ PDF...",
        "uploading": "ðŸ“¤ Ð—Ð°Ð³Ñ€ÑƒÐ·ÐºÐ° Ñ„Ð°Ð¹Ð»Ð°...",
        "success": "âœ… **Ð“Ð¾Ñ‚Ð¾Ð²Ð¾!**\nðŸ“„ PDF Ñ„Ð°Ð¹Ð» Ð³Ð¾Ñ‚Ð¾Ð² Ðº ÑÐºÐ°Ñ‡Ð¸Ð²Ð°Ð½Ð¸ÑŽ",
        "success_album": "âœ… **Ð“Ð¾Ñ‚Ð¾Ð²Ð¾!**\nðŸ“„ {count} Ð¸Ð·Ð¾Ð±Ñ€Ð°Ð¶ÐµÐ½Ð¸Ð¹ Ð² Ð¾Ð´Ð½Ð¾Ð¼ PDF",
        "error": "âŒ **ÐžÑˆÐ¸Ð±ÐºÐ°**\n{error}\n\nðŸ”„ ÐŸÐ¾Ð¿Ñ€Ð¾Ð±ÑƒÐ¹Ñ‚Ðµ ÑÐ½Ð¾Ð²Ð°",
        "not_member": "ðŸ”’ **Ð¢Ñ€ÐµÐ±ÑƒÐµÑ‚ÑÑ Ð¿Ð¾Ð´Ð¿Ð¸ÑÐºÐ°**\n\nðŸ“¢ ÐŸÐ¾Ð´Ð¿Ð¸ÑˆÐ¸Ñ‚ÐµÑÑŒ Ð½Ð° {channel}\nâœ… Ð—Ð°Ñ‚ÐµÐ¼ Ð²ÐµÑ€Ð½Ð¸Ñ‚ÐµÑÑŒ Ð¸ Ð½Ð°Ð¶Ð¼Ð¸Ñ‚Ðµ /start",
        "title": "PDF Ð”Ð¾ÐºÑƒÐ¼ÐµÐ½Ñ‚",
        "title_album": "Ð¤Ð¾Ñ‚Ð¾Ð°Ð»ÑŒÐ±Ð¾Ð¼",
        "watermark": "Â© PDF Bot Pro | {channel}",
        "footer": "Ð¡Ð¾Ð·Ð´Ð°Ð½Ð¾: {date}",
        "enhance_prompt": "Ð£Ð»ÑƒÑ‡ÑˆÐ¸ ÑÑ‚Ð¾Ñ‚ Ñ‚ÐµÐºÑÑ‚ Ð¿Ñ€Ð¾Ñ„ÐµÑÑÐ¸Ð¾Ð½Ð°Ð»ÑŒÐ½Ð¾ Ð½Ð° Ñ€ÑƒÑÑÐºÐ¾Ð¼ ÑÐ·Ñ‹ÐºÐµ",
        "settings": "âš™ï¸ **ÐÐ°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸**\n\nÐ’Ñ‹Ð±ÐµÑ€Ð¸Ñ‚Ðµ Ñ‡Ñ‚Ð¾ Ð¸Ð·Ð¼ÐµÐ½Ð¸Ñ‚ÑŒ:",
        "template_select": "ðŸŽ¨ Ð’Ñ‹Ð±ÐµÑ€Ð¸Ñ‚Ðµ ÑˆÐ°Ð±Ð»Ð¾Ð½:",
        "quality_select": "ðŸ“Š Ð’Ñ‹Ð±ÐµÑ€Ð¸Ñ‚Ðµ ÐºÐ°Ñ‡ÐµÑÑ‚Ð²Ð¾ PDF:",
        "template_changed": "âœ… Ð¨Ð°Ð±Ð»Ð¾Ð½ Ð¸Ð·Ð¼ÐµÐ½ÐµÐ½ Ð½Ð°: {template}",
        "quality_changed": "âœ… ÐšÐ°Ñ‡ÐµÑÑ‚Ð²Ð¾ Ð¸Ð·Ð¼ÐµÐ½ÐµÐ½Ð¾ Ð½Ð°: {quality}",
        "stats": "ðŸ“Š **Ð’Ð°ÑˆÐ° ÑÑ‚Ð°Ñ‚Ð¸ÑÑ‚Ð¸ÐºÐ°**\n\nðŸ“„ PDF Ñ„Ð°Ð¹Ð»Ð¾Ð²: {pdfs}\nðŸ“ Ð¢ÐµÐºÑÑ‚Ð¾Ð²: {texts}\nðŸ–¼ï¸ Ð˜Ð·Ð¾Ð±Ñ€Ð°Ð¶ÐµÐ½Ð¸Ð¹: {images}\nðŸ“ Ð¤Ð°Ð¹Ð»Ð¾Ð²: {files}",
        "help": "ðŸ“– **ÐŸÐ¾Ð¼Ð¾Ñ‰ÑŒ**\n\n/start - Ð—Ð°Ð¿ÑƒÑÐº\n/settings - ÐÐ°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸\n/stats - Ð¡Ñ‚Ð°Ñ‚Ð¸ÑÑ‚Ð¸ÐºÐ°\n/help - ÐŸÐ¾Ð¼Ð¾Ñ‰ÑŒ",
        "file_received": "ðŸ“ **Ð¤Ð°Ð¹Ð» Ð¿Ð¾Ð»ÑƒÑ‡ÐµÐ½!**\nðŸ“ {filename}\nâ³ ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ°...",
        "docx_not_supported": "âš ï¸ ÐŸÐ¾Ð´Ð´ÐµÑ€Ð¶ÐºÐ° Word Ð½ÐµÐ´Ð¾ÑÑ‚ÑƒÐ¿Ð½Ð°",
        "classic": "ðŸŽ¨ ÐšÐ»Ð°ÑÑÐ¸ÐºÐ°",
        "modern": "âœ¨ ÐœÐ¾Ð´ÐµÑ€Ð½",
        "dark": "ðŸŒ™ Ð¢Ñ‘Ð¼Ð½Ñ‹Ð¹",
        "high": "ðŸ”· Ð’Ñ‹ÑÐ¾ÐºÐ¾Ðµ",
        "medium": "ðŸ”¶ Ð¡Ñ€ÐµÐ´Ð½ÐµÐµ",
        "low": "ðŸ”¸ ÐÐ¸Ð·ÐºÐ¾Ðµ"
    }
}

# ============ Ø¥Ø¹Ø¯Ø§Ø¯Ø§Øª Ø§Ù„Ù…Ø³ØªØ®Ø¯Ù… ============
user_settings = {}

def get_user_settings(user_id):
    if user_id not in user_settings:
        user_settings[user_id] = {'template': 'modern', 'quality': 'high'}
    return user_settings[user_id]

def set_user_setting(user_id, key, value):
    if user_id not in user_settings:
        user_settings[user_id] = {'template': 'modern', 'quality': 'high'}
    user_settings[user_id][key] = value

# ============ Ø§Ù„Ù‚ÙˆØ§Ù„Ø¨ ============
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

class Localization:
    def __init__(self, lang):
        self.lang = lang if lang in TRANSLATIONS else 'en'
    
    def get(self, key, **kwargs):
        text = TRANSLATIONS[self.lang].get(key, TRANSLATIONS['en'].get(key, key))
        return text.format(**kwargs) if kwargs else text
    
    def format_date(self):
        return datetime.now().strftime('%Y-%m-%d %H:%M')

# ============ Ø§Ù„Ø®Ø·ÙˆØ· ============
class FontManager:
    FONT_PATHS = {
        'ar': '/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf',
        'en': '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        'ru': '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        'tr': '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        'fr': '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        'es': '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        'default': '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    }
    
    def __init__(self):
        self.loaded_fonts = {}
        for lang, path in self.FONT_PATHS.items():
            if os.path.exists(path):
                try:
                    font_name = f'Font_{lang}'
                    pdfmetrics.registerFont(TTFont(font_name, path))
                    self.loaded_fonts[lang] = font_name
                except Exception:
                    self.loaded_fonts[lang] = 'Helvetica'
            else:
                self.loaded_fonts[lang] = 'Helvetica'
    
    def get_font(self, lang):
        return self.loaded_fonts.get(lang, 'Helvetica')

font_manager = FontManager()

# ============ ÙØ­Øµ Ø§Ù„Ø¹Ø¶ÙˆÙŠØ© (Ù…Ø¹ Ø§Ù„Ø¥ØµÙ„Ø§Ø­Ø§Øª) ============
async def check_membership(user_id, context):
    try:
        # 1. Ø§Ù„ØªØ£ÙƒØ¯ Ø£Ù† Ø§Ù„Ù‚Ù†Ø§Ø© ØªØ¨Ø¯Ø£ Ø¨Ù€ @
        target = TARGET_CHANNEL
        if not target.startswith("@"):
            target = f"@{target}"
        
        # 2. Ù…Ø­Ø§ÙˆÙ„Ø© Ø¬Ù„Ø¨ Ø­Ø§Ù„Ø© Ø§Ù„Ù…Ø³ØªØ®Ø¯Ù…
        logger.info(f"ðŸ” Checking membership for user {user_id} in {target}...")
        member = await context.bot.get_chat_member(chat_id=target, user_id=user_id)
        
        logger.info(f"ðŸ‘¤ Status for {user_id}: {member.status}")

        # 3. Ø§Ù„ØªØ­Ù‚Ù‚ Ù…Ù† Ø§Ù„Ø­Ø§Ù„Ø§Øª Ø§Ù„Ù…Ø³Ù…ÙˆØ­ Ø¨Ù‡Ø§
        valid_statuses = ["creator", "administrator", "member"]
        
        # Ø§Ù„ØªØ­Ù‚Ù‚ Ø¨Ø§Ø³ØªØ®Ø¯Ø§Ù… Ø§Ù„Ù†ØµÙˆØµ (Ù„Ù„Ù†Ø³Ø® Ø§Ù„Ø­Ø¯ÙŠØ«Ø©) Ø£Ùˆ Ø§Ù„Ù€ Enums (Ù„Ù„Ù†Ø³Ø® Ø§Ù„Ù‚Ø¯ÙŠÙ…Ø©)
        if member.status in valid_statuses or \
           member.status in [ChatMember.OWNER, ChatMember.ADMINISTRATOR, ChatMember.MEMBER]:
            return True
            
        return False

    except Exception as e:
        logger.error(f"âŒ Membership Check Error: {e}")
        logger.warning(f"âš ï¸ Ù‡Ø§Ù…: ØªØ£ÙƒØ¯ Ø£Ù† Ø§Ù„Ø¨ÙˆØª Ù…Ø´Ø±Ù (Admin) ÙÙŠ Ø§Ù„Ù‚Ù†Ø§Ø© {TARGET_CHANNEL}")
        return False

# ============ Ollama ============
def call_ollama(prompt, system=""):
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "system": system,
            "stream": False
        }, timeout=30)
        data = response.json()
        return data.get("response", prompt)
    except Exception as e:
        logger.error(f"Ollama error: {e}")
        return prompt

# ============ Ø¥Ù†Ø´Ø§Ø¡ PDF Ù…Ù† Ù†Øµ ============
def create_pdf_text(content, chat_id, lang, user_id):
    loc = Localization(lang)
    font_name = font_manager.get_font(lang)
    settings = get_user_settings(user_id)
    template = TEMPLATES[settings['template']]

    filename = f"doc_{chat_id}_{int(time.time())}.pdf"
    filepath = os.path.join(PDF_DIR, filename)

    enhanced = call_ollama(content, loc.get('enhance_prompt'))

    c = canvas.Canvas(filepath, pagesize=A4)
    width, height = A4

    LEFT_MARGIN = 60
    RIGHT_MARGIN = 60
    TOP_MARGIN = 120
    BOTTOM_MARGIN = 70

    base_font = font_name if font_name != 'Helvetica' else "Helvetica"
    font_size = 11
    line_height = 16
    max_text_width = width - LEFT_MARGIN - RIGHT_MARGIN

    def draw_page_frame():
        c.setFillColor(HexColor(template['bg_color']))
        c.rect(0, 0, width, height, fill=True, stroke=False)

        # Watermark
        c.saveState()
        c.setFillColor(HexColor(template['watermark_color']))
        c.setFont("Helvetica-Bold", 46)
        c.translate(width / 2, height / 2)
        c.rotate(45)
        # Ù‡Ù†Ø§ Ø³ÙŠØ¸Ù‡Ø± Ø§Ø³Ù… Ø§Ù„Ù‚Ù†Ø§Ø© Ø§Ù„ØµØ­ÙŠØ­Ø© (@medbibliotekaa)
        c.drawCentredString(0, 0, loc.get('watermark', channel=TARGET_CHANNEL))
        
        russian_font = font_manager.get_font('ru')
        try:
            c.setFont(russian_font, 26)
        except Exception:
            c.setFont("Helvetica", 26)
        c.drawCentredString(0, -55, "Dr Mohammed Dashir")
        c.restoreState()

        if settings['template'] in ['modern', 'dark']:
            c.setFillColor(HexColor(template['accent_color']))
            c.rect(0, height - 8, width, 8, fill=True, stroke=False)

        c.setFillColor(HexColor(template['header_color']))
        c.setFont("Helvetica-Bold", 20)
        c.drawString(LEFT_MARGIN, height - 50, loc.get('title'))
        
        c.setFont("Helvetica", 10)
        c.setFillColor(HexColor(template['footer_color']))
        c.drawString(LEFT_MARGIN, height - 70, loc.format_date())
        c.setStrokeColor(HexColor(template['accent_color']))
        c.setLineWidth(1.5)
        c.line(LEFT_MARGIN, height - 80, width - RIGHT_MARGIN, height - 80)

        c.setFillColor(HexColor(template['footer_color']))
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(width / 2, 35, "Â© All Rights Reserved - Dr Mohammed Dashir")
        c.setFont("Helvetica", 8)
        c.drawCentredString(
            width / 2,
            22,
            f"{TARGET_CHANNEL} â€¢ " + loc.get('footer', date=loc.format_date())
        )

        if settings['template'] in ['modern', 'dark']:
            c.setFillColor(HexColor(template['accent_color']))
            c.rect(0, 0, width, 5, fill=True, stroke=False)

        c.setFont(base_font, font_size)
        c.setFillColor(HexColor(template['text_color']))

    draw_page_frame()
    y = height - TOP_MARGIN

    for raw_line in enhanced.split("\n"):
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

# ============ Ø£Ù„Ø¨ÙˆÙ… Ø§Ù„ØµÙˆØ± ============
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
        c.drawCentredString(width / 2, 28, "Â© All Rights Reserved - Dr Mohammed Dashir")
        c.setFont("Helvetica", 8)
        c.drawCentredString(
            width / 2,
            16,
            f"{TARGET_CHANNEL} â€¢ " + loc.get('footer', date=loc.format_date())
        )

        if settings['template'] in ['modern', 'dark']:
            c.setFillColor(HexColor(template['accent_color']))
            c.rect(0, 0, width, 4, fill=True, stroke=False)

    c.save()
    return filepath

def cleanup_file(filepath, delay=120):
    time.sleep(delay)
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"ðŸ—‘ï¸ Deleted: {filepath}")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

# ============ Ù…Ø¹Ø§Ù„Ø¬Ø§Øª Ø§Ù„Ø¨ÙˆØª ============
albums = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = user.language_code or 'en'
    loc = Localization(lang)

    # Ø³ÙŠÙ‚ÙˆÙ… Ù‡Ø°Ø§ Ø§Ù„ÙØ­Øµ Ø¨Ø§Ù„ØªØ­Ù‚Ù‚ Ù…Ù† Ø§Ù„Ù‚Ù†Ø§Ø© @medbibliotekaa Ø­ØµØ±Ø§Ù‹
    if not await check_membership(user.id, context):
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

    if not await check_membership(user.id, context):
        await update.message.reply_text(loc.get('not_member', channel=TARGET_CHANNEL))
        return

    keyboard = [
        [InlineKeyboardButton("ðŸŽ¨ " + loc.get('template_select').replace(':', ''), callback_data="menu_template")],
        [InlineKeyboardButton("ðŸ“Š " + loc.get('quality_select').replace(':', ''), callback_data="menu_quality")]
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

    if not await check_membership(user.id, context):
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

    if not await check_membership(user.id, context):
        await update.message.reply_text(loc.get('not_member', channel=TARGET_CHANNEL))
        return

    await update.message.reply_text(loc.get('help'), parse_mode='Markdown')

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    lang = user.language_code or 'en'
    loc = Localization(lang)

    if not await check_membership(user.id, context):
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

    if not await check_membership(user.id, context):
        await update.message.reply_text(loc.get('not_member', channel=TARGET_CHANNEL))
        return

    text = update.message.text
    if text.startswith('/'):
        return

    await acquire_request_slot()
    
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    processing_msg = await update.message.reply_text(loc.get('received'), parse_mode='Markdown')

    try:
        await asyncio.sleep(0.5)
        await processing_msg.edit_text(loc.get('processing_step1'), parse_mode='Markdown')
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        
        await asyncio.sleep(0.5)
        await processing_msg.edit_text(loc.get('processing_step2'), parse_mode='Markdown')
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        
        await processing_msg.edit_text(loc.get('processing_step3'), parse_mode='Markdown')
        pdf_path = create_pdf_text(text, str(chat_id), lang, user.id)
        update_stats(user.id, 'texts')
        update_stats(user.id, 'pdfs')

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
        threading.Thread(target=cleanup_file, args=(pdf_path, 120)).start()
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

    if not await check_membership(user_id, context):
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
                    threading.Thread(target=cleanup_file, args=(img, 10)).start()
                threading.Thread(target=cleanup_file, args=(pdf_path, 120)).start()
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

    if not await check_membership(user.id, context):
        await update.message.reply_text(loc.get('not_member', channel=TARGET_CHANNEL))
        return

    document = update.message.document
    file_name = document.file_name.lower()

    await acquire_request_slot()
    
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    processing_msg = await update.message.reply_text(
        loc.get('file_received', filename=document.file_name), 
        parse_mode='Markdown'
    )

    try:
        file = await document.get_file()
        file_path = os.path.join(PDF_DIR, f"file_{chat_id}_{int(time.time())}_{document.file_name}")
        await file.download_to_drive(file_path)

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
            await processing_msg.edit_text(loc.get('processing_step2'), parse_mode='Markdown')
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(0.3)
            
            await processing_msg.edit_text(loc.get('processing_step3'), parse_mode='Markdown')
            pdf_path = create_pdf_text(content, str(chat_id), lang, user.id)
            update_stats(user.id, 'files')
            update_stats(user.id, 'pdfs')

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
            threading.Thread(target=cleanup_file, args=(pdf_path, 120)).start()
        else:
            await processing_msg.edit_text(loc.get('error', error="Empty file"), parse_mode='Markdown')

        threading.Thread(target=cleanup_file, args=(file_path, 10)).start()
    except Exception as e:
        await processing_msg.edit_text(loc.get('error', error=str(e)), parse_mode='Markdown')
    finally:
        await release_request_slot()

# ============ Ø§Ù„ØªØ´ØºÙŠÙ„ ============
def main():
    logger.info("ðŸš€ Starting PDF Bot Pro v2.2...")
    logger.info(f"ðŸ“ PDF Directory: {PDF_DIR}")
    logger.info(f"ðŸ“¢ Target Channel: {TARGET_CHANNEL}")  # Ø³ÙŠØ·Ø¨Ø¹ Ø§Ù„Ù‚Ù†Ø§Ø© Ø§Ù„ØµØ­ÙŠØ­Ø© Ù„Ù„ØªØ£ÙƒØ¯
    
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(callback_handler))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    logger.info("âœ… Bot is running!")
    application.run_polling()

if __name__ == "__main__":
    main()
