import uuid
from datetime import UTC, datetime, timedelta

from flask import Blueprint, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from app_core import db
from models import AuthToken, Member
from settings import AUTH_LOCKOUT_MINUTES, AUTH_MAX_FAILED_ATTEMPTS, AUTH_TOKEN_TTL_HOURS
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


@auth_bp.route("/api/auth/init", methods=["POST"])
def auth_init():
    data = request.get_json() or {}
    phone = (data.get("phone") or "").strip()

    if not validate_phone(phone):
        return jsonify({"error": "Telefona Nr. jābūt ar 8 cipariem"}), 400

    user = Member.query.filter_by(phone=phone).first()
    if not user:
        return jsonify({"error": "Jūs neesat biedrs"}), 404
    if normalize_role(user.role) == "admin":
        return jsonify({"error": "Jūs neesat biedrs"}), 404
    if normalize_role(user.role) == "member":
        return jsonify({"error": "Jums nav tiesību ienākt."}), 403

    return jsonify({"needs_pin_setup": user.pin_hash is None})


@auth_bp.route("/api/auth/setup-pin", methods=["POST"])
def setup_pin():
    data = request.get_json() or {}
    phone = (data.get("phone") or "").strip()
    pin = (data.get("pin") or "").strip()
    pin_confirm = (data.get("pin_confirm") or "").strip()

    if not validate_phone(phone):
        return jsonify({"error": "Telefona Nr. jābūt ar 8 cipariem"}), 400
    if not validate_pin(pin):
        return jsonify({"error": "PIN kodam jābūt ar 4 cipariem"}), 400
    if pin != pin_confirm:
        return jsonify({"error": "PIN kodi nesakrīt"}), 400

    user = Member.query.filter_by(phone=phone).first()
    if not user:
        return jsonify({"error": "Jūs neesat biedrs"}), 404
    if normalize_role(user.role) == "member":
        return jsonify({"error": "Jums nav tiesību ienākt."}), 403
    if user.pin_hash:
        return jsonify({"error": "PIN kods jau ir uzstādīts"}), 409

    user.pin_hash = generate_password_hash(pin)
    db.session.commit()
    return jsonify({"message": "PIN kods veiksmīgi saglabāts"})


@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    phone = (data.get("phone") or "").strip()
    pin = (data.get("pin") or "").strip()

    if not validate_phone(phone):
        return jsonify({"error": "Telefona Nr. jābūt ar 8 cipariem"}), 400

    user = Member.query.filter_by(phone=phone).first()
    if not user:
        return jsonify({"error": "Jūs neesat biedrs"}), 404
    if normalize_role(user.role) == "member":
        return jsonify({"error": "Jums nav tiesību ienākt."}), 403

    now = datetime.now(UTC)
    if user.login_locked_until:
        locked_until = user.login_locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=UTC)
        if locked_until > now:
            return jsonify({"error": "Konts īslaicīgi bloķēts pēc vairākiem neveiksmīgiem mēģinājumiem"}), 429
        user.login_locked_until = None

    if not user.pin_hash:
        return jsonify({"error": "Lūdzu vispirms uzstādiet PIN kodu"}), 409
    if not validate_pin(pin) or not check_password_hash(user.pin_hash, pin):
        user.failed_login_attempts = int(user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= AUTH_MAX_FAILED_ATTEMPTS:
            user.failed_login_attempts = 0
            user.login_locked_until = now + timedelta(minutes=AUTH_LOCKOUT_MINUTES)
            db.session.commit()
            return jsonify({"error": "Konts īslaicīgi bloķēts pēc vairākiem neveiksmīgiem mēģinājumiem"}), 429
        db.session.commit()
        return jsonify({"error": "Nepareizs PIN kods"}), 401

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

    return jsonify(
        {
            "token": token,
            "user": member_to_dict(user),
        }
    )


@auth_bp.route("/api/auth/logout", methods=["POST"])
@token_required()
def logout():
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "").strip()
    AuthToken.query.filter_by(token=token).delete()
    db.session.commit()
    return jsonify({"message": "Izrakstīšanās izdevusies"})


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
