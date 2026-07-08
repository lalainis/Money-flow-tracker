# Money flow tracker

Flask + Vue.js + PostgreSQL application for tracking association income and expenses.

## Requirements

- Python 3.11+
- PostgreSQL

## Run Locally

1. Create `.env` from `.env.example`.
2. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

3. Run the application:

   ```powershell
   python app.py
   ```

4. Open `http://127.0.0.1:5000`.

## Tests

1. Run automated tests:

   ```powershell
   python -m pytest -q
   ```

2. Tests also include attachment checks:

- allowed formats: `pdf`, `jpg`, `jpeg`, `png`, `txt`, `doc`, `docx`, `xlsx`
- unsupported file type and malformed multipart request are rejected with `400`

## CI (GitHub Actions)

- Workflow file: `.github/workflows/tests.yml`
- Tests run automatically on `push` and `pull_request`

## First Admin Account Setup

- For security reasons, there are no built-in default admin credentials.
- Before first startup, set these environment variables:
  - `BOOTSTRAP_ADMIN_PHONE` (exactly 8 digits)
  - `BOOTSTRAP_ADMIN_PIN` (exactly 4 digits)
- The admin account is created only when the database has no members yet.

## Roles

- Cashier
- Board
- Auditor
- admins
- Member

## Notes

- If `DATABASE_URL` is not set, a local SQLite database (`app.db`) is used for demo purposes.
- In production, PostgreSQL is recommended according to the PRD.

## Internet Security

- `SECRET_KEY` is mandatory in production.
- `CORS_ALLOWED_ORIGINS` must contain public frontend domains (comma-separated).
- `AUTH_TOKEN_TTL_HOURS` sets token/session lifetime in hours.
- `AUTH_MAX_FAILED_ATTEMPTS` and `AUTH_LOCKOUT_MINUTES` enable PIN brute-force protection.
- For first startup on an empty database, `BOOTSTRAP_ADMIN_PHONE` and `BOOTSTRAP_ADMIN_PIN` are required.

## Deploy to Server (Ubuntu + Nginx + systemd)

Prepared files in the repository:

- `deploy/linux/systemd/biedribas-finansists.service`
- `deploy/linux/nginx/biedribas-finansists.conf`
- `deploy/linux/env.production.example`

1. Log in to the server and install required packages:

   ```bash
   sudo apt update
   sudo apt install -y python3 python3-venv python3-pip nginx postgresql postgresql-contrib
   ```

2. Copy the project to the server:

   ```bash
   sudo mkdir -p /opt/biedribas-finansists
   sudo chown -R $USER:$USER /opt/biedribas-finansists
   # then copy project files to /opt/biedribas-finansists (git clone or scp)
   ```

3. Set up Python environment and dependencies:

   ```bash
   cd /opt/biedribas-finansists
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -U pip
   pip install -r requirements.txt
   ```

4. Create production env file:

   ```bash
   sudo cp deploy/linux/env.production.example /etc/biedribas-finansists.env
   sudo nano /etc/biedribas-finansists.env
   ```

   Required changes:

- `SECRET_KEY` to a long random value
- `DATABASE_URL` to your PostgreSQL connection
- `CORS_ALLOWED_ORIGINS` to your frontend URL (if using a domain)
- `BOOTSTRAP_ADMIN_PHONE` to an 8-digit admin phone number
- `BOOTSTRAP_ADMIN_PIN` to a 4-digit admin PIN (strong, not trivial)

5. Prepare PostgreSQL database:

   ```bash
   sudo -u postgres psql
   CREATE DATABASE finansists;
   CREATE USER finansists_user WITH PASSWORD 'strong-password';
   GRANT ALL PRIVILEGES ON DATABASE finansists TO finansists_user;
   \q
   ```

   Then update `DATABASE_URL` in `/etc/biedribas-finansists.env`.

6. Enable systemd service:

   ```bash
   sudo cp deploy/linux/systemd/biedribas-finansists.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable biedribas-finansists
   sudo systemctl start biedribas-finansists
   sudo systemctl status biedribas-finansists
   ```

7. Enable Nginx reverse proxy:

   ```bash
   sudo cp deploy/linux/nginx/biedribas-finansists.conf /etc/nginx/sites-available/biedribas-finansists
   sudo ln -s /etc/nginx/sites-available/biedribas-finansists /etc/nginx/sites-enabled/biedribas-finansists
   sudo nginx -t
   sudo systemctl restart nginx
   ```

8. Open firewall:

   ```bash
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   sudo ufw enable
   ```

9. Verification:

   Open `http://......`.
