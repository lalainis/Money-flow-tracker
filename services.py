import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import jsonify, request
from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash

from app_core import db
from models import AuthToken, Expense, Income, Member, MemberSeasonFee, MemberStatus, Period, PeriodLock, AuditLog
from settings import ALLOWED_ATTACHMENT_EXTENSIONS, AUTH_COOKIE_NAME, AUTH_TOKEN_TTL_HOURS, ROLES


def to_decimal(value):
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Invalid numeric value") from exc


def current_period():
    period = Period.query.filter_by(active=True).first()
    if period:
        return period

    today = date.today()
    year = today.year if today.month >= 4 else today.year - 1
    period = Period(
        season_label=f"{year}/{year + 1}",
        start_date=date(year, 4, 1),
        end_date=date(year + 1, 3, 31),
        carry_over=0,
        active=True,
    )
    db.session.add(period)
    db.session.commit()
    return period


def get_or_create_period_lock(season_label):
    period_lock = PeriodLock.query.filter_by(season_label=season_label).first()
    if period_lock:
        return period_lock

    period_lock = PeriodLock(season_label=season_label)
    db.session.add(period_lock)
    db.session.flush()
    return period_lock


def get_period_for_request():
    season_label = (request.args.get("season_label") or "").strip()
    if season_label:
        period = Period.query.filter_by(season_label=season_label).order_by(Period.id.desc()).first()
        if period:
            return period
    return current_period()


def period_totals(period):
    income_sum = (
        db.session.query(db.func.coalesce(db.func.sum(Income.amount), 0))
        .filter(
            Income.entry_date >= period.start_date,
            Income.entry_date <= period.end_date,
        )
        .scalar()
    )
    expense_sum = (
        db.session.query(db.func.coalesce(db.func.sum(Expense.amount), 0))
        .filter(
            Expense.entry_date >= period.start_date,
            Expense.entry_date <= period.end_date,
        )
        .scalar()
    )

    income_total = to_decimal(income_sum) + to_decimal(period.carry_over)
    expense_total = to_decimal(expense_sum)
    diff = income_total - expense_total

    return {
        "income_total": float(income_total),
        "expense_total": float(expense_total),
        "difference": float(diff),
        "balance": float(diff) if diff >= 0 else 0.0,
        "deficit": float(diff) if diff < 0 else 0.0,
    }


def normalize_role(raw_role):
    role = str(raw_role or "").strip().lower()
    aliases = {
        "kasieris": "cashier",
        "cashier": "cashier",
        "valde": "board",
        "board": "board",
        "revizors": "auditor",
        "auditors": "auditor",
        "auditor": "auditor",
        "admins": "admin",
        "admin": "admin",
        "biedrs": "member",
        "member": "member",
    }
    return aliases.get(role, role)


def member_to_dict(member, paid_this_period_override=None, membership_fee_override=None):
    normalized_role = normalize_role(member.role)
    paid_this_period = (
        float(paid_this_period_override) if paid_this_period_override is not None else float(member.paid_this_period)
    )
    membership_fee = (
        float(membership_fee_override) if membership_fee_override is not None else float(member.membership_fee)
    )
    return {
        "id": member.id,
        "list_no": member.list_no,
        "first_name": member.first_name,
        "last_name": member.last_name,
        "phone": member.phone,
        "status": member.status,
        "membership_fee": membership_fee,
        "paid_this_period": paid_this_period,
        "joining_fee_paid": bool(member.joining_fee_paid),
        "role": normalized_role,
        "has_pin": member.pin_hash is not None,
    }


def is_admin_member(member):
    return normalize_role(member.role) == "admin"


def get_member_season_fee(member_id, season_label):
    return MemberSeasonFee.query.filter_by(member_id=member_id, season_label=season_label).first()


def get_effective_membership_fee(member, season_label):
    if season_label:
        fee_row = get_member_season_fee(member.id, season_label)
        if fee_row:
            return to_decimal(fee_row.membership_fee)
    return to_decimal(member.membership_fee)


def set_membership_fee_for_season(member, season_label, membership_fee):
    fee_value = to_decimal(membership_fee)
    fee_row = get_member_season_fee(member.id, season_label)
    if fee_row:
        fee_row.membership_fee = fee_value
    else:
        db.session.add(
            MemberSeasonFee(
                member_id=member.id,
                season_label=season_label,
                membership_fee=fee_value,
            )
        )
    return fee_value


def token_required(allowed_roles=None):
    allowed_roles = allowed_roles or ROLES

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            auth = request.headers.get("Authorization", "")
            token = auth.replace("Bearer ", "").strip() or request.cookies.get(AUTH_COOKIE_NAME, "").strip()
            session_token = AuthToken.query.filter_by(token=token).first()
            if session_token and session_token.expires_at:
                expires_at = session_token.expires_at
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
                if expires_at <= datetime.now(UTC):
                    db.session.delete(session_token)
                    db.session.commit()
                    session_token = None

            user_id = session_token.member_id if session_token else None
            if not user_id:
                return jsonify({"error": "Authorization is required"}), 401

            user = db.session.get(Member, user_id)
            if not user:
                return jsonify({"error": "User not found"}), 401

            user_role = normalize_role(user.role)
            if user_role not in allowed_roles:
                return jsonify({"error": "Insufficient permissions"}), 403

            request.current_user = user
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def validate_phone(phone):
    return phone.isdigit() and len(phone) == 8


