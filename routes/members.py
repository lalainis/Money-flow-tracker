from datetime import date

from flask import Blueprint, jsonify, request

from app_core import db
from models import Income, Member, MemberSeasonFee, MemberStatus
from services import (
    current_period,
    ensure_unique_member_numbers,
    get_effective_membership_fee,
    get_period_for_request,
    is_admin_member,
    member_to_dict,
    next_member_list_no,
    normalize_member_status,
    normalize_role,
    parse_entry_date,
    recalculate_member_paid_this_period,
    resequence_members,
    set_membership_fee_for_season,
    to_bool,
    to_decimal,
    token_required,
    validate_phone,
)
from settings import ROLES

members_bp = Blueprint("members", __name__)


@members_bp.route("/api/member-statuses")
@token_required({"board", "admin"})
def member_statuses():
    statuses = MemberStatus.query.order_by(MemberStatus.id.asc()).all()
    return jsonify({"statuses": [s.name for s in statuses]})


@members_bp.route("/api/members", methods=["GET"])
@token_required({"board", "admin", "auditor", "cashier", "member"})
def list_members():
    if ensure_unique_member_numbers():
        db.session.commit()

    period = get_period_for_request()
    requester_role = normalize_role(request.current_user.role)
    members = Member.query.order_by(Member.list_no).all()
    if requester_role != "admin":
        members = [m for m in members if normalize_role(m.role) != "admin"]

    paid_rows = (
        db.session.query(
            Income.member_id,
            db.func.coalesce(db.func.sum(Income.amount), 0),
        )
        .filter(
            Income.income_type.in_(["member_fee", "biedra nauda"]),
            Income.member_id.isnot(None),
            Income.entry_date >= period.start_date,
            Income.entry_date <= period.end_date,
        )
        .group_by(Income.member_id)
        .all()
    )
    paid_map = {member_id: total for member_id, total in paid_rows}
    fee_rows = MemberSeasonFee.query.filter_by(season_label=period.season_label).all()
    fee_map = {row.member_id: row.membership_fee for row in fee_rows}

    return jsonify(
        [
            member_to_dict(
                m,
                paid_this_period_override=paid_map.get(m.id, 0),
                membership_fee_override=fee_map.get(m.id, m.membership_fee),
            )
            for m in members
        ]
    )


@members_bp.route("/api/members", methods=["POST"])
@token_required({"board", "admin"})
def create_member():
    data = request.get_json() or {}

    phone = str(data.get("phone", "")).strip()
    role = normalize_role(data.get("role", "member"))
    season_label = str(data.get("season_label", current_period().season_label)).strip()
    try:
        membership_fee = to_decimal(data.get("membership_fee", 0) or 0)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    status = normalize_member_status(data.get("status", "Member"))
    valid_statuses = [s.name for s in MemberStatus.query.all()]
    if status not in valid_statuses:
        return jsonify({"error": f"Invalid status. Allowed values: {', '.join(valid_statuses)}"}), 400

    if not validate_phone(phone):
        return jsonify({"error": "Phone number must contain 8 digits"}), 400
    if Member.query.filter_by(phone=phone).first():
        return jsonify({"error": "A user with this phone number already exists"}), 409
    if role not in ROLES:
        return jsonify({"error": "Invalid role"}), 400
    if normalize_role(request.current_user.role) != "admin" and role == "admin":
        return jsonify({"error": "Only admin can create admin accounts"}), 403

    member = Member(
        list_no=next_member_list_no(),
        first_name=str(data.get("first_name", "")).strip() or "FirstName",
        last_name=str(data.get("last_name", "")).strip() or "LastName",
        phone=phone,
        status=status,
        membership_fee=membership_fee,
        paid_this_period=0,
        joining_fee_paid=to_bool(data.get("joining_fee_paid", False)),
        role=role,
    )

    db.session.add(member)
    db.session.flush()
    set_membership_fee_for_season(member, season_label, membership_fee)
    db.session.commit()

    return jsonify(member_to_dict(member)), 201


