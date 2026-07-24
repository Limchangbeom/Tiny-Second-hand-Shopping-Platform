from flask import Blueprint, abort, render_template
from flask_login import current_user
from sqlalchemy import func, or_

from ..extensions import db, socketio
from ..models import Message, User, conversation_key
from ..utils import active_user_required, mark_direct_messages_read


chat_bp = Blueprint("chat", __name__, url_prefix="/chat")


def _emit_read_receipts(thread_key, reader_id, unread_messages, read_at):
    if not unread_messages or not read_at:
        return
    socketio.emit(
        "messages_read",
        {
            "thread_key": thread_key,
            "reader_id": reader_id,
            "message_ids": [message.id for message in unread_messages],
            "read_at": read_at.strftime("%Y-%m-%d %H:%M:%S"),
        },
        room=thread_key,
    )


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
    unread_rows = (
        db.session.query(Message.thread_key, func.count(Message.id))
        .filter(
            Message.room_type == "direct",
            Message.recipient_id == current_user.id,
            Message.is_removed.is_(False),
            Message.is_read.is_(False),
        )
        .group_by(Message.thread_key)
        .all()
    )
    unread_map = {thread_key: count for thread_key, count in unread_rows}
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
            thread_map[other_user.id] = {
                "user": other_user,
                "last_message": message,
                "unread_count": unread_map.get(message.thread_key, 0),
                "is_last_from_me": message.sender_id == current_user.id,
            }

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
    unread_messages, read_at = mark_direct_messages_read(thread_key, current_user.id)
    _emit_read_receipts(thread_key, current_user.id, unread_messages, read_at)

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
