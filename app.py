import os
import sqlite3
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "uganda_coach_secret_2026")
app.permanent_session_lifetime = timedelta(hours=24)

# Render / Proxy Config
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

DATABASE = os.path.join(os.path.dirname(__file__), "database.db")
SPORTS = ["Athletics", "Chess", "Checkers", "Football", "Gym/Fitness", "Handball", "Netball", "Scrabble", "Swimming", "Volleyball"]

ADMIN_USERNAME = "FAROUK"
ADMIN_PASSWORD = "FAROUK2020"

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
    with app.app_context():
        db = get_db()
        db.executescript("""
            CREATE TABLE IF NOT EXISTS coaches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL, email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL, full_name TEXT, phone TEXT,
                sport TEXT, bio TEXT, location TEXT, image_url TEXT,
                is_verified INTEGER DEFAULT 0, payment_status TEXT DEFAULT 'pending'
            );
        """)
        db.commit()

init_db()

@app.route("/")
def index():
    db = get_db()
    coaches = db.execute("SELECT * FROM coaches WHERE is_verified = 1 AND payment_status = 'paid'").fetchall()
    return render_template("student.html", coaches=coaches, sports=SPORTS)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_id = (request.form.get("login_id") or "").strip()
        password = request.form.get("password") or ""

        # Admin Logic
        if login_id.upper() == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session.permanent = True
            session["user_id"] = "admin"
            session["is_admin"] = True
            return redirect(url_for("admin"))

        # Coach Logic
        db = get_db()
        user = db.execute("SELECT * FROM coaches WHERE username = ? OR email = ?", (login_id, login_id)).fetchone()
        if user and (check_password_hash(user["password"], password) or user["password"] == password):
            session.permanent = True
            session["user_id"] = user["id"]
            session["is_admin"] = False
            return redirect(url_for("coach_dashboard"))
        
        flash("Invalid credentials.", "danger")
    return render_template("login.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        try:
            db = get_db()
            db.execute("INSERT INTO coaches (username, email, password) VALUES (?, ?, ?)",
                       (username, email, generate_password_hash(password)))
            db.commit()
            flash("Account created! Please log in.", "success")
            return redirect(url_for("login"))
        except:
            flash("Error: Username/Email taken.", "danger")
    return render_template("signup.html")

@app.route("/coach", methods=["GET", "POST"])
def coach_dashboard():
    if "user_id" not in session or session.get("is_admin"):
        return redirect(url_for("login"))
    db = get_db()
    if request.method == "POST":
        db.execute("UPDATE coaches SET full_name=?, phone=?, sport=?, bio=?, location=?, image_url=?, payment_status='submitted' WHERE id=?",
                   (request.form.get("full_name"), request.form.get("phone"), request.form.get("sport"), 
                    request.form.get("bio"), request.form.get("location"), request.form.get("image_url"), session["user_id"]))
        db.commit()
        flash("Profile updated.", "success")
    coach = db.execute("SELECT * FROM coaches WHERE id = ?", (session["user_id"],)).fetchone()
    return render_template("coach.html", coach=coach, sports=SPORTS)

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not session.get("is_admin"):
        return redirect(url_for("login"))
    db = get_db()
    if request.method == "POST":
        action, cid = request.form.get("action"), request.form.get("coach_id")
        if action == "approve": db.execute("UPDATE coaches SET is_verified=1, payment_status='paid' WHERE id=?", (cid,))
        elif action == "delete": db.execute("DELETE FROM coaches WHERE id=?", (cid,))
        db.commit()
    pending = db.execute("SELECT * FROM coaches WHERE is_verified = 0").fetchall()
    verified = db.execute("SELECT * FROM coaches WHERE is_verified = 1").fetchall()
    return render_template("admin.html", pending=pending, verified=verified, sports=SPORTS)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)
