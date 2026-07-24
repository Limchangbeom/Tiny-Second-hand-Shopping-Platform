from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, render_template, request
from flask_login import current_user
from sqlalchemy import func, or_
from sqlalchemy.orm import aliased

from ..extensions import db
from ..models import (
    AdminActionLog,
    Message,
    Product,
    ProductFavorite,
    Report,
    Transfer,
    User,
    utcnow,
)
from ..utils import (
    admin_required,
    log_admin_action,
    redirect_back_or_default,
    sanitize_text,
)


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _coerce_amount(value):
    if not value:
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return None


@admin_bp.route("/")
@admin_required
def dashboard():
    stats = {
        "users": User.query.count(),
        "suspended_users": User.query.filter_by(is_suspended=True).count(),
        "products": Product.query.count(),
        "blocked_products": Product.query.filter_by(is_blocked=True).count(),
        "open_reports": Report.query.filter_by(status="open").count(),
        "messages": Message.query.count(),
        "transfers": Transfer.query.count(),
        "favorites": ProductFavorite.query.count(),
    }
    recent_reports = Report.query.order_by(Report.created_at.desc()).limit(10).all()
    recent_logs = (
        AdminActionLog.query.order_by(AdminActionLog.created_at.desc()).limit(10).all()
    )
    return render_template(
        "admin/dashboard.html",
        stats=stats,
        recent_reports=recent_reports,
        recent_logs=recent_logs,
    )


@admin_bp.route("/users")
@admin_required
def users():
    keyword = sanitize_text(request.args.get("q", ""), 50)
    status_filter = sanitize_text(request.args.get("status", "all"), 20)
    role_filter = sanitize_text(request.args.get("role", "all"), 20)
    sort = sanitize_text(request.args.get("sort", "newest"), 20)

    query = User.query
    if keyword:
        like_pattern = f"%{keyword}%"
        query = query.filter(
            or_(
                User.username.ilike(like_pattern),
                User.display_name.ilike(like_pattern),
                User.bio.ilike(like_pattern),
            )
        )
    if status_filter == "active":
        query = query.filter(User.is_deleted.is_(False), User.is_suspended.is_(False))
    elif status_filter == "suspended":
        query = query.filter(User.is_deleted.is_(False), User.is_suspended.is_(True))
    elif status_filter == "deleted":
        query = query.filter(User.is_deleted.is_(True))

    if role_filter == "admin":
        query = query.filter(User.is_admin.is_(True))
    elif role_filter == "member":
        query = query.filter(User.is_admin.is_(False))

    if sort == "oldest":
        query = query.order_by(User.created_at.asc())
    elif sort == "name":
        query = query.order_by(User.display_name.asc(), User.username.asc())
    elif sort == "balance_high":
        query = query.order_by(User.balance.desc(), User.created_at.desc())
    elif sort == "balance_low":
        query = query.order_by(User.balance.asc(), User.created_at.desc())
    else:
        query = query.order_by(User.created_at.desc())

    users = query.all()
    return render_template(
        "admin/users.html",
        users=users,
        keyword=keyword,
        status_filter=status_filter,
        role_filter=role_filter,
        sort=sort,
        result_count=len(users),
    )


@admin_bp.route("/users/<int:user_id>/<string:action>", methods=["POST"])
@admin_required
def user_action(user_id, action):
    user = db.session.get(User, user_id)
    if not user:
        flash("대상 사용자를 찾을 수 없습니다.", "danger")
        return redirect_back_or_default("admin.users")
    if user.is_deleted:
        flash("탈퇴 처리된 계정은 수정할 수 없습니다.", "warning")
        return redirect_back_or_default("admin.users")

    if action == "suspend":
        user.is_suspended = True
        detail = "계정 정지"
    elif action == "reactivate":
        user.is_suspended = False
        detail = "계정 복구"
    elif action == "promote":
        user.is_admin = True
        detail = "관리자 승격"
    elif action == "demote":
        if user.id == current_user.id:
            flash("자기 자신을 강등할 수 없습니다.", "warning")
            return redirect_back_or_default("admin.users")
        user.is_admin = False
        detail = "관리자 해제"
    else:
        flash("지원하지 않는 작업입니다.", "danger")
        return redirect_back_or_default("admin.users")

    log_admin_action(current_user, action, "user", user.id, detail)
    db.session.commit()
    flash("사용자 상태가 변경되었습니다.", "success")
    return redirect_back_or_default("admin.users")


