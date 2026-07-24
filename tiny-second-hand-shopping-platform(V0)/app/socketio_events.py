from flask_login import current_user
from flask_socketio import emit, join_room

from .extensions import db
from .models import Message, User, conversation_key, utcnow
from .utils import sanitize_text


HANDLERS_REGISTERED = False


def _serialize_message(message):
    return {
        "id": message.id,
        "sender_id": message.sender_id,
        "sender_name": message.sender.display_name,
        "sender_username": message.sender.username,
        "room_type": message.room_type,
        "body": message.body,
        "created_at": message.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _chat_rate_limited(user_id):
    return False


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
    return True


def register_socket_handlers(socketio):
    global HANDLERS_REGISTERED

    if HANDLERS_REGISTERED:
        return
    HANDLERS_REGISTERED = True

    @socketio.on("connect")
    def handle_connect():
        if not current_user.is_authenticated:
            return False
        if current_user.is_deleted:
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

        if not room.startswith("dm:"):
            emit("chat_error", {"message": "잘못된 채팅방 정보입니다."})
            return

        join_room(room)

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

        message = Message(
            sender_id=current_user.id,
            room_type="global",
            thread_key="global",
            body=body,
        )
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
        message = Message(
            sender_id=current_user.id,
            recipient_id=recipient.id,
            room_type="direct",
            thread_key=room,
            body=body,
        )
        db.session.add(message)
        db.session.commit()
        emit("new_message", _serialize_message(message), room=room)
