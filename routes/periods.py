from datetime import date

from flask import Blueprint, jsonify, request

from app_core import db
from models import Member, Period
from services import (
    calculate_membership_fee_for_period,
    current_period,
    get_or_create_period_lock,
    normalize_role,
    set_membership_fee_for_season,
    to_decimal,
    token_required,
)

periods_bp = Blueprint("periods", __name__)


@periods_bp.route("/api/periods/available")
@token_required()
def available_periods():
    periods = Period.query.order_by(Period.start_date.desc()).all()
    if not periods:
        periods = [current_period()]

    unique = []
    seen = set()
    for period in periods:
        if period.season_label in seen:
            continue
        seen.add(period.season_label)
        unique.append(
            {
                "season_label": period.season_label,
                "start_date": period.start_date.isoformat(),
                "end_date": period.end_date.isoformat(),
                "active": bool(period.active),
            }
        )

    return jsonify({"periods": unique})


@periods_bp.route("/api/period", methods=["POST"])
@token_required({"board", "admin"})
def update_period():
    data = request.get_json() or {}
    season_label = (data.get("season_label") or "").strip()
    try:
        default_membership_fee = to_decimal(data.get("default_membership_fee", 0) or 0)
        carry_over = to_decimal(data.get("carry_over", 0) or 0)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    current_user_role = normalize_role(request.current_user.role)
    active_period = Period.query.filter_by(active=True).first()
    is_new_season = active_period is None or active_period.season_label != season_label

    period_lock = get_or_create_period_lock(season_label)
    if current_user_role == "board" and period_lock.membership_fee_locked:
        return jsonify({"error": "In this period, membership fee can be changed only by admin after first save"}), 403
    if current_user_role == "board" and period_lock.carry_over_locked:
        return jsonify({"error": "In this period, carry over can be changed only by admin after first save"}), 403

    if len(season_label) != 9 or "/" not in season_label:
        return jsonify({"error": "Season format must be yyyy/yyyy"}), 400

    try:
        start_year = int(season_label[:4])
        end_year = int(season_label[5:])
    except ValueError:
        return jsonify({"error": "Season format must be yyyy/yyyy"}), 400
    if end_year != start_year + 1:
        return jsonify({"error": "Season years do not match yyyy/yyyy format"}), 400

    if is_new_season:
        Period.query.update({"active": False})
        period = Period(
            season_label=season_label,
            start_date=date(start_year, 4, 1),
            end_date=date(end_year, 3, 31),
            carry_over=0,
            active=True,
        )
        db.session.add(period)
    else:
        period = active_period
        period.start_date = date(start_year, 4, 1)
        period.end_date = date(end_year, 3, 31)
        period.active = True
    period.carry_over = carry_over

    members = Member.query.all()

    if default_membership_fee > 0:
        for member in members:
            fee_value = calculate_membership_fee_for_period(member, default_membership_fee)
            set_membership_fee_for_season(member, season_label, fee_value)
            member.membership_fee = fee_value
            member.paid_this_period = 0

        if current_user_role == "board":
            period_lock.membership_fee_locked = True

    if current_user_role == "board":
        period_lock.carry_over_locked = True

    if is_new_season:
        for member in members:
            member.joining_fee_paid = False

    db.session.commit()
    return jsonify({"message": "Reporting period updated"})
