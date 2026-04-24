"""
Get My Coach Uganda - Flask App
- Persistent storage via Supabase (survives restarts, scales to thousands)
- In-memory fallback ONLY when Supabase is unreachable (dev/local use)
- Admin approval is REQUIRED before any coach appears on the student page
- Each coach is stored by unique id — adding/editing one NEVER affects another
"""
import os
import uuid
import base64
import mimetypes
from functools import wraps
from datetime import timedelta

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash
)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash

# ---------- App setup ----------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-change-me-in-production")
app.permanent_session_lifetime = timedelta(hours=24)
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
PAYMENT_DETAILS = {
    "mtn": "+256 789268324",
    "airtel": "+256 757307541",
}

# ---------- Lazy Supabase client ----------
_supabase = None
def get_supabase():
    global _supabase
    if _supabase is None:
        url = os.environ.get("SUPABASE_URL")
        key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
               or os.environ.get("SUPABASE_KEY")
               or os.environ.get("SUPABASE_ANON_KEY"))
        if not url or not key:
            return None
        try:
            from supabase import create_client
            _supabase = create_client(url, key)
        except Exception as e:
            app.logger.error(f"Supabase init failed: {e}")
            return None
    return _supabase

# ---------- In-memory fallback (DEV ONLY — do NOT rely on this in production) ----------
_users_mem = {}
_coaches_mem = {}

def seed_admin_mem():
    if "admin" not in _users_mem:
        _users_mem["admin"] = {
            "id": str(uuid.uuid4()), "username": "admin",
            "email": "admin@getmycoach.ug",
            "password_hash": generate_password_hash("admin123"),
            "role": "admin",
        }
    if "FAROUK" not in _users_mem:
        _users_mem["FAROUK"] = {
            "id": str(uuid.uuid4()), "username": "FAROUK",
            "email": "farouk@getmycoach.ug",
            "password_hash": generate_password_hash("FAROUK2020"),
            "role": "admin",
        }
seed_admin_mem()

# ---------- Data layer (Supabase first, memory fallback) ----------
def find_user(login_id: str):
    """Look up by username or email."""
    sb = get_supabase()
    login_id = login_id.strip().lower()
    if sb:
        try:
            res = sb.table("app_users").select("*").or_(
                f"username.ilike.{login_id},email.ilike.{login_id}"
            ).limit(1).execute()
            if res.data:
                return res.data[0]
        except Exception as e:
            app.logger.error(f"find_user supabase error: {e}")
    # fallback
    for u in _users_mem.values():
        if u["username"].lower() == login_id or (u.get("email") or "").lower() == login_id:
            return u
    return None

def create_user(username, email, password, role):
    sb = get_supabase()
    user = {
        "id": str(uuid.uuid4()),
        "username": username,
        "email": (email or "").lower(),
        "password_hash": generate_password_hash(password),
        "role": role if role in ("student", "coach") else "student",
    }
    if sb:
        try:
            sb.table("app_users").insert(user).execute()
            return user
        except Exception as e:
            app.logger.error(f"create_user supabase error: {e}")
    _users_mem[username] = user
    return user

def get_coach(coach_id):
    sb = get_supabase()
    if sb:
        try:
            res = sb.table("coaches").select("*").eq("id", coach_id).limit(1).execute()
            if res.data:
                return res.data[0]
        except Exception as e:
            app.logger.error(f"get_coach error: {e}")
    return _coaches_mem.get(coach_id)

def upsert_coach(coach_id: str, data: dict):
    """Upsert by id — NEVER touches other rows."""
    data["id"] = coach_id
    sb = get_supabase()
    if sb:
        try:
            sb.table("coaches").upsert(data, on_conflict="id").execute()
            return
        except Exception as e:
            app.logger.error(f"upsert_coach error: {e}")
    # Fallback merge
    existing = _coaches_mem.get(coach_id, {})
    existing.update(data)
    _coaches_mem[coach_id] = existing

