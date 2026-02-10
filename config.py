import os

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Admin IDs: comma-separated, example: "123456789,987654321"
ADMIN_IDS = [
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
]

# Railway Postgres
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# (Optional) Provider API key - reserved for later integration
HOTSIM_API_KEY = os.getenv("HOTSIM_API_KEY", "").strip()

# Defaults used by db.py/settings
DEFAULT_PRICE_USD = float(os.getenv("DEFAULT_PRICE_USD", "0.5"))
DEFAULT_DAILY_LIMIT = int(os.getenv("DEFAULT_DAILY_LIMIT", "5"))

# UI behavior
SHOW_ADMIN_BUTTON_FOR_ADMINS = os.getenv("SHOW_ADMIN_BUTTON_FOR_ADMINS", "1").strip() == "1"
