import os
from flask import Flask, render_template, request, redirect, url_for, session
from supabase import create_client, Client
from dotenv import load_dotenv

# Load local .env for development
load_dotenv()

app = Flask(__name__)
# Secret key for session security
app.secret_key = os.environ.get("FLASK_SECRET", "farouk_cms_uganda_2026")

# --- SUPABASE CONFIGURATION ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

# Initialize Supabase Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# --- ROUTES ---

@app.route('/')
def index():
    """Face 1: The Login Portal"""
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    """Unified Login Logic with Admin Override"""
    login_id = request.form.get('login_id', '').strip()
    password = request.form.get('password', '')

    # 1. --- THE FAROUK OVERRIDE ---
    # This allows you to access the Admin Face without a DB record
    if login_id == "FAROUK" and password == "FAROUK2020":
        session['user_id'] = "admin_static_bypass"
        session['role'] = "admin"
        session['username'] = "FAROUK"
        return redirect(url_for('student_face'))

    try:
        # 2. Database Lookup: Check both 'username' and 'email' columns
        user_query = supabase.table('profiles').select('*') \
            .or_(f"username.eq.{login_id},email.eq.{login_id}").execute()

        if not user_query.data:
            return "Login Error: Account not found. Please register as a coach first."

        user_info = user_query.data[0]
        
        # 3. Authenticate with Supabase Auth using the found email
        auth_response = supabase.auth.sign_in_with_password({
            "email": user_info['email'], 
            "password": password
        })
        
        # 4. Success - Set Session Data
        session['user_id'] = auth_response.user.id
        session['role'] = user_info.get('role', 'student')
        session['username'] = user_info.get('username')
        
        return redirect(url_for('student_face'))
        
    except Exception as e:
        return f"Authentication failed: {str(e)}"

@app.route('/student')
def student_face():
    """Face 1: Directory Face"""
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    # Fetch coaches who are verified for the public directory
    coaches_res = supabase.table('profiles').select('*').eq('role', 'coach').eq('is_verified', True).execute()
    return render_template('student.html', coaches=coaches_res.data, role=session.get('role'))

@app.route('/coach', methods=['GET', 'POST'])
def coach_face():
    """Face 2: Coach Management Face"""
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        # Activation via NCS Sport Code
        code = request.form.get('activation_code', '').upper()
        try:
            supabase.rpc('activate_coach_profile', {
                'user_id': session['user_id'], 
                'input_code': code
            }).execute()
        except Exception as e:
            return f"Verification Error: {str(e)}"
            
    # Fetch updated profile data
    profile_data = supabase.table('profiles').select('*').eq('id', session['user_id']).single().execute()
    return render_template('coach.html', profile=profile_data.data, role=session.get('role'))

@app.route('/admin')
def admin_face():
    """Face 3: Admin Command Center"""
    if session.get('role') != 'admin':
        return "Unauthorized: Admin access only.", 403
    
    # Pull active, unused codes for the dashboard
    codes_res = supabase.table('coach_codes').select('*').eq('is_used', False).order('created_at', desc=True).execute()
    return render_template('admin.html', codes=codes_res.data)

@app.route('/admin/generate', methods=['POST'])
def generate_code_action():
    """Internal Admin Action to create new sport-specific codes"""
    if session.get('role') != 'admin':
        return "Unauthorized", 403
        
    sport_abbr = request.form.get('sport_abbr', 'GEN').upper()
    try:
        supabase.rpc('generate_coach_code', {'sport_abbr': sport_abbr}).execute()
        return redirect(url_for('admin_face'))
    except Exception as e:
        # This triggers if RLS is still on or SQL functions are missing
        return f"Database Error: {str(e)}"

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Listen on all interfaces for Render deployment
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
