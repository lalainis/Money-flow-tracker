from datetime import UTC, datetime

from app_core import db


class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    list_no = db.Column(db.Integer, nullable=False)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    phone = db.Column(db.String(8), unique=True, nullable=False)
    status = db.Column(db.String(50), nullable=False, default="active")
    membership_fee = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    paid_this_period = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    joining_fee_paid = db.Column("Iestāšanās maksa", db.Boolean, nullable=False, default=False)
    role = db.Column(db.String(20), nullable=False, default="member")
    pin_hash = db.Column(db.String(255), nullable=True)
    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    login_locked_until = db.Column(db.DateTime(timezone=True), nullable=True)


class MemberStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)


class AuthToken(db.Model):
    __tablename__ = "auth_token"
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(36), unique=True, nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey("member.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)


class MemberSeasonFee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("member.id"), nullable=False)
    season_label = db.Column(db.String(9), nullable=False)
    membership_fee = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    __table_args__ = (db.UniqueConstraint("member_id", "season_label", name="uq_member_season_fee"),)


class Period(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    season_label = db.Column(db.String(9), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    carry_over = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    active = db.Column(db.Boolean, nullable=False, default=True)


class PeriodLock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    season_label = db.Column(db.String(9), unique=True, nullable=False)
    membership_fee_locked = db.Column(db.Boolean, nullable=False, default=False)
    carry_over_locked = db.Column(db.Boolean, nullable=False, default=False)


class Income(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    income_type = db.Column(db.String(20), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey("member.id"), nullable=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    entry_date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(255), nullable=True)


class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    entry_date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    attachment = db.Column(db.String(255), nullable=True)
    created_by_member_id = db.Column(db.Integer, db.ForeignKey("member.id"), nullable=True)


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(30), nullable=False)
    entity_type = db.Column(db.String(30), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    season_label = db.Column(db.String(9), nullable=False)
    changed_by_member_id = db.Column(db.Integer, db.ForeignKey("member.id"), nullable=False)
    changed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    old_data = db.Column(db.Text, nullable=True)
    new_data = db.Column(db.Text, nullable=True)
