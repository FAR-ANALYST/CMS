import os
from flask import Flask, render_template, request, redirect, url_for, session
from supabase import create_client, Client
from dotenv import load_dotenv

# Load local environment variables
load_dotenv()

app = Flask(__name__)
# Secret key for session encryption
app.secret_key = os.environ.get("FLASK_SECRET", "farouk_uganda_sports_master_2026")

# --- SUPABASE CONFIGURATION ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    print("⚠️ WARNING: Supabase credentials missing from Environment Variables.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# --- ROUTES ---

@app.route('/')
def index():
    """Face 1: Login Page"""
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    """Unified Login with Admin Override"""
    login_id = request.form.get('login_id', '').strip()
    password = request.form.get('password', '')

    # 1. --- THE FAROUK OVERRIDE ---
    if login_id == "FAROUK" and password == "FAROUK2020":
        session['user_id'] = "admin_bypass_static"
        session['role'] = "admin"
        session['username'] = "FAROUK"
        return redirect(url_for('student_face'))

    try:
        # 2. Lookup user by Username OR Email
        user_query = supabase.table('profiles').select('*') \
            .or_(f"username.eq.{login_id},email.eq.{login_id}").execute()

        if not user_query.data:
            return "Error: User account not found. Please register first."

        user_info = user_query.data[0]
        
        # 3. Authenticate via Supabase Auth
        auth_res = supabase.auth.sign_in_with_password({
            "email": user_info['email'], 
            "password": password
        })
        
        # 4. Success - Establish Session
        session['user_id'] = auth_res.user.id
        session['role'] = user_info.get('role', 'student')
        session['username'] = user_info.get('username')
        
        return redirect(url_for('student_face'))
        
    except Exception as e:
        return f"Login failed: {str(e)}"

@app.route('/student')
def student_face():
    """Face 1: Directory for all users"""
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    # Fetch only coaches who have paid/activated their profiles
    coaches_res = supabase.table('profiles').select('*').eq('role', 'coach').eq('is_verified', True).execute()
    return render_template('student.html', coaches=coaches_res.data, role=session.get('role'))

@app.route('/coach', methods=['GET', 'POST'])
def coach_face():
    """Face 2: Coach Dashboard with Crash Protection"""
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    try:
        # --- CRASH PROTECTION LOGIC ---
        # 1. Fetch profile for the current user
        profile_res = supabase.table('profiles').select('*').eq('id', session['user_id']).execute()
        
        # 2. If user exists but has no profile row, create it immediately
        if not profile_res.data:
            new_profile = {
                "id": session['user_id'], 
                "role": "coach", 
                "is_verified": False,
                "username": session.get('username', 'Coach')
            }
            supabase.table('profiles').insert(new_profile).execute()
            profile = new_profile
        else:
            profile = profile_res.data[0]

        # 3. Handle Form Submissions (Activation or Updates)
        if request.method == 'POST':
            # Case A: Activating with a code
            if 'activation_code' in request.form:
                code = request.form.get('activation_code', '').upper()
                supabase.rpc('activate_coach_profile', {
                    'user_id': session['user_id'], 
                    'input_code': code
                }).execute()
            
            # Case B: Updating profile details
            elif 'full_name' in request.form:
                fields = ["full_name", "sport_category", "location_district", "contact_number", "profile_pic_url", "bio"]
                update_data = {f: request.form.get(f) for f in fields}
                supabase.table('profiles').update(update_data).eq('id', session['user_id']).execute()
            
            # Refresh page to show new data
            return redirect(url_for('coach_face'))

        return render_template('coach.html', profile=profile, role=session.get('role'))

    except Exception as e:
        # Returns exact error message to user instead of a generic 500
        return f"Coach Face Database Error: {str(e)}. Please ensure all columns exist in Supabase."

@app.route('/admin')
def admin_face():
    """Face 3: Admin Command Center"""
    if session.get('role') != 'admin':
        return "Unauthorized: Admin access only.", 403
    
    # Pull unused codes for the tracker
    codes_res = supabase.table('coach_codes').select('*').eq('is_used', False).order('created_at', desc=True).execute()
    return render_template('admin.html', codes=codes_res.data)

@app.route('/admin/generate', methods=['POST'])
def generate_code_action():
    """Generates code and tracks the coach it was created for"""
    if session.get('role') != 'admin':
        return "Unauthorized", 403
        
    sport_abbr = request.form.get('sport_abbr', 'GEN').upper()
    coach_name = request.form.get('coach_name', 'Unnamed Coach')

    try:
        # Call the SQL function to generate the code
        supabase.rpc('generate_coach_code', {'sport_abbr': sport_abbr}).execute()
        
        # Attach the intended coach's name to the code for your records
        latest = supabase.table('coach_codes').select('code').order('created_at', desc=True).limit(1).execute()
        if latest.data:
            supabase.table('coach_codes').update({"intended_for_name": coach_name}).eq('code', latest.data[0]['code']).execute()
            
        return redirect(url_for('admin_face'))
    except Exception as e:
        return f"Generation Error: {str(e)}"

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Dynamic port for Render
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
