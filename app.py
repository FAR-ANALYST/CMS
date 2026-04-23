import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "farouk_getmycoach_uganda_2026")

# ── Sports list — single source of truth for all three faces ──
SPORTS = [
    "Athletics",
    "Chess",
    "Checkers",
    "Football",
    "Gym / Fitness",
    "Handball",
    "Netball",
    "Scrabble",
    "Swimming",
    "Volleyball",
]

# ── Lazy Supabase client — only created on first request, not at import time.
#    This prevents Render from crashing during build if env vars aren't ready yet.
_supabase = None

def get_db():
    """Return (or lazily create) the Supabase client."""
    global _supabase
    if _supabase is None:
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_ANON_KEY", "")
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_ANON_KEY must be set in environment variables."
            )
        _supabase = create_client(url, key)
    return _supabase


def get_status_info(status: str) -> dict:
    states = {
        "pending": {
            "msg":   "Action Required: Complete your profile and submit for review.",
            "color": "text-neutral-400",
        },
        "submitted": {
            "msg":   "Under Review — awaiting payment confirmation from Admin (UGX 20,000).",
            "color": "text-yellow-400",
        },
        "paid": {
            "msg":   "Verified & Live! Your profile is now visible to students.",
            "color": "text-green-400",
        },
    }
    return states.get(status, states["pending"])


# ══════════════════════════════════════════════
#  GLOBAL ERROR HANDLERS
#  These stop Render showing a blank page on
#  any unhandled exception.
# ══════════════════════════════════════════════

@app.errorhandler(404)
def not_found(e):
    return render_template("login.html", error="Page not found. Please log in."), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("login.html",
                           error=f"Server error: {e}. Please try again."), 500


@app.errorhandler(Exception)
def unhandled(e):
    app.logger.error(f"Unhandled exception: {e}", exc_info=True)
    return render_template("login.html",
                           error=f"Something went wrong: {e}"), 500


# ══════════════════════════════════════════════
#  SAFETY REDIRECTS
#  Old templates or bookmarks may reference
#  /signup or /register — catch them here so
#  Flask never raises a BuildError.
# ══════════════════════════════════════════════

@app.route("/signup")
@app.route("/register")
def signup():
    """Catch-all for any old /signup or /register references."""
    return redirect(url_for("index"))


# ══════════════════════════════════════════════
#  LOGIN / LOGOUT
# ══════════════════════════════════════════════

@app.route("/")
def index():
    # If user is already logged in, send them to the right face
    if "user_id" in session:
        role = session.get("role", "student")
        if role == "admin":
            return redirect(url_for("admin_face"))
        if role == "coach":
            return redirect(url_for("coach_face"))
        return redirect(url_for("student_face"))
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    login_id = request.form.get("login_id", "").strip()
    password  = request.form.get("password", "")

    # ── Admin hard-coded override ──
    if login_id == "FAROUK" and password == "FAROUK2020":
        session.update({
            "user_id":  "00000000-0000-0000-0000-000000000000",
            "role":     "admin",
            "username": "FAROUK",
        })
        return redirect(url_for("admin_face"))

    try:
        db  = get_db()
        res = db.table("profiles").select("*") \
                .or_(f"username.eq.{login_id},email.eq.{login_id}").execute()

        if not res.data:
            return render_template("login.html",
                                   error="User not found. Please register via WhatsApp.")

        user = res.data[0]
        auth = db.auth.sign_in_with_password({
            "email":    user["email"],
            "password": password,
        })

        session.update({
            "user_id":  auth.user.id,
            "role":     user.get("role", "student"),
            "username": user.get("username", ""),
        })

        role = session["role"]
        if role == "coach":
            return redirect(url_for("coach_face"))
        if role == "admin":
            return redirect(url_for("admin_face"))
        return redirect(url_for("student_face"))

    except Exception as e:
        return render_template("login.html", error=f"Login failed: {e}")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ══════════════════════════════════════════════
