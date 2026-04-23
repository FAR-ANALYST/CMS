"""
Get My Coach Uganda — Flask backend (Render-ready, hardened)
Black & Gold theme. Single source of truth for sport categories.
"""
import os
import uuid
import traceback
from functools import wraps
from datetime import timedelta

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify
)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production-please")

# Render sits behind a reverse proxy — required for HTTPS + secure cookies.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Session cookie hardening (works on both localhost & Render)
app.config.update(
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") != "development",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=24),
)

# ---------------------------------------------------------------------------
# Single source of truth — sport categories
# ---------------------------------------------------------------------------
SPORTS = [
    "Athletics", "Checkers", "Chess", "Football", "Gym/Fitness",
    "Handball", "Netball", "Scrabble", "Swimming", "Volleyball",
]

ADMIN_USERNAME = "FAROUK"
ADMIN_PASSWORD = "FAROUK"   # change in production via env var if needed

# ---------------------------------------------------------------------------
# Lazy Supabase client (won't crash startup if env vars missing)
# ---------------------------------------------------------------------------
_supabase = None

def get_supabase():
    global _supabase
    if _supabase is not None:
        return _supabase
    try:
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
        if not url or not key:
            print("[WARN] SUPABASE_URL / SUPABASE_KEY not set — DB calls will fail.")
            return None
        _supabase = create_client(url, key)
        return _supabase
    except Exception as e:
        print(f"[ERROR] Supabase init failed: {e}")
        return None

# ---------------------------------------------------------------------------
# Auth decorators
# ---------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrap

def admin_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admin access only.", "danger")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrap

