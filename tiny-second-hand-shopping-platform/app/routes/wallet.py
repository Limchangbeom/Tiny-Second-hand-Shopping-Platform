from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user
from sqlalchemy import func, or_

from ..extensions import db, limiter
from ..forms import TransferForm
from ..models import Transfer, User
from ..utils import active_user_required, sanitize_text


wallet_bp = Blueprint("wallet", __name__, url_prefix="/wallet")


@wallet_bp.route("/", methods=["GET", "POST"])
@active_user_required
@limiter.limit("10 per hour")
def index():
    form = TransferForm()

    if form.validate_on_submit():
        receiver_username = form.recipient_username.data.strip().lower()
        recipient = User.query.filter(
            func.lower(User.username) == receiver_username,
            User.is_deleted.is_(False),
        ).first()
        amount = Decimal(str(form.amount.data)).quantize(Decimal("0.01"))

        if not recipient:
            flash("받는 사람을 찾을 수 없습니다.", "danger")
        elif recipient.id == current_user.id:
            flash("자기 자신에게는 송금할 수 없습니다.", "warning")
        elif recipient.is_suspended:
            flash("정지된 계정에게는 송금할 수 없습니다.", "warning")
        elif amount <= 0:
            flash("송금 금액은 0보다 커야 합니다.", "warning")
        elif Decimal(str(current_user.balance)) < amount:
            flash("잔액이 부족합니다.", "danger")
        else:
            current_user.balance = Decimal(str(current_user.balance)) - amount
            recipient.balance = Decimal(str(recipient.balance)) + amount

            transfer = Transfer(
                sender_id=current_user.id,
                recipient_id=recipient.id,
                amount=amount,
                note=sanitize_text(form.note.data, 160),
            )
            db.session.add(transfer)
            db.session.commit()
            flash("송금이 완료되었습니다.", "success")
            return redirect(url_for("wallet.index"))

    transactions = (
        Transfer.query.filter(
            or_(
                Transfer.sender_id == current_user.id,
                Transfer.recipient_id == current_user.id,
            )
        )
        .order_by(Transfer.created_at.desc())
        .limit(30)
        .all()
    )
    return render_template("wallet/index.html", form=form, transactions=transactions)
