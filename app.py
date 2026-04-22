import os
from flask import Flask, render_template, request, redirect, url_for, session
from supabase import create_client, Client
from dotenv import load_dotenv

# Load local .env for testing; Render will use its own dashboard variables
load_dotenv()

app = Flask(__name__)
# A secure secret key is required for session management
app.secret_key = os.environ.get("FLASK_SECRET", "uganda_sports_network_2026")

# --- SUPABASE CONFIGURATION ---
# These MUST match the "Name of Variable" you typed in Render
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    print("⚠️ Error: Supabase credentials not found in environment variables.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# --- ROUTES ---

@app.route('/')
def index():
    """Face 1 & 2: The entry point for login."""
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email')
    password = request.form.get('password')
    try:
        # Authenticate via Supabase Auth
        response = supabase.auth.sign_in_with_password({"email": email, "password": password})
        session['user_id'] = response.user.id
        
        # Pull profile to determine the 'Face' (role)
        # Note: 'profiles' table must exist with a 'role' column
        profile = supabase.table('profiles').select('role').eq('id', response.user.id).single().execute()
        session['role'] = profile.data.get('role', 'student')
        
        return redirect(url_for('student_face'))
    except Exception as e:
        return f"Authentication failed: {str(e)}"

@app.route('/student')
def student_face():
    """Face 1: Directory of verified coaches for students."""
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    # Get all coaches who have successfully activated their profiles
    coaches_res = supabase.table('profiles').select('*').eq('role', 'coach').eq('is_verified', True).execute()
    return render_template('student.html', coaches=coaches_res.data, role=session.get('role'))

@app.route('/coach', methods=['GET', 'POST'])
def coach_face():
    """Face 2: Coach Dashboard for profile management and activation."""
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        # Activation logic using the unique 3-letter code
        code = request.form.get('activation_code')
        try:
            # Calls the SQL function we created in Supabase
            supabase.rpc('activate_coach_profile', {
                'user_id': session['user_id'], 
                'input_code': code.upper()
            }).execute()
        except Exception as e:
            return f"Activation Error: {str(e)}"
            
    # Fetch latest profile data to check verification status
    profile = supabase.table('profiles').select('*').eq('id', session['user_id']).single().execute()
    return render_template('coach.html', profile=profile.data, role=session.get('role'))

@app.route('/admin')
def admin_face():
    """Face 3: Administrator Face for generating 3-letter sport codes."""
    if session.get('role') != 'admin':
        return "Unauthorized: Admin access required.", 403
    
    # Fetch unused codes to display in the dashboard
    codes_res = supabase.table('coach_codes').select('*').eq('is_used', False).order('created_at', desc=True).execute()
    return render_template('admin.html', codes=codes_res.data)

@app.route('/admin/generate', methods=['POST'])
def generate_code_action():
    """Triggered from Face 3 to create a new unique code."""
    if session.get('role') != 'admin':
        return "Unauthorized", 403
        
    sport_abbr = request.form.get('sport_abbr', 'NCS').upper()
    try:
        # Calls generate_coach_code(sport_abbr) in Supabase
        supabase.rpc('generate_coach_code', {'sport_abbr': sport_abbr}).execute()
        return redirect(url_for('admin_face'))
    except Exception as e:
        return f"Code Generation Error: {str(e)}"

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Local run setting; Render will use gunicorn in production
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=False)
