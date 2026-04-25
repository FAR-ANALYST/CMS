"""
Get My Coach Uganda — Flask + Supabase Postgres
Deploys on Render (Free) using a Supabase Postgres connection.

ENV VARS REQUIRED on Render:
  DATABASE_URL        e.g. postgresql://postgres:PASSWORD@db.xxxx.supabase.co:5432/postgres
  FLASK_SECRET        any long random string
  SUPABASE_URL        https://xxxx.supabase.co
  SUPABASE_ANON_KEY   the anon/public key (used for Storage uploads)
  SUPABASE_BUCKET     e.g. uploads   (create a PUBLIC bucket with this name)
"""

import os
import uuid
from datetime import timedelta

import psycopg2
import psycopg2.extras
import requests
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, g, abort
)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ─────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "change-me-in-production")
app.permanent_session_lifetime = timedelta(hours=24)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

DATABASE_URL      = os.environ.get("DATABASE_URL")
SUPABASE_URL      = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_BUCKET   = os.environ.get("SUPABASE_BUCKET", "uploads")

SPORTS = [
    "Athletics", "Chess", "Checkers", "Football", "Gym/Fitness",
    "Handball", "Netball", "Scrabble", "Swimming", "Volleyball",
]

PREVIEW_LIMIT = 8  # first N coaches shown before search


# ── DB helpers ──────────────────────────────────────────────────
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL env var not set")
        db = g._database = psycopg2.connect(DATABASE_URL, sslmode="require")
    return db


def query(sql, params=(), one=False, commit=False):
    db  = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, params)
    if commit:
        db.commit()
        try:
            row = cur.fetchone() if cur.description else None
        except psycopg2.ProgrammingError:
            row = None
        cur.close()
        return row
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db:
        db.close()


# ── Supabase Storage upload ─────────────────────────────────────
def upload_to_supabase(file_storage, folder="misc"):
    """Upload to Supabase Storage. Returns the public URL or '' on failure."""
    if not file_storage or not file_storage.filename:
        return ""
    if not (SUPABASE_URL and SUPABASE_ANON_KEY):
        return ""

    ext  = os.path.splitext(secure_filename(file_storage.filename))[1] or ".jpg"
    name = f"{folder}/{uuid.uuid4().hex}{ext}"

    upload_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{name}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "apikey": SUPABASE_ANON_KEY,
        "Content-Type": file_storage.mimetype or "application/octet-stream",
        "x-upsert": "true",
    }
    file_storage.stream.seek(0)
    r = requests.post(upload_url, headers=headers, data=file_storage.stream.read())
    if r.status_code not in (200, 201):
        print("Supabase upload failed:", r.status_code, r.text)
        return ""

    return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{name}"


# ── Auth helpers ────────────────────────────────────────────────
def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return query("SELECT * FROM users WHERE id = %s", (uid,), one=True)


def is_admin():
    return bool(session.get("is_admin"))


@app.context_processor
def inject_globals():
    return {
        "SPORTS": SPORTS,
        "current_user": current_user(),
        "is_admin": is_admin(),
    }


# ════════════════════════════════════════════════════════════════
# PUBLIC / STUDENT ROUTES
# ════════════════════════════════════════════════════════════════
@app.route("/")
def home():
    """Landing — events with auto status (upcoming/live/completed)."""
    rows = query(
        """SELECT e.*,
                  COALESCE(json_agg(ei.image_url ORDER BY ei.id)
                           FILTER (WHERE ei.image_url IS NOT NULL),
                           '[]'::json) AS images
             FROM events e
             LEFT JOIN event_images ei ON ei.event_id = e.id
            WHERE e.is_active = TRUE
            GROUP BY e.id
            ORDER BY e.event_date ASC NULLS LAST, e.created_at DESC"""
    )

    from datetime import datetime, timezone, timedelta
    today = (datetime.now(timezone.utc) + timedelta(hours=3)).date()  # Uganda EAT

    events = []
    for ev in rows:
        ev = dict(ev)
        start = ev.get("event_date")
        end   = ev.get("end_date") or start
        if not start:
            ev["status"] = "upcoming"
        elif today < start:
            ev["status"] = "upcoming"
        elif start <= today <= end:
            ev["status"] = "live"
        else:
            ev["status"] = "completed"
        events.append(ev)

    return render_template("home.html", events=events)



