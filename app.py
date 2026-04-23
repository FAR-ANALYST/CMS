import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from supabase import create_client, Client
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "farouk_getmycoach_uganda_2026")

# --- SUPABASE CONFIG ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    print("WARNING: Supabase credentials missing from environment variables.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


# --- HELPER: Communication Status Banner ---
def get_status_info(status):
    """Returns a user-friendly message and color class based on payment/verification state."""
    states = {
        'pending':   {"msg": "Action Required: Complete your profile and submit for review.", "color": "text-neutral-400", "dot": "bg-neutral-500"},
        'submitted': {"msg": "Under Review: Awaiting payment confirmation from Admin (UGX 20,000).", "color": "text-yellow-400", "dot": "bg-yellow-400"},
        'paid':      {"msg": "Verified & Live! Your profile is now visible to students.", "color": "text-green-400", "dot": "bg-green-400"},
    }
    return states.get(status, states['pending'])


# ─────────────────────────────────────────────
#  LOGIN / LOGOUT
# ─────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('login.html')


@app.route('/login', methods=['POST'])
def login():
    login_id = request.form.get('login_id', '').strip()
    password  = request.form.get('password', '')

    # ── ADMIN OVERRIDE (FAROUK) ──
    if login_id == "FAROUK" and password == "FAROUK2020":
        session.update({
            'user_id':  "00000000-0000-0000-0000-000000000000",
            'role':     "admin",
            'username': "FAROUK"
        })
        return redirect(url_for('admin_face'))

    # ── STANDARD LOGIN ──
    try:
        res = supabase.table('profiles').select('*') \
            .or_(f"username.eq.{login_id},email.eq.{login_id}").execute()

        if not res.data:
            return render_template('login.html', error="User not found. Please register.")

        user = res.data[0]
        auth = supabase.auth.sign_in_with_password({"email": user['email'], "password": password})

        session.update({
            'user_id':  auth.user.id,
            'role':     user.get('role', 'student'),
            'username': user.get('username', '')
        })

        if session['role'] == 'coach':
            return redirect(url_for('coach_face'))
        if session['role'] == 'admin':
            return redirect(url_for('admin_face'))
        return redirect(url_for('student_face'))

    except Exception as e:
        return render_template('login.html', error=f"Login failed: {str(e)}")


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


# ─────────────────────────────────────────────
#  STUDENT FACE  –  /student
#  Only verified (paid) coaches appear here.
# ─────────────────────────────────────────────

@app.route('/student')
def student_face():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    sport = request.args.get('sport', '')
    loc   = request.args.get('location', '')

    query = (supabase.table('profiles').select('*')
             .eq('role', 'coach')
             .eq('is_verified', True)
             .eq('payment_status', 'paid'))

    if sport: query = query.eq('sport_category', sport)
    if loc:   query = query.eq('location_district', loc)

    coaches = query.execute().data

    # Build filter dropdown options from ALL verified coaches
    all_verified = (supabase.table('profiles')
                    .select('sport_category, location_district')
                    .eq('role', 'coach')
                    .eq('is_verified', True)
                    .execute().data)

    sports    = sorted({c['sport_category']   for c in all_verified if c.get('sport_category')})
    locations = sorted({c['location_district'] for c in all_verified if c.get('location_district')})

    return render_template('student.html',
                           coaches=coaches,
                           sports=sports,
                           locations=locations,
                           selected_sport=sport,
                           selected_location=loc,
                           role=session.get('role'))


# ─────────────────────────────────────────────
#  COACH FACE  –  /coach
#  Coach submits details → status → 'submitted'
#  Admin sees the submission and marks paid.
# ─────────────────────────────────────────────

