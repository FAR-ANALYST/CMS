import os
from flask import Flask, render_template, request, redirect, url_for, session
from supabase import create_client, Client
from dotenv import load_dotenv

# Load .env for local development
load_dotenv()

app = Flask(__name__)
# Secret key for secure session handling
app.secret_key = os.environ.get("FLASK_SECRET", "farouk_uganda_sports_2026")

# --- SUPABASE CONFIGURATION ---
# Ensure these match the "Name of Variable" keys in your Render Dashboard
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    print("⚠️ WARNING: Supabase credentials missing. Check Render Environment Variables.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# --- ROUTES ---

@app.route('/')
def index():
    """Initial landing page (Login Face)."""
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    """Unified Login: Handles Username, Email, and Admin Override."""
    login_id = request.form.get('login_id', '').strip()
    password = request.form.get('password', '')

    # 1. --- THE FAROUK OVERRIDE ---
    if login_id == "FAROUK" and password == "FAROUK2020":
        session['user_id'] = "admin_override_static"
        session['role'] = "admin"
        session['username'] = "FAROUK"
        return redirect(url_for('student_face'))

    try:
        # 2. Database Lookup: Check if login_id matches 'username' OR 'email'
        user_query = supabase.table('profiles').select('id, email, role, username') \
            .or_(f"username.eq.{login_id},email.eq.{login_id}").execute()

        if not user_query.data:
            return "Login Error: User not found in system."

        # 3. Authenticate with Supabase Auth using the linked email
        actual_email = user_query.data[0]['email']
        auth_response = supabase.auth.sign_in_with_password({
            "email": actual_email, 
            "password": password
        })
        
        # 4. Set Session Data
        session['user_id'] = auth_response.user.id
        session['role'] = user_query.data[0]['role']
        session['username'] = user_query.data[0]['username']
        
        return redirect(url_for('student_face'))
        
    except Exception as e:
        return f"Authentication failed: {str(e)}"

@app.route('/student')
def student_face():
    """Face 1: Directory of verified coaches."""
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    # Fetch coaches who have activated their profiles via Face 2
    coaches_res = supabase.table('profiles').select('*').eq('role', 'coach').eq('is_verified', True).execute()
    return render_template('student.html', coaches=coaches_res.data, role=session.get('role'))

@app.route('/coach', methods=['GET', 'POST'])
def coach_face():
    """Face 2: Coach Dashboard for profile activation and management."""
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        # Activation using the 3-letter sport code (e.g., CHE-1234)
        code = request.form.get('activation_code', '').upper()
        try:
            # Executes the SQL logic in Supabase to verify the code
            supabase.rpc('activate_coach_profile', {
                'user_id': session['user_id'], 
                'input_code': code
            }).execute()
        except Exception as e:
            return f"Activation Failed: {str(e)}"
            
    # Refresh profile data to check current status
    profile_res = supabase.table('profiles').select('*').eq('id', session['user_id']).single().execute()
    return render_template('coach.html', profile=profile_res.data, role=session.get('role'))

@app.route('/admin')
def admin_face():
    """Face 3: Admin Command Center for generating codes."""
    if session.get('role') != 'admin':
        return "Access Denied: Admin privileges required.", 403
    
    # Fetch unused codes to display to the admin
    codes_res = supabase.table('coach_codes').select('*').eq('is_used', False).order('created_at', desc=True).execute()
    return render_template('admin.html', codes=codes_res.data)

@app.route('/admin/generate', methods=['POST'])
def generate_code_action():
    """Generates a new 3-letter sport code (Face 3)."""
    if session.get('role') != 'admin':
        return "Unauthorized", 403
        
    sport_abbr = request.form.get('sport_abbr', 'GEN').upper()
    try:
        # Calls the SQL generator function
        supabase.rpc('generate_coach_code', {'sport_abbr': sport_abbr}).execute()
        return redirect(url_for('admin_face'))
    except Exception as e:
        return f"Error generating code: {str(e)}"

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Dynamic port for Render deployment
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
