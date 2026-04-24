"""
Get My Coach Uganda - Flask App
Hardened for Render deployment with black & gold theme.
"""
import os
import uuid
from functools import wraps
from datetime import timedelta

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, abort
)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash

# ---------- App setup ----------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-change-me-in-production")
app.permanent_session_lifetime = timedelta(hours=24)

# Render runs behind a proxy — required for HTTPS session cookies
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

app.config.update(
    SESSION_COOKIE_SECURE=os.environ.get("RENDER", "") != "",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

# ---------- Constants ----------
SPORTS = [
    "Athletics", "Checkers", "Chess", "Football", "Gym/Fitness",
    "Handball", "Netball", "Scrabble", "Swimming", "Volleyball",
]

DISTRICTS = [
    "Kampala", "Wakiso", "Mukono", "Jinja", "Entebbe", "Mbarara",
    "Gulu", "Lira", "Mbale", "Masaka", "Fort Portal", "Soroti",
]

# ---------- Lazy Supabase client (won't crash startup) ----------
_supabase = None

def get_supabase():
    global _supabase
    if _supabase is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
        if not url or not key:
            return None
        try:
            from supabase import create_client
            _supabase = create_client(url, key)
        except Exception as e:
            app.logger.error(f"Supabase init failed: {e}")
            return None
    return _supabase

# ---------- In-memory fallback store (works without Supabase) ----------
_users = {}     # username -> {id, username, email, password_hash, role}
_coaches = {}   # id -> coach dict

def seed_admin():
    # Default admin
    if "admin" not in _users:
        _users["admin"] = {
            "id": str(uuid.uuid4()),
            "username": "admin",
            "email": "admin@getmycoach.ug",
            "password_hash": generate_password_hash("admin123"),
            "role": "admin",
        }
    # Super-admin: FAROUK / FAROUK2020
    if "FAROUK" not in _users:
        _users["FAROUK"] = {
            "id": str(uuid.uuid4()),
            "username": "FAROUK",
            "email": "farouk@getmycoach.ug",
            "password_hash": generate_password_hash("FAROUK2020"),
            "role": "admin",
        }

seed_admin()

# MTN / Airtel payment details shown on the coach page
PAYMENT_DETAILS = {
    "mtn": "+256 789268324",
    "airtel": "+256 757307541",
}

# ---------- Auth helpers ----------
def login_required(role=None):
    """Require login. Admins can access any role-restricted page."""
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("login"))
            user_role = session.get("role")
            # Admin can access every face
            if role and user_role != role and user_role != "admin":
                flash("You don't have access to that page.", "danger")
                return redirect(url_for("login"))
            return f(*args, **kwargs)
        return wrapper
    return deco

# ---------- Context processor (templates always have these) ----------
@app.context_processor
def inject_globals():
    return {
        "SPORTS": SPORTS,
        "DISTRICTS": DISTRICTS,
        "current_user": {
            "id": session.get("user_id"),
            "username": session.get("username"),
            "role": session.get("role"),
        } if "user_id" in session else None,
    }

