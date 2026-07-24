from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user

from ..extensions import db, limiter
from ..forms import ReportForm
from ..models import Product, Report, User
from ..utils import active_user_required, apply_auto_moderation, sanitize_text


reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


def _load_report_target(target_type, target_id):
    if target_type == "product":
        target = db.session.get(Product, target_id)
    elif target_type == "user":
        target = db.session.get(User, target_id)
    else:
        target = None
    if target_type == "user" and target and target.is_deleted:
        target = None
    if target_type == "product" and target and target.is_deleted:
        target = None
    if not target:
        abort(404)
    return target


def _report_redirect(target_type, target_id):
    if target_type == "product":
        return url_for("products.detail", product_id=target_id)
    return url_for("main.user_detail", user_id=target_id)


@reports_bp.route("/new/<string:target_type>/<int:target_id>", methods=["GET", "POST"])
@active_user_required
@limiter.limit("10 per hour")
def create_report(target_type, target_id):
    target = _load_report_target(target_type, target_id)
    form = ReportForm()

    if target_type == "product" and target.seller_id == current_user.id:
        flash("자신의 상품은 신고할 수 없습니다.", "warning")
        return redirect(_report_redirect(target_type, target_id))
    if target_type == "user" and target.id == current_user.id:
        flash("자기 자신은 신고할 수 없습니다.", "warning")
        return redirect(_report_redirect(target_type, target_id))

    if form.validate_on_submit():
        existing_report = Report.query.filter_by(
            reporter_id=current_user.id,
            target_type=target_type,
            target_product_id=target.id if target_type == "product" else None,
            target_user_id=target.id if target_type == "user" else None,
            status="open",
        ).first()
        if existing_report:
            flash("이미 처리 대기 중인 신고가 있습니다.", "warning")
            return redirect(_report_redirect(target_type, target_id))

        report = Report(
            reporter_id=current_user.id,
            target_type=target_type,
            target_product_id=target.id if target_type == "product" else None,
            target_user_id=target.id if target_type == "user" else None,
            reason=sanitize_text(form.reason.data, 500),
        )
        db.session.add(report)
        moderation_notes = apply_auto_moderation(target_type, target.id)
        db.session.commit()
        flash_message = "신고가 접수되었습니다."
        if moderation_notes:
            flash_message = f"{flash_message} {' '.join(moderation_notes)}"
        flash(flash_message, "success")
        return redirect(_report_redirect(target_type, target_id))

    return render_template(
        "reports/create.html", form=form, target=target, target_type=target_type
    )
