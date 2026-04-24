import os
import sqlite3
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "uganda_coach_secret_2026")
app.permanent_session_lifetime = timedelta(hours=24)

# Render sits behind a reverse proxy — required so Flask sees HTTPS correctly
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Session cookies must be Secure on Render (HTTPS) and SameSite=Lax to survive redirects
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

DATABASE = os.path.join(os.path.dirname(__file__), "database.db")

SPORTS = [
    "Athletics", "Chess", "Checkers", "Football", "Gym/Fitness",
    "Handball", "Netball", "Scrabble", "Swimming", "Volleyball",
]

# ---------------------------------------------------------------------------
# HARD-CODED ADMIN CREDENTIALS  ← THIS IS THE LOGIN YOU WANT
# ---------------------------------------------------------------------------
ADMIN_USERNAME = "FAROUK"
ADMIN_PASSWORD = "FAROUK2020"

# ---------------------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------------------
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

def init_db():
    conn = sqlite3.connect(DATABASE)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS coaches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT,
            phone TEXT,
            sport TEXT,
            bio TEXT,
            location TEXT,
            image_url TEXT,
            is_verified INTEGER DEFAULT 0,
            payment_status TEXT DEFAULT 'pending'
        );
        CREATE INDEX IF NOT EXISTS idx_coaches_sport ON coaches(sport);
        CREATE INDEX IF NOT EXISTS idx_coaches_status ON coaches(payment_status, is_verified);
    """)
    conn.commit()
    conn.close()

# Run at import time so gunicorn (Render) initializes the DB on boot
init_db()

# ---------------------------------------------------------------------------
# ROUTES
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    db = get_db()
    coaches = db.execute(
        "SELECT * FROM coaches WHERE is_verified = 1 AND payment_status = 'paid'"
    ).fetchall()
    return render_template("student.html", coaches=coaches, sports=SPORTS)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_id = (request.form.get("login_id") or "").strip()
        password = request.form.get("password") or ""

        # ---- ADMIN BYPASS (hardcoded) ----
        if login_id.upper() == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session.permanent = True
            session["user_id"] = "admin"
            session["is_admin"] = True
            flash("Welcome, FAROUK!", "success")
            return redirect(url_for("admin"))

        # ---- COACH LOGIN ----
        db = get_db()
        user = db.execute(
            "SELECT * FROM coaches WHERE username = ? OR email = ?",
            (login_id, login_id),
        ).fetchone()

        if user and (
            check_password_hash(user["password"], password)
            or user["password"] == password  # legacy plaintext fallback
        ):
            session.permanent = True
            session["user_id"] = user["id"]
            session["is_admin"] = False
            return redirect(url_for("coach_dashboard"))

        flash("Invalid username or password.", "danger")

    return render_template("login.html")

@app.route("/signup", methods=["GET", "POST"])
@app.route("/register", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not (username and email and password):
            flash("All fields are required.", "danger")
            return render_template("signup.html")

        try:
            db = get_db()
            db.execute(
                "INSERT INTO coaches (username, email, password) VALUES (?, ?, ?)",
                (username, email, generate_password_hash(password)),
            )
            db.commit()
            flash("Account created — please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("That username or email is already taken.", "danger")

    return render_template("signup.html")

@app.route("/coach", methods=["GET", "POST"])
def coach_dashboard():
    if "user_id" not in session or session.get("is_admin"):
        return redirect(url_for("login"))

    db = get_db()

    if request.method == "POST":
        db.execute(
            """UPDATE coaches SET full_name=?, phone=?, sport=?, bio=?,
               location=?, image_url=?, payment_status='submitted'
               WHERE id=?""",
            (
                request.form.get("full_name"),
                request.form.get("phone"),
                request.form.get("sport"),
                request.form.get("bio"),
                request.form.get("location"),
                request.form.get("image_url"),
                session["user_id"],
            ),
        )
        db.commit()
        flash("Profile saved — awaiting admin approval.", "success")
        return redirect(url_for("coach_dashboard"))

    coach = db.execute(
        "SELECT * FROM coaches WHERE id = ?", (session["user_id"],)
    ).fetchone()
    return render_template("coach.html", coach=coach, sports=SPORTS)

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    db = get_db()

    if request.method == "POST":
        action = request.form.get("action")
        cid = request.form.get("coach_id")
        if action == "approve" and cid:
            db.execute(
                "UPDATE coaches SET is_verified=1, payment_status='paid' WHERE id=?",
                (cid,),
            )
        elif action == "remove" and cid:
            db.execute(
                "UPDATE coaches SET is_verified=0, payment_status='pending' WHERE id=?",
                (cid,),
            )
        elif action == "delete" and cid:
            db.execute("DELETE FROM coaches WHERE id=?", (cid,))
        db.commit()
        return redirect(url_for("admin"))

    pending = db.execute(
        "SELECT * FROM coaches WHERE is_verified = 0"
    ).fetchall()
    verified = db.execute(
        "SELECT * FROM coaches WHERE is_verified = 1"
    ).fetchall()
    return render_template(
        "admin.html", pending=pending, verified=verified, sports=SPORTS
    )

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ---------------------------------------------------------------------------
# ERROR HANDLERS — never return a blank Render 500
# ---------------------------------------------------------------------------
@app.errorhandler(404)
def not_found(e):
    return redirect(url_for("index"))

@app.errorhandler(500)
def server_error(e):
    flash("Something went wrong. Please try again.", "danger")
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
