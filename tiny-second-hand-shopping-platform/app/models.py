from datetime import datetime
from decimal import Decimal

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow():
    return datetime.utcnow()


def conversation_key(user_a_id, user_b_id):
    low_id, high_id = sorted([int(user_a_id), int(user_b_id)])
    return f"dm:{low_id}:{high_id}"


class User(db.Model, UserMixin):
    __table_args__ = (
        db.CheckConstraint("balance >= 0", name="ck_user_balance_non_negative"),
    )

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(60), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    bio = db.Column(db.String(300), nullable=False, default="")
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    is_suspended = db.Column(db.Boolean, nullable=False, default=False)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    balance = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("100000.00"))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    products = db.relationship("Product", back_populates="seller", lazy="dynamic")
    reports_sent = db.relationship(
        "Report",
        foreign_keys="Report.reporter_id",
        back_populates="reporter",
        lazy="dynamic",
    )
    reports_received = db.relationship(
        "Report",
        foreign_keys="Report.target_user_id",
        back_populates="target_user",
        lazy="dynamic",
    )
    reports_reviewed = db.relationship(
        "Report",
        foreign_keys="Report.reviewed_by_id",
        back_populates="reviewed_by",
        lazy="dynamic",
    )
    messages_sent = db.relationship(
        "Message",
        foreign_keys="Message.sender_id",
        back_populates="sender",
        lazy="dynamic",
    )
    messages_received = db.relationship(
        "Message",
        foreign_keys="Message.recipient_id",
        back_populates="recipient",
        lazy="dynamic",
    )
    transfers_sent = db.relationship(
        "Transfer",
        foreign_keys="Transfer.sender_id",
        back_populates="sender",
        lazy="dynamic",
    )
    transfers_received = db.relationship(
        "Transfer",
        foreign_keys="Transfer.recipient_id",
        back_populates="recipient",
        lazy="dynamic",
    )
    admin_actions = db.relationship(
        "AdminActionLog",
        foreign_keys="AdminActionLog.admin_id",
        back_populates="admin",
        lazy="dynamic",
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username}>"


class Product(db.Model):
    __table_args__ = (
        db.CheckConstraint("price >= 0", name="ck_product_price_non_negative"),
        db.CheckConstraint(
            "status in ('available', 'reserved', 'sold')",
            name="ck_product_status_valid",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    title = db.Column(db.String(80), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(40), nullable=False, default="general")
    price = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="available")
    image_filename = db.Column(db.String(255), nullable=True)
    is_blocked = db.Column(db.Boolean, nullable=False, default=False)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    seller = db.relationship("User", back_populates="products")
    reports = db.relationship("Report", back_populates="target_product", lazy="dynamic")

    def __repr__(self):
        return f"<Product {self.title}>"


class Report(db.Model):
    __table_args__ = (
        db.CheckConstraint(
            "target_type in ('user', 'product')",
            name="ck_report_target_type_valid",
        ),
        db.CheckConstraint(
            "status in ('open', 'resolved')",
            name="ck_report_status_valid",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    target_type = db.Column(db.String(10), nullable=False)
    target_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    target_product_id = db.Column(
        db.Integer, db.ForeignKey("product.id"), nullable=True
    )
    reason = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="open")
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)

    reporter = db.relationship(
        "User", foreign_keys=[reporter_id], back_populates="reports_sent"
    )
    target_user = db.relationship(
        "User",
        foreign_keys=[target_user_id],
        back_populates="reports_received",
    )
    target_product = db.relationship("Product", back_populates="reports")
    reviewed_by = db.relationship(
        "User",
        foreign_keys=[reviewed_by_id],
        back_populates="reports_reviewed",
    )


class Message(db.Model):
    __table_args__ = (
        db.CheckConstraint(
            "room_type in ('global', 'direct')",
            name="ck_message_room_type_valid",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    recipient_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=True, index=True
    )
    room_type = db.Column(db.String(20), nullable=False)
    thread_key = db.Column(db.String(50), nullable=False, index=True)
    body = db.Column(db.String(400), nullable=False)
    is_removed = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    sender = db.relationship(
        "User", foreign_keys=[sender_id], back_populates="messages_sent"
    )
    recipient = db.relationship(
        "User", foreign_keys=[recipient_id], back_populates="messages_received"
    )


class Transfer(db.Model):
    __table_args__ = (
        db.CheckConstraint("amount > 0", name="ck_transfer_amount_positive"),
    )

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    note = db.Column(db.String(160), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    sender = db.relationship(
        "User", foreign_keys=[sender_id], back_populates="transfers_sent"
    )
    recipient = db.relationship(
        "User",
        foreign_keys=[recipient_id],
        back_populates="transfers_received",
    )


class AdminActionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    action_type = db.Column(db.String(50), nullable=False)
    target_type = db.Column(db.String(20), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    details = db.Column(db.String(300), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    admin = db.relationship(
        "User", foreign_keys=[admin_id], back_populates="admin_actions"
    )
