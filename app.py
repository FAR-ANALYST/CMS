import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ── ProxyFix: CRITICAL for Render ────────────────────────────────
# Sets up the app to handle HTTPS behind Render's reverse proxy
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# ── Session / cookie settings ──────────────────────────────────
app.secret_key = os.environ.get("FLASK_SECRET", "farouk_getmycoach_uganda_2026_x9k")
app.config.update(
    SESSION_COOKIE_HTTPONLY = True,
    SESSION_COOKIE_SAMESITE = "Lax",
    SESSION_COOKIE_SECURE   = False, # Set to True in production if using HTTPS
    PERMANENT_SESSION_LIFETIME = 86400, 
)

# ── Sports — single source of truth ───────────────────────────
SPORTS = [
    "Athletics", "Chess", "Checkers", "Football", 
    "Gym / Fitness", "Handball", "Netball", "Scrabble", 
    "Swimming", "Volleyball",
]

# ── Lazy Supabase client ───────────────────────────────────────
_supabase = None

def get_db():
    global _supabase
    if _supabase is None:
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_ANON_KEY", "")
        if not url or not key:
            # On Render, if these are missing, the app will crash on first DB call
            return None 
        _supabase = create_client(url, key)
    return _supabase

def get_status_info(status: str) -> dict:
    states = {
        "pending":   {"msg": "Action Required: Complete your profile and submit for review.", "color": "text-neutral-400"},
        "submitted": {"msg": "Under Review — awaiting payment confirmation (UGX 20,000).", "color": "text-yellow-400"},
        "paid":      {"msg": "Verified & Live! Your profile is now visible to students.", "color": "text-green-400"},
    }
    return states.get(status, states["pending"])

# ══════════════════════════════════════════════
#  GLOBAL ERROR HANDLERS
# ══════════════════════════════════════════════

@app.errorhandler(404)
def not_found(e):
    return render_template("login.html", error="Page not found."), 404

@app.errorhandler(500)
def server_error(e):
    return render_template("login.html", error="Internal Server Error."), 500

# ══════════════════════════════════════════════
#  ROUTES
# ══════════════════════════════════════════════

@app.route("/signup")
@app.route("/register")
def signup():
    return redirect(url_for("index"))

@app.route("/")
def index():
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login():
    login_id = request.form.get("login_id", "").strip()
    password  = request.form.get("password", "")

    if not login_id or not password:
        return render_template("login.html", error="Enter credentials.")

    if login_id == "FAROUK" and password == "FAROUK2020":
        session.clear()
        session["user_id"]  = "00000000-0000-0000-0000-000000000000"
        session["role"]     = "admin"
        session["username"] = "FAROUK"
        session.permanent   = True
        return redirect(url_for("admin_face"))

    try:
        db = get_db()
        if not db: return "Database Configuration Missing", 500
        
        user = None
        by_username = db.table("profiles").select("*").eq("username", login_id).execute()
        if by_username.data:
            user = by_username.data[0]
        else:
            by_email = db.table("profiles").select("*").eq("email", login_id).execute()
            if by_email.data:
                user = by_email.data[0]

        if user is None:
            return render_template("login.html", error="No account found.")

        auth_res = db.auth.sign_in_with_password({"email": user["email"], "password": password})

        session.clear()
        session["user_id"]  = auth_res.user.id
        session["role"]     = user.get("role", "student")
        session["username"] = user.get("username", "")
        session.permanent   = True

        if session["role"] == "admin": return redirect(url_for("admin_face"))
        if session["role"] == "coach": return redirect(url_for("coach_face"))
        return redirect(url_for("student_face"))

    except Exception as e:
        return render_template("login.html", error=f"Login failed: {str(e)}")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/student")
def student_face():
    if "user_id" not in session: return redirect(url_for("index"))
    sport = request.args.get("sport", "")
    loc   = request.args.get("location", "")
    coaches, locations = [], []
    try:
        db = get_db()
        q = db.table("profiles").select("*").eq("role", "coach").eq("is_verified", True).eq("payment_status", "paid")
        if sport: q = q.eq("sport_category", sport)
        if loc:   q = q.eq("location_district", loc)
        coaches = q.execute().data
        loc_rows = db.table("profiles").select("location_district").eq("role", "coach").eq("is_verified", True).execute().data
        locations = sorted({r["location_district"] for r in loc_rows if r.get("location_district")})
    except Exception as e: flash(f"Error: {e}")
    return render_template("student.html", coaches=coaches, sports=SPORTS, locations=locations, 
                           selected_sport=sport, selected_location=loc, role=session.get("role"))