def list_coaches(status_filter=None, verified_only=False):
    sb = get_supabase()
    if sb:
        try:
            q = sb.table("coaches").select("*")
            if status_filter:
                q = q.eq("payment_status", status_filter)
            if verified_only:
                q = q.eq("is_verified", True)
            res = q.order("full_name").execute()
            return res.data or []
        except Exception as e:
            app.logger.error(f"list_coaches error: {e}")
    out = list(_coaches_mem.values())
    if status_filter:
        out = [c for c in out if c.get("payment_status") == status_filter]
    if verified_only:
        out = [c for c in out if c.get("is_verified")]
    return out

def update_coach_status(coach_id, *, is_verified, payment_status):
    sb = get_supabase()
    if sb:
        try:
            sb.table("coaches").update({
                "is_verified": is_verified,
                "payment_status": payment_status,
            }).eq("id", coach_id).execute()
            return
        except Exception as e:
            app.logger.error(f"update_coach_status error: {e}")
    if coach_id in _coaches_mem:
        _coaches_mem[coach_id]["is_verified"] = is_verified
        _coaches_mem[coach_id]["payment_status"] = payment_status

# ---------- Image upload helper ----------
COACH_IMAGE_BUCKET = "coach-images"
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB

def handle_image_upload(file_storage, owner_id: str, fallback_url: str = "") -> str:
    """
    Accept a Flask FileStorage (from request.files), validate size/type,
    upload to Supabase Storage if available, else return a base64 data URL.
    Returns the public URL (or fallback_url if no file given).
    """
    if not file_storage or not file_storage.filename:
        return fallback_url

    data = file_storage.read()
    if not data:
        return fallback_url
    if len(data) > MAX_IMAGE_BYTES:
        flash("Image is larger than 5 MB — please choose a smaller photo.", "danger")
        return fallback_url

    mime = file_storage.mimetype or mimetypes.guess_type(file_storage.filename)[0] or "image/jpeg"
    if not mime.startswith("image/"):
        flash("Please upload an image file (JPG or PNG).", "danger")
        return fallback_url

    ext = mimetypes.guess_extension(mime) or ".jpg"
    if ext == ".jpe":
        ext = ".jpg"
    object_path = f"{owner_id}/{uuid.uuid4().hex}{ext}"

    sb = get_supabase()
    if sb:
        try:
            sb.storage.from_(COACH_IMAGE_BUCKET).upload(
                path=object_path,
                file=data,
                file_options={"content-type": mime, "upsert": "true"},
            )
            return sb.storage.from_(COACH_IMAGE_BUCKET).get_public_url(object_path)
        except Exception as e:
            app.logger.error(f"Storage upload failed, falling back to data URL: {e}")

    # Fallback: embed as base64 data URL (works without Supabase Storage)
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"

