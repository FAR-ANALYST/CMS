"""
Get My Coach Uganda - Flask App
Production-ready for Render deployment.
"""
import os
import sqlite3
import uuid
from datetime import timedelta
from functools import wraps
from pathlib import Path

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, g, send_from_directory, abort
)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ---------------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = str(INSTANCE_DIR / "getmycoach.db")
SCHEMA_PATH = BASE_DIR / "schema.sql"

ALLOWED_IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "gif"}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB

SPORTS = [
    "Athletics", "Chess", "Checkers", "Football", "Gym/Fitness",
    "Handball", "Netball", "Scrabble", "Swimming", "Volleyball",
]

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@getmycoach.ug")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "FAROUK")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "change-me-in-production-getmycoach-2026")
app.permanent_session_lifetime = timedelta(hours=24)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

# Render runs behind a reverse proxy (HTTPS terminated upstream)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Secure session cookies — only mark Secure in production (Render sets RENDER=true)
IS_PROD = os.environ.get("RENDER", "").lower() == "true"
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=IS_PROD,
)

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
    return db


@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables on import — works under gunicorn/WSGI on Render."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")

        if SCHEMA_PATH.exists():
            with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
        else:
            # Inline fallback schema
            conn.executescript(INLINE_SCHEMA)

        # Seed default admin
        cur = conn.execute("SELECT id FROM users WHERE email = ?", (ADMIN_EMAIL,))
        if cur.fetchone() is None:
            conn.execute(
                "INSERT INTO users (id, email, full_name, password_hash, role) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    ADMIN_EMAIL,
                    "Site Admin",
                    generate_password_hash(ADMIN_PASSWORD),
                    "admin",
                ),
            )
        conn.commit()
        conn.close()
    except Exception:
        import traceback
        traceback.print_exc()


