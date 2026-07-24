from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, logout_user
from sqlalchemy import or_

from ..extensions import db
from ..forms import ProfileForm, WithdrawalForm
from ..models import Message, Product, ProductFavorite, Transfer, User
from ..utils import (
    active_user_required,
    get_favorite_product_ids,
    get_product_favorite_counts,
    sanitize_text,
    withdraw_user_account,
)


main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    recent_products = (
        Product.query.filter_by(is_deleted=False, is_blocked=False)
        .order_by(Product.created_at.desc())
        .limit(6)
        .all()
    )
    stats = {
        "users": User.query.filter_by(is_deleted=False).count(),
        "products": Product.query.filter_by(is_deleted=False).count(),
        "messages": Message.query.filter_by(is_removed=False).count(),
        "transfers": Transfer.query.count(),
        "favorites": ProductFavorite.query.count(),
    }
    favorite_product_ids = get_favorite_product_ids(
        current_user.id if current_user.is_authenticated else None
    )
    favorite_counts = get_product_favorite_counts(
        [product.id for product in recent_products]
    )
    return render_template(
        "index.html",
        products=recent_products,
        stats=stats,
        favorite_product_ids=favorite_product_ids,
        favorite_counts=favorite_counts,
    )


@main_bp.route("/users")
def users():
    keyword = sanitize_text(request.args.get("q", ""), 50)
    query = User.query
    if not (current_user.is_authenticated and current_user.is_admin):
        query = query.filter(User.is_deleted.is_(False))
    if keyword:
        like_pattern = f"%{keyword}%"
        query = query.filter(
            or_(
                User.username.ilike(like_pattern),
                User.display_name.ilike(like_pattern),
            )
        )
    users = query.order_by(User.is_admin.desc(), User.created_at.desc()).all()
    return render_template("profile/users.html", users=users, keyword=keyword)


@main_bp.route("/users/<int:user_id>")
def user_detail(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    if user.is_deleted and not (
        current_user.is_authenticated and current_user.is_admin
    ):
        abort(404)

    products_query = Product.query.filter_by(seller_id=user.id, is_deleted=False)
    if not (
        current_user.is_authenticated
        and (current_user.id == user.id or current_user.is_admin)
    ):
        products_query = products_query.filter_by(is_blocked=False)
    products = products_query.order_by(Product.created_at.desc()).all()
    favorite_product_ids = get_favorite_product_ids(
        current_user.id if current_user.is_authenticated else None
    )
    favorite_counts = get_product_favorite_counts([product.id for product in products])
    return render_template(
        "profile/user_detail.html",
        profile_user=user,
        products=products,
        favorite_product_ids=favorite_product_ids,
        favorite_counts=favorite_counts,
    )


@main_bp.route("/profile", methods=["GET", "POST"])
@active_user_required
def profile():
    form = ProfileForm()
    if form.validate_on_submit():
        current_user.display_name = sanitize_text(form.display_name.data, 60)
        current_user.bio = sanitize_text(form.bio.data, 300)
        if form.new_password.data:
            current_user.set_password(form.new_password.data)
        db.session.commit()
        flash("프로필이 저장되었습니다.", "success")
        return redirect(url_for("main.profile"))

    if request.method == "GET":
        form.display_name.data = current_user.display_name
        form.bio.data = current_user.bio

    return render_template("profile/profile.html", form=form, updated=False)


@main_bp.route("/profile/withdraw", methods=["GET", "POST"])
@active_user_required
def withdraw():
    if current_user.is_admin:
        flash("관리자 계정은 직접 탈퇴할 수 없습니다.", "warning")
        return redirect(url_for("main.profile"))

    form = WithdrawalForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.password.data):
            flash("비밀번호가 올바르지 않습니다.", "danger")
        else:
            withdraw_user_account(current_user)
            db.session.commit()
            logout_user()
            flash("회원 탈퇴가 완료되었습니다.", "success")
            return redirect(url_for("main.index"))

    return render_template("profile/withdraw.html", form=form)
