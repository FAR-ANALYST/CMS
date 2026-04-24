import os
import sqlite3
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "uganda_gold_2026_final")
app.permanent_session_lifetime = timedelta(hours=24)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# File Upload Setup
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DATABASE = "database.db"
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
    if db: db.close()

# --- THE GATEKEEPER ---
@app.before_request
def require_login():
    allowed = ['welcome', 'login', 'signup', 'static']
    if request.endpoint not in allowed and 'user_id' not in session:
        return redirect(url_for('welcome'))

# --- CORE ROUTES ---

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
    if cat or loc:
        if cat: query += " AND category = ?"; params.append(cat)
        if loc: query += " AND location LIKE ?"; params.append(f"%{loc}%")
    else:
        query += " LIMIT 8" # Limit to 8 coaches on immediate load
    coaches = db.execute(query, params).fetchall()
    return render_template("student.html", coaches=coaches, SPORTS=SPORTS)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        lid = request.form.get("login_id", "").strip()
        pwd = request.form.get("password", "")
        if lid.upper() == ADMIN_USERNAME and pwd == ADMIN_PASSWORD:
            session.update({"user_id": "admin", "is_admin": True})
            return redirect(url_for("admin"))
        user = get_db().execute("SELECT * FROM coaches WHERE username=? OR email=?", (lid, lid)).fetchone()
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
            return redirect(url_for("login"))
        except: flash("User already exists", "danger")
    return render_template("signup.html")

@app.route("/coach")
def coach_dashboard():
    db = get_db()
    u_id = session.get("user_id")
    if session.get("is_admin"):
        submissions = db.execute("SELECT * FROM coaches").fetchall()
    else:
        submissions = db.execute("SELECT * FROM coaches WHERE id = ?", (u_id,)).fetchall()
    return render_template("coach.html", submissions=submissions, SPORTS=SPORTS)

@app.route("/coach/submit", methods=["POST"])
def coach_submit():
    db = get_db()
    u_id = session.get("user_id")
    img_url = request.form.get("existing_image")
    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename != '':
            fn = secure_filename(f"up_{u_id}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
            img_url = f"/static/uploads/{fn}"
    db.execute("""UPDATE coaches SET full_name=?, phone=?, category=?, location=?, bio=?, image_url=?, 
                  payment_status='submitted', is_verified=0 WHERE id=?""",
               (request.form.get("full_name"), request.form.get("phone"), request.form.get("category"),
                request.form.get("location"), request.form.get("bio"), img_url, u_id))
    db.commit()
    return redirect(url_for("coach_dashboard"))

# --- ADMIN ROUTES ---

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not session.get("is_admin"): return redirect(url_for("login"))
    db = get_db()
    if request.method == "POST" and request.form.get("action") == "quick_add":
        img = ""
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '':
                fn = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
                img = f"/static/uploads/{fn}"
        db.execute("""INSERT INTO coaches (full_name, phone, category, location, bio, image_url, is_verified, payment_status, username, email, password) 
                      VALUES (?,?,?,?,?,?,1,'paid',?,?,'admin_pass')""", 
                   (request.form.get("full_name"), request.form.get("phone"), request.form.get("category"), 
                    request.form.get("location"), request.form.get("bio"), img, request.form.get("full_name"), f"{request.form.get('full_name')}@system.com"))
        db.commit()
    pending = db.execute("SELECT * FROM coaches WHERE is_verified = 0 AND full_name IS NOT NULL").fetchall()
    live = db.execute("SELECT * FROM coaches WHERE is_verified = 1").fetchall()
    return render_template("admin.html", pending=pending, live=live, SPORTS=SPORTS)

@app.route("/admin/approve/<int:sub_id>", methods=["POST"])
def admin_approve(sub_id):
    get_db().execute("UPDATE coaches SET is_verified=1, payment_status='paid' WHERE id=?", (sub_id,))
    get_db().commit()
    return redirect(url_for("admin"))

@app.route("/admin/delete/<int:sub_id>", methods=["POST"])
def admin_delete(sub_id):
    get_db().execute("DELETE FROM coaches WHERE id=?", (sub_id,))
    get_db().commit()
    return redirect(url_for("admin"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("welcome"))

# Initialize Database
with app.app_context():
    get_db().execute("CREATE TABLE IF NOT EXISTS coaches (id INTEGER PRIMARY KEY, username, email, password, full_name, phone, category, bio, location, image_url, is_verified DEFAULT 0, payment_status DEFAULT 'pending')")
    get_db().commit()

if __name__ == "__main__":
    app.run(debug=True)
