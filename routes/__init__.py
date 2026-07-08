from .auth import auth_bp
from .finance import finance_bp
from .members import members_bp
from .periods import periods_bp
from .web import web_bp


def register_blueprints(app):
    app.register_blueprint(web_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(members_bp)
    app.register_blueprint(finance_bp)
    app.register_blueprint(periods_bp)
