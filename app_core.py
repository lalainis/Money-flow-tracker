from flask import Flask
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy

from settings import (
	CORS_ALLOWED_ORIGINS,
	DATABASE_URL,
	DB_CONNECT_TIMEOUT_SECONDS,
	DB_KEEPALIVES_COUNT,
	DB_KEEPALIVES_IDLE_SECONDS,
	DB_KEEPALIVES_INTERVAL_SECONDS,
	DB_MAX_OVERFLOW,
	DB_POOL_PRE_PING,
	DB_POOL_RECYCLE_SECONDS,
	DB_POOL_SIZE,
	DB_POOL_TIMEOUT_SECONDS,
	SECRET_KEY,
)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = SECRET_KEY

if DATABASE_URL.startswith("postgresql"):
	app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
		"pool_pre_ping": DB_POOL_PRE_PING,
		"pool_recycle": DB_POOL_RECYCLE_SECONDS,
		"pool_timeout": DB_POOL_TIMEOUT_SECONDS,
		"pool_size": DB_POOL_SIZE,
		"max_overflow": DB_MAX_OVERFLOW,
		"connect_args": {
			"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS,
			"keepalives": 1,
			"keepalives_idle": DB_KEEPALIVES_IDLE_SECONDS,
			"keepalives_interval": DB_KEEPALIVES_INTERVAL_SECONDS,
			"keepalives_count": DB_KEEPALIVES_COUNT,
		},
	}

CORS(
	app,
	resources={r"/api/*": {"origins": CORS_ALLOWED_ORIGINS}},
	allow_headers=["Authorization", "Content-Type"],
	methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
)

limiter = Limiter(
	key_func=get_remote_address,
	app=app,
	default_limits=[],
	storage_uri="memory://",
)

db = SQLAlchemy(app)
