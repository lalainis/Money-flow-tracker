import os

from app_core import app, db
from models import AuditLog, AuthToken, Expense, Income, Member, MemberSeasonFee, MemberStatus, Period
from routes import register_blueprints
from services import ensure_schema_compatibility, ensure_seed_data
from settings import BASE_DIR, EXPENSE_CATEGORIES, ROLES, UPLOAD_DIR

register_blueprints(app)


def initialize_app_data():
    with app.app_context():
        db.create_all()
        ensure_schema_compatibility()
        ensure_seed_data()


initialize_app_data()


if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_RUN_HOST", "0.0.0.0"),
        port=int(os.getenv("FLASK_RUN_PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )
