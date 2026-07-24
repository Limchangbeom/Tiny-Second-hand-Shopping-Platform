from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import current_user, logout_user
from sqlalchemy import inspect, text
from flask_wtf.csrf import generate_csrf
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config

from .extensions import csrf, db, limiter, login_manager, socketio
from .models import Message, ProductFavorite, User
from .routes.admin import admin_bp
from .routes.auth import auth_bp
from .routes.chat import chat_bp
from .routes.main import main_bp
from .routes.products import products_bp
from .routes.reports import reports_bp
from .routes.wallet import wallet_bp
from .socketio_events import register_socket_handlers
from .utils import create_default_admin


def ensure_runtime_schema():
    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())
    if "user" not in table_names:
        return

    user_columns = {column["name"] for column in inspector.get_columns("user")}
    if "is_deleted" not in user_columns:
        db.session.execute(
            text("ALTER TABLE user ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0")
        )
    if "deleted_at" not in user_columns:
        db.session.execute(text("ALTER TABLE user ADD COLUMN deleted_at DATETIME"))

    if "message" in table_names:
        message_columns = {
            column["name"] for column in inspector.get_columns("message")
        }
        if "is_read" not in message_columns:
            db.session.execute(
                text(
                    "ALTER TABLE message ADD COLUMN is_read BOOLEAN NOT NULL DEFAULT 0"
                )
            )
        if "read_at" not in message_columns:
            db.session.execute(text("ALTER TABLE message ADD COLUMN read_at DATETIME"))
    db.session.commit()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    socketio.init_app(
        app,
        cors_allowed_origins=app.config["SOCKETIO_CORS_ALLOWED_ORIGINS"],
        manage_session=False,
    )

    setattr(login_manager, "login_view", "auth.login")
    setattr(login_manager, "login_message", "로그인이 필요합니다.")
    setattr(login_manager, "login_message_category", "warning")

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.before_request
    def force_logout_for_suspended_users():
        endpoint = request.endpoint or ""
        if not current_user.is_authenticated:
            return None
        if (current_user.is_suspended or current_user.is_deleted) and endpoint not in {
            "auth.login",
            "auth.logout",
            "static",
        }:
            is_deleted_user = current_user.is_deleted
            logout_user()
            if is_deleted_user:
                flash("탈퇴 처리된 계정입니다.", "danger")
            else:
                flash("계정이 정지되어 자동 로그아웃되었습니다.", "danger")
            return redirect(url_for("auth.login"))
        return None

    @app.context_processor
    def inject_template_helpers():
        unread_direct_count = 0
        favorite_count = 0
        if current_user.is_authenticated:
            unread_direct_count = Message.query.filter_by(
                room_type="direct",
                recipient_id=current_user.id,
                is_removed=False,
                is_read=False,
            ).count()
            favorite_count = ProductFavorite.query.filter_by(
                user_id=current_user.id
            ).count()
        return {
            "csrf_token": generate_csrf,
            "unread_direct_count": unread_direct_count,
            "favorite_count": favorite_count,
        }

    @app.after_request
    def apply_security_headers(response):
        request_url = urlsplit(request.host_url)
        origin = f"{request_url.scheme}://{request_url.netloc}"
        socket_origin = (
            f"{'wss' if request_url.scheme == 'https' else 'ws'}://{request_url.netloc}"
        )
        csp = (
            "default-src 'self'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            "img-src 'self' data: blob:; "
            "script-src 'self' https://cdn.socket.io; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            f"connect-src 'self' {origin} {socket_origin};"
        )
        response.headers.setdefault("Content-Security-Policy", csp)
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        return response

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(wallet_bp)
    app.register_blueprint(admin_bp)

    @app.errorhandler(403)
    def forbidden(_error):
        return (
            render_template(
                "errors/error.html",
                code=403,
                title="접근 거부",
                message="이 페이지에 접근할 권한이 없습니다.",
            ),
            403,
        )

    @app.errorhandler(404)
    def not_found(_error):
        return (
            render_template(
                "errors/error.html",
                code=404,
                title="페이지 없음",
                message="요청한 페이지를 찾을 수 없습니다.",
            ),
            404,
        )

    @app.errorhandler(413)
    def file_too_large(_error):
        return (
            render_template(
                "errors/error.html",
                code=413,
                title="업로드 제한",
                message="파일 크기가 제한을 초과했습니다. 2MB 이하 이미지를 사용하세요.",
            ),
            413,
        )

    @app.errorhandler(429)
    def rate_limited(_error):
        return (
            render_template(
                "errors/error.html",
                code=429,
                title="요청 제한",
                message="요청이 너무 많습니다. 잠시 후 다시 시도하세요.",
            ),
            429,
        )

    with app.app_context():
        db.create_all()
        ensure_runtime_schema()
        create_default_admin()

    register_socket_handlers(socketio)
    return app
