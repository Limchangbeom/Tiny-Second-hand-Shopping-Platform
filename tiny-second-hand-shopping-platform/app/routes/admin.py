from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_

from ..extensions import db
from ..models import AdminActionLog, Message, Product, Report, Transfer, User, utcnow
from ..utils import admin_required, log_admin_action, sanitize_text


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


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
    query = User.query
    if keyword:
        like_pattern = f"%{keyword}%"
        query = query.filter(
            or_(
                User.username.ilike(like_pattern), User.display_name.ilike(like_pattern)
            )
        )
    users = query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=users, keyword=keyword)


@admin_bp.route("/users/<int:user_id>/<string:action>", methods=["POST"])
@admin_required
def user_action(user_id, action):
    user = db.session.get(User, user_id)
    if not user:
        flash("대상 사용자를 찾을 수 없습니다.", "danger")
        return redirect(url_for("admin.users"))
    if user.is_deleted:
        flash("탈퇴 처리된 계정은 수정할 수 없습니다.", "warning")
        return redirect(url_for("admin.users"))

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
            return redirect(url_for("admin.users"))
        user.is_admin = False
        detail = "관리자 해제"
    else:
        flash("지원하지 않는 작업입니다.", "danger")
        return redirect(url_for("admin.users"))

    log_admin_action(current_user, action, "user", user.id, detail)
    db.session.commit()
    flash("사용자 상태가 변경되었습니다.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/products")
@admin_required
def products():
    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template("admin/products.html", products=products)


@admin_bp.route("/products/<int:product_id>/<string:action>", methods=["POST"])
@admin_required
def product_action(product_id, action):
    product = db.session.get(Product, product_id)
    if not product:
        flash("대상 상품을 찾을 수 없습니다.", "danger")
        return redirect(url_for("admin.products"))

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
        return redirect(url_for("admin.products"))

    log_admin_action(current_user, action, "product", product.id, detail)
    db.session.commit()
    flash("상품 상태가 변경되었습니다.", "success")
    return redirect(url_for("admin.products"))


@admin_bp.route("/reports")
@admin_required
def reports():
    reports = Report.query.order_by(Report.created_at.desc()).all()
    return render_template("admin/reports.html", reports=reports)


@admin_bp.route("/reports/<int:report_id>/<string:action>", methods=["POST"])
@admin_required
def report_action(report_id, action):
    report = db.session.get(Report, report_id)
    if not report:
        flash("대상 신고를 찾을 수 없습니다.", "danger")
        return redirect(url_for("admin.reports"))

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
        return redirect(url_for("admin.reports"))

    log_admin_action(current_user, action, "report", report.id, detail)
    db.session.commit()
    flash("신고 상태가 변경되었습니다.", "success")
    return redirect(url_for("admin.reports"))


@admin_bp.route("/messages")
@admin_required
def messages():
    messages = Message.query.order_by(Message.created_at.desc()).limit(120).all()
    return render_template("admin/messages.html", messages=messages)


@admin_bp.route("/messages/<int:message_id>/<string:action>", methods=["POST"])
@admin_required
def message_action(message_id, action):
    message = db.session.get(Message, message_id)
    if not message:
        flash("대상 메시지를 찾을 수 없습니다.", "danger")
        return redirect(url_for("admin.messages"))

    if action == "remove":
        message.is_removed = True
        detail = "메시지 숨김"
    elif action == "restore":
        message.is_removed = False
        detail = "메시지 복구"
    else:
        flash("지원하지 않는 작업입니다.", "danger")
        return redirect(url_for("admin.messages"))

    log_admin_action(current_user, action, "message", message.id, detail)
    db.session.commit()
    flash("메시지 상태가 변경되었습니다.", "success")
    return redirect(url_for("admin.messages"))


@admin_bp.route("/transactions")
@admin_required
def transactions():
    transfers = Transfer.query.order_by(Transfer.created_at.desc()).limit(150).all()
    return render_template("admin/transactions.html", transfers=transfers)
