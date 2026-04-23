import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, flash
from supabase import create_client, Client
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "farouk_getmycoach_uganda_2026")

SUPABASE_URL     = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ── All supported sports (single source of truth used by Python too) ──
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

def get_status_info(status):
    states = {
        "pending":   {"msg": "Action Required: Complete your profile and submit for review.",         "color": "text-neutral-400"},
        "submitted": {"msg": "Under Review — awaiting payment confirmation from Admin (UGX 20,000).", "color": "text-yellow-400"},
        "paid":      {"msg": "Verified & Live! Your profile is now visible to students.",             "color": "text-green-400"},
    }
    return states.get(status, states["pending"])


# ──────────────────────────────────────────────
#  LOGIN / LOGOUT
# ──────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    login_id = request.form.get("login_id", "").strip()
    password  = request.form.get("password", "")

    if login_id == "FAROUK" and password == "FAROUK2020":
        session.update({"user_id": "00000000-0000-0000-0000-000000000000", "role": "admin", "username": "FAROUK"})
        return redirect(url_for("admin_face"))

    try:
        res = supabase.table("profiles").select("*").or_(f"username.eq.{login_id},email.eq.{login_id}").execute()
        if not res.data:
            return render_template("login.html", error="User not found. Please register.")
        user = res.data[0]
        auth = supabase.auth.sign_in_with_password({"email": user["email"], "password": password})
        session.update({"user_id": auth.user.id, "role": user.get("role", "student"), "username": user.get("username", "")})
        if session["role"] == "coach":
            return redirect(url_for("coach_face"))
        if session["role"] == "admin":
            return redirect(url_for("admin_face"))
        return redirect(url_for("student_face"))
    except Exception as e:
        return render_template("login.html", error=f"Login failed: {e}")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ──────────────────────────────────────────────
#  STUDENT FACE  — only paid+verified coaches
# ──────────────────────────────────────────────

@app.route("/student")
def student_face():
    if "user_id" not in session:
        return redirect(url_for("index"))

    sport = request.args.get("sport", "")
    loc   = request.args.get("location", "")

    q = (supabase.table("profiles").select("*")
         .eq("role", "coach")
         .eq("is_verified", True)
         .eq("payment_status", "paid"))
    if sport: q = q.eq("sport_category", sport)
    if loc:   q = q.eq("location_district", loc)
    coaches = q.execute().data

    # Build location list dynamically from live coaches
    all_v = (supabase.table("profiles")
             .select("location_district")
             .eq("role", "coach")
             .eq("is_verified", True)
             .execute().data)
    locations = sorted({c["location_district"] for c in all_v if c.get("location_district")})

    return render_template("student.html",
                           coaches=coaches,
                           sports=SPORTS,          # fixed list so all categories always show
                           locations=locations,
                           selected_sport=sport,
                           selected_location=loc,
                           role=session.get("role"))


# ──────────────────────────────────────────────
#  COACH FACE  — editable at all times
# ──────────────────────────────────────────────

@app.route("/coach", methods=["GET", "POST"])
def coach_face():
    if "user_id" not in session:
        return redirect(url_for("index"))

    is_admin = session.get("role") == "admin"

    if request.method == "POST" and not is_admin:
        try:
            file    = request.files.get("profile_image")
            img_url = request.form.get("existing_url", "")

            if file and file.filename:
                filename  = secure_filename(f"{session['user_id']}_{file.filename}")
                temp_path = os.path.join("/tmp", filename)
                file.save(temp_path)
                with open(temp_path, "rb") as f:
                    supabase.storage.from_("coaches").upload(f"photos/{filename}", f, {"upsert": "true"})
                img_url = supabase.storage.from_("coaches").get_public_url(f"photos/{filename}")

            update_data = {
                "full_name":         request.form.get("full_name", "").strip(),
                "sport_category":    request.form.get("sport_category", "").strip(),
                "location_district": request.form.get("location_district", "").strip(),
                "contact_number":    request.form.get("contact_number", "").strip(),
                "bio":               request.form.get("bio", "").strip(),
                "profile_pic_url":   img_url,
                "role":              "coach",
                # Always reset to submitted so admin sees the latest version
                "payment_status":    "submitted",
                "is_verified":       False,
            }
            supabase.table("profiles").update(update_data).eq("id", session["user_id"]).execute()
            flash("Profile submitted! Admin will review and confirm your payment shortly.")
        except Exception as e:
            flash(f"Error saving profile: {e}")
        return redirect(url_for("coach_face"))

    # ── GET ──
    profile     = {}
    status_info = get_status_info("pending")

    if not is_admin:
        try:
            p = supabase.table("profiles").select("*").eq("id", session["user_id"]).execute()
            if p.data:
                profile     = p.data[0]
                status_info = get_status_info(profile.get("payment_status", "pending"))
            else:
                # Auto-create blank row for new coach
                supabase.table("profiles").insert({
                    "id":             session["user_id"],
                    "role":           "coach",
                    "is_verified":    False,
                    "payment_status": "pending",
                }).execute()
        except Exception as e:
            flash(f"Database error: {e}")
    else:
        profile     = {"full_name": "Admin Preview Mode"}
        status_info = get_status_info("paid")

    return render_template("coach.html",
                           profile=profile,
                           status_info=status_info,
                           sports=SPORTS,
                           role=session.get("role"))


