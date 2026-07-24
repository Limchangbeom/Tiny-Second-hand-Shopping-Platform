from flask import Blueprint, abort, render_template
from flask_login import current_user
from sqlalchemy import or_

from ..extensions import db
from ..models import Message, User, conversation_key
from ..utils import active_user_required


chat_bp = Blueprint("chat", __name__, url_prefix="/chat")


@chat_bp.route("/")
@active_user_required
def hub():
    available_users = (
        User.query.filter(
            User.id != current_user.id,
            User.is_deleted.is_(False),
            User.is_suspended.is_(False),
        )
        .order_by(User.is_admin.desc(), User.display_name.asc())
        .all()
    )
    recent_direct_messages = (
        Message.query.filter(
            Message.room_type == "direct",
            or_(
                Message.sender_id == current_user.id,
                Message.recipient_id == current_user.id,
            ),
            Message.is_removed.is_(False),
        )
        .order_by(Message.created_at.desc())
        .all()
    )

    thread_map = {}
    for message in recent_direct_messages:
        other_user = (
            message.recipient
            if message.sender_id == current_user.id
            else message.sender
        )
        if other_user and not other_user.is_deleted and other_user.id not in thread_map:
            thread_map[other_user.id] = {"user": other_user, "last_message": message}

    threads = list(thread_map.values())
    return render_template("chat/hub.html", users=available_users, threads=threads)


@chat_bp.route("/global")
@active_user_required
def global_chat():
    messages = (
        Message.query.filter_by(room_type="global", is_removed=False)
        .order_by(Message.created_at.desc())
        .limit(80)
        .all()
    )
    messages.reverse()
    return render_template("chat/global.html", messages=messages)


@chat_bp.route("/direct/<int:user_id>")
@active_user_required
def direct_chat(user_id):
    if user_id == current_user.id:
        abort(404)

    other_user = db.session.get(User, user_id)
    if not other_user or other_user.is_deleted:
        abort(404)

    thread_key = conversation_key(current_user.id, other_user.id)
    messages = (
        Message.query.filter_by(
            room_type="direct", thread_key=thread_key, is_removed=False
        )
        .order_by(Message.created_at.desc())
        .limit(100)
        .all()
    )
    messages.reverse()
    return render_template(
        "chat/direct.html",
        messages=messages,
        other_user=other_user,
        thread_key=thread_key,
    )
