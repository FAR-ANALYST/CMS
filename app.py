import os
import sqlite3
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "uganda_gold_2026_super")
app.permanent_session_lifetime = timedelta(hours=24)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

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
    if db is not None: db.close()

# --- THE GATEKEEPER FIX ---
@app.before_request
def require_login():
    # Allow these endpoints to load without being logged in
    allowed = ['welcome', 'login', 'signup', 'static']
    if request.endpoint not in allowed and 'user_id' not in session:
        return redirect(url_for('welcome'))

# --- ROUTES ---

@app.route("/welcome")
def welcome():
    return render_template("welcome.html")

@app.route("/")
def index():
    db = get_db()
    cat = request.args.get('category', '')
    loc = request.args.get('location', '')
    query = "SELECT * FROM coaches WHERE is_verified = 1 AND payment_status = 'paid'"
    params = []
    if cat: query += " AND category = ?"; params.append(cat)
    if loc: query += " AND location LIKE ?"; params.append(f"%{loc}%")
    coaches = db.execute(query, params).fetchall()
    return render_template("student.html", coaches=coaches, SPORTS=SPORTS, category=cat, location=loc)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        lid = (request.form.get("login_id") or "").strip()
        pwd = (request.form.get("password") or "")

        if lid.upper() == ADMIN_USERNAME and pwd == ADMIN_PASSWORD:
            session.update({"user_id": "admin", "is_admin": True})
            return redirect(url_for("admin"))

        db = get_db()
        user = db.execute("SELECT * FROM coaches WHERE username=? OR email=?", (lid, lid)).fetchone()
        if user and (check_password_hash(user["password"], pwd) or user["password"] == pwd):
            session.update({"user_id": user["id"], "is_admin": False})
            return redirect(url_for("index"))
        
        flash("Invalid Credentials", "danger")
    return render_template("login.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        u, e, p = request.form.get("username"), request.form.get("email"), request.form.get("password")
        try:
            db = get_db()
            db.execute("INSERT INTO coaches (username, email, password) VALUES (?, ?, ?)", 
                       (u, e.lower(), generate_password_hash(p)))
            db.commit()
            flash("Account created!", "success")
            return redirect(url_for("login"))
        except:
            flash("Error creating account.", "danger")
    return render_template("signup.html")

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not session.get("is_admin"): return redirect(url_for("login"))
    db = get_db()
    if request.method == "POST" and request.form.get("action") == "quick_add":
        db.execute("""INSERT INTO coaches (full_name, phone, category, location, bio, is_verified, payment_status, username, email, password) 
                      VALUES (?,?,?,?,?,1,'paid', ?, ?, 'added_by_admin')""", 
                   (request.form.get("full_name"), request.form.get("phone"), request.form.get("category"), 
                    request.form.get("location"), request.form.get("bio"), 
                    request.form.get("full_name").replace(" ","_").lower(), 
                    request.form.get("full_name").replace(" ","") + "@system.com"))
        db.commit()
        return redirect(url_for("admin"))

    pending = db.execute("SELECT * FROM coaches WHERE is_verified = 0 AND full_name IS NOT NULL").fetchall()
    live = db.execute("SELECT * FROM coaches WHERE is_verified = 1").fetchall()
    return render_template("admin.html", pending=pending, live=live, SPORTS=SPORTS)

@app.route("/admin/approve/<int:sub_id>", methods=["POST"])
def admin_approve(sub_id):
    db = get_db()
    db.execute("UPDATE coaches SET is_verified=1, payment_status='paid' WHERE id=?", (sub_id,))
    db.commit()
    return redirect(url_for("admin"))

@app.route("/admin/delete/<int:sub_id>", methods=["POST"])
def admin_delete(sub_id):
    db = get_db()
    db.execute("DELETE FROM coaches WHERE id=?", (sub_id,))
    db.commit()
    return redirect(url_for("admin"))

@app.route("/coach")
def coach_dashboard():
    if "user_id" not in session or session.get("is_admin"): return redirect(url_for("login"))
    db = get_db()
    submissions = db.execute("SELECT * FROM coaches WHERE id = ?", (session["user_id"],)).fetchall()
    return render_template("coach.html", submissions=submissions, SPORTS=SPORTS)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("welcome"))

with app.app_context():
    get_db().execute("""CREATE TABLE IF NOT EXISTS coaches (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, email TEXT, password TEXT,
        full_name TEXT, phone TEXT, category TEXT, bio TEXT, location TEXT, 
        is_verified INTEGER DEFAULT 0, payment_status TEXT DEFAULT 'pending')""")
    get_db().commit()

if __name__ == "__main__":
    app.run(debug=True)
