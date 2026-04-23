"""
Get My Coach Uganda — Flask version
-----------------------------------
Mirrors the React/Lovable app:
  • Roles: admin, coach, student
  • Coach submits profile -> "submitted" -> Admin verifies -> "paid" + verified
  • Verified coaches appear in the public Student directory
  • Admin (FAROUK / FAROUK2020) can also register coaches from the Coach page
"""
import os
import uuid
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, abort, send_from_directory
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy

# ---------------------------------------------------------------- config
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "instance", "app.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB

db = SQLAlchemy(app)

# ---------------------------------------------------------------- constants
SPORT_CATEGORIES = [
    "Chess", "Football", "Basketball", "Tennis", "Swimming",
    "Athletics", "Volleyball", "Rugby", "Boxing", "Martial Arts",
    "Cricket", "Cycling",
]
ADMIN_USERNAME = "FAROUK"
ADMIN_PASSWORD = "FAROUK2020"
ADMIN_EMAIL = "farouk@getmycoach.ug"
ALLOWED_EXT = {"png", "jpg", "jpeg", "webp", "gif"}

# ---------------------------------------------------------------- models
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = db.Column(db.String(180), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    roles = db.relationship("UserRole", backref="user", cascade="all, delete-orphan")
    profile = db.relationship("Profile", backref="user", uselist=False, cascade="all, delete-orphan")

    def has_role(self, role):
        return any(r.role == role for r in self.roles)

    def primary_role(self):
        names = {r.role for r in self.roles}
        for r in ("admin", "coach", "student"):
            if r in names:
                return r
        return None

    def add_role(self, role):
        if not self.has_role(role):
            db.session.add(UserRole(user_id=self.id, role=role))


class UserRole(db.Model):
    __tablename__ = "user_roles"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin | coach | student
    __table_args__ = (db.UniqueConstraint("user_id", "role", name="uq_user_role"),)


class Profile(db.Model):
    __tablename__ = "profiles"
    id = db.Column(db.String, db.ForeignKey("users.id"), primary_key=True)
    full_name = db.Column(db.String(120), default="")
    phone = db.Column(db.String(40), default="")
    category = db.Column(db.String(40), default="")
    experience_years = db.Column(db.Integer, default=0)
    hourly_rate = db.Column(db.Integer, default=0)
    location = db.Column(db.String(120), default="")
    bio = db.Column(db.Text, default="")
    image_url = db.Column(db.String(255), default="")
    is_verified = db.Column(db.Boolean, default=False)
    payment_status = db.Column(db.String(20), default="pending")  # pending|submitted|paid
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------- helpers
def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return db.session.get(User, uid)


@app.context_processor
def inject_globals():
    u = current_user()
    return {
        "current_user": u,
        "user_role": u.primary_role() if u else None,
        "SPORT_CATEGORIES": SPORT_CATEGORIES,
    }


def login_required(view):
    @wraps(view)
    def w(*a, **kw):
        if not current_user():
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("auth"))
        return view(*a, **kw)
    return w


def role_required(*roles):
    def deco(view):
        @wraps(view)
        def w(*a, **kw):
            u = current_user()
            if not u:
                return redirect(url_for("auth"))
            if not any(u.has_role(r) for r in roles):
                abort(403)
            return view(*a, **kw)
        return w
    return deco


def allowed_file(name):
    return "." in name and name.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def seed_admin():
    """Make sure the FAROUK admin account exists."""
    if not User.query.filter_by(email=ADMIN_EMAIL).first():
        u = User(
            email=ADMIN_EMAIL,
            full_name=ADMIN_USERNAME,
            password_hash=generate_password_hash(ADMIN_PASSWORD),
        )
        db.session.add(u)
        db.session.flush()
        db.session.add(UserRole(user_id=u.id, role="admin"))
        db.session.add(Profile(id=u.id, full_name=ADMIN_USERNAME))
        db.session.commit()


# ---------------------------------------------------------------- routes
@app.route("/")
def index():
    u = current_user()
    if not u:
        return redirect(url_for("auth"))
    role = u.primary_role()
    if role == "admin":
        return redirect(url_for("admin"))
    if role == "coach":
        return redirect(url_for("coach"))
    return redirect(url_for("student"))


