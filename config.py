import os

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Admins (مثال: 123456789,987654321)
ADMIN_IDS = [
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
]

# Database (Railway Postgres)
DATABASE_URL = os.getenv("DATABASE_URL")

# API key (سيستخدم لاحقاً عند ربط مزود الأرقام)
HOTSIM_API_KEY = os.getenv("HOTSIM_API_KEY")

# السعر الافتراضي للرقم
PRICE_PER_NUMBER = float(os.getenv("PRICE_PER_NUMBER", "0.5"))

# الحد اليومي الافتراضي لكل مستخدم
DEFAULT_DAILY_LIMIT = int(os.getenv("DEFAULT_DAILY_LIMIT", "5"))

# هل يظهر زر الادمن في القائمة الرئيسية
SHOW_ADMIN_BUTTON_FOR_ADMINS = os.getenv(
    "SHOW_ADMIN_BUTTON_FOR_ADMINS",
    "1"
) == "1"
