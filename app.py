"""
Get My Coach Uganda — Flask version
Multi-coach submissions, admin approval queue, admin quick-add (auto-live),
local photo uploads to /static/uploads.

Run locally:
    pip install -r requirements.txt
    python app.py
Then open http://localhost:5000
"""
import os
import sqlite3
import uuid
from functools import wraps
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, g, send_from_directory, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "instance", "getmycoach.db")
UPLOAD_DIR = os.path.join(APP_DIR, "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB upload cap

SPORT_CATEGORIES = [
    "Football", "Basketball", "Volleyball", "Tennis", "Swimming",
    "Athletics", "Boxing", "Rugby", "Cricket", "Netball",
    "Badminton", "Table Tennis", "Martial Arts", "Cycling", "Other",
]

# ---------- Database ----------
def get_db():
    if "db" not in g:
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
    schema = os.path.join(APP_DIR, "schema.sql")
    with open(schema, "r") as f:
        sql = f.read()
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(sql)
        # Seed default admin if none exists
        cur = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
        if cur.fetchone()[0] == 0:
            conn.execute(
                "INSERT INTO users (id, email, password_hash, full_name, role) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    "admin@getmycoach.ug",
                    generate_password_hash("FAROUK"),
                    "Super Admin",
                    "admin",
                ),
            )
        conn.commit()

# ---------- Auth helpers ----------
def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return get_db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()

def login_required(role=None):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            u = current_user()
            if not u:
                flash("Please log in.", "warning")
                return redirect(url_for("login", next=request.path))
            if role and u["role"] != role and u["role"] != "admin":
                flash("You don't have access to that page.", "error")
                return redirect(url_for("index"))
            return fn(*a, **kw)
        return wrapper
    return deco

@app.context_processor
def inject_globals():
    return dict(current_user=current_user(), sport_categories=SPORT_CATEGORIES)

# ---------- Upload helper ----------
def allowed_file(name: str) -> bool:
    return "." in name and name.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def save_photo(file_storage) -> str | None:
    if not file_storage or file_storage.filename == "":
        return None
    if not allowed_file(file_storage.filename):
        flash("Photo must be png/jpg/jpeg/gif/webp.", "error")
        return None
    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    fname = f"{uuid.uuid4().hex}.{ext}"
    file_storage.save(os.path.join(UPLOAD_DIR, secure_filename(fname)))
    return f"/static/uploads/{fname}"

# ---------- Routes ----------
@app.route("/")
def index():
    return redirect(url_for("student"))

# ----- Auth -----
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        full_name = request.form.get("full_name", "").strip()
        role = request.form.get("role", "student")
        if role not in ("student", "coach"):
            role = "student"
        db = get_db()
        if db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            flash("Email already registered.", "error")
            return render_template("signup.html")
        uid = str(uuid.uuid4())
        db.execute(
            "INSERT INTO users (id, email, password_hash, full_name, role) "
            "VALUES (?, ?, ?, ?, ?)",
            (uid, email, generate_password_hash(password), full_name, role),
        )
        db.commit()
        session["user_id"] = uid
        flash("Welcome! Account created.", "success")
        return redirect(url_for(role))
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        # FAROUK admin shortcut
        if password == "FAROUK":
            db = get_db()
            row = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if not row:
                uid = str(uuid.uuid4())
                db.execute(
                    "INSERT INTO users (id, email, password_hash, full_name, role) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (uid, email, generate_password_hash("FAROUK"), "Admin", "admin"),
                )
                db.commit()
                session["user_id"] = uid
            else:
                db.execute("UPDATE users SET role='admin' WHERE id=?", (row["id"],))
                db.commit()
                session["user_id"] = row["id"]
            return redirect(url_for("admin"))
        db = get_db()
        row = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not row or not check_password_hash(row["password_hash"], password):
            flash("Invalid credentials.", "error")
            return render_template("login.html")
        session["user_id"] = row["id"]
        return redirect(url_for(row["role"]))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("login"))

# ----- Student -----
@app.route("/student")
def student():
    db = get_db()
    category = request.args.get("category", "").strip()
    location = request.args.get("location", "").strip()
    sql = ("SELECT * FROM coach_submissions "
           "WHERE is_verified=1 AND payment_status='paid'")
    params = []
    if category:
        sql += " AND category = ?"
        params.append(category)
    if location:
        sql += " AND location LIKE ?"
        params.append(f"%{location}%")
    sql += " ORDER BY created_at DESC"
    coaches = db.execute(sql, params).fetchall()
    return render_template("student.html", coaches=coaches,
                           filter_category=category, filter_location=location)