# ---------------------------------------------------------------------------
# Routes — Auth
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    # Always render the login page; no auto-redirect (prevents loops on Render).
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_id = (request.form.get("login_id") or "").strip()
        password = (request.form.get("password") or "").strip()

        if not login_id or not password:
            flash("Please enter both username/email and password.", "danger")
            return render_template("login.html")

        # Hard-coded super-admin shortcut
        if login_id.upper() == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session.permanent = True
            session["user_id"] = "admin-farouk"
            session["username"] = "FAROUK"
            session["role"] = "admin"
            flash("Welcome, Admin FAROUK.", "success")
            return redirect(url_for("admin"))

        sb = get_supabase()
        if sb is None:
            flash("Backend not configured. Contact administrator.", "danger")
            return render_template("login.html")

        try:
            # Try username first, then email — avoids OR-filter quoting issues.
            res = sb.table("coach_users").select("*").eq("username", login_id).limit(1).execute()
            user = res.data[0] if res.data else None
            if not user:
                res = sb.table("coach_users").select("*").eq("email", login_id).limit(1).execute()
                user = res.data[0] if res.data else None

            if not user or not check_password_hash(user.get("password_hash", ""), password):
                flash("Invalid credentials.", "danger")
                return render_template("login.html")

            session.permanent = True
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user.get("role", "coach")
            flash(f"Welcome back, {user['username']}.", "success")
            return redirect(url_for("admin" if session["role"] == "admin" else "coach"))

        except Exception as e:
            print(f"[ERROR] Login failed: {e}")
            traceback.print_exc()
            flash("Login error. Please try again.", "danger")
            return render_template("login.html")

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
@app.route("/signup", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()

        if not all([username, email, password]):
            flash("All fields are required.", "danger")
            return render_template("login.html", show_register=True)

        sb = get_supabase()
        if sb is None:
            flash("Backend not configured.", "danger")
            return render_template("login.html", show_register=True)

        try:
            new_user = {
                "id": str(uuid.uuid4()),
                "username": username,
                "email": email,
                "password_hash": generate_password_hash(password),
                "role": "coach",
            }
            sb.table("coach_users").insert(new_user).execute()

            # Create the empty profile row, awaiting admin verification later.
            sb.table("coach_profiles").insert({
                "user_id": new_user["id"],
                "full_name": username,
                "is_verified": False,
                "payment_status": "pending",
            }).execute()

            flash("Account created. Please log in.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            print(f"[ERROR] Signup failed: {e}")
            flash("Could not create account. Username/email may exist.", "danger")
            return render_template("login.html", show_register=True)

    return render_template("login.html", show_register=True)

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("login"))

# ---------------------------------------------------------------------------
# Routes — Coach
# ---------------------------------------------------------------------------
@app.route("/coach", methods=["GET", "POST"])
@login_required
def coach():
    sb = get_supabase()
    if sb is None:
        flash("Backend not configured.", "danger")
        return redirect(url_for("login"))

    user_id = session["user_id"]

    if request.method == "POST":
        try:
            data = {
                "full_name": request.form.get("full_name", "").strip(),
                "phone": request.form.get("phone", "").strip(),
                "category": request.form.get("category", "").strip(),
                "location": request.form.get("location", "").strip(),
                "bio": request.form.get("bio", "").strip(),
                "experience_years": int(request.form.get("experience_years") or 0),
                "hourly_rate": int(request.form.get("hourly_rate") or 0),
                "image_url": request.form.get("image_url", "").strip() or None,
            }

            # Existing?
            existing = sb.table("coach_profiles").select("*").eq("user_id", user_id).execute()
            if existing.data:
                current = existing.data[0]
                # If already paid+verified, keep status; otherwise mark submitted.
                if not (current.get("is_verified") and current.get("payment_status") == "paid"):
                    data["payment_status"] = "submitted"
                sb.table("coach_profiles").update(data).eq("user_id", user_id).execute()
                flash("Profile updated.", "success")
            else:
                data["user_id"] = user_id
                data["payment_status"] = "submitted"
                data["is_verified"] = False
                sb.table("coach_profiles").insert(data).execute()
                flash("Profile submitted to admin for approval.", "success")

            return redirect(url_for("coach"))
        except Exception as e:
            print(f"[ERROR] Coach save: {e}")
            flash("Could not save profile.", "danger")

    # GET — load current profile
    profile = {}
    try:
        res = sb.table("coach_profiles").select("*").eq("user_id", user_id).limit(1).execute()
        if res.data:
            profile = res.data[0]
    except Exception as e:
        print(f"[ERROR] Coach load: {e}")

    return render_template("coach.html", profile=profile, sports=SPORTS)

# ---------------------------------------------------------------------------
# Routes — Admin
# ---------------------------------------------------------------------------
@app.route("/admin")
@admin_required
def admin():
    sb = get_supabase()
    pending, live = [], []
    if sb is not None:
        try:
            res = sb.table("coach_profiles").select("*").execute()
            for p in (res.data or []):
                if p.get("is_verified") and p.get("payment_status") == "paid":
                    live.append(p)
                else:
                    pending.append(p)
        except Exception as e:
            print(f"[ERROR] Admin load: {e}")
            flash("Could not load profiles.", "danger")
    return render_template("admin.html", pending=pending, live=live, sports=SPORTS)

@app.route("/admin/approve/<user_id>", methods=["POST"])
@admin_required
def admin_approve(user_id):
    sb = get_supabase()
    if sb is not None:
        try:
            sb.table("coach_profiles").update({
                "is_verified": True,
                "payment_status": "paid",
            }).eq("user_id", user_id).execute()
            flash("Coach approved and now live.", "success")
        except Exception as e:
            print(f"[ERROR] Approve: {e}")
            flash("Could not approve coach.", "danger")
    return redirect(url_for("admin"))

@app.route("/admin/remove/<user_id>", methods=["POST"])
@admin_required
def admin_remove(user_id):
    sb = get_supabase()
    if sb is not None:
        try:
            sb.table("coach_profiles").update({
                "is_verified": False,
                "payment_status": "pending",
            }).eq("user_id", user_id).execute()
            flash("Coach removed from public listing.", "info")
        except Exception as e:
            print(f"[ERROR] Remove: {e}")
            flash("Could not remove coach.", "danger")
    return redirect(url_for("admin"))

@app.route("/admin/add_coach", methods=["POST"])
@admin_required
def admin_add_coach():
    """Admin adds a coach directly — goes live instantly, no approval queue."""
    sb = get_supabase()
    if sb is None:
        flash("Backend not configured.", "danger")
        return redirect(url_for("admin"))

    try:
        new_id = str(uuid.uuid4())
        sb.table("coach_profiles").insert({
            "user_id": new_id,
            "full_name": request.form.get("full_name", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "category": request.form.get("category", "").strip(),
            "location": request.form.get("location", "").strip(),
            "bio": request.form.get("bio", "").strip(),
            "experience_years": int(request.form.get("experience_years") or 0),
            "hourly_rate": int(request.form.get("hourly_rate") or 0),
            "image_url": request.form.get("image_url", "").strip() or None,
            "is_verified": True,
            "payment_status": "paid",
        }).execute()
        flash("Coach added directly and now live on the student page.", "success")
    except Exception as e:
        print(f"[ERROR] Admin add coach: {e}")
        flash("Could not add coach.", "danger")
    return redirect(url_for("admin"))

# ---------------------------------------------------------------------------
# Routes — Student (public)
# ---------------------------------------------------------------------------
@app.route("/student")
def student():
    sb = get_supabase()
    coaches = []
    locations = []
    if sb is not None:
        try:
            res = (sb.table("coach_profiles")
                   .select("*")
                   .eq("is_verified", True)
                   .eq("payment_status", "paid")
                   .execute())
            coaches = res.data or []
            locations = sorted({c.get("location") for c in coaches if c.get("location")})
        except Exception as e:
            print(f"[ERROR] Student load: {e}")

    sport_filter = request.args.get("sport", "").strip()
    location_filter = request.args.get("location", "").strip()

    if sport_filter:
        coaches = [c for c in coaches if (c.get("category") or "") == sport_filter]
    if location_filter:
        coaches = [c for c in coaches if (c.get("location") or "") == location_filter]

    return render_template(
        "student.html",
        coaches=coaches,
        sports=SPORTS,
        locations=locations,
        sport_filter=sport_filter,
        location_filter=location_filter,
    )

# ---------------------------------------------------------------------------
# Health & error handlers
# ---------------------------------------------------------------------------
@app.route("/health")
def health():
    return jsonify(status="ok", supabase=bool(get_supabase()))

@app.errorhandler(404)
def not_found(e):
    return redirect(url_for("login"))

@app.errorhandler(500)
def server_error(e):
    print(f"[500] {e}")
    traceback.print_exc()
    flash("Something went wrong. Please try again.", "danger")
    return redirect(url_for("login"))

@app.errorhandler(Exception)
def unhandled(e):
    print(f"[UNHANDLED] {e}")
    traceback.print_exc()
    flash("Unexpected error. Please try again.", "danger")
    return redirect(url_for("login"))

# ---------------------------------------------------------------------------
# Local dev entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
