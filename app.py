import os
from flask import Flask, render_template, request, redirect, url_for, session
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "ncs_uganda_2026")

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

    # --- ADMIN OVERRIDE ---
    if login_id == "FAROUK" and password == "FAROUK2020":
        session['user_id'] = "admin_override"
        session['role'] = "admin"
        session['username'] = "FAROUK"
        return redirect(url_for('student_face'))

    try:
        user_query = supabase.table('profiles').select('*') \
            .or_(f"username.eq.{login_id},email.eq.{login_id}").execute()

        if not user_query.data:
            return "User not found. Register first."

        user_data = user_query.data[0]
        auth_res = supabase.auth.sign_in_with_password({"email": user_data['email'], "password": password})
        
        session['user_id'] = auth_res.user.id
        session['role'] = user_data.get('role', 'student')
        session['username'] = user_data.get('username')
        
        return redirect(url_for('student_face'))
    except Exception as e:
        return f"Login Error: {str(e)}"

@app.route('/student')
def student_face():
    if 'user_id' not in session: return redirect(url_for('index'))
    # Fetch only verified coaches
    coaches = supabase.table('profiles').select('*').eq('role', 'coach').eq('is_verified', True).execute()
    return render_template('student.html', coaches=coaches.data, role=session.get('role'))

@app.route('/coach', methods=['GET', 'POST'])
def coach_face():
    if 'user_id' not in session: return redirect(url_for('index'))
    
    if request.method == 'POST':
        code = request.form.get('activation_code', '').upper()
        try:
            supabase.rpc('activate_coach_profile', {'user_id': session['user_id'], 'input_code': code}).execute()
        except Exception as e:
            return f"Code Error: {str(e)}"

    profile = supabase.table('profiles').select('*').eq('id', session['user_id']).single().execute()
    return render_template('coach.html', profile=profile.data, role=session.get('role'))

@app.route('/admin')
def admin_face():
    if session.get('role') != 'admin': return "Access Denied", 403
    codes = supabase.table('coach_codes').select('*').eq('is_used', False).execute()
    return render_template('admin.html', codes=codes.data)

@app.route('/admin/generate', methods=['POST'])
def generate_code_action():
    if session.get('role') != 'admin': return "Unauthorized", 403
    sport = request.form.get('sport_abbr', 'GEN').upper()
    supabase.rpc('generate_coach_code', {'sport_abbr': sport}).execute()
    return redirect(url_for('admin_face'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
