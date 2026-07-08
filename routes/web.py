from flask import Blueprint, jsonify, render_template, send_from_directory

from settings import BASE_DIR, EXPENSE_CATEGORIES

web_bp = Blueprint("web", __name__)


@web_bp.route("/")
def index():
    return render_template("index.html")


@web_bp.route("/assets/<path:filename>")
def asset_file(filename):
    return send_from_directory(BASE_DIR, filename)


@web_bp.route("/api/config")
def config():
    return jsonify({"expense_categories": EXPENSE_CATEGORIES})
