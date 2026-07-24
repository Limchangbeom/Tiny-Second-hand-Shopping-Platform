from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, or_

from ..extensions import db, limiter
from ..forms import ProductForm
from ..models import Product, ProductFavorite, User
from ..utils import (
    active_user_required,
    delete_image_file,
    get_favorite_product_ids,
    get_product_favorite_counts,
    log_admin_action,
    redirect_back_or_default,
    sanitize_text,
    validate_and_save_image,
)


products_bp = Blueprint("products", __name__, url_prefix="/products")


def _get_product_or_404(product_id):
    product = db.session.get(Product, product_id)
    if not product:
        abort(404)
    return product


def _ensure_product_owner_or_admin(product):
    if not current_user.is_authenticated:
        abort(403)
    if current_user.id != product.seller_id and not current_user.is_admin:
        abort(403)


def _apply_listing_filters(query, keyword, status):
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
    if status in {"available", "reserved", "sold"}:
        query = query.filter(Product.status == status)
    return query


def _apply_listing_sort(query, sort):
    if sort == "price_low":
        return query.order_by(Product.price.asc(), Product.created_at.desc())
    if sort == "price_high":
        return query.order_by(Product.price.desc(), Product.created_at.desc())
    if sort == "popular":
        favorite_counts_subquery = (
            db.session.query(
                ProductFavorite.product_id.label("product_id"),
                func.count(ProductFavorite.id).label("favorite_count"),
            )
            .group_by(ProductFavorite.product_id)
            .subquery()
        )
        return query.outerjoin(
            favorite_counts_subquery,
            favorite_counts_subquery.c.product_id == Product.id,
        ).order_by(
            func.coalesce(favorite_counts_subquery.c.favorite_count, 0).desc(),
            Product.created_at.desc(),
        )
    return query.order_by(Product.created_at.desc())


def _render_listing(query, *, keyword, status, sort, saved_only=False):
    query = _apply_listing_filters(query, keyword, status)
    products = _apply_listing_sort(query, sort).all()
    favorite_product_ids = get_favorite_product_ids(
        current_user.id if current_user.is_authenticated else None
    )
    favorite_counts = get_product_favorite_counts([product.id for product in products])
    return render_template(
        "products/list.html",
        products=products,
        keyword=keyword,
        status=status,
        sort=sort,
        saved_only=saved_only,
        favorite_product_ids=favorite_product_ids,
        favorite_counts=favorite_counts,
    )


@products_bp.route("/")
def product_list():
    keyword = sanitize_text(request.args.get("q", ""), 80)
    status = sanitize_text(request.args.get("status", ""), 20)
    sort = sanitize_text(request.args.get("sort", "latest"), 20)

    query = Product.query.join(User).filter(
        Product.is_deleted.is_(False), Product.is_blocked.is_(False)
    )
    return _render_listing(query, keyword=keyword, status=status, sort=sort)


@products_bp.route("/favorites")
@active_user_required
def favorite_products():
    keyword = sanitize_text(request.args.get("q", ""), 80)
    status = sanitize_text(request.args.get("status", ""), 20)
    sort = sanitize_text(request.args.get("sort", "latest"), 20)

    query = (
        Product.query.join(User)
        .join(ProductFavorite, ProductFavorite.product_id == Product.id)
        .filter(
            ProductFavorite.user_id == current_user.id,
            Product.is_deleted.is_(False),
            Product.is_blocked.is_(False),
        )
    )
    return _render_listing(
        query, keyword=keyword, status=status, sort=sort, saved_only=True
    )


@products_bp.route("/mine")
@active_user_required
def my_products():
    products = (
        Product.query.filter_by(seller_id=current_user.id)
        .order_by(Product.created_at.desc())
        .all()
    )
    favorite_counts = get_product_favorite_counts([product.id for product in products])
    return render_template(
        "products/manage.html",
        products=products,
        favorite_counts=favorite_counts,
    )