#  STUDENT FACE  — /student
#  Only coaches where is_verified=True AND
#  payment_status='paid' are shown.
# ══════════════════════════════════════════════

@app.route("/student")
def student_face():
    if "user_id" not in session:
        return redirect(url_for("index"))

    try:
        db    = get_db()
        sport = request.args.get("sport", "")
        loc   = request.args.get("location", "")

        q = (db.table("profiles").select("*")
               .eq("role", "coach")
               .eq("is_verified", True)
               .eq("payment_status", "paid"))
        if sport: q = q.eq("sport_category", sport)
        if loc:   q = q.eq("location_district", loc)
        coaches = q.execute().data

        # Locations come from live coaches only (dynamic)
        loc_rows  = (db.table("profiles")
                       .select("location_district")
                       .eq("role", "coach")
                       .eq("is_verified", True)
                       .execute().data)
        locations = sorted({r["location_district"]
                            for r in loc_rows if r.get("location_district")})

        return render_template("student.html",
                               coaches=coaches,
                               sports=SPORTS,
                               locations=locations,
                               selected_sport=sport,
                               selected_location=loc,
                               role=session.get("role"))

    except Exception as e:
        flash(f"Could not load directory: {e}")
        return render_template("student.html",
                               coaches=[],
                               sports=SPORTS,
                               locations=[],
                               selected_sport="",
                               selected_location="",
                               role=session.get("role"))


# ══════════════════════════════════════════════
#  COACH FACE  — /coach
#  Always fully editable.
#  Submitting sets payment_status='submitted'
#  and is_verified=False until admin marks paid.
# ══════════════════════════════════════════════

@app.route("/coach", methods=["GET", "POST"])
def coach_face():
    if "user_id" not in session:
        return redirect(url_for("index"))

    is_admin = session.get("role") == "admin"

    # ── POST: save / update profile ──
    if request.method == "POST" and not is_admin:
        try:
            db      = get_db()
            file    = request.files.get("profile_image")
            img_url = request.form.get("existing_url", "")

            if file and file.filename:
                filename  = secure_filename(f"{session['user_id']}_{file.filename}")
                temp_path = os.path.join("/tmp", filename)
                file.save(temp_path)
                try:
                    with open(temp_path, "rb") as f:
                        db.storage.from_("coaches").upload(
                            f"photos/{filename}", f, {"upsert": "true"}
                        )
                    img_url = db.storage.from_("coaches").get_public_url(
                        f"photos/{filename}"
                    )
                except Exception as img_err:
                    flash(f"Photo upload failed (profile saved without image): {img_err}")

            update_data = {
                "full_name":         request.form.get("full_name", "").strip(),
                "sport_category":    request.form.get("sport_category", "").strip(),
                "location_district": request.form.get("location_district", "").strip(),
                "contact_number":    request.form.get("contact_number", "").strip(),
                "bio":               request.form.get("bio", "").strip(),
                "profile_pic_url":   img_url,
                "role":              "coach",
                "payment_status":    "submitted",   # signals Admin queue
                "is_verified":       False,          # hidden from students until paid
            }

            db.table("profiles").update(update_data).eq("id", session["user_id"]).execute()
            flash("Profile submitted! Admin will review and confirm your payment shortly.")

        except Exception as e:
            flash(f"Error saving profile: {e}")

        return redirect(url_for("coach_face"))

    # ── GET: load current profile ──
    profile     = {}
    status_info = get_status_info("pending")

    if not is_admin:
        try:
            db = get_db()
            p  = db.table("profiles").select("*").eq("id", session["user_id"]).execute()
            if p.data:
                profile     = p.data[0]
                status_info = get_status_info(profile.get("payment_status", "pending"))
            else:
                # First visit — create a blank row so the form loads cleanly
                db.table("profiles").insert({
                    "id":             session["user_id"],
                    "role":           "coach",
                    "is_verified":    False,
                    "payment_status": "pending",
                }).execute()
        except Exception as e:
            flash(f"Could not load profile: {e}")
    else:
        profile     = {"full_name": "Admin Preview Mode"}
        status_info = get_status_info("paid")

    return render_template("coach.html",
                           profile=profile,
                           status_info=status_info,
                           sports=SPORTS,
                           role=session.get("role"))


