"""
Get My Coach Uganda - Flask Application
Connects students with verified sports coaches across Uganda.

Flow:
  1. Coach signs up & submits profile  -> payment_status='submitted', is_verified=False
  2. Admin sees pending profile        -> clicks "Mark Paid & Go Live"
  3. Coach goes live                   -> payment_status='paid', is_verified=True
  4. Students see the coach in the public directory
  5. Admin can "Remove" anytime        -> hidden from students again
"""

import os
import uuid
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify
)
from supabase import create_client, Client
from werkzeug.utils import secure_filename

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "change-me-in-production")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "Missing SUPABASE_URL or SUPABASE_ANON_KEY environment variables."
    )

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@getmycoach.ug")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

BUCKET = "coach-images"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

SPORT_CATEGORIES = [
    "Chess", "Football", "Volleyball", "Netball", "Scrabble",
    "Athletics", "Gym", "Handball", "Swimming", "Checkers",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def login_required(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                flash("You do not have access to that page.", "error")
                return redirect(url_for("login"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Admin access required.", "error")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def upload_image(file_storage) -> str | None:
    """Upload image to Supabase storage, return the public URL (or None)."""
    if not file_storage or file_storage.filename == "":
        return None
    if not allowed_file(file_storage.filename):
        return None

    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    path = f"{uuid.uuid4().hex}.{ext}"
    file_bytes = file_storage.read()

    supabase.storage.from_(BUCKET).upload(
        path,
        file_bytes,
        file_options={"content-type": file_storage.mimetype, "upsert": "true"},
    )
    return supabase.storage.from_(BUCKET).get_public_url(path)


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        role = request.form.get("role", "student")
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        # Admin shortcut
        if role == "admin":
            if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
                session.clear()
                session["is_admin"] = True
                session["user_id"] = "admin"
                session["role"] = "admin"
                return redirect(url_for("admin_dashboard"))
            flash("Invalid admin credentials.", "error")
            return redirect(url_for("login"))

        try:
            auth = supabase.auth.sign_in_with_password(
                {"email": email, "password": password}
            )
            session.clear()
            session["user_id"] = auth.user.id
            session["email"] = email
            session["role"] = role
            if role == "coach":
                return redirect(url_for("coach_dashboard"))
            return redirect(url_for("student_dashboard"))
        except Exception as e:
            flash(f"Login failed: {e}", "error")
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/signup", methods=["POST"])
def signup():
    role = request.form.get("role", "student")
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    full_name = request.form.get("full_name", "").strip()

    try:
        auth = supabase.auth.sign_up({"email": email, "password": password})
        user_id = auth.user.id

        # Create profile row
        supabase.table("profiles").insert({
            "id": user_id,
            "email": email,
            "full_name": full_name,
            "role": role,
            "is_verified": False,
            "payment_status": "pending",
        }).execute()

        session.clear()
        session["user_id"] = user_id
        session["email"] = email
        session["role"] = role

        flash("Account created! Please complete your profile.", "success")
        if role == "coach":
            return redirect(url_for("coach_dashboard"))
        return redirect(url_for("student_dashboard"))
    except Exception as e:
        flash(f"Signup failed: {e}", "error")
        return redirect(url_for("login"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Coach
# ---------------------------------------------------------------------------
@app.route("/coach", methods=["GET"])
@login_required(role="coach")
def coach_dashboard():
    user_id = session["user_id"]
    res = supabase.table("profiles").select("*").eq("id", user_id).single().execute()
    profile = res.data or {}
    return render_template(
        "coach.html",
        profile=profile,
        categories=SPORT_CATEGORIES,
    )


@app.route("/coach/save", methods=["POST"])
@login_required(role="coach")
def coach_save():
    user_id = session["user_id"]

    update = {
        "full_name": request.form.get("full_name", "").strip(),
        "phone": request.form.get("phone", "").strip(),
        "category": request.form.get("category", "").strip(),
        "experience_years": int(request.form.get("experience_years") or 0),
        "hourly_rate": int(request.form.get("hourly_rate") or 0),
        "location": request.form.get("location", "").strip(),
        "bio": request.form.get("bio", "").strip(),
    }

    # Optional new image
    image_file = request.files.get("image")
    if image_file and image_file.filename:
        url = upload_image(image_file)
        if url:
            update["image_url"] = url

    # Mark as submitted -> awaiting admin verification after payment
    existing = (
        supabase.table("profiles").select("payment_status").eq("id", user_id).single().execute().data
    )
    if not existing or existing.get("payment_status") in (None, "pending"):
        update["payment_status"] = "submitted"
        update["is_verified"] = False

    supabase.table("profiles").update(update).eq("id", user_id).execute()
    flash("Profile saved! It is now awaiting admin verification.", "success")
    return redirect(url_for("coach_dashboard"))


# ---------------------------------------------------------------------------
# Student
# ---------------------------------------------------------------------------
@app.route("/student")
@login_required(role="student")
def student_dashboard():
    category = request.args.get("category", "").strip()
    location = request.args.get("location", "").strip()

    query = (
        supabase.table("profiles")
        .select("*")
        .eq("role", "coach")
        .eq("is_verified", True)
        .eq("payment_status", "paid")
    )
    if category:
        query = query.eq("category", category)
    if location:
        query = query.ilike("location", f"%{location}%")

    coaches = query.execute().data or []

    return render_template(
        "student.html",
        coaches=coaches,
        categories=SPORT_CATEGORIES,
        selected_category=category,
        selected_location=location,
    )


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
@app.route("/admin")
@admin_required
def admin_dashboard():
    pending = (
        supabase.table("profiles")
        .select("*")
        .eq("role", "coach")
        .eq("payment_status", "submitted")
        .order("created_at", desc=True)
        .execute()
        .data
        or []
    )
    live = (
        supabase.table("profiles")
        .select("*")
        .eq("role", "coach")
        .eq("is_verified", True)
        .eq("payment_status", "paid")
        .order("created_at", desc=True)
        .execute()
        .data
        or []
    )
    return render_template("admin.html", pending=pending, live=live)


@app.route("/admin/approve/<coach_id>", methods=["POST"])
@admin_required
def admin_approve(coach_id):
    supabase.table("profiles").update({
        "is_verified": True,
        "payment_status": "paid",
    }).eq("id", coach_id).execute()
    flash("Coach marked as paid and is now live for students.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/remove/<coach_id>", methods=["POST"])
@admin_required
def admin_remove(coach_id):
    supabase.table("profiles").update({
        "is_verified": False,
        "payment_status": "pending",
    }).eq("id", coach_id).execute()
    flash("Coach removed from public directory.", "success")
    return redirect(url_for("admin_dashboard"))


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
