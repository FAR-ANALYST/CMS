import os
from flask import Flask, render_template, request, redirect, url_for, session
from supabase import create_client, Client
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "farouk_final_fix_2026")

supabase: Client = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_ANON_KEY"))

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    login_id, password = request.form.get('login_id', '').strip(), request.form.get('password', '')
    if login_id == "FAROUK" and password == "FAROUK2020":
        # We give the admin a fake ID that looks like a UUID to satisfy any shared logic
        session.update({'user_id': "00000000-0000-0000-0000-000000000000", 'role': "admin"})
        return redirect(url_for('admin_face'))
    try:
        user = supabase.table('profiles').select('*').or_(f"username.eq.{login_id},email.eq.{login_id}").execute().data[0]
        auth = supabase.auth.sign_in_with_password({"email": user['email'], "password": password})
        session.update({'user_id': auth.user.id, 'role': user.get('role', 'student')})
        return redirect(url_for('student_face'))
    except: return "Login Failed."

@app.route('/student')
def student_face():
    if 'user_id' not in session: return redirect(url_for('index'))
    query = supabase.table('profiles').select('*').eq('role', 'coach').eq('is_verified', True)
    
    # Filtering
    sport = request.args.get('sport')
    loc = request.args.get('location')
    if sport: query = query.eq('sport_category', sport)
    if loc: query = query.eq('location_district', loc)
    
    coaches = query.execute().data
    
    # Get filters from verified coaches only
    all_v = supabase.table('profiles').select('sport_category, location_district').eq('role', 'coach').eq('is_verified', True).execute().data
    sports = sorted(list(set(c['sport_category'] for c in all_v if c['sport_category'])))
    locations = sorted(list(set(c['location_district'] for c in all_v if c['location_district'])))
    
    return render_template('student.html', coaches=coaches, sports=sports, locations=locations, role=session.get('role'))

@app.route('/coach', methods=['GET', 'POST'])
def coach_face():
    if 'user_id' not in session: return redirect(url_for('index'))
    
    # Admin viewing coach face preview
    if session.get('role') == "admin":
        return render_template('coach.html', profile={"full_name": "Admin Preview"}, role="admin")

    if request.method == 'POST':
        file = request.files.get('profile_image')
        img_url = request.form.get('existing_url')
        
        if file and file.filename != '':
            filename = secure_filename(f"{session['user_id']}_{file.filename}")
            temp = os.path.join('/tmp', filename); file.save(temp)
            with open(temp, 'rb') as f:
                supabase.storage.from_('coaches').upload(f"photos/{filename}", f, {"upsert": "true"})
            img_url = supabase.storage.from_('coaches').get_public_url(f"photos/{filename}")

        data = {
            "full_name": request.form.get('full_name'),
            "sport_category": request.form.get('sport_category'),
            "location_district": request.form.get('location_district'),
            "contact_number": request.form.get('contact_number'),
            "profile_pic_url": img_url,
            "bio": request.form.get('bio'),
            "payment_status": "submitted" # This triggers visibility on Admin Page
        }
        supabase.table('profiles').update(data).eq('id', session['user_id']).execute()
        return redirect(url_for('coach_face'))

    p = supabase.table('profiles').select('*').eq('id', session['user_id']).execute().data
    return render_template('coach.html', profile=p[0] if p else {}, role=session.get('role'))

@app.route('/admin')
def admin_face():
    if session.get('role') != 'admin': return redirect(url_for('index'))
    # This query fetches coaches who have submitted but are not verified
    pending = supabase.table('profiles').select('*').eq('role', 'coach').eq('is_verified', False).eq('payment_status', 'submitted').execute().data
    return render_template('admin.html', pending=pending, role='admin')

@app.route('/admin/mark_paid/<id>')
def mark_paid(id):
    if session.get('role') != 'admin': return "Denied", 403
    supabase.table('profiles').update({"is_verified": True, "payment_status": "paid"}).eq('id', id).execute()
    return redirect(url_for('admin_face'))

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('index'))
