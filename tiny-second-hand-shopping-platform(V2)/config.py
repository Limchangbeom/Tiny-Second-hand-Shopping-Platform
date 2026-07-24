from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.environ.get(
        "SECRET_KEY", "change-this-secret-key-before-production"
    )
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'instance' / 'market.db'}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = str(BASE_DIR / "app" / "static" / "uploads")
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
    PRODUCT_REPORT_THRESHOLD = int(os.environ.get("PRODUCT_REPORT_THRESHOLD", "3"))
    USER_REPORT_THRESHOLD = int(os.environ.get("USER_REPORT_THRESHOLD", "5"))
    CHAT_WINDOW_SECONDS = int(os.environ.get("CHAT_WINDOW_SECONDS", "10"))
    CHAT_WINDOW_LIMIT = int(os.environ.get("CHAT_WINDOW_LIMIT", "5"))

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    PREFERRED_URL_SCHEME = os.environ.get("PREFERRED_URL_SCHEME", "http")
    WTF_CSRF_TIME_LIMIT = None

    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "ChangeMe123!")
    ADMIN_DISPLAY_NAME = os.environ.get("ADMIN_DISPLAY_NAME", "Platform Admin")

    SOCKETIO_CORS_ALLOWED_ORIGINS = [
        origin.strip()
        for origin in os.environ.get(
            "SOCKETIO_CORS_ALLOWED_ORIGINS",
            "http://127.0.0.1:5000,http://localhost:5000",
        ).split(",")
        if origin.strip()
    ]
