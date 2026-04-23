import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from supabase import create_client, Client
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "farouk_comms_system_2026")

supabase: Client = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_ANON_KEY"))

# --- HELPER: Communication Status ---
def get_status_info(status):
    """Returns a user-friendly message and color based on the communication state"""
    states = {
        'pending': {"msg": "Action Required: Complete your profile.", "color": "text-neutral-500"},
        'submitted': {"msg": "Status: Under Review by Farouk. Please pay UGX 20,000.", "color": "text-yellow-500"},
        'paid': {"msg": "Status: Verified & Live on Student Page!", "color": "text-green-500"}
    }
    return states.get(status, states['pending'])

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    login_id = request.form.get('login_id', '').strip()
    password = request.form.get('password', '')

    if login_id == "FAROUK" and password == "FAROUK2020":
        session.update({'user_id': "00000000-0000-0000-0000-000000000000", 'role': "admin"})
        return redirect(url_for('admin_face'))

    try:
        user_data = supabase.table('profiles').select('*').or_(f"username.eq.{login_id},email.eq.{login_id}").execute()
        if not user_data.data: return "User not found."
        
        user = user_data.data[0]
        auth = supabase.auth.sign_in_with_password({"email": user['email'], "password": password})
        session.update({'user_id': auth.user.id, 'role': user.get('role', 'student')})
        
        return redirect(url_for('coach_face') if session['role'] == 'coach' else url_for('student_face'))
    except: return "Login Failed."

@app.route('/student')
def student_face():
    if 'user_id' not in session: return redirect(url_for('index'))
    
    # COMMUNICATION: Students only see coaches who have reached the 'paid' state
    query = supabase.table('profiles').select('*').eq('role', 'coach').eq('is_verified', True).eq('payment_status', 'paid')
    
    sport, loc = request.args.get('sport'), request.args.get('location')
    if sport: query = query.eq('sport_category', sport)
    if loc: query = query.eq('location_district', loc)
    
    coaches = query.execute().data
    return render_template('student.html', coaches=coaches, role=session.get('role'))

@app.route('/coach', methods=['GET', 'POST'])
def coach_face():
    if 'user_id' not in session: return redirect(url_for('index'))
    
    if request.method == 'POST' and session.get('role') != 'admin':
        file = request.files.get('profile_image')
        img_url = request.form.get('existing_url')
        
        if file and file.filename != '':
            filename = secure_filename(f"{session['user_id']}_{file.filename}")
            temp_path = os.path.join('/tmp', filename)
            file.save(temp_path)
            with open(temp_path, 'rb') as f:
                supabase.storage.from_('coaches').upload(f"photos/{filename}", f, {"upsert": "true"})
            img_url = supabase.storage.from_('coaches').get_public_url(f"photos/{filename}")

        # COMMUNICATION: Sending update to Admin
        update_data = {
            "full_name": request.form.get('full_name'),
            "sport_category": request.form.get('sport_category'),
            "location_district": request.form.get('location_district'),
            "contact_number": request.form.get('contact_number'),
            "profile_pic_url": img_url,
            "payment_status": "submitted", # Message to Admin: "I've submitted!"
            "is_verified": False
        }
        supabase.table('profiles').update(update_data).eq('id', session['user_id']).execute()
        flash("Profile submitted to Admin for approval.")
        return redirect(url_for('coach_face'))

    # Fetch profile and current status communication
    p_data = supabase.table('profiles').select('*').eq('id', session['user_id']).execute()
    profile = p_data.data[0] if p_data.data else {}
    status_info = get_status_info(profile.get('payment_status', 'pending'))

    return render_template('coach.html', profile=profile, status_info=status_info, role=session.get('role'))

@app.route('/admin')
def admin_face():
    if session.get('role') != 'admin': return redirect(url_for('index'))
    
    # COMMUNICATION: Admin sees only those who sent the 'submitted' signal
    pending = supabase.table('profiles').select('*').eq('role', 'coach').eq('payment_status', 'submitted').execute().data
    return render_template('admin.html', pending=pending, role='admin')

@app.route('/admin/mark_paid/<coach_id>')
def mark_paid(coach_id):
    if session.get('role') != 'admin': return "Unauthorized", 403
    
    # COMMUNICATION: Admin signals to the Coach and Student face that payment is cleared
    supabase.table('profiles').update({
        "is_verified": True, 
        "payment_status": "paid"
    }).eq('id', coach_id).execute()
    
    return redirect(url_for('admin_face'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))