def validate_pin(pin):
    return pin.isdigit() and len(pin) == 4


def is_allowed_attachment(filename):
    extension = filename.rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
    return bool(extension) and extension in ALLOWED_ATTACHMENT_EXTENSIONS


def parse_entry_date(raw_value):
    try:
        return datetime.strptime(raw_value or date.today().isoformat(), "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid date format. Use YYYY-MM-DD") from exc


def to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "ja"}
    return bool(value)


def localize_income_type(raw_type):
    value = (raw_type or "").strip().lower()
    mapping = {
        "member_fee": "Membership fee",
        "membership_fee": "Membership fee",
        "biedra nauda": "Membership fee",
        "neplānots ienākums": "Other income",
        "neplanots ienakums": "Other income",
        "other_income": "Other income",
    }
    return mapping.get(value, raw_type)


def normalize_member_status(raw_status):
    status = str(raw_status or "").strip()
    aliases = {
        "Biedrs": "Member",
        "Kandidāts": "Candidate",
        "Kandidats": "Candidate",
        "Vecbiedrs 2/3": "Senior 2/3",
        "Vecbiedrs 1/2": "Senior 1/2",
    }
    return aliases.get(status, status)


def normalize_expense_category(raw_category):
    category = str(raw_category or "").strip()
    aliases = {
        "Saimnieciskie izdevumi": "Operating expenses",
        "Būvmateriāli": "Construction materials",
        "Buvmateriali": "Construction materials",
        "Piebarošana": "Feed",
        "Piebarosana": "Feed",
        "Nodokļi": "Taxes",
        "Nodokli": "Taxes",
        "Licences": "Licenses",
        "Platību maksājumi": "Land payments",
        "Platibu maksajumi": "Land payments",
        "Internets": "Internet",
        "Elektrība": "Electricity",
        "Elektriba": "Electricity",
        "Apdrošināšana": "Insurance",
        "Apdrosinasana": "Insurance",
        "Pļaušanas izdevumi": "Mowing expenses",
        "Plausanas izdevumi": "Mowing expenses",
        "Bebru uzraudzības izdevumi": "Beaver monitoring expenses",
        "Bebru uzraudzibas izdevumi": "Beaver monitoring expenses",
        "LMS biedru maksa": "LMS membership fee",
        "Bankas komisijas maksa": "Bank commission fee",
        "Citi": "Other",
    }
    return aliases.get(category, category)


def calculate_membership_fee_for_period(member, base_fee):
    status = (member.status or "").strip().lower()
    status_aliases = {
        "biedrs": "member",
        "kandidāts": "candidate",
        "kandidats": "candidate",
        "vecbiedrs 2/3": "senior 2/3",
        "vecbiedrs 1/2": "senior 1/2",
    }
    status = status_aliases.get(status, status)
    base = to_decimal(base_fee)
    fee = base

    if status == "vip":
        fee = Decimal("0.00")
    elif status == "senior 2/3":
        fee = (base * Decimal("2") / Decimal("3")).quantize(Decimal("0.01"))
    elif status == "senior 1/2":
        fee = (base / Decimal("2")).quantize(Decimal("0.01"))

    if to_bool(member.joining_fee_paid):
        fee += (base * Decimal("2")).quantize(Decimal("0.01"))

    return fee.quantize(Decimal("0.01"))


def recalculate_member_paid_this_period(member_id):
    if not member_id:
        return

    member = db.session.get(Member, member_id)
    if not member:
        return

    active_period = current_period()
    paid_total = (
        db.session.query(db.func.coalesce(db.func.sum(Income.amount), 0))
        .filter(
            Income.income_type.in_(["member_fee", "biedra nauda"]),
            Income.member_id == member.id,
            Income.entry_date >= active_period.start_date,
            Income.entry_date <= active_period.end_date,
        )
        .scalar()
    )
    member.paid_this_period = to_decimal(paid_total)


def season_label_for_date(entry_date):
    period = (
        Period.query.filter(
            Period.start_date <= entry_date,
            Period.end_date >= entry_date,
        )
        .order_by(Period.start_date.desc())
        .first()
    )
    if period:
        return period.season_label
    return current_period().season_label


def income_to_payload(income_row):
    return {
        "id": income_row.id,
        "income_type": income_row.income_type,
        "member_id": income_row.member_id,
        "amount": float(income_row.amount),
        "entry_date": income_row.entry_date.isoformat(),
        "description": income_row.description or "",
    }


def expense_to_payload(expense_row):
    return {
        "id": expense_row.id,
        "category": expense_row.category,
        "amount": float(expense_row.amount),
        "entry_date": expense_row.entry_date.isoformat(),
        "description": expense_row.description or "",
        "attachment": expense_row.attachment,
    }