# ══════════════════════════════════════════════
#  ADMIN FACE  — /admin
# ══════════════════════════════════════════════

@app.route("/admin")
def admin_face():
    if session.get("role") != "admin":
        return redirect(url_for("index"))

    try:
        db = get_db()

        # Coaches who submitted but haven't been paid/verified yet
        pending = (db.table("profiles").select("*")
                     .eq("role", "coach")
                     .eq("is_verified", False)
                     .eq("payment_status", "submitted")
                     .execute().data)

        # Coaches currently live on the student page
        verified = (db.table("profiles").select("*")
                      .eq("role", "coach")
                      .eq("is_verified", True)
                      .execute().data)

    except Exception as e:
        flash(f"Could not load admin data: {e}")
        pending  = []
        verified = []

    return render_template("admin.html",
                           pending=pending,
                           verified=verified,
                           sports=SPORTS,
                           role="admin")


@app.route("/admin/mark_paid/<coach_id>")
def mark_paid(coach_id):
    """Flip the switch: coach becomes live on the student directory."""
    if session.get("role") != "admin":
        return redirect(url_for("index"))
    try:
        get_db().table("profiles").update({
            "is_verified":    True,
            "payment_status": "paid",
        }).eq("id", coach_id).execute()
        flash("Coach marked as paid and is now live on the student directory.")
    except Exception as e:
        flash(f"Could not verify coach: {e}")
    return redirect(url_for("admin_face"))


@app.route("/admin/remove/<coach_id>")
def remove_coach(coach_id):
    """Un-verify a coach (e.g. payment bounced)."""
    if session.get("role") != "admin":
        return redirect(url_for("index"))
    try:
        get_db().table("profiles").update({
            "is_verified":    False,
            "payment_status": "pending",
        }).eq("id", coach_id).execute()
        flash("Coach removed from the live directory.")
    except Exception as e:
        flash(f"Could not remove coach: {e}")
    return redirect(url_for("admin_face"))


@app.route("/admin/add_coach", methods=["POST"])
def admin_add_coach():
    """Admin adds a coach directly — goes live immediately, no approval needed."""
    if session.get("role") != "admin":
        return redirect(url_for("index"))

    try:
        db      = get_db()
        file    = request.files.get("profile_image")
        img_url = ""

        if file and file.filename:
            filename  = secure_filename(f"admin_{uuid.uuid4().hex}_{file.filename}")
            temp_path = os.path.join("/tmp", filename)
            file.save(temp_path)
            try:
                with open(temp_path, "rb") as f:
                    db.storage.from_("coaches").upload(
                        f"photos/{filename}", f, {"upsert": "true"}
                    )
                img_url = db.storage.from_("coaches").get_public_url(f"photos/{filename}")
            except Exception as img_err:
                flash(f"Photo upload failed (coach saved without image): {img_err}")

        coach_data = {
            "id":                str(uuid.uuid4()),
            "role":              "coach",
            "full_name":         request.form.get("full_name", "").strip(),
            "sport_category":    request.form.get("sport_category", "").strip(),
            "location_district": request.form.get("location_district", "").strip(),
            "contact_number":    request.form.get("contact_number", "").strip(),
            "bio":               request.form.get("bio", "").strip(),
            "profile_pic_url":   img_url,
            "is_verified":       True,    # live immediately
            "payment_status":    "paid",
        }

        db.table("profiles").insert(coach_data).execute()
        flash(f"Coach '{coach_data['full_name']}' added and is now live on the directory.")

    except Exception as e:
        flash(f"Error adding coach: {e}")

    return redirect(url_for("admin_face"))


# ══════════════════════════════════════════════
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
