import os
import sqlite3
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "uganda_gold_secret_2026")
app.permanent_session_lifetime = timedelta(hours=24)

# Production Proxy Fix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

DATABASE = os.path.join(os.path.dirname(__file__), "database.db")
SPORTS = ["Athletics", "Chess", "Checkers", "Football", "Gym/Fitness", "Handball", "Netball", "Scrabble", "Swimming", "Volleyball"]

# SUPER ADMIN CREDENTIALS
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
    if db is not None: db.close()

def init_db():
    with app.app_context():
        db = get_db()
        db.executescript("""
            CREATE TABLE IF NOT EXISTS coaches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL, 
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL, 
                full_name TEXT, 
                phone TEXT,
                category TEXT, 
                bio TEXT, 
                location TEXT, 
                image_url TEXT,
                experience_years INTEGER DEFAULT 0,
                hourly_rate INTEGER DEFAULT 0,
                is_verified INTEGER DEFAULT 0, 
                payment_status TEXT DEFAULT 'pending'
            );
        """)
        db.commit()

init_db()

# ---------------------------------------------------------------------------
# LOGIN & LOGOUT
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_id = (request.form.get("login_id") or "").strip()
        password = request.form.get("password") or ""

        if login_id.upper() == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session.update({"user_id": "admin", "is_admin": True})
            return redirect(url_for("admin"))

        db = get_db()
        user = db.execute("SELECT * FROM coaches WHERE username = ? OR email = ?", (login_id, login_id)).fetchone()
        if user and (check_password_hash(user["password"], password) or user["password"] == password):
            session.update({"user_id": user["id"], "is_admin": False})
            return redirect(url_for("coach_dashboard"))
        
        flash("Access Denied: Invalid Credentials", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ---------------------------------------------------------------------------
# STUDENT / HOME
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    db = get_db()
    category = request.args.get('category', '')
    location = request.args.get('location', '')
    query = "SELECT * FROM coaches WHERE is_verified = 1 AND payment_status = 'paid'"
    params = []
    if category:
        query += " AND category = ?"; params.append(category)
    if location:
        query += " AND location LIKE ?"; params.append(f"%{location}%")
    
    coaches = db.execute(query, params).fetchall()
    return render_template("student.html", coaches=coaches, SPORTS=SPORTS, category=category, location=location)

# ---------------------------------------------------------------------------
# COACH ROUTES (Matching your coach.html)
# ---------------------------------------------------------------------------
@app.route("/coach")
def coach_dashboard():
    if "user_id" not in session or session.get("is_admin"): return redirect(url_for("login"))
    db = get_db()
    submissions = db.execute("SELECT * FROM coaches WHERE id = ?", (session["user_id"],)).fetchall()
    return render_template("coach.html", submissions=submissions, SPORTS=SPORTS)

@app.route("/coach/submit", methods=["POST"])
def coach_submit():
    db = get_db()
    db.execute("UPDATE coaches SET full_name=?, phone=?, category=?, location=?, bio=?, payment_status='submitted' WHERE id=?",
               (request.form.get("full_name"), request.form.get("phone"), request.form.get("category"),
                request.form.get("location"), request.form.get("bio"), session["user_id"]))
    db.commit()
    flash("Profile submitted to FAROUK for approval.", "success")
    return redirect(url_for("coach_dashboard"))

@app.route("/coach/edit/<int:sub_id>", methods=["POST"])
def coach_edit(sub_id):
    db = get_db()
    db.execute("UPDATE coaches SET full_name=?, phone=?, category=?, location=?, bio=? WHERE id=?",
               (request.form.get("full_name"), request.form.get("phone"), request.form.get("category"),
                request.form.get("location"), request.form.get("bio"), sub_id))
    db.commit()
    return redirect(url_for("coach_dashboard"))

@app.route("/coach/delete/<int:sub_id>", methods=["POST"])
def coach_delete(sub_id):
    db = get_db()
    db.execute("DELETE FROM coaches WHERE id=?", (sub_id,))
    db.commit()
    return redirect(url_for("coach_dashboard"))

# ---------------------------------------------------------------------------
# ADMIN ROUTES (Matching your admin.html)
# ---------------------------------------------------------------------------
@app.route("/admin")
def admin():
    if not session.get("is_admin"): return redirect(url_for("login"))
    db = get_db()
    pending = db.execute("SELECT * FROM coaches WHERE is_verified = 0 AND full_name IS NOT NULL").fetchall()
    live = db.execute("SELECT * FROM coaches WHERE is_verified = 1").fetchall()
    return render_template("admin.html", pending=pending, live=live, SPORTS=SPORTS)

@app.route("/admin/add", methods=["POST"])
def admin_add():
    # Admin quick add logic
    return redirect(url_for("admin"))

@app.route("/admin/approve/<int:sub_id>", methods=["POST"])
def admin_approve(sub_id):
    db = get_db()
    db.execute("UPDATE coaches SET is_verified=1, payment_status='paid' WHERE id=?", (sub_id,))
    db.commit()
    return redirect(url_for("admin"))

@app.route("/admin/unapprove/<int:sub_id>", methods=["POST"])
def admin_unapprove(sub_id):
    db = get_db()
    db.execute("UPDATE coaches SET is_verified=0, payment_status='pending' WHERE id=?", (sub_id,))
    db.commit()
    return redirect(url_for("admin"))

@app.route("/admin/delete/<int:sub_id>", methods=["POST"])
def admin_delete(sub_id):
    db = get_db()
    db.execute("DELETE FROM coaches WHERE id=?", (sub_id,))
    db.commit()
    return redirect(url_for("admin"))

# SIGNUP (Missing from your HTML redirects but needed)
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        u, e, p = request.form.get("username"), request.form.get("email"), request.form.get("password")
        try:
            db = get_db()
            db.execute("INSERT INTO coaches (username, email, password) VALUES (?, ?, ?)", (u, e.lower(), generate_password_hash(p)))
            db.commit()
            return redirect(url_for("login"))
        except: return "Signup Error"
    return render_template("signup.html")

if __name__ == "__main__":
    app.run(debug=True)
