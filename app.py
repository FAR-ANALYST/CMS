import os
import sqlite3
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "farouk_systems_premium_2026")
app.permanent_session_lifetime = timedelta(hours=24)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db")

SPORTS = [
    "Athletics", "Chess", "Checkers", "Football", "Gym/Fitness",
    "Handball", "Netball", "Scrabble", "Swimming", "Volleyball"
]
ADMIN_USERNAME = "FAROUK"
ADMIN_PASSWORD = "FAROUK2020"


# ── Database helpers ───────────────────────────────────────────

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db:
        db.close()

def init_db():
    """Create tables on every startup. Safe to call repeatedly."""
    conn = sqlite3.connect(DATABASE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS coaches (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            username       TEXT,
            email          TEXT UNIQUE,
            password       TEXT,
            full_name      TEXT,
            phone          TEXT,
            category       TEXT,
            bio            TEXT,
            location       TEXT,
            image_url      TEXT,
            is_verified    INTEGER DEFAULT 0,
            payment_status TEXT    DEFAULT 'pending'
        )
    """)
    conn.commit()
    conn.close()

# Run on import so gunicorn/Render always has tables ready
init_db()


# ── Auth guard ─────────────────────────────────────────────────

@app.before_request
def require_login():
    public = {"welcome", "login", "signup", "static"}
    if request.endpoint not in public and "user_id" not in session:
        return redirect(url_for("welcome"))


# ══════════════════════════════════════════════
#  STUDENT FACE  /
# ══════════════════════════════════════════════

@app.route("/")
def index():
    db  = get_db()
    cat = request.args.get("category", "")
    loc = request.args.get("location", "")

    # Only show verified coaches
    query  = "SELECT * FROM coaches WHERE is_verified = 1"
    params = []
    if cat:
        query += " AND category = ?"
        params.append(cat)
    if loc:
        query += " AND location LIKE ?"
        params.append(f"%{loc}%")

    coaches = db.execute(query, params).fetchall()
    return render_template("student.html", coaches=coaches, SPORTS=SPORTS)


# ══════════════════════════════════════════════
#  COACH FACE
# ══════════════════════════════════════════════

@app.route("/coach")
def coach_dashboard():
    db   = get_db()
    u_id = session.get("user_id")
    if session.get("is_admin"):
        submissions = db.execute("SELECT * FROM coaches").fetchall()
    else:
        submissions = db.execute(
            "SELECT * FROM coaches WHERE id = ?", (u_id,)
        ).fetchall()
    return render_template("coach.html", submissions=submissions, SPORTS=SPORTS)


@app.route("/coach/submit", methods=["POST"])
def coach_submit():
    u_id = session.get("user_id")
    if not u_id:
        return redirect(url_for("login"))

    db        = get_db()
    full_name = request.form.get("full_name", "").strip()
    phone     = request.form.get("phone", "").strip()
    category  = request.form.get("category", "").strip()
    location  = request.form.get("location", "").strip()
    bio       = request.form.get("bio", "").strip()
    img_url   = request.form.get("existing_image", "")

    # Handle optional photo upload
    if "image" in request.files:
        file = request.files["image"]
        if file and file.filename:
            fn = secure_filename(f"up_{u_id}_{file.filename}")
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], fn))
            img_url = f"/static/uploads/{fn}"

    # ── THE FIX ──────────────────────────────────────────────
    # Set payment_status = 'submitted' so the admin query can
    # distinguish real submissions from blank new signups.
    # Also reset is_verified = 0 so any re-submission goes back
    # into the pending queue for re-approval.
    db.execute(
        """
        UPDATE coaches
        SET full_name      = ?,
            phone          = ?,
            category       = ?,
            location       = ?,
            bio            = ?,
            image_url      = ?,
            is_verified    = 0,
            payment_status = 'submitted'
        WHERE id = ?
        """,
        (full_name, phone, category, location, bio, img_url, u_id)
    )
    db.commit()

    flash("Profile submitted to Farouk for approval!", "success")
    return redirect(url_for("coach_dashboard"))


# ══════════════════════════════════════════════
#  ADMIN FACE  /admin
# ══════════════════════════════════════════════

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    db = get_db()

    # Admin can add a coach directly (goes live immediately)
    if request.method == "POST" and request.form.get("action") == "quick_add":
        img = ""
        if "image" in request.files:
            file = request.files["image"]
            if file and file.filename:
                fn = secure_filename(file.filename)
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], fn))
                img = f"/static/uploads/{fn}"

        name  = request.form.get("full_name", "").strip()
        email = f"{name.replace(' ', '_').lower()}@system.com"
        db.execute(
            """
            INSERT INTO coaches
                (full_name, phone, category, location, bio,
                 image_url, is_verified, payment_status,
                 username, email, password)
            VALUES (?,?,?,?,?,?,1,'paid',?,?,'admin_added')
            """,
            (
                name,
                request.form.get("phone", ""),
                request.form.get("category", ""),
                request.form.get("location", ""),
                request.form.get("bio", ""),
                img,
                name,
                email,
            )
        )
        db.commit()
        flash(f"Coach '{name}' added and is now live.", "success")
        return redirect(url_for("admin"))

    # ── THE FIX ──────────────────────────────────────────────
    # Filter by payment_status = 'submitted' so only coaches who
    # actually filled out and submitted their form appear here.
    # Plain new signups (payment_status = 'pending') are excluded.
    pending = db.execute(
        "SELECT * FROM coaches WHERE is_verified = 0 AND payment_status = 'submitted'"
    ).fetchall()

    live = db.execute(
        "SELECT * FROM coaches WHERE is_verified = 1"
    ).fetchall()

    return render_template("admin.html", pending=pending, live=live, SPORTS=SPORTS)


@app.route("/admin/approve/<int:sub_id>", methods=["POST"])
def admin_approve(sub_id):
    if not session.get("is_admin"):
        return redirect(url_for("login"))
    db = get_db()
    db.execute(
        "UPDATE coaches SET is_verified = 1, payment_status = 'paid' WHERE id = ?",
        (sub_id,)
    )
    db.commit()
    flash("Coach approved and is now live.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/delete/<int:sub_id>", methods=["POST"])
def admin_delete(sub_id):
    if not session.get("is_admin"):
        return redirect(url_for("login"))
    db = get_db()
    db.execute("DELETE FROM coaches WHERE id = ?", (sub_id,))
    db.commit()
    return redirect(url_for("admin"))


# ══════════════════════════════════════════════
#  AUTH ROUTES
# ══════════════════════════════════════════════

@app.route("/welcome")
def welcome():
    return render_template("welcome.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        lid = request.form.get("login_id", "").strip()
        pwd = request.form.get("password", "")

        # Admin hard-coded bypass
        if lid.upper() == ADMIN_USERNAME and pwd == ADMIN_PASSWORD:
            session.clear()
            session.update({"user_id": "admin", "is_admin": True})
            session.permanent = True
            return redirect(url_for("admin"))

        # Coach / student lookup
        user = get_db().execute(
            "SELECT * FROM coaches WHERE username = ? OR email = ?",
            (lid, lid)
        ).fetchone()

        if user and (
            check_password_hash(user["password"], pwd)
            or user["password"] == pwd          # fallback for admin_added
        ):
            session.clear()
            session.update({"user_id": user["id"], "is_admin": False})
            session.permanent = True
            return redirect(url_for("coach_dashboard"))

        flash("Invalid credentials. Please try again.", "danger")

    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        e = request.form.get("email", "").strip().lower()
        p = request.form.get("password", "")
        try:
            db = get_db()
            db.execute(
                "INSERT INTO coaches (username, email, password) VALUES (?, ?, ?)",
                (u, e, generate_password_hash(p))
            )
            db.commit()
            flash("Account created! Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("That email is already registered.", "danger")
        except Exception as ex:
            flash(f"Error: {ex}", "danger")

    return render_template("signup.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("welcome"))


# ══════════════════════════════════════════════
if __name__ == "__main__":
    app.run(debug=True)