@members_bp.route("/api/members/<int:member_id>", methods=["PUT"])
@token_required({"board", "admin"})
def update_member(member_id):
    member = db.session.get(Member, member_id)
    if not member:
        return jsonify({"error": "Member not found"}), 404

    requester_role = normalize_role(request.current_user.role)
    if requester_role != "admin" and is_admin_member(member):
        return jsonify({"error": "Admin account can only be viewed and edited by admin"}), 403

    data = request.get_json() or {}
    phone = str(data.get("phone", member.phone)).strip()
    season_label = str(
        data.get("season_label") or request.args.get("season_label") or current_period().season_label
    ).strip()

    if not validate_phone(phone):
        return jsonify({"error": "Phone number must contain 8 digits"}), 400

    duplicate = Member.query.filter(Member.phone == phone, Member.id != member_id).first()
    if duplicate:
        return jsonify({"error": "Phone number is already in use"}), 409

    member.first_name = str(data.get("first_name", member.first_name)).strip()
    member.last_name = str(data.get("last_name", member.last_name)).strip()
    member.phone = phone
    if "status" in data:
        new_status = normalize_member_status(data["status"])
        valid_statuses = [s.name for s in MemberStatus.query.all()]
        if new_status not in valid_statuses:
            return jsonify({"error": f"Invalid status. Allowed values: {', '.join(valid_statuses)}"}), 400
        member.status = new_status
    try:
        membership_fee = to_decimal(data.get("membership_fee", get_effective_membership_fee(member, season_label)))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    set_membership_fee_for_season(member, season_label, membership_fee)
    if current_period().season_label == season_label:
        member.membership_fee = membership_fee
    member.joining_fee_paid = to_bool(data.get("joining_fee_paid", member.joining_fee_paid))

    if requester_role == "admin":
        role = normalize_role(data.get("role", member.role))
        if role not in ROLES:
            return jsonify({"error": "Invalid role"}), 400
        member.role = role

    db.session.commit()
    return jsonify(member_to_dict(member, membership_fee_override=membership_fee))


@members_bp.route("/api/members/<int:member_id>", methods=["DELETE"])
@token_required({"board", "admin"})
def delete_member(member_id):
    member = db.session.get(Member, member_id)
    if not member:
        return jsonify({"error": "Member not found"}), 404

    if normalize_role(request.current_user.role) != "admin" and is_admin_member(member):
        return jsonify({"error": "Only admin can delete admin accounts"}), 403

    db.session.delete(member)
    db.session.commit()

    resequence_members()
    db.session.commit()

    return jsonify({"message": "Member deleted"})


@members_bp.route("/api/members/<int:member_id>/pin", methods=["DELETE"])
@token_required({"admin"})
def clear_member_pin(member_id):
    member = db.session.get(Member, member_id)
    if not member:
        return jsonify({"error": "Member not found"}), 404

    if member.pin_hash is None:
        return jsonify({"error": "PIN is already cleared"}), 409

    member.pin_hash = None
    db.session.commit()

    return jsonify({"message": "PIN deleted"})


@members_bp.route("/api/members/<int:member_id>/payment", methods=["POST"])
@token_required({"cashier", "admin"})
def record_member_payment(member_id):
    member = db.session.get(Member, member_id)
    if not member:
        return jsonify({"error": "Member not found"}), 404

    if normalize_role(request.current_user.role) != "admin" and is_admin_member(member):
        return jsonify({"error": "Admin account is not accessible"}), 403

    data = request.get_json() or {}
    try:
        amount = to_decimal(data.get("amount", 0) or 0)
        entry_date = parse_entry_date(data.get("entry_date", date.today().isoformat()))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if amount <= 0:
        return jsonify({"error": "Amount must be greater than 0"}), 400

    income = Income(
        income_type="member_fee",
        member_id=member.id,
        amount=amount,
        entry_date=entry_date,
        description="Membership fee payment",
    )
    db.session.add(income)
    db.session.flush()

    recalculate_member_paid_this_period(member.id)
    db.session.commit()

    active_period = current_period()
    current_membership_fee = get_effective_membership_fee(member, active_period.season_label)
    progress = 0.0
    if current_membership_fee > 0:
        progress = float((to_decimal(member.paid_this_period) / current_membership_fee) * 100)

    return jsonify({"message": "Payment added", "progress_percent": round(progress, 2)})