@admin_bp.route("/products")
@admin_required
def products():
    keyword = sanitize_text(request.args.get("q", ""), 80)
    status_filter = sanitize_text(request.args.get("status", "all"), 20)
    state_filter = sanitize_text(request.args.get("state", "all"), 20)
    sort = sanitize_text(request.args.get("sort", "newest"), 20)

    query = Product.query.join(User)
    if keyword:
        like_pattern = f"%{keyword}%"
        query = query.filter(
            or_(
                Product.title.ilike(like_pattern),
                Product.description.ilike(like_pattern),
                Product.category.ilike(like_pattern),
                User.username.ilike(like_pattern),
                User.display_name.ilike(like_pattern),
            )
        )
    if status_filter in {"available", "reserved", "sold"}:
        query = query.filter(Product.status == status_filter)

    if state_filter == "active":
        query = query.filter(
            Product.is_blocked.is_(False), Product.is_deleted.is_(False)
        )
    elif state_filter == "blocked":
        query = query.filter(Product.is_blocked.is_(True))
    elif state_filter == "deleted":
        query = query.filter(Product.is_deleted.is_(True))
    elif state_filter == "flagged":
        query = query.filter(
            or_(Product.is_blocked.is_(True), Product.is_deleted.is_(True))
        )

    if sort == "oldest":
        query = query.order_by(Product.created_at.asc())
    elif sort == "price_high":
        query = query.order_by(Product.price.desc(), Product.created_at.desc())
    elif sort == "price_low":
        query = query.order_by(Product.price.asc(), Product.created_at.desc())
    else:
        query = query.order_by(Product.created_at.desc())

    products = query.all()
    favorite_counts = {
        product_id: count
        for product_id, count in (
            db.session.query(ProductFavorite.product_id, func.count(ProductFavorite.id))
            .filter(
                ProductFavorite.product_id.in_([product.id for product in products])
            )
            .group_by(ProductFavorite.product_id)
            .all()
            if products
            else []
        )
    }
    return render_template(
        "admin/products.html",
        products=products,
        favorite_counts=favorite_counts,
        keyword=keyword,
        status_filter=status_filter,
        state_filter=state_filter,
        sort=sort,
        result_count=len(products),
    )


@admin_bp.route("/products/<int:product_id>/<string:action>", methods=["POST"])
@admin_required
def product_action(product_id, action):
    product = db.session.get(Product, product_id)
    if not product:
        flash("대상 상품을 찾을 수 없습니다.", "danger")
        return redirect_back_or_default("admin.products")

    if action == "block":
        product.is_blocked = True
        detail = "상품 차단"
    elif action == "unblock":
        product.is_blocked = False
        detail = "상품 차단 해제"
    elif action == "delete":
        product.is_deleted = True
        detail = "상품 삭제"
    elif action == "restore":
        product.is_deleted = False
        detail = "상품 복구"
    else:
        flash("지원하지 않는 작업입니다.", "danger")
        return redirect_back_or_default("admin.products")

    log_admin_action(current_user, action, "product", product.id, detail)
    db.session.commit()
    flash("상품 상태가 변경되었습니다.", "success")
    return redirect_back_or_default("admin.products")


@admin_bp.route("/reports")
@admin_required
def reports():
    reporter_alias = aliased(User)
    target_user_alias = aliased(User)

    keyword = sanitize_text(request.args.get("q", ""), 80)
    target_type_filter = sanitize_text(request.args.get("target_type", "all"), 20)
    status_filter = sanitize_text(request.args.get("status", "all"), 20)
    sort = sanitize_text(request.args.get("sort", "newest"), 20)

    query = (
        Report.query.join(reporter_alias, Report.reporter)
        .outerjoin(target_user_alias, Report.target_user)
        .outerjoin(Product, Report.target_product)
    )
    if keyword:
        like_pattern = f"%{keyword}%"
        query = query.filter(
            or_(
                Report.reason.ilike(like_pattern),
                reporter_alias.username.ilike(like_pattern),
                reporter_alias.display_name.ilike(like_pattern),
                target_user_alias.username.ilike(like_pattern),
                target_user_alias.display_name.ilike(like_pattern),
                Product.title.ilike(like_pattern),
            )
        )
    if target_type_filter in {"user", "product"}:
        query = query.filter(Report.target_type == target_type_filter)
    if status_filter in {"open", "resolved"}:
        query = query.filter(Report.status == status_filter)

    if sort == "oldest":
        query = query.order_by(Report.created_at.asc())
    else:
        query = query.order_by(Report.created_at.desc())

    reports = query.all()
    return render_template(
        "admin/reports.html",
        reports=reports,
        keyword=keyword,
        target_type_filter=target_type_filter,
        status_filter=status_filter,
        sort=sort,
        result_count=len(reports),
    )


@admin_bp.route("/reports/<int:report_id>/<string:action>", methods=["POST"])
@admin_required
def report_action(report_id, action):
    report = db.session.get(Report, report_id)
    if not report:
        flash("대상 신고를 찾을 수 없습니다.", "danger")
        return redirect_back_or_default("admin.reports")

    if action == "resolve":
        report.status = "resolved"
        report.reviewed_by_id = current_user.id
        report.resolved_at = utcnow()
        detail = "신고 처리 완료"
    elif action == "reopen":
        report.status = "open"
        report.reviewed_by_id = None
        report.resolved_at = None
        detail = "신고 재오픈"
    else:
        flash("지원하지 않는 작업입니다.", "danger")
        return redirect_back_or_default("admin.reports")

    log_admin_action(current_user, action, "report", report.id, detail)
    db.session.commit()
    flash("신고 상태가 변경되었습니다.", "success")
    return redirect_back_or_default("admin.reports")


