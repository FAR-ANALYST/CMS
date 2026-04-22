import os
from flask import Flask, render_template, request, redirect, url_for, session
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = "uganda_sports_secret_key"

# Supabase Connection
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_ANON_KEY")
supabase: Client = create_client(url, key)

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email')
    password = request.form.get('password')
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        session['user_id'] = res.user.id
        # Fetch role from profiles table
        profile = supabase.table('profiles').select('role').eq('id', res.user.id).single().execute()
        session['role'] = profile.data['role']
        return redirect(url_for('student_face'))
    except Exception as e:
        return f"Login Error: {str(e)}"

@app.route('/student')
def student_face():
    if 'user_id' not in session: return redirect(url_for('index'))
    # Face 1: Get all active coaches
    coaches = supabase.table('profiles').select('*').eq('role', 'coach').eq('is_verified', True).execute()
    return render_template('student.html', coaches=coaches.data, role=session.get('role'))

@app.route('/coach', methods=['GET', 'POST'])
def coach_face():
    if 'user_id' not in session: return redirect(url_for('index'))
    
    if request.method == 'POST':
        code = request.form.get('activation_code')
        try:
            supabase.rpc('activate_coach_profile', {'user_id': session['user_id'], 'input_code': code}).execute()
        except Exception as e:
            return f"Activation Error: {str(e)}"
            
    profile = supabase.table('profiles').select('*').eq('id', session['user_id']).single().execute()
    return render_template('coach.html', profile=profile.data, role=session.get('role'))

@app.route('/admin')
def admin_face():
    if session.get('role') != 'admin': return "Access Denied", 403
    codes = supabase.table('coach_codes').select('*').eq('is_used', False).execute()
    return render_template('admin.html', codes=codes.data)

@app.route('/admin/generate', methods=['POST'])
def generate_code():
    sport_abbr = request.form.get('sport_abbr').upper()
    supabase.rpc('generate_coach_code', {'sport_abbr': sport_abbr}).execute()
    return redirect(url_for('admin_face'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