# ----- Coach -----
@app.route("/coach", methods=["GET", "POST"])
@login_required(role="coach")
def coach():
    user = current_user()
    db = get_db()
    if request.method == "POST":
        full_name = request.form["full_name"].strip()
        if not full_name:
            flash("Full name is required.", "error")
            return redirect(url_for("coach"))
        image_url = save_photo(request.files.get("photo"))
        db.execute(
            "INSERT INTO coach_submissions "
            "(id, owner_id, full_name, phone, category, location, bio, image_url, "
            "experience_years, hourly_rate, is_verified, payment_status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'submitted')",
            (
                str(uuid.uuid4()), user["id"], full_name,
                request.form.get("phone", "").strip() or None,
                request.form.get("category", "").strip() or None,
                request.form.get("location", "").strip() or None,
                request.form.get("bio", "").strip() or None,
                image_url,
                int(request.form.get("experience_years") or 0),
                int(request.form.get("hourly_rate") or 0),
            ),
        )
        db.commit()
        flash("Coach submitted — awaiting admin approval after payment.", "success")
        return redirect(url_for("coach"))

    submissions = db.execute(
        "SELECT * FROM coach_submissions WHERE owner_id=? ORDER BY created_at DESC",
        (user["id"],),
    ).fetchall()
    return render_template("coach.html", submissions=submissions)

@app.route("/coach/delete/<sid>", methods=["POST"])
@login_required(role="coach")
def coach_delete(sid):
    user = current_user()
    db = get_db()
    db.execute(
        "DELETE FROM coach_submissions WHERE id=? AND (owner_id=? OR ?='admin')",
        (sid, user["id"], user["role"]),
    )
    db.commit()
    flash("Submission removed.", "success")
    return redirect(url_for("coach"))

# ----- Admin -----
@app.route("/admin", methods=["GET", "POST"])
@login_required(role="admin")
def admin():
    user = current_user()
    db = get_db()
    if request.method == "POST":
        full_name = request.form["full_name"].strip()
        if not full_name:
            flash("Full name is required.", "error")
            return redirect(url_for("admin"))
        image_url = save_photo(request.files.get("photo"))
        db.execute(
            "INSERT INTO coach_submissions "
            "(id, owner_id, full_name, phone, category, location, bio, image_url, "
            "experience_years, hourly_rate, is_verified, payment_status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'paid')",
            (
                str(uuid.uuid4()), user["id"], full_name,
                request.form.get("phone", "").strip() or None,
                request.form.get("category", "").strip() or None,
                request.form.get("location", "").strip() or None,
                request.form.get("bio", "").strip() or None,
                image_url,
                int(request.form.get("experience_years") or 0),
                int(request.form.get("hourly_rate") or 0),
            ),
        )
        db.commit()
        flash("Coach added & published live.", "success")
        return redirect(url_for("admin"))

    pending = db.execute(
        "SELECT * FROM coach_submissions "
        "WHERE NOT (is_verified=1 AND payment_status='paid') "
        "ORDER BY created_at DESC"
    ).fetchall()
    live = db.execute(
        "SELECT * FROM coach_submissions "
        "WHERE is_verified=1 AND payment_status='paid' "
        "ORDER BY created_at DESC"
    ).fetchall()
    return render_template("admin.html", pending=pending, live=live)

@app.route("/admin/approve/<sid>", methods=["POST"])
@login_required(role="admin")
def admin_approve(sid):
    db = get_db()
    db.execute(
        "UPDATE coach_submissions SET is_verified=1, payment_status='paid', "
        "updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (sid,),
    )
    db.commit()
    flash("Coach is now live.", "success")
    return redirect(url_for("admin"))

@app.route("/admin/delete/<sid>", methods=["POST"])
@login_required(role="admin")
def admin_delete(sid):
    db = get_db()
    db.execute("DELETE FROM coach_submissions WHERE id=?", (sid,))
    db.commit()
    flash("Coach removed.", "success")
    return redirect(url_for("admin"))

# ----- Static uploads (explicit so it works on any host) -----
@app.route("/static/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# ---------- CLI ----------
@app.cli.command("init-db")
def init_db_cmd():
    init_db()
    print(f"Initialized DB at {DB_PATH}")

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        init_db()
        print(f"Created DB at {DB_PATH}")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
