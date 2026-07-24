from functools import wraps
from pathlib import Path
from secrets import token_urlsafe
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import bleach
from PIL import Image, UnidentifiedImageError
from flask import abort, current_app, flash, redirect, request, url_for
from flask_login import current_user, login_required, logout_user
from werkzeug.utils import secure_filename

from .extensions import db
from .models import AdminActionLog, Product, Report, User, utcnow


def sanitize_text(value, max_length=None):
    cleaned = bleach.clean(
        value or "", tags=[], attributes={}, protocols=[], strip=True
    )
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.split()) for line in cleaned.split("\n")]
    cleaned = "\n".join(lines).strip()
    if max_length is not None:
        cleaned = cleaned[:max_length].strip()
    return cleaned


def is_safe_next_url(target):
    if not target:
        return False
    ref_url = urlsplit(request.host_url)
    test_url = urlsplit(urljoin(request.host_url, target))
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc


def active_user_required(view):
    @wraps(view)
    @login_required
    def wrapped_view(*args, **kwargs):
        if current_user.is_suspended or current_user.is_deleted:
            is_deleted_user = current_user.is_deleted
            logout_user()
            if is_deleted_user:
                flash("탈퇴 처리된 계정은 서비스를 사용할 수 없습니다.", "danger")
            else:
                flash("정지된 계정은 서비스를 사용할 수 없습니다.", "danger")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped_view


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped_view(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped_view


def validate_and_save_image(file_storage):
    if not file_storage or not file_storage.filename:
        return None

    filename = secure_filename(file_storage.filename)
    if "." not in filename:
        raise ValueError("확장자가 있는 이미지 파일만 업로드할 수 있습니다.")

    extension = filename.rsplit(".", 1)[1].lower()
    if extension not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        raise ValueError("허용되지 않는 이미지 형식입니다.")

    try:
        image = Image.open(file_storage.stream)
        image.verify()
        file_storage.stream.seek(0)
    except (UnidentifiedImageError, OSError):
        raise ValueError("손상되었거나 위장된 파일은 업로드할 수 없습니다.")

    saved_name = f"{uuid4().hex}.{extension}"
    destination = Path(current_app.config["UPLOAD_FOLDER"]) / saved_name
    file_storage.save(destination)
    return saved_name


def delete_image_file(filename):
    if not filename:
        return
    file_path = Path(current_app.config["UPLOAD_FOLDER"]) / filename
    if file_path.exists() and file_path.is_file():
        file_path.unlink()


def withdraw_user_account(user):
    if user.is_admin:
        raise ValueError("관리자 계정은 직접 탈퇴할 수 없습니다.")

    for product in user.products.all():
        delete_image_file(product.image_filename)
        product.image_filename = None
        product.is_deleted = True
        product.is_blocked = True

    user.username = f"withdrawn_{user.id}_{uuid4().hex[:8]}"
    user.display_name = "탈퇴한 사용자"
    user.bio = "탈퇴 처리된 계정입니다."
    user.is_suspended = True
    user.is_deleted = True
    user.deleted_at = utcnow()
    user.set_password(token_urlsafe(32))


def create_default_admin():
    username = current_app.config["ADMIN_USERNAME"].strip().lower()
    admin = User.query.filter_by(username=username).first()
    if admin:
        return admin

    admin = User(
        username=username,
        display_name=current_app.config["ADMIN_DISPLAY_NAME"],
        bio="시스템 초기 관리자 계정입니다.",
        is_admin=True,
    )
    admin.set_password(current_app.config["ADMIN_PASSWORD"])
    db.session.add(admin)
    db.session.commit()
    return admin


def log_admin_action(admin_user, action_type, target_type, target_id, details=""):
    log = AdminActionLog(
        admin_id=admin_user.id,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        details=sanitize_text(details, 300),
    )
    db.session.add(log)


def apply_auto_moderation(target_type, target_id):
    notes = []

    if target_type == "product":
        open_count = Report.query.filter_by(
            target_type="product",
            target_product_id=target_id,
            status="open",
        ).count()
        product = db.session.get(Product, target_id)
        if product and open_count >= current_app.config["PRODUCT_REPORT_THRESHOLD"]:
            product.is_blocked = True
            notes.append("신고 누적으로 상품이 자동 차단되었습니다.")

    if target_type == "user":
        open_count = Report.query.filter_by(
            target_type="user",
            target_user_id=target_id,
            status="open",
        ).count()
        user = db.session.get(User, target_id)
        if (
            user
            and not user.is_admin
            and open_count >= current_app.config["USER_REPORT_THRESHOLD"]
        ):
            user.is_suspended = True
            notes.append("신고 누적으로 계정이 자동 정지되었습니다.")

    return notes