def create_audit_log(action, entity_type, entity_id, season_label, old_data=None, new_data=None):
    db.session.add(
        AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            season_label=season_label,
            changed_by_member_id=request.current_user.id,
            old_data=json.dumps(old_data, ensure_ascii=False) if old_data is not None else None,
            new_data=json.dumps(new_data, ensure_ascii=False) if new_data is not None else None,
        )
    )


def resequence_members():
    members = Member.query.order_by(Member.list_no, Member.id).all()
    for index, member in enumerate(members, start=1):
        member.list_no = index


def ensure_unique_member_numbers():
    members = Member.query.order_by(Member.list_no, Member.id).all()
    changed = False
    for index, member in enumerate(members, start=1):
        if member.list_no != index:
            member.list_no = index
            changed = True
    return changed


def next_member_list_no():
    current_max = db.session.query(db.func.coalesce(db.func.max(Member.list_no), 0)).scalar()
    return int(current_max) + 1


def ensure_seed_data():
    default_statuses = ["Member", "Candidate", "VIP", "Senior 2/3", "Senior 1/2"]
    for name in default_statuses:
        if not MemberStatus.query.filter_by(name=name).first():
            db.session.add(MemberStatus(name=name))

    status_aliases = {
        "active": "Member",
        "member": "Member",
        "biedrs": "Member",
        "candidate": "Candidate",
        "kandidāts": "Candidate",
        "kandidats": "Candidate",
        "vip": "VIP",
        "vecbiedrs 2/3": "Senior 2/3",
        "vecbiedrs 1/2": "Senior 1/2",
    }
    for member in Member.query.all():
        normalized = (member.status or "").strip().lower()
        if normalized in status_aliases:
            member.status = status_aliases[normalized]

    db.session.commit()


def ensure_schema_compatibility():
    inspector = inspect(db.engine)

    if inspector.has_table("member"):
        member_columns = {column["name"] for column in inspector.get_columns("member")}
        alter_statements = []
        if "membership_fee" not in member_columns:
            alter_statements.append("ALTER TABLE member ADD COLUMN membership_fee NUMERIC(10, 2) NOT NULL DEFAULT 0")
        if "paid_this_period" not in member_columns:
            alter_statements.append("ALTER TABLE member ADD COLUMN paid_this_period NUMERIC(10, 2) NOT NULL DEFAULT 0")
        if "role" not in member_columns:
            alter_statements.append("ALTER TABLE member ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'member'")
        if "pin_hash" not in member_columns:
            alter_statements.append("ALTER TABLE member ADD COLUMN pin_hash VARCHAR(255)")
        if "failed_login_attempts" not in member_columns:
            alter_statements.append("ALTER TABLE member ADD COLUMN failed_login_attempts INTEGER NOT NULL DEFAULT 0")
        if "login_locked_until" not in member_columns:
            alter_statements.append("ALTER TABLE member ADD COLUMN login_locked_until TIMESTAMP")
        if "Iestāšanās maksa" not in member_columns:
            alter_statements.append('ALTER TABLE member ADD COLUMN "Iestāšanās maksa" BOOLEAN NOT NULL DEFAULT FALSE')

        for statement in alter_statements:
            db.session.execute(text(statement))

    if inspector.has_table("period"):
        period_columns = {column["name"] for column in inspector.get_columns("period")}
        alter_statements = []
        if "carry_over" not in period_columns:
            alter_statements.append("ALTER TABLE period ADD COLUMN carry_over NUMERIC(10, 2) NOT NULL DEFAULT 0")
        if "active" not in period_columns:
            alter_statements.append("ALTER TABLE period ADD COLUMN active BOOLEAN NOT NULL DEFAULT TRUE")

        for statement in alter_statements:
            db.session.execute(text(statement))

    if inspector.has_table("auth_token"):
        token_columns = {column["name"] for column in inspector.get_columns("auth_token")}
        if "expires_at" not in token_columns:
            db.session.execute(text("ALTER TABLE auth_token ADD COLUMN expires_at TIMESTAMP"))
            default_expiry = datetime.now(UTC) + timedelta(hours=AUTH_TOKEN_TTL_HOURS)
            db.session.execute(
                text("UPDATE auth_token SET expires_at = :expires_at WHERE expires_at IS NULL"),
                {"expires_at": default_expiry},
            )

    db.session.commit()

    if Member.query.count() == 0:
        admin = Member(
            list_no=1,
            first_name="Admin",
            last_name="Konts",
            phone="29123456",
            status="VIP",
            membership_fee=0,
            paid_this_period=0,
            role="admin",
            pin_hash=generate_password_hash("0308"),
        )
        db.session.add(admin)
        db.session.commit()

    period = current_period()

    for member in Member.query.all():
        if not get_member_season_fee(member.id, period.season_label):
            db.session.add(
                MemberSeasonFee(
                    member_id=member.id,
                    season_label=period.season_label,
                    membership_fee=to_decimal(member.membership_fee),
                )
            )
    db.session.commit()