@admin_bp.route("/messages")
@admin_required
def messages():
    sender_alias = aliased(User)
    recipient_alias = aliased(User)

    keyword = sanitize_text(request.args.get("q", ""), 80)
    room_type_filter = sanitize_text(request.args.get("room_type", "all"), 20)
    state_filter = sanitize_text(request.args.get("state", "all"), 20)
    read_filter = sanitize_text(request.args.get("read", "all"), 20)
    sort = sanitize_text(request.args.get("sort", "newest"), 20)

    query = Message.query.join(sender_alias, Message.sender).outerjoin(
        recipient_alias, Message.recipient
    )
    if keyword:
        like_pattern = f"%{keyword}%"
        query = query.filter(
            or_(
                Message.body.ilike(like_pattern),
                sender_alias.username.ilike(like_pattern),
                sender_alias.display_name.ilike(like_pattern),
                recipient_alias.username.ilike(like_pattern),
                recipient_alias.display_name.ilike(like_pattern),
            )
        )
    if room_type_filter in {"global", "direct"}:
        query = query.filter(Message.room_type == room_type_filter)
    if state_filter == "visible":
        query = query.filter(Message.is_removed.is_(False))
    elif state_filter == "removed":
        query = query.filter(Message.is_removed.is_(True))
    if read_filter == "read":
        query = query.filter(Message.room_type == "direct", Message.is_read.is_(True))
    elif read_filter == "unread":
        query = query.filter(Message.room_type == "direct", Message.is_read.is_(False))

    if sort == "oldest":
        query = query.order_by(Message.created_at.asc())
    else:
        query = query.order_by(Message.created_at.desc())

    messages = query.limit(200).all()
    return render_template(
        "admin/messages.html",
        messages=messages,
        keyword=keyword,
        room_type_filter=room_type_filter,
        state_filter=state_filter,
        read_filter=read_filter,
        sort=sort,
        result_count=len(messages),
    )


@admin_bp.route("/messages/<int:message_id>/<string:action>", methods=["POST"])
@admin_required
def message_action(message_id, action):
    message = db.session.get(Message, message_id)
    if not message:
        flash("대상 메시지를 찾을 수 없습니다.", "danger")
        return redirect_back_or_default("admin.messages")

    if action == "remove":
        message.is_removed = True
        detail = "메시지 숨김"
    elif action == "restore":
        message.is_removed = False
        detail = "메시지 복구"
    else:
        flash("지원하지 않는 작업입니다.", "danger")
        return redirect_back_or_default("admin.messages")

    log_admin_action(current_user, action, "message", message.id, detail)
    db.session.commit()
    flash("메시지 상태가 변경되었습니다.", "success")
    return redirect_back_or_default("admin.messages")


@admin_bp.route("/transactions")
@admin_required
def transactions():
    sender_alias = aliased(User)
    recipient_alias = aliased(User)

    keyword = sanitize_text(request.args.get("q", ""), 80)
    min_amount = request.args.get("min_amount", "")
    max_amount = request.args.get("max_amount", "")
    minimum_amount = _coerce_amount(min_amount)
    maximum_amount = _coerce_amount(max_amount)
    sort = sanitize_text(request.args.get("sort", "newest"), 20)

    query = Transfer.query.join(sender_alias, Transfer.sender).join(
        recipient_alias, Transfer.recipient
    )
    if keyword:
        like_pattern = f"%{keyword}%"
        query = query.filter(
            or_(
                Transfer.note.ilike(like_pattern),
                sender_alias.username.ilike(like_pattern),
                sender_alias.display_name.ilike(like_pattern),
                recipient_alias.username.ilike(like_pattern),
                recipient_alias.display_name.ilike(like_pattern),
            )
        )
    if minimum_amount is not None:
        query = query.filter(Transfer.amount >= minimum_amount)
    if maximum_amount is not None:
        query = query.filter(Transfer.amount <= maximum_amount)

    if sort == "oldest":
        query = query.order_by(Transfer.created_at.asc())
    elif sort == "amount_high":
        query = query.order_by(Transfer.amount.desc(), Transfer.created_at.desc())
    elif sort == "amount_low":
        query = query.order_by(Transfer.amount.asc(), Transfer.created_at.desc())
    else:
        query = query.order_by(Transfer.created_at.desc())

    transfers = query.limit(200).all()
    return render_template(
        "admin/transactions.html",
        transfers=transfers,
        keyword=keyword,
        min_amount=min_amount,
        max_amount=max_amount,
        sort=sort,
        result_count=len(transfers),
    )