INLINE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'coach',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS coach_submissions (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    full_name TEXT NOT NULL,
    phone TEXT,
    category TEXT,
    location TEXT,
    bio TEXT,
    image_url TEXT,
    experience_years INTEGER DEFAULT 0,
    hourly_rate INTEGER DEFAULT 0,
    is_verified INTEGER NOT NULL DEFAULT 0,
    payment_status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_subs_owner ON coach_submissions(owner_id);
CREATE INDEX IF NOT EXISTS idx_subs_status ON coach_submissions(payment_status, is_verified);
CREATE INDEX IF NOT EXISTS idx_subs_category ON coach_submissions(category);
"""

# Run on import — required for gunicorn on Render
init_db()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


def login_required(role=None):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("login"))
            if role and user["role"] != role:
                flash("You don't have access to that page.", "danger")
                return redirect(url_for("index"))
            return view(*args, **kwargs)
        return wrapper
    return decorator


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTS


def save_image(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_file(file_storage.filename):
        flash("Unsupported image type.", "warning")
        return None
    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    fname = f"{uuid.uuid4().hex}.{ext}"
    safe = secure_filename(fname)
    file_storage.save(UPLOAD_DIR / safe)
    return f"/static/uploads/{safe}"


# ---------------------------------------------------------------------------
# Context processors
# ---------------------------------------------------------------------------
@app.context_processor
def inject_globals():
    return {"SPORTS": SPORTS, "current_user": current_user()}


# ---------------------------------------------------------------------------
# Routes — public
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    db = get_db()
    category = request.args.get("category", "").strip()
    location = request.args.get("location", "").strip()

    sql = ("SELECT * FROM coach_submissions "
           "WHERE is_verified = 1 AND payment_status = 'paid'")
    params = []
    if category:
        sql += " AND category = ?"
        params.append(category)
    if location:
        sql += " AND location LIKE ?"
        params.append(f"%{location}%")
    sql += " ORDER BY created_at DESC"

    coaches = db.execute(sql, params).fetchall()
    return render_template(
        "student.html",
        coaches=coaches, category=category, location=location,
    )


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email and password are required.", "danger")
            return render_template("login.html")

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session.permanent = True
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            flash(f"Welcome back, {user['full_name'] or user['email']}!", "success")
            return redirect(url_for("admin" if user["role"] == "admin" else "coach_dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
@app.route("/register", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")

        if not email or not password or len(password) < 6:
            flash("Email and a password (min 6 chars) are required.", "danger")
            return render_template("signup.html")

        db = get_db()
        existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            flash("An account with that email already exists.", "warning")
            return render_template("signup.html")

        uid = str(uuid.uuid4())
        db.execute(
            "INSERT INTO users (id, email, full_name, password_hash, role) "
            "VALUES (?, ?, ?, ?, 'coach')",
            (uid, email, full_name, generate_password_hash(password)),
        )
        db.commit()

        session.permanent = True
        session["user_id"] = uid
        session["role"] = "coach"
        flash("Account created. Complete your coach profile below.", "success")
        return redirect(url_for("coach_dashboard"))

    return render_template("signup.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Coach routes
# ---------------------------------------------------------------------------
@app.route("/coach")
@login_required(role="coach")
def coach_dashboard():
    db = get_db()
    user = current_user()
    submissions = db.execute(
        "SELECT * FROM coach_submissions WHERE owner_id = ? ORDER BY created_at DESC",
        (user["id"],),
    ).fetchall()
    return render_template("coach.html", submissions=submissions)


@app.route("/coach/submit", methods=["POST"])
@login_required(role="coach")
def coach_submit():
    user = current_user()
    image_url = save_image(request.files.get("image"))

    db = get_db()
    db.execute(
        """INSERT INTO coach_submissions
           (id, owner_id, full_name, phone, category, location, bio,
            image_url, experience_years, hourly_rate,
            is_verified, payment_status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'submitted')""",
        (
            str(uuid.uuid4()),
            user["id"],
            request.form.get("full_name", "").strip(),
            request.form.get("phone", "").strip(),
            request.form.get("category", "").strip(),
            request.form.get("location", "").strip(),
            request.form.get("bio", "").strip(),
            image_url,
            int(request.form.get("experience_years") or 0),
            int(request.form.get("hourly_rate") or 0),
        ),
    )
    db.commit()
    flash("Profile submitted. Awaiting admin verification.", "success")
    return redirect(url_for("coach_dashboard"))


@app.route("/coach/edit/<sub_id>", methods=["POST"])
@login_required(role="coach")
def coach_edit(sub_id):
    user = current_user()
    db = get_db()
    row = db.execute(
        "SELECT * FROM coach_submissions WHERE id = ? AND owner_id = ?",
        (sub_id, user["id"]),
    ).fetchone()
    if not row:
        abort(404)

    image_url = save_image(request.files.get("image")) or row["image_url"]
    db.execute(
        """UPDATE coach_submissions SET
            full_name = ?, phone = ?, category = ?, location = ?, bio = ?,
            image_url = ?, experience_years = ?, hourly_rate = ?,
            updated_at = CURRENT_TIMESTAMP
           WHERE id = ? AND owner_id = ?""",
        (
            request.form.get("full_name", "").strip(),
            request.form.get("phone", "").strip(),
            request.form.get("category", "").strip(),
            request.form.get("location", "").strip(),
            request.form.get("bio", "").strip(),
            image_url,
            int(request.form.get("experience_years") or 0),
            int(request.form.get("hourly_rate") or 0),
            sub_id,
            user["id"],
        ),
    )
    db.commit()
    flash("Profile updated.", "success")
    return redirect(url_for("coach_dashboard"))


@app.route("/coach/delete/<sub_id>", methods=["POST"])
@login_required(role="coach")
def coach_delete(sub_id):
    user = current_user()
    db = get_db()
    db.execute(
        "DELETE FROM coach_submissions WHERE id = ? AND owner_id = ?",
        (sub_id, user["id"]),
    )
    db.commit()
    flash("Submission removed.", "info")
    return redirect(url_for("coach_dashboard"))


# ---------------------------------------------------------------------------
# Admin routes
# ---------------------------------------------------------------------------
@app.route("/admin")
@login_required(role="admin")
def admin():
    db = get_db()
    pending = db.execute(
        "SELECT * FROM coach_submissions "
        "WHERE is_verified = 0 OR payment_status != 'paid' "
        "ORDER BY created_at DESC"
    ).fetchall()
    live = db.execute(
        "SELECT * FROM coach_submissions "
        "WHERE is_verified = 1 AND payment_status = 'paid' "
        "ORDER BY created_at DESC"
    ).fetchall()
    return render_template("admin.html", pending=pending, live=live)


@app.route("/admin/approve/<sub_id>", methods=["POST"])
@login_required(role="admin")
def admin_approve(sub_id):
    db = get_db()
    db.execute(
        "UPDATE coach_submissions SET is_verified = 1, payment_status = 'paid', "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (sub_id,),
    )
    db.commit()
    flash("Coach approved and now live.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/unapprove/<sub_id>", methods=["POST"])
@login_required(role="admin")
def admin_unapprove(sub_id):
    db = get_db()
    db.execute(
        "UPDATE coach_submissions SET is_verified = 0, payment_status = 'pending', "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (sub_id,),
    )
    db.commit()
    flash("Coach removed from live directory.", "info")
    return redirect(url_for("admin"))


@app.route("/admin/delete/<sub_id>", methods=["POST"])
@login_required(role="admin")
def admin_delete(sub_id):
    db = get_db()
    db.execute("DELETE FROM coach_submissions WHERE id = ?", (sub_id,))
    db.commit()
    flash("Submission deleted.", "info")
    return redirect(url_for("admin"))


@app.route("/admin/add", methods=["POST"])
@login_required(role="admin")
def admin_add():
    """Admin adds a coach directly — goes live immediately."""
    user = current_user()
    image_url = save_image(request.files.get("image"))
    db = get_db()
    db.execute(
        """INSERT INTO coach_submissions
           (id, owner_id, full_name, phone, category, location, bio,
            image_url, experience_years, hourly_rate,
            is_verified, payment_status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'paid')""",
        (
            str(uuid.uuid4()),
            user["id"],
            request.form.get("full_name", "").strip(),
            request.form.get("phone", "").strip(),
            request.form.get("category", "").strip(),
            request.form.get("location", "").strip(),
            request.form.get("bio", "").strip(),
            image_url,
            int(request.form.get("experience_years") or 0),
            int(request.form.get("hourly_rate") or 0),
        ),
    )
    db.commit()
    flash("Coach added and is now live.", "success")
    return redirect(url_for("admin"))


# ---------------------------------------------------------------------------
# Health + error handlers
# ---------------------------------------------------------------------------
@app.route("/healthz")
def healthz():
    return {"status": "ok"}, 200


@app.errorhandler(404)
def not_found(_e):
    return render_template("error.html", code=404, message="Page not found."), 404


@app.errorhandler(500)
def server_error(_e):
    return render_template("error.html", code=500, message="Something went wrong."), 500


@app.errorhandler(Exception)
def unhandled(e):
    import traceback
    traceback.print_exc()
    return render_template("error.html", code=500, message=str(e)), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
