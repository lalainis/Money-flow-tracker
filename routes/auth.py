import uuid
from datetime import UTC, datetime, timedelta

from flask import Blueprint, jsonify, request
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash, generate_password_hash

from app_core import db, limiter
from models import AuthToken, Member
from settings import (
    AUTH_INIT_RATE_IP,
    AUTH_INIT_RATE_PHONE,
    AUTH_LOCKOUT_MINUTES,
    AUTH_LOGIN_RATE_IP,
    AUTH_LOGIN_RATE_PHONE,
    AUTH_MAX_FAILED_ATTEMPTS,
    AUTH_SETUP_PIN_RATE_IP,
    AUTH_SETUP_PIN_RATE_PHONE,
    AUTH_TOKEN_TTL_HOURS,
)
from settings import AUTH_COOKIE_NAME, AUTH_COOKIE_SAMESITE, AUTH_COOKIE_SECURE
from services import (
    get_period_for_request,
    member_to_dict,
    normalize_role,
    period_totals,
    token_required,
    validate_phone,
    validate_pin,
)

auth_bp = Blueprint("auth", __name__)


def _phone_or_ip_key():
    data = request.get_json(silent=True) or {}
    phone = str(data.get("phone") or "").strip()
    ip = get_remote_address()
    return f"{ip}:{phone or 'no-phone'}"


@auth_bp.route("/api/auth/init", methods=["POST"])
@limiter.limit(AUTH_INIT_RATE_IP)
@limiter.limit(AUTH_INIT_RATE_PHONE, key_func=_phone_or_ip_key)
def auth_init():
    data = request.get_json() or {}
    phone = (data.get("phone") or "").strip()

    if not validate_phone(phone):
        return jsonify({"error": "Phone number must contain 8 digits"}), 400

    user = Member.query.filter_by(phone=phone).first()
    if not user or normalize_role(user.role) in {"admin", "member"}:
        return jsonify({"needs_pin_setup": False})

    return jsonify({"needs_pin_setup": user.pin_hash is None})


@auth_bp.route("/api/auth/setup-pin", methods=["POST"])
@limiter.limit(AUTH_SETUP_PIN_RATE_IP)
@limiter.limit(AUTH_SETUP_PIN_RATE_PHONE, key_func=_phone_or_ip_key)
def setup_pin():
    data = request.get_json() or {}
    phone = (data.get("phone") or "").strip()
    pin = (data.get("pin") or "").strip()
    pin_confirm = (data.get("pin_confirm") or "").strip()

    if not validate_phone(phone):
        return jsonify({"error": "Phone number must contain 8 digits"}), 400
    if not validate_pin(pin):
        return jsonify({"error": "PIN must contain 4 digits"}), 400
    if pin != pin_confirm:
        return jsonify({"error": "PIN values do not match"}), 400

    user = Member.query.filter_by(phone=phone).first()
    if not user or normalize_role(user.role) == "member":
        return jsonify({"error": "Unable to set PIN for this account"}), 400
    if user.pin_hash:
        return jsonify({"error": "Unable to set PIN for this account"}), 400

    user.pin_hash = generate_password_hash(pin)
    db.session.commit()
    return jsonify({"message": "PIN saved successfully"})


@auth_bp.route("/api/auth/login", methods=["POST"])
@limiter.limit(AUTH_LOGIN_RATE_IP)
@limiter.limit(AUTH_LOGIN_RATE_PHONE, key_func=_phone_or_ip_key)
def login():
    data = request.get_json() or {}
    phone = (data.get("phone") or "").strip()
    pin = (data.get("pin") or "").strip()

    if not validate_phone(phone):
        return jsonify({"error": "Phone number must contain 8 digits"}), 400

    user = Member.query.filter_by(phone=phone).first()
    if not user or normalize_role(user.role) == "member":
        return jsonify({"error": "Invalid phone number or PIN"}), 401

    now = datetime.now(UTC)
    if user.login_locked_until:
        locked_until = user.login_locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=UTC)
        if locked_until > now:
            return jsonify({"error": "Account temporarily locked after multiple failed attempts"}), 429
        user.login_locked_until = None

    if not user.pin_hash:
        return jsonify({"error": "Invalid phone number or PIN"}), 401
    if not validate_pin(pin) or not check_password_hash(user.pin_hash, pin):
        user.failed_login_attempts = int(user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= AUTH_MAX_FAILED_ATTEMPTS:
            user.failed_login_attempts = 0
            user.login_locked_until = now + timedelta(minutes=AUTH_LOCKOUT_MINUTES)
            db.session.commit()
            return jsonify({"error": "Account temporarily locked after multiple failed attempts"}), 429
        db.session.commit()
        return jsonify({"error": "Invalid phone number or PIN"}), 401

    user.failed_login_attempts = 0
    user.login_locked_until = None

    token = str(uuid.uuid4())
    db.session.add(
        AuthToken(
            token=token,
            member_id=user.id,
            expires_at=now + timedelta(hours=AUTH_TOKEN_TTL_HOURS),
        )
    )
    db.session.commit()

    response = jsonify(
        {
            "token": token,
            "user": member_to_dict(user),
        }
    )
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=int(timedelta(hours=AUTH_TOKEN_TTL_HOURS).total_seconds()),
        httponly=True,
        secure=AUTH_COOKIE_SECURE,
        samesite=AUTH_COOKIE_SAMESITE,
        path="/",
    )
    return response


@auth_bp.route("/api/auth/logout", methods=["POST"])
@token_required()
def logout():
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "").strip() or request.cookies.get(AUTH_COOKIE_NAME, "").strip()
    AuthToken.query.filter_by(token=token).delete()
    db.session.commit()
    response = jsonify({"message": "Logged out successfully"})
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")
    return response


@auth_bp.route("/api/dashboard")
@token_required()
def dashboard():
    period = get_period_for_request()
    totals = period_totals(period)

    return jsonify(
        {
            "period": {
                "season_label": period.season_label,
                "start_date": period.start_date.isoformat(),
                "end_date": period.end_date.isoformat(),
                "carry_over": float(period.carry_over),
            },
            "totals": totals,
        }
    )
