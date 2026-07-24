from datetime import timedelta

from flask import current_app, request
from flask_login import current_user
from flask_socketio import emit, join_room

from .extensions import db
from .models import Message, User, conversation_key, utcnow
from .utils import mark_direct_messages_read, sanitize_text


HANDLERS_REGISTERED = False


def _serialize_message(message):
    return {
        "id": message.id,
        "sender_id": message.sender_id,
        "recipient_id": message.recipient_id,
        "sender_name": message.sender.display_name,
        "sender_username": message.sender.username,
        "room_type": message.room_type,
        "thread_key": message.thread_key,
        "body": message.body,
        "is_read": bool(message.is_read),
        "read_at": (
            message.read_at.strftime("%Y-%m-%d %H:%M:%S") if message.read_at else None
        ),
        "created_at": message.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _serialize_read_event(thread_key, reader_id, unread_messages, read_at):
    if not unread_messages or not read_at:
        return None
    return {
        "thread_key": thread_key,
        "reader_id": reader_id,
        "message_ids": [message.id for message in unread_messages],
        "read_at": read_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _chat_rate_limited(user_id):
    cutoff = utcnow() - timedelta(seconds=current_app.config["CHAT_WINDOW_SECONDS"])
    recent_count = Message.query.filter(
        Message.sender_id == user_id,
        Message.created_at >= cutoff,
    ).count()
    return recent_count >= current_app.config["CHAT_WINDOW_LIMIT"]


def _validate_active_user():
    if not current_user.is_authenticated:
        emit("chat_error", {"message": "로그인 후 채팅을 사용할 수 있습니다."})
        return False
    if current_user.is_deleted:
        emit("chat_error", {"message": "탈퇴 처리된 계정은 채팅을 사용할 수 없습니다."})
        return False
    if current_user.is_suspended:
        emit("chat_error", {"message": "정지된 계정은 채팅을 사용할 수 없습니다."})
        return False
    return True


def _origin_allowed():
    allowed_origins = current_app.config.get("SOCKETIO_CORS_ALLOWED_ORIGINS", [])
    request_origin = request.headers.get("Origin")
    if not allowed_origins or not request_origin:
        return True
    return request_origin in allowed_origins


def _parse_direct_room(room):
    if not room.startswith("dm:"):
        return None
    try:
        _, left_id, right_id = room.split(":")
        return {int(left_id), int(right_id)}
    except ValueError:
        return None


def register_socket_handlers(socketio):
    global HANDLERS_REGISTERED

    if HANDLERS_REGISTERED:
        return
    HANDLERS_REGISTERED = True

    @socketio.on("connect")
    def handle_connect():
        if not current_user.is_authenticated:
            return False
        if current_user.is_deleted or current_user.is_suspended:
            return False
        if not _origin_allowed():
            return False

    @socketio.on("join_room")
    def handle_join_room(data):
        if not _validate_active_user():
            return

        room = (data or {}).get("room", "")
        if room == "global":
            join_room("global")
            return

        participant_ids = _parse_direct_room(room)
        if not participant_ids:
            emit("chat_error", {"message": "잘못된 채팅방 정보입니다."})
            return
        if current_user.id not in participant_ids:
            emit("chat_error", {"message": "해당 개인 채팅방에 접근할 수 없습니다."})
            return

        join_room(room)
        unread_messages, read_at = mark_direct_messages_read(room, current_user.id)
        read_event = _serialize_read_event(
            room, current_user.id, unread_messages, read_at
        )
        if read_event:
            emit("messages_read", read_event, room=room)

    @socketio.on("mark_direct_read")
    def handle_mark_direct_read(data):
        if not _validate_active_user():
            return

        room = (data or {}).get("room", "")
        participant_ids = _parse_direct_room(room)
        if not participant_ids:
            emit("chat_error", {"message": "잘못된 채팅방 정보입니다."})
            return
        if current_user.id not in participant_ids:
            emit("chat_error", {"message": "해당 개인 채팅방에 접근할 수 없습니다."})
            return

        unread_messages, read_at = mark_direct_messages_read(room, current_user.id)
        read_event = _serialize_read_event(
            room, current_user.id, unread_messages, read_at
        )
        if read_event:
            emit("messages_read", read_event, room=room)

    @socketio.on("send_global_message")
    def handle_global_message(data):
        if not _validate_active_user():
            return
        if _chat_rate_limited(current_user.id):
            emit(
                "chat_error",
                {
                    "message": "너무 빠르게 메시지를 보내고 있습니다. 잠시 후 다시 시도하세요."
                },
            )
            return

        body = sanitize_text((data or {}).get("body", ""), 400)
        if not body:
            emit("chat_error", {"message": "메시지를 입력하세요."})
            return

        message = Message()
        message.sender_id = current_user.id
        message.room_type = "global"
        message.thread_key = "global"
        message.body = body
        message.is_read = True
        message.read_at = utcnow()
        db.session.add(message)
        db.session.commit()
        emit("new_message", _serialize_message(message), room="global")

    @socketio.on("send_direct_message")
    def handle_direct_message(data):
        if not _validate_active_user():
            return
        if _chat_rate_limited(current_user.id):
            emit(
                "chat_error",
                {
                    "message": "너무 빠르게 메시지를 보내고 있습니다. 잠시 후 다시 시도하세요."
                },
            )
            return

        body = sanitize_text((data or {}).get("body", ""), 400)
        recipient_id = (data or {}).get("recipient_id")
        if not body:
            emit("chat_error", {"message": "메시지를 입력하세요."})
            return

        try:
            recipient_id = int(recipient_id)
        except (TypeError, ValueError):
            emit("chat_error", {"message": "상대방 정보를 확인할 수 없습니다."})
            return

        recipient = db.session.get(User, recipient_id)
        if not recipient or recipient.is_deleted or recipient.id == current_user.id:
            emit("chat_error", {"message": "유효하지 않은 상대방입니다."})
            return
        if recipient.is_suspended:
            emit(
                "chat_error",
                {"message": "정지된 계정에게는 메시지를 보낼 수 없습니다."},
            )
            return

        room = conversation_key(current_user.id, recipient.id)
        message = Message()
        message.sender_id = current_user.id
        message.recipient_id = recipient.id
        message.room_type = "direct"
        message.thread_key = room
        message.body = body
        db.session.add(message)
        db.session.commit()
        emit("new_message", _serialize_message(message), room=room)
