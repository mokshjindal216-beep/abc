import os

# NEWS & AI
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# CLOUD ASSETS
CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET")

# SOCIAL CREDENTIALS
# Note: We use IG_ACCESS_TOKEN for both Instagram and to fetch the FB Page Token
IG_USER_ID = os.environ.get("IG_USER_ID")
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN")

# FACEBOOK (Just the Page ID is needed now)
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")

# YOUTUBE
YT_REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN")
YT_CLIENT_ID = os.environ.get("YT_CLIENT_ID")
YT_CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET")

# NOTIFICATIONS
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_ADMIN_ID = os.environ.get("TELEGRAM_ADMIN_ID")
