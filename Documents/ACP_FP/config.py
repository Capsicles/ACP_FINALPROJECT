import os


class Config:
    SECRET_KEY = (
        os.environ.get("SECRET_KEY") or "your-secret-key-here-change-in-production"
    )
    DATABASE_PATH = os.path.join(os.path.dirname(__file__), "game_hub.db")
    ADMIN_EMAIL = "admin@gmail.com"
    ADMIN_PASSWORD = "admin123"