# ──────────────────────────────────────────────
#  ADMIN FACE
# ──────────────────────────────────────────────

@app.route("/admin")
def admin_face():
    if session.get("role") != "admin":
        return redirect(url_for("index"))

    pending = (supabase.table("profiles").select("*")
               .eq("role", "coach")
               .eq("is_verified", False)
               .eq("payment_status", "submitted")
               .execute().data)

    verified = (supabase.table("profiles").select("*")
                .eq("role", "coach")
                .eq("is_verified", True)
                .execute().data)

    return render_template("admin.html",
                           pending=pending,
                           verified=verified,
                           sports=SPORTS,
                           role="admin")


# ── Mark coach as paid → goes live on student page ──
@app.route("/admin/mark_paid/<coach_id>")
def mark_paid(coach_id):
    if session.get("role") != "admin":
        return "Unauthorized", 403
    supabase.table("profiles").update({"is_verified": True, "payment_status": "paid"}).eq("id", coach_id).execute()
    flash("Coach marked as paid and is now live on the student directory.")
    return redirect(url_for("admin_face"))


# ── Remove / un-verify a coach ──
@app.route("/admin/remove/<coach_id>")
def remove_coach(coach_id):
    if session.get("role") != "admin":
        return "Unauthorized", 403
    supabase.table("profiles").update({"is_verified": False, "payment_status": "pending"}).eq("id", coach_id).execute()
    return redirect(url_for("admin_face"))


# ── Admin adds a coach directly (bypasses coach self-signup) ──
@app.route("/admin/add_coach", methods=["POST"])
def admin_add_coach():
    if session.get("role") != "admin":
        return "Unauthorized", 403

    file    = request.files.get("profile_image")
    img_url = ""

    if file and file.filename:
        filename  = secure_filename(f"admin_{uuid.uuid4().hex}_{file.filename}")
        temp_path = os.path.join("/tmp", filename)
        file.save(temp_path)
        try:
            with open(temp_path, "rb") as f:
                supabase.storage.from_("coaches").upload(f"photos/{filename}", f, {"upsert": "true"})
            img_url = supabase.storage.from_("coaches").get_public_url(f"photos/{filename}")
        except Exception as e:
            flash(f"Image upload error: {e}")

    new_id = str(uuid.uuid4())
    coach_data = {
        "id":                new_id,
        "role":              "coach",
        "full_name":         request.form.get("full_name", "").strip(),
        "sport_category":    request.form.get("sport_category", "").strip(),
        "location_district": request.form.get("location_district", "").strip(),
        "contact_number":    request.form.get("contact_number", "").strip(),
        "bio":               request.form.get("bio", "").strip(),
        "profile_pic_url":   img_url,
        # Admin-added coaches go live immediately
        "is_verified":       True,
        "payment_status":    "paid",
    }

    try:
        supabase.table("profiles").insert(coach_data).execute()
        flash(f"Coach '{coach_data['full_name']}' added and is now live on the directory.")
    except Exception as e:
        flash(f"Error adding coach: {e}")

    return redirect(url_for("admin_face"))


# ──────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
