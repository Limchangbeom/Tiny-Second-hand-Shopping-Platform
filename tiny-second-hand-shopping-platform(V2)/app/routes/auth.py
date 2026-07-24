from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func

from ..extensions import db, limiter
from ..forms import LoginForm, RegistrationForm
from ..models import User
from ..utils import is_safe_next_url, sanitize_text


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = RegistrationForm()
    if form.validate_on_submit():
        username = form.username.data.strip().lower()
        existing_user = User.query.filter(func.lower(User.username) == username).first()
        if existing_user:
            flash("이미 사용 중인 아이디입니다.", "danger")
        else:
            user = User(
                username=username,
                display_name=sanitize_text(form.display_name.data, 60),
                bio=sanitize_text(form.bio.data, 300),
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash("회원가입이 완료되었습니다. 로그인해주세요.", "success")
            return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data.strip().lower()
        user = User.query.filter(func.lower(User.username) == username).first()
        if not user or not user.check_password(form.password.data):
            flash("아이디 또는 비밀번호가 올바르지 않습니다.", "danger")
        elif user.is_deleted:
            flash(
                "탈퇴 처리된 계정입니다. 동일 계정으로는 로그인할 수 없습니다.",
                "danger",
            )
        elif user.is_suspended:
            flash("정지된 계정입니다. 관리자에게 문의하세요.", "danger")
        else:
            session.clear()
            login_user(user, remember=False)
            next_url = request.args.get("next")
            if next_url and is_safe_next_url(next_url):
                return redirect(next_url)
            return redirect(url_for("main.index"))

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("로그아웃되었습니다.", "success")
    return redirect(url_for("main.index"))
