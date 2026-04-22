import os
from flask import Flask, render_template, request, redirect, url_for, session
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "farouk_master_key_2026")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    login_id = request.form.get('login_id', '').strip()
    password = request.form.get('password', '')

    if login_id == "FAROUK" and password == "FAROUK2020":
        session['user_id'] = "admin_bypass_static"
        session['role'] = "admin"
        return redirect(url_for('student_face'))

    try:
        user_query = supabase.table('profiles').select('*').or_(f"username.eq.{login_id},email.eq.{login_id}").execute()
        if not user_query.data: return "User not found."
        user = user_query.data[0]
        auth = supabase.auth.sign_in_with_password({"email": user['email'], "password": password})
        session['user_id'] = auth.user.id
        session['role'] = user.get('role', 'student')
        return redirect(url_for('student_face'))
    except Exception as e: return f"Login Error: {str(e)}"

@app.route('/student')
def student_face():
    if 'user_id' not in session: return redirect(url_for('index'))
    coaches = supabase.table('profiles').select('*').eq('role', 'coach').eq('is_verified', True).execute()
    return render_template('student.html', coaches=coaches.data, role=session.get('role'))

@app.route('/coach', methods=['GET', 'POST'])
def coach_face():
    if 'user_id' not in session: return redirect(url_for('index'))
    
    # FIX: Check if Admin is viewing the page to avoid UUID errors
    if session.get('user_id') == "admin_bypass_static":
        profile = {"full_name": "FAROUK (Admin)", "role": "admin", "is_verified": True}
    else:
        try:
            profile_res = supabase.table('profiles').select('*').eq('id', session['user_id']).execute()
            if not profile_res.data:
                # Auto-create profile for new coach
                new_data = {"id": session['user_id'], "role": "coach", "is_verified": False}
                supabase.table('profiles').insert(new_data).execute()
                profile = new_data
            else:
                profile = profile_res.data[0]
        except Exception as e:
            return f"Coach Face Database Error: {str(e)}"

    if request.method == 'POST' and session.get('user_id') != "admin_bypass_static":
        if 'activation_code' in request.form:
            code = request.form.get('activation_code', '').upper()
            try:
                supabase.rpc('activate_coach_profile', {'user_id': session['user_id'], 'input_code': code}).execute()
            except Exception as e: return f"Activation Error: {str(e)}"
        
        elif 'full_name' in request.form:
            fields = ["full_name", "sport_category", "location_district", "contact_number", "profile_pic_url", "bio"]
            update_data = {f: request.form.get(f) for f in fields}
            supabase.table('profiles').update(update_data).eq('id', session['user_id']).execute()
        
        return redirect(url_for('coach_face'))
            
    return render_template('coach.html', profile=profile, role=session.get('role'))

@app.route('/admin')
def admin_face():
    if session.get('role') != 'admin': return "Access Denied", 403
    codes = supabase.table('coach_codes').select('*').eq('is_used', False).order('created_at', desc=True).execute()
    return render_template('admin.html', codes=codes.data)

@app.route('/admin/generate', methods=['POST'])
def generate_code_action():
    if session.get('role') != 'admin': return "Unauthorized", 403
    sport = request.form.get('sport_abbr', 'GEN').upper()
    coach_name = request.form.get('coach_name', 'Unnamed Coach')
    try:
        supabase.rpc('generate_coach_code', {'sport_abbr': sport}).execute()
        latest = supabase.table('coach_codes').select('code').order('created_at', desc=True).limit(1).execute()
        if latest.data:
            supabase.table('coach_codes').update({"intended_for_name": coach_name}).eq('code', latest.data[0]['code']).execute()
        return redirect(url_for('admin_face'))
    except Exception as e: return f"Code Gen Error: {str(e)}"

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