@products_bp.route("/new", methods=["GET", "POST"])
@active_user_required
@limiter.limit("10 per hour")
def create_product():
    form = ProductForm()
    if form.validate_on_submit():
        product = Product()
        product.seller_id = current_user.id
        product.title = sanitize_text(form.title.data, 80)
        product.category = sanitize_text(form.category.data, 40)
        product.description = sanitize_text(form.description.data, 1200)
        product.price = form.price.data
        product.status = form.status.data
        if form.image.data:
            try:
                product.image_filename = validate_and_save_image(form.image.data)
            except ValueError as exc:
                flash(str(exc), "danger")
                return render_template(
                    "products/form.html", form=form, title="상품 등록"
                )

        db.session.add(product)
        db.session.commit()
        flash("상품이 등록되었습니다.", "success")
        return redirect(url_for("products.detail", product_id=product.id))

    return render_template("products/form.html", form=form, title="상품 등록")


@products_bp.route("/<int:product_id>")
def detail(product_id):
    product = _get_product_or_404(product_id)
    can_view_hidden = current_user.is_authenticated and (
        current_user.id == product.seller_id or current_user.is_admin
    )
    if product.is_deleted and not can_view_hidden:
        abort(404)
    if product.is_blocked and not can_view_hidden:
        abort(404)

    favorite_product_ids = get_favorite_product_ids(
        current_user.id if current_user.is_authenticated else None
    )
    favorite_counts = get_product_favorite_counts([product.id])
    return render_template(
        "products/detail.html",
        product=product,
        favorite_product_ids=favorite_product_ids,
        favorite_counts=favorite_counts,
    )


@products_bp.route("/<int:product_id>/favorite", methods=["POST"])
@active_user_required
def toggle_favorite(product_id):
    product = _get_product_or_404(product_id)
    if product.is_deleted or product.is_blocked:
        abort(404)

    favorite = ProductFavorite.query.filter_by(
        user_id=current_user.id,
        product_id=product.id,
    ).first()
    changed = False
    if favorite:
        db.session.delete(favorite)
        flash("찜 목록에서 상품을 제거했습니다.", "success")
        changed = True
    elif current_user.id == product.seller_id:
        flash("자신의 상품은 찜할 수 없습니다.", "warning")
    else:
        favorite = ProductFavorite()
        favorite.user_id = current_user.id
        favorite.product_id = product.id
        db.session.add(favorite)
        flash("찜 목록에 상품을 추가했습니다.", "success")
        changed = True

    if changed:
        db.session.commit()
    return redirect_back_or_default("products.detail", product_id=product.id)


@products_bp.route("/<int:product_id>/edit", methods=["GET", "POST"])
@active_user_required
@limiter.limit("20 per hour")
def edit(product_id):
    product = _get_product_or_404(product_id)
    _ensure_product_owner_or_admin(product)

    form = ProductForm()
    if form.validate_on_submit():
        product.title = sanitize_text(form.title.data, 80)
        product.category = sanitize_text(form.category.data, 40)
        product.description = sanitize_text(form.description.data, 1200)
        product.price = form.price.data
        product.status = form.status.data

        if form.image.data:
            try:
                new_filename = validate_and_save_image(form.image.data)
            except ValueError as exc:
                flash(str(exc), "danger")
                return render_template(
                    "products/form.html", form=form, title="상품 수정", product=product
                )
            delete_image_file(product.image_filename)
            product.image_filename = new_filename

        db.session.commit()
        flash("상품 정보가 수정되었습니다.", "success")
        return redirect(url_for("products.detail", product_id=product.id))

    if request.method == "GET":
        form.title.data = product.title
        form.category.data = product.category
        form.description.data = product.description
        form.price.data = product.price
        form.status.data = product.status

    return render_template(
        "products/form.html", form=form, title="상품 수정", product=product
    )


@products_bp.route("/<int:product_id>/delete", methods=["POST"])
@active_user_required
def delete(product_id):
    product = _get_product_or_404(product_id)
    _ensure_product_owner_or_admin(product)
    product.is_deleted = True
    if current_user.is_admin:
        log_admin_action(
            current_user, "delete_product", "product", product.id, product.title
        )
    db.session.commit()
    flash("상품이 삭제 처리되었습니다.", "success")
    return redirect(url_for("products.my_products"))