# ---------- Routes ----------
@app.route("/")
def index():
    # Always render landing/login — never auto-redirect (avoids cookie loops)
    return render_template("login.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_id = (request.form.get("login_id") or "").strip().lower()
        password = request.form.get("password") or ""

        user = None
        # Look up by username or email in memory store
        for u in _users.values():
            if u["username"].lower() == login_id or (u.get("email") or "").lower() == login_id:
                user = u
                break

        if user and check_password_hash(user["password_hash"], password):
            session.permanent = True
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            flash(f"Welcome back, {user['username']}!", "success")
            if user["role"] == "admin":
                return redirect(url_for("admin"))
            elif user["role"] == "coach":
                return redirect(url_for("coach"))
            else:
                return redirect(url_for("student"))

        flash("Invalid username/email or password.", "danger")
        return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/signup", methods=["GET", "POST"])
@app.route("/register", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        role = request.form.get("role") or "student"

        if not username or not password:
            flash("Username and password are required.", "danger")
            return redirect(url_for("signup"))
        if username.lower() in (u.lower() for u in _users):
            flash("Username already taken.", "danger")
            return redirect(url_for("signup"))

        user_id = str(uuid.uuid4())
        _users[username] = {
            "id": user_id,
            "username": username,
            "email": email,
            "password_hash": generate_password_hash(password),
            "role": role if role in ("student", "coach") else "student",
        }
        flash("Account created — please log in.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

# ---------- Student page ----------
@app.route("/student")
def student():
    sport_filter = request.args.get("sport", "").strip()
    location_filter = request.args.get("location", "").strip()

    # Only show verified + paid coaches
    visible = [
        c for c in _coaches.values()
        if c.get("is_verified") and c.get("payment_status") == "paid"
    ]
    if sport_filter:
        visible = [c for c in visible if c.get("category") == sport_filter]
    if location_filter:
        visible = [c for c in visible if c.get("location") == location_filter]

    locations = sorted({
        c["location"] for c in _coaches.values()
        if c.get("is_verified") and c.get("payment_status") == "paid" and c.get("location")
    })

    return render_template(
        "student.html",
        coaches=visible,
        sport_filter=sport_filter,
        location_filter=location_filter,
        locations=locations,
    )

# ---------- Coach page ----------
@app.route("/coach", methods=["GET", "POST"])
@login_required(role="coach")
def coach():
    user_id = session["user_id"]
    profile = _coaches.get(user_id) or {
        "id": user_id,
        "full_name": session.get("username", ""),
        "phone": "", "category": "", "experience_years": 0,
        "hourly_rate": 0, "location": "", "bio": "",
        "image_url": "", "is_verified": False, "payment_status": "pending",
    }

    if request.method == "POST":
        profile.update({
            "full_name": request.form.get("full_name", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "category": request.form.get("category", "").strip(),
            "experience_years": int(request.form.get("experience_years") or 0),
            "hourly_rate": int(request.form.get("hourly_rate") or 0),
            "location": request.form.get("location", "").strip(),
            "bio": request.form.get("bio", "").strip(),
            "image_url": request.form.get("image_url", "").strip(),
        })
        # Move to "submitted" unless already paid/verified
        if profile.get("payment_status") != "paid":
            profile["payment_status"] = "submitted"
        _coaches[user_id] = profile
        flash("Profile saved — awaiting admin approval.", "success")
        return redirect(url_for("coach"))

    return render_template("coach.html", profile=profile, payment_details=PAYMENT_DETAILS)

# ---------- Admin page ----------
@app.route("/admin")
@login_required(role="admin")
def admin():
    pending = [c for c in _coaches.values() if c.get("payment_status") == "submitted"]
    live = [
        c for c in _coaches.values()
        if c.get("payment_status") == "paid" and c.get("is_verified")
    ]
    return render_template("admin.html", pending=pending, live=live)

@app.route("/admin/approve/<coach_id>", methods=["POST"])
@login_required(role="admin")
def admin_approve(coach_id):
    if coach_id in _coaches:
        _coaches[coach_id]["is_verified"] = True
        _coaches[coach_id]["payment_status"] = "paid"
        flash("Coach approved and now live.", "success")
    return redirect(url_for("admin"))

@app.route("/admin/remove/<coach_id>", methods=["POST"])
@login_required(role="admin")
def admin_remove(coach_id):
    if coach_id in _coaches:
        _coaches[coach_id]["is_verified"] = False
        _coaches[coach_id]["payment_status"] = "pending"
        flash("Coach removed from live listings.", "info")
    return redirect(url_for("admin"))

@app.route("/admin/add_coach", methods=["POST"])
@login_required(role="admin")
def admin_add_coach():
    cid = str(uuid.uuid4())
    _coaches[cid] = {
        "id": cid,
        "full_name": request.form.get("full_name", "").strip(),
        "phone": request.form.get("phone", "").strip(),
        "category": request.form.get("category", "").strip(),
        "experience_years": int(request.form.get("experience_years") or 0),
        "hourly_rate": int(request.form.get("hourly_rate") or 0),
        "location": request.form.get("location", "").strip(),
        "bio": request.form.get("bio", "").strip(),
        "image_url": request.form.get("image_url", "").strip(),
        "is_verified": True,
        "payment_status": "paid",
    }
    flash("Coach added directly and is now live.", "success")
    return redirect(url_for("admin"))

# ---------- Health & error handlers ----------
@app.route("/healthz")
def healthz():
    return {"status": "ok"}, 200

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="Page not found"), 404

@app.errorhandler(500)
def server_error(e):
    app.logger.error(f"500 error: {e}")
    return render_template("error.html", code=500, message="Server error"), 500

@app.errorhandler(Exception)
def unhandled(e):
    app.logger.exception(e)
    return render_template("error.html", code=500, message=str(e)), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
