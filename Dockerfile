FROM python:3.11-slim

# تثبيت حزم النظام المطلوبة (خصوصاً الخطوط لـ reportlab + العربية)
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

# مجلد العمل داخل الحاوية
WORKDIR /app

# تثبيت مكتبات بايثون
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ بقية ملفات المشروع
COPY . .

# إخراج مباشر للّوغ بدون Buffer
ENV PYTHONUNBUFFERED=1

# أمر التشغيل: شغّل ملف البوت مالك
CMD ["python", "pdf-bot-pro.py"]