# ---------- Auth helpers ----------
def login_required(role=None):
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("login"))
            user_role = session.get("role")
            if role and user_role != role and user_role != "admin":
                flash("You don't have access to that page.", "danger")
                return redirect(url_for("login"))
            return f(*args, **kwargs)
        return wrapper
    return deco

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
    return render_template("login.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_id = (request.form.get("login_id") or "").strip()
        password = request.form.get("password") or ""
        user = find_user(login_id)
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
            return redirect(url_for("student"))
        flash("Invalid username/email or password.", "danger")
        return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/signup", methods=["GET", "POST"])
@app.route("/register", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        role = request.form.get("role") or "student"
        if not username or not password:
            flash("Username and password are required.", "danger")
            return redirect(url_for("signup"))
        if find_user(username) or (email and find_user(email)):
            flash("Username or email already taken.", "danger")
            return redirect(url_for("signup"))
        create_user(username, email, password, role)
        flash("Account created — please log in.", "success")
        return redirect(url_for("login"))
    return render_template("signup.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

# ---------- Student ----------
@app.route("/student")
def student():
    sport_filter = request.args.get("sport", "").strip()
    location_filter = request.args.get("location", "").strip()
    visible = [
        c for c in list_coaches(verified_only=True)
        if c.get("payment_status") == "paid"
    ]
    if sport_filter:
        visible = [c for c in visible if c.get("category") == sport_filter]
    if location_filter:
        visible = [c for c in visible if c.get("location") == location_filter]
    locations = sorted({c["location"] for c in visible if c.get("location")})
    return render_template(
        "student.html",
        coaches=visible,
        sport_filter=sport_filter,
        location_filter=location_filter,
        locations=locations,
    )

# ---------- Coach ----------
@app.route("/coach", methods=["GET", "POST"])
@login_required(role="coach")
def coach():
    user_id = session["user_id"]
    profile = get_coach(user_id) or {
        "id": user_id,
        "full_name": session.get("username", ""),
        "phone": "", "category": "", "experience_years": 0,
        "hourly_rate": 0, "location": "", "bio": "",
        "image_url": "", "is_verified": False, "payment_status": "pending",
    }

    if request.method == "POST":
        # Handle uploaded photo (keep existing if no new file chosen)
        new_image_url = handle_image_upload(
            request.files.get("image_file"),
            owner_id=user_id,
            fallback_url=profile.get("image_url", ""),
        )
        updated = {
            "full_name": (request.form.get("full_name") or "").strip(),
            "phone": (request.form.get("phone") or "").strip(),
            "category": (request.form.get("category") or "").strip(),
            "experience_years": int(request.form.get("experience_years") or 0),
            "hourly_rate": int(request.form.get("hourly_rate") or 0),
            "location": (request.form.get("location") or "").strip(),
            "bio": (request.form.get("bio") or "").strip(),
            "image_url": new_image_url,
            # ALWAYS reset to "submitted" on edit — admin must re-approve.
            # This is the rule: coaches NEVER auto-publish to students.
            "is_verified": False,
            "payment_status": "submitted",
        }
        upsert_coach(user_id, updated)
        flash("Profile saved — awaiting admin approval before going live.", "success")
        return redirect(url_for("coach"))

    return render_template("coach.html", profile=profile, payment_details=PAYMENT_DETAILS)

# ---------- Admin ----------
@app.route("/admin")
@login_required(role="admin")
def admin():
    pending = list_coaches(status_filter="submitted")
    live = [c for c in list_coaches(verified_only=True) if c.get("payment_status") == "paid"]
    return render_template("admin.html", pending=pending, live=live)

@app.route("/admin/approve/<coach_id>", methods=["POST"])
@login_required(role="admin")
def admin_approve(coach_id):
    update_coach_status(coach_id, is_verified=True, payment_status="paid")
    flash("Coach approved and now live on the student page.", "success")
    return redirect(url_for("admin"))

@app.route("/admin/remove/<coach_id>", methods=["POST"])
@login_required(role="admin")
def admin_remove(coach_id):
    update_coach_status(coach_id, is_verified=False, payment_status="pending")
    flash("Coach removed from live listings.", "info")
    return redirect(url_for("admin"))

@app.route("/admin/add_coach", methods=["POST"])
@login_required(role="admin")
def admin_add_coach():
    """Admin direct-add: still goes through approval queue (NOT auto-live)."""
    cid = str(uuid.uuid4())
    new_image_url = handle_image_upload(
        request.files.get("image_file"),
        owner_id=cid,
        fallback_url="",
    )
    upsert_coach(cid, {
        "full_name": (request.form.get("full_name") or "").strip(),
        "phone": (request.form.get("phone") or "").strip(),
        "category": (request.form.get("category") or "").strip(),
        "experience_years": int(request.form.get("experience_years") or 0),
        "hourly_rate": int(request.form.get("hourly_rate") or 0),
        "location": (request.form.get("location") or "").strip(),
        "bio": (request.form.get("bio") or "").strip(),
        "image_url": new_image_url,
        "is_verified": False,
        "payment_status": "submitted",
    })
    flash("Coach added to the pending queue — approve below to make them live.", "success")
    return redirect(url_for("admin"))

# ---------- Health & errors ----------
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