# ----- AUTH ------------------------------------------------------
@app.route("/auth", methods=["GET", "POST"])
def auth():
    """Single page for both login and signup, plus FAROUK shortcut."""
    if request.method == "POST":
        mode = request.form.get("mode", "login")
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        # FAROUK super-admin shortcut: works from the login form too
        if email.upper() == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            seed_admin()
            admin = User.query.filter_by(email=ADMIN_EMAIL).first()
            session["user_id"] = admin.id
            flash("Welcome, FAROUK 👑", "success")
            return redirect(url_for("admin"))

        if mode == "signup":
            full_name = request.form.get("full_name", "").strip()
            role = request.form.get("role", "student")
            if role not in ("student", "coach"):
                role = "student"
            if not email or not password:
                flash("Email and password are required.", "danger")
                return redirect(url_for("auth"))
            if User.query.filter_by(email=email).first():
                flash("That email is already registered.", "danger")
                return redirect(url_for("auth"))
            user = User(
                email=email,
                full_name=full_name,
                password_hash=generate_password_hash(password),
            )
            db.session.add(user)
            db.session.flush()
            db.session.add(UserRole(user_id=user.id, role=role))
            db.session.add(Profile(id=user.id, full_name=full_name))
            db.session.commit()
            session["user_id"] = user.id
            flash("Account created.", "success")
            return redirect(url_for("index"))

        # login
        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash("Invalid email or password.", "danger")
            return redirect(url_for("auth"))
        session["user_id"] = user.id
        return redirect(url_for("index"))

    return render_template("auth.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Signed out.", "info")
    return redirect(url_for("auth"))


# ----- COACH -----------------------------------------------------
@app.route("/coach", methods=["GET", "POST"])
@login_required
def coach():
    """Coach profile editor.
    Admin can also use this page; saving will tag them as a coach so the
    submission appears in the admin verification queue (matches the React app).
    """
    u = current_user()
    profile = u.profile or Profile(id=u.id)
    if not u.profile:
        db.session.add(profile)
        db.session.commit()

    if request.method == "POST":
        # photo upload
        file = request.files.get("photo")
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Unsupported image type.", "danger")
                return redirect(url_for("coach"))
            ext = secure_filename(file.filename).rsplit(".", 1)[1].lower()
            fname = f"{u.id}_{uuid.uuid4().hex}.{ext}"
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], fname))
            profile.image_url = url_for("static", filename=f"uploads/{fname}")

        profile.full_name = request.form.get("full_name", "").strip()
        profile.phone = request.form.get("phone", "").strip()
        profile.category = request.form.get("category", "").strip()
        profile.location = request.form.get("location", "").strip()
        profile.bio = request.form.get("bio", "").strip()
        try:
            profile.experience_years = int(request.form.get("experience_years") or 0)
        except ValueError:
            profile.experience_years = 0
        try:
            profile.hourly_rate = int(request.form.get("hourly_rate") or 0)
        except ValueError:
            profile.hourly_rate = 0

        # Mark as submitted unless admin has already approved
        if profile.payment_status != "paid":
            profile.payment_status = "submitted"

        # Ensure user is tagged as coach so admin sees them
        u.add_role("coach")

        db.session.commit()
        flash("Profile saved. Awaiting admin verification.", "success")
        return redirect(url_for("coach"))

    return render_template("coach.html", profile=profile, is_admin=u.has_role("admin"))


# ----- ADMIN -----------------------------------------------------
@app.route("/admin")
@role_required("admin")
def admin():
    coach_ids = [r.user_id for r in UserRole.query.filter_by(role="coach").all()]
    rows = (
        Profile.query.filter(Profile.id.in_(coach_ids))
        .order_by(Profile.updated_at.desc())
        .all()
    ) if coach_ids else []
    pending = [p for p in rows if p.payment_status == "submitted"]
    live = [p for p in rows if p.payment_status == "paid" and p.is_verified]
    # attach email for display
    for p in pending + live:
        p.email = p.user.email if p.user else ""
    return render_template("admin.html", pending=pending, live=live)


@app.route("/admin/<coach_id>/approve", methods=["POST"])
@role_required("admin")
def admin_approve(coach_id):
    p = db.session.get(Profile, coach_id)
    if not p:
        abort(404)
    p.is_verified = True
    p.payment_status = "paid"
    db.session.commit()
    flash(f"{p.full_name or 'Coach'} is now live.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/<coach_id>/remove", methods=["POST"])
@role_required("admin")
def admin_remove(coach_id):
    p = db.session.get(Profile, coach_id)
    if not p:
        abort(404)
    p.is_verified = False
    p.payment_status = "pending"
    db.session.commit()
    flash("Coach removed from the public directory.", "info")
    return redirect(url_for("admin"))


# ----- STUDENT ---------------------------------------------------
@app.route("/student")
@login_required
def student():
    category = request.args.get("category", "").strip()
    location = request.args.get("location", "").strip()

    coach_ids = [r.user_id for r in UserRole.query.filter_by(role="coach").all()]
    q = Profile.query.filter(
        Profile.id.in_(coach_ids) if coach_ids else False,
        Profile.is_verified == True,  # noqa: E712
        Profile.payment_status == "paid",
    )
    if category:
        q = q.filter(Profile.category == category)
    if location:
        q = q.filter(Profile.location.ilike(f"%{location}%"))
    coaches = q.order_by(Profile.updated_at.desc()).all()
    return render_template(
        "student.html",
        coaches=coaches,
        category=category,
        location=location,
    )


# ---------------------------------------------------------------- bootstrap
with app.app_context():
    db.create_all()
    seed_admin()


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