@app.route('/coach', methods=['GET', 'POST'])
def coach_face():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    is_admin = (session.get('role') == 'admin')

    # ── POST: Coach submits/updates profile ──
    if request.method == 'POST' and not is_admin:
        try:
            file    = request.files.get('profile_image')
            img_url = request.form.get('existing_url', '')

            # Handle image upload to Supabase Storage
            if file and file.filename != '':
                filename  = secure_filename(f"{session['user_id']}_{file.filename}")
                temp_path = os.path.join('/tmp', filename)
                file.save(temp_path)

                with open(temp_path, 'rb') as f:
                    supabase.storage.from_('coaches').upload(
                        f"photos/{filename}", f, {"upsert": "true"}
                    )
                img_url = supabase.storage.from_('coaches').get_public_url(f"photos/{filename}")

            update_data = {
                "full_name":         request.form.get('full_name', '').strip(),
                "sport_category":    request.form.get('sport_category', '').strip(),
                "location_district": request.form.get('location_district', '').strip(),
                "contact_number":    request.form.get('contact_number', '').strip(),
                "bio":               request.form.get('bio', '').strip(),
                "profile_pic_url":   img_url,
                "payment_status":    "submitted",   # ← signals Admin
                "is_verified":       False,          # ← hidden from students
                "role":              "coach",
            }

            supabase.table('profiles').update(update_data).eq('id', session['user_id']).execute()
            flash("Profile submitted! Admin will review and confirm your payment shortly.")

        except Exception as e:
            flash(f"Error saving profile: {str(e)}")

        return redirect(url_for('coach_face'))

    # ── GET: Load profile ──
    profile     = {}
    status_info = get_status_info('pending')

    if not is_admin:
        try:
            p = supabase.table('profiles').select('*').eq('id', session['user_id']).execute()
            if p.data:
                profile     = p.data[0]
                status_info = get_status_info(profile.get('payment_status', 'pending'))
            else:
                # Auto-create a blank coach row so the page doesn't crash
                supabase.table('profiles').insert({
                    "id":             session['user_id'],
                    "role":           "coach",
                    "is_verified":    False,
                    "payment_status": "pending"
                }).execute()
        except Exception as e:
            flash(f"Database error: {str(e)}")
    else:
        profile     = {"full_name": "Admin Preview Mode"}
        status_info = get_status_info('paid')

    return render_template('coach.html',
                           profile=profile,
                           status_info=status_info,
                           role=session.get('role'))


# ─────────────────────────────────────────────
#  ADMIN FACE  –  /admin
#  Sees all coaches with status = 'submitted'.
#  Clicking "Mark as Paid" → is_verified=True, payment_status='paid'
#  → coach immediately appears on Student Page.
# ─────────────────────────────────────────────

@app.route('/admin')
def admin_face():
    if session.get('role') != 'admin':
        return redirect(url_for('index'))

    # Coaches who have submitted but not yet been verified/paid
    pending = (supabase.table('profiles').select('*')
               .eq('role', 'coach')
               .eq('is_verified', False)
               .eq('payment_status', 'submitted')
               .execute().data)

    # Coaches already verified (for reference table)
    verified = (supabase.table('profiles').select('*')
                .eq('role', 'coach')
                .eq('is_verified', True)
                .execute().data)

    return render_template('admin.html',
                           pending=pending,
                           verified=verified,
                           role='admin')


@app.route('/admin/mark_paid/<coach_id>')
def mark_paid(coach_id):
    if session.get('role') != 'admin':
        return "Unauthorized", 403

    # ← THE KEY CONNECTION: flip the switches so coach goes live on Student Page
    supabase.table('profiles').update({
        "is_verified":    True,
        "payment_status": "paid"
    }).eq('id', coach_id).execute()

    return redirect(url_for('admin_face'))


@app.route('/admin/remove/<coach_id>')
def remove_coach(coach_id):
    """Admin can un-verify a coach (e.g. if payment bounced)."""
    if session.get('role') != 'admin':
        return "Unauthorized", 403

    supabase.table('profiles').update({
        "is_verified":    False,
        "payment_status": "pending"
    }).eq('id', coach_id).execute()

    return redirect(url_for('admin_face'))


# ─────────────────────────────────────────────
#  RUN
# ─────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
