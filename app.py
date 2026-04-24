import os
import sqlite3
import secrets
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask import (
    Flask, g, render_template, request, redirect, url_for,
    session, flash, abort, send_from_directory
)

# ---------- Config ----------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "instance", "getmycoach.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXT = {"png", "jpg", "jpeg", "webp", "gif"}

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB

SPORT_CATEGORIES = [
    "Football", "Basketball", "Volleyball", "Athletics", "Swimming",
    "Tennis", "Boxing", "Rugby", "Cricket", "Netball", "Martial Arts",
    "Cycling", "Gym & Fitness", "Other",
]

# ---------- DB helpers ----------
def get_db():
    if "db" not in g:
        # Ensure the instance/ directory exists even if the FS was wiped
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(_e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    """Create tables and seed default admin if missing."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    schema_path = os.path.join(BASE_DIR, "schema.sql")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    # Seed default admin
    admin_email = "admin@getmycoach.ug"
    admin_pw = "FAROUK"
    row = conn.execute("SELECT id FROM users WHERE email = ?", (admin_email,)).fetchone()
    if not row:
        conn.execute(
            "INSERT INTO users (email, password_hash, full_name, role) VALUES (?,?,?,?)",
            (admin_email, generate_password_hash(admin_pw), "Super Admin", "admin"),
        )
        conn.commit()
    conn.close()

# Run on import so gunicorn / Render also initializes the DB
try:
    init_db()
except Exception:
    import traceback; traceback.print_exc()

# ---------- Auth helpers ----------
def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()

@app.context_processor
def inject_user():
    return {"current_user": current_user(), "categories": SPORT_CATEGORIES}

def login_required(role=None):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            u = current_user()
            if not u:
                flash("Please log in.", "warning")
                return redirect(url_for("login", next=request.path))
            if role and u["role"] != role and u["role"] != "admin":
                abort(403)
            return fn(*a, **kw)
        return wrapper
    return deco

def allowed_file(name):
    return "." in name and name.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def save_photo(file_storage):
    if not file_storage or file_storage.filename == "":
        return None
    if not allowed_file(file_storage.filename):
        flash("Unsupported image type.", "danger")
        return None
    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    fname = f"{secrets.token_hex(8)}_{int(datetime.utcnow().timestamp())}.{ext}"
    path = os.path.join(UPLOAD_DIR, secure_filename(fname))
    file_storage.save(path)
    return f"/static/uploads/{fname}"

# ---------- Routes ----------
@app.route("/")
def index():
    return redirect(url_for("student"))

# ----- Auth -----
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        full_name = request.form.get("full_name", "").strip()
        role = request.form.get("role", "student")
        if role not in ("student", "coach"):
            role = "student"
        if not email or not password or len(password) < 6:
            flash("Email and a password (min 6 chars) are required.", "danger")
            return render_template("signup.html")
        db = get_db()
        if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            flash("That email is already registered. Try logging in.", "warning")
            return render_template("signup.html")
        db.execute(
            "INSERT INTO users (email, password_hash, full_name, role) VALUES (?,?,?,?)",
            (email, generate_password_hash(password), full_name, role),
        )
        db.commit()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        session["user_id"] = user["id"]
        flash("Welcome to GetMyCoach!", "success")
        return redirect(url_for(role))
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        # FAROUK shortcut: log in as default admin from anywhere
        if password == "FAROUK" and email in ("", "admin@getmycoach.ug"):
            db = get_db()
            user = db.execute(
                "SELECT * FROM users WHERE email = ?", ("admin@getmycoach.ug",)
            ).fetchone()
            if user:
                session["user_id"] = user["id"]
                flash("Admin access granted.", "success")
                return redirect(url_for("admin"))
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "danger")
            return render_template("login.html")
        session["user_id"] = user["id"]
        flash("Logged in.", "success")
        return redirect(url_for(user["role"]))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("login"))

# ----- Student (public) -----
@app.route("/student")
def student():
    db = get_db()
    category = request.args.get("category", "").strip()
    location = request.args.get("location", "").strip()
    sql = """SELECT * FROM coach_submissions
             WHERE is_verified = 1 AND payment_status = 'paid'"""
    params = []
    if category:
        sql += " AND category = ?"
        params.append(category)
    if location:
        sql += " AND LOWER(location) LIKE ?"
        params.append(f"%{location.lower()}%")
    sql += " ORDER BY created_at DESC"
    coaches = db.execute(sql, params).fetchall()
    return render_template(
        "student.html",
        coaches=coaches, category=category, location=location,
    )

# ----- Coach dashboard -----
@app.route("/coach", methods=["GET", "POST"])
@login_required(role="coach")
def coach():
    db = get_db()
    user = current_user()
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        if not full_name:
            flash("Full name is required.", "danger")
            return redirect(url_for("coach"))
        photo_url = save_photo(request.files.get("image"))
        db.execute(
            """INSERT INTO coach_submissions
               (owner_id, full_name, phone, category, location, bio, image_url,
                experience_years, hourly_rate, is_verified, payment_status)
               VALUES (?,?,?,?,?,?,?,?,?,0,'submitted')""",
            (
                user["id"],
                full_name,
                request.form.get("phone", "").strip(),
                request.form.get("category", "").strip(),
                request.form.get("location", "").strip(),
                request.form.get("bio", "").strip(),
                photo_url,
                int(request.form.get("experience_years") or 0),
                int(request.form.get("hourly_rate") or 0),
            ),
        )
        db.commit()
        flash("Submission received! Pay UGX 20,000 then admin will verify.", "success")
        return redirect(url_for("coach"))
    submissions = db.execute(
        "SELECT * FROM coach_submissions WHERE owner_id = ? ORDER BY created_at DESC",
        (user["id"],),
    ).fetchall()
    return render_template("coach.html", submissions=submissions)

@app.route("/coach/delete/<int:sub_id>", methods=["POST"])
@login_required(role="coach")
def coach_delete(sub_id):
    db = get_db()
    user = current_user()
    row = db.execute(
        "SELECT * FROM coach_submissions WHERE id = ? AND owner_id = ?",
        (sub_id, user["id"]),
    ).fetchone()
    if not row and user["role"] != "admin":
        abort(404)
    db.execute("DELETE FROM coach_submissions WHERE id = ?", (sub_id,))
    db.commit()
    flash("Submission deleted.", "info")
    return redirect(url_for("coach"))

# ----- Admin -----
@app.route("/admin", methods=["GET", "POST"])
@login_required(role="admin")
def admin():
    db = get_db()
    if request.method == "POST":
        # Quick-add coach (live immediately)
        full_name = request.form.get("full_name", "").strip()
        if not full_name:
            flash("Full name is required.", "danger")
            return redirect(url_for("admin"))
        photo_url = save_photo(request.files.get("image"))
        db.execute(
            """INSERT INTO coach_submissions
               (owner_id, full_name, phone, category, location, bio, image_url,
                experience_years, hourly_rate, is_verified, payment_status)
               VALUES (?,?,?,?,?,?,?,?,?,1,'paid')""",
            (
                current_user()["id"],
                full_name,
                request.form.get("phone", "").strip(),
                request.form.get("category", "").strip(),
                request.form.get("location", "").strip(),
                request.form.get("bio", "").strip(),
                photo_url,
                int(request.form.get("experience_years") or 0),
                int(request.form.get("hourly_rate") or 0),
            ),
        )
        db.commit()
        flash("Coach added and live.", "success")
        return redirect(url_for("admin"))
    pending = db.execute(
        """SELECT * FROM coach_submissions
           WHERE is_verified = 0 OR payment_status != 'paid'
           ORDER BY created_at DESC"""
    ).fetchall()
    live = db.execute(
        """SELECT * FROM coach_submissions
           WHERE is_verified = 1 AND payment_status = 'paid'
           ORDER BY created_at DESC"""
    ).fetchall()
    return render_template("admin.html", pending=pending, live=live)

@app.route("/admin/approve/<int:sub_id>", methods=["POST"])
@login_required(role="admin")
def admin_approve(sub_id):
    db = get_db()
    db.execute(
        """UPDATE coach_submissions
           SET is_verified = 1, payment_status = 'paid', updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (sub_id,),
    )
    db.commit()
    flash("Coach approved and live.", "success")
    return redirect(url_for("admin"))

@app.route("/admin/delete/<int:sub_id>", methods=["POST"])
@login_required(role="admin")
def admin_delete(sub_id):
    db = get_db()
    db.execute("DELETE FROM coach_submissions WHERE id = ?", (sub_id,))
    db.commit()
    flash("Submission removed.", "info")
    return redirect(url_for("admin"))

# Static uploads (Flask serves /static automatically; this is just explicit)
@app.route("/static/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)

@app.errorhandler(403)
def forbidden(_e):
    return render_template("base.html", forbidden=True), 403

@app.errorhandler(404)
def not_found(_e):
    return render_template("base.html", notfound=True), 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