@app.route("/coach", methods=["GET", "POST"])
def coach_face():
    if "user_id" not in session: return redirect(url_for("index"))
    is_admin = (session.get("role") == "admin")
    db = get_db()

    if request.method == "POST" and not is_admin:
        try:
            file = request.files.get("profile_image")
            img_url = request.form.get("existing_url", "")
            if file and file.filename:
                filename = secure_filename(f"{session['user_id']}_{file.filename}")
                temp_path = os.path.join("/tmp", filename)
                file.save(temp_path)
                with open(temp_path, "rb") as f:
                    db.storage.from_("coaches").upload(f"photos/{filename}", f, {"upsert": "true"})
                img_url = db.storage.from_("coaches").get_public_url(f"photos/{filename}")

            db.table("profiles").update({
                "full_name": request.form.get("full_name", "").strip(),
                "sport_category": request.form.get("sport_category", "").strip(),
                "location_district": request.form.get("location_district", "").strip(),
                "contact_number": request.form.get("contact_number", "").strip(),
                "bio": request.form.get("bio", "").strip(),
                "profile_pic_url": img_url,
                "role": "coach", "payment_status": "submitted", "is_verified": False,
            }).eq("id", session["user_id"]).execute()
            flash("Profile submitted for review!")
        except Exception as e: flash(f"Save error: {e}")
        return redirect(url_for("coach_face"))

    profile, status_info = {}, get_status_info("pending")
    if not is_admin:
        p = db.table("profiles").select("*").eq("id", session["user_id"]).execute()
        if p.data:
            profile = p.data[0]
            status_info = get_status_info(profile.get("payment_status", "pending"))
    else:
        profile, status_info = {"full_name": "Admin Preview"}, get_status_info("paid")
    
    return render_template("coach.html", profile=profile, status_info=status_info, sports=SPORTS, role=session.get("role"))

@app.route("/admin")
def admin_face():
    if session.get("role") != "admin": return redirect(url_for("index"))
    pending, verified = [], []
    try:
        db = get_db()
        pending = db.table("profiles").select("*").eq("role", "coach").eq("is_verified", False).eq("payment_status", "submitted").execute().data
        verified = db.table("profiles").select("*").eq("role", "coach").eq("is_verified", True).execute().data
    except Exception as e: flash(f"Load error: {e}")
    return render_template("admin.html", pending=pending, verified=verified, sports=SPORTS, role="admin")

@app.route("/admin/mark_paid/<coach_id>")
def mark_paid(coach_id):
    if session.get("role") != "admin": return redirect(url_for("index"))
    get_db().table("profiles").update({"is_verified": True, "payment_status": "paid"}).eq("id", coach_id).execute()
    return redirect(url_for("admin_face"))

@app.route("/admin/remove/<coach_id>")
def remove_coach(coach_id):
    if session.get("role") != "admin": return redirect(url_for("index"))
    get_db().table("profiles").update({"is_verified": False, "payment_status": "pending"}).eq("id", coach_id).execute()
    return redirect(url_for("admin_face"))

@app.route("/admin/add_coach", methods=["POST"])
def admin_add_coach():
    if session.get("role") != "admin": return redirect(url_for("index"))
    try:
        db, file, img_url = get_db(), request.files.get("profile_image"), ""
        if file and file.filename:
            filename = secure_filename(f"adm_{uuid.uuid4().hex}")
            temp_path = os.path.join("/tmp", filename)
            file.save(temp_path)
            with open(temp_path, "rb") as f:
                db.storage.from_("coaches").upload(f"photos/{filename}", f, {"upsert": "true"})
            img_url = db.storage.from_("coaches").get_public_url(f"photos/{filename}")
        
        db.table("profiles").insert({
            "id": str(uuid.uuid4()), "role": "coach", "full_name": request.form.get("full_name", "").strip(),
            "sport_category": request.form.get("sport_category"), "location_district": request.form.get("location_district"),
            "contact_number": request.form.get("contact_number"), "bio": request.form.get("bio"),
            "profile_pic_url": img_url, "is_verified": True, "payment_status": "paid",
        }).execute()
    except Exception as e: flash(f"Error: {e}")
    return redirect(url_for("admin_face"))

# ── MAIN ───────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