@app.route("/coaches")
def coaches():
    """Coach directory. Shows 8 by default; full list after search."""
    cat = request.args.get("category", "").strip()
    loc = request.args.get("location", "").strip()
    searched = bool(cat or loc)

    sql = "SELECT * FROM coaches WHERE is_verified = TRUE"
    params = []
    if cat:
        sql += " AND category = %s"; params.append(cat)
    if loc:
        sql += " AND location ILIKE %s"; params.append(f"%{loc}%")
    sql += " ORDER BY created_at DESC"
    if not searched:
        sql += f" LIMIT {PREVIEW_LIMIT}"

    coaches_rows = query(sql, tuple(params))
    total_live   = query("SELECT COUNT(*) AS n FROM coaches WHERE is_verified = TRUE", one=True)["n"]

    return render_template(
        "coaches.html",
        coaches=coaches_rows,
        searched=searched,
        total_live=total_live,
        preview_limit=PREVIEW_LIMIT,
        cat=cat, loc=loc,
    )


# ════════════════════════════════════════════════════════════════
# AUTH
# ════════════════════════════════════════════════════════════════
@app.route("/welcome")
def welcome():
    return render_template("welcome.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        e = request.form.get("email", "").strip().lower()
        p = request.form.get("password", "")
        role = request.form.get("role", "student")
        if role not in ("student", "coach"):
            role = "student"

        if not (u and e and p):
            flash("All fields are required.", "danger")
            return render_template("signup.html")

        try:
            row = query(
                """INSERT INTO users (username, email, password, role)
                   VALUES (%s,%s,%s,%s) RETURNING id""",
                (u, e, generate_password_hash(p), role),
                commit=True,
            )
            # if coach, create empty coach profile linked to user
            if role == "coach":
                query(
                    """INSERT INTO coaches (user_id, full_name, is_verified, payment_status)
                       VALUES (%s,%s,FALSE,'pending')""",
                    (row["id"], u),
                    commit=True,
                )
            flash("Account created — please log in.", "success")
            return redirect(url_for("login"))
        except psycopg2.errors.UniqueViolation:
            get_db().rollback()
            flash("That email is already registered.", "danger")
        except Exception as ex:
            get_db().rollback()
            flash(f"Error: {ex}", "danger")

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        lid = request.form.get("login_id", "").strip()
        pwd = request.form.get("password", "")

        user = query(
            "SELECT * FROM users WHERE username = %s OR email = %s",
            (lid, lid.lower()),
            one=True,
        )
        if user and check_password_hash(user["password"], pwd):
            session.clear()
            session.update({
                "user_id":  user["id"],
                "is_admin": user["role"] == "admin",
                "role":     user["role"],
                "username": user["username"],
            })
            session.permanent = True
            if user["role"] == "admin":
                return redirect(url_for("admin"))
            if user["role"] == "coach":
                return redirect(url_for("coach_dashboard"))
            return redirect(url_for("home"))

        flash("Invalid credentials.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ════════════════════════════════════════════════════════════════
# COACH DASHBOARD
# ════════════════════════════════════════════════════════════════
@app.route("/coach")
def coach_dashboard():
    user = current_user()
    if not user or user["role"] not in ("coach", "admin"):
        return redirect(url_for("login"))

    profile = query(
        "SELECT * FROM coaches WHERE user_id = %s",
        (user["id"],),
        one=True,
    )
    return render_template("coach.html", profile=profile)

@app.route("/coach/submit", methods=["POST"])
def coach_submit():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    data = request.form
    img_url = upload_to_supabase(request.files.get("image"), folder="coaches")
    # ... your existing image upload logic ...

    query(
        """INSERT INTO coaches
             (user_id, full_name, phone, category, location, bio,
              image_url, is_verified, payment_status)
           VALUES (%s,%s,%s,%s,%s,%s,%s,FALSE,'submitted')""",
        (user["id"], data["full_name"], data["phone"], data["category"],
         data["location"], data["bio"], img_url),
        commit=True,
    )

    flash("Coach submitted successfully!", "success")
    return redirect(url_for("coach_dashboard"))


# ════════════════════════════════════════════════════════════════
# ADMIN
# ════════════════════════════════════════════════════════════════
def require_admin():
    if not is_admin():
        abort(403)


@app.route("/admin", methods=["GET", "POST"])
def admin():
    require_admin()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "quick_add_coach":
            img = upload_to_supabase(request.files.get("image"), folder="coaches") if "image" in request.files else ""
            query(
                """INSERT INTO coaches
                     (full_name, phone, category, location, bio,
                      image_url, is_verified, payment_status)
                   VALUES (%s,%s,%s,%s,%s,%s,TRUE,'paid')""",
                (
                    request.form.get("full_name", "").strip(),
                    request.form.get("phone", "").strip(),
                    request.form.get("category", "").strip(),
                    request.form.get("location", "").strip(),
                    request.form.get("bio", "").strip(),
                    img,
                ),
                commit=True,
            )
            flash("Coach added — live immediately.", "success")
            return redirect(url_for("admin"))

        if action == "create_event":
            event_row = query(
               """INSERT INTO events (title, description, location, event_date, end_date, is_active)
   VALUES (%s,%s,%s,%s,%s,TRUE) RETURNING id""",
                (
                    request.form["title"].strip(),
    request.form.get("description", "").strip(),
    request.form.get("location", "").strip(),
    request.form.get("event_date") or None,
    request.form.get("end_date") or request.form.get("event_date") or None,
                ),
                commit=True,
            )
            event_id = event_row["id"]
            files = request.files.getlist("images")
            for f in files:
                url = upload_to_supabase(f, folder="events")
                if url:
                    query(
                        "INSERT INTO event_images (event_id, image_url) VALUES (%s,%s)",
                        (event_id, url),
                        commit=True,
                    )
            flash("Event created and is now live.", "success")
            return redirect(url_for("admin"))

    pending = query(
        "SELECT * FROM coaches WHERE is_verified = FALSE AND payment_status='submitted' ORDER BY updated_at DESC NULLS LAST"
    )
    live = query(
        "SELECT * FROM coaches WHERE is_verified = TRUE ORDER BY created_at DESC"
    )
    events = query(
        """SELECT e.*,
                  COALESCE(json_agg(ei.image_url ORDER BY ei.id)
                           FILTER (WHERE ei.image_url IS NOT NULL),
                           '[]'::json) AS images
             FROM events e
             LEFT JOIN event_images ei ON ei.event_id = e.id
            GROUP BY e.id
            ORDER BY e.created_at DESC"""
    )
    return render_template("admin.html", pending=pending, live=live, events=events)


@app.route("/admin/coach/<int:cid>/approve", methods=["POST"])
def admin_approve(cid):
    require_admin()
    query(
        "UPDATE coaches SET is_verified=TRUE, payment_status='paid' WHERE id=%s",
        (cid,), commit=True,
    )
    flash("Coach approved.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/coach/<int:cid>/delete", methods=["POST"])
def admin_delete_coach(cid):
    require_admin()
    query("DELETE FROM coaches WHERE id=%s", (cid,), commit=True)
    flash("Coach removed.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/event/<int:eid>/toggle", methods=["POST"])
def admin_toggle_event(eid):
    require_admin()
    query("UPDATE events SET is_active = NOT is_active WHERE id=%s", (eid,), commit=True)
    return redirect(url_for("admin"))


@app.route("/admin/event/<int:eid>/delete", methods=["POST"])
def admin_delete_event(eid):
    require_admin()
    query("DELETE FROM events WHERE id=%s", (eid,), commit=True)
    flash("Event deleted.", "success")
    return redirect(url_for("admin"))


# ── Errors ──────────────────────────────────────────────────────
@app.errorhandler(403)
def err403(e):
    return render_template("error.html", code=403, message="Access denied."), 403

@app.errorhandler(404)
def err404(e):
    return render_template("error.html", code=404, message="Page not found."), 404


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
