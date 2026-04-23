import os
from flask import Flask, render_template, request, redirect, url_for, session
from supabase import create_client, Client
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Load environment variables (Supabase URL and Key)
load_dotenv()

app = Flask(__name__)
# Secret key for session management
app.secret_key = os.environ.get("FLASK_SECRET", "farouk_ultimate_2026_secure")

# Initialize Supabase
supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"), 
    os.environ.get("SUPABASE_ANON_KEY")
)

# --- NAVIGATION HELPER ---
# We use this to prevent UUID errors when the Admin (FAROUK) 
# tries to access coach-specific database features.
def get_role():
    return session.get('role', 'student')

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    login_id = request.form.get('login_id', '').strip()
    password = request.form.get('password', '')

    # 1. ADMIN BYPASS (FAROUK)
    if login_id == "FAROUK" and password == "FAROUK2020":
        # Use a dummy UUID for the admin to avoid database syntax errors
        session.update({
            'user_id': "00000000-0000-0000-0000-000000000000", 
            'role': "admin"
        })
        return redirect(url_for('admin_face'))

    # 2. STANDARD LOGIN (COACH / STUDENT)
    try:
        # Check if user exists by username or email
        user_data = supabase.table('profiles').select('*').or_(f"username.eq.{login_id},email.eq.{login_id}").execute()
        if not user_data.data:
            return "User not found."
        
        user = user_data.data[0]
        # Authenticate with Supabase Auth
        auth = supabase.auth.sign_in_with_password({"email": user['email'], "password": password})
        
        session.update({
            'user_id': auth.user.id, 
            'role': user.get('role', 'student')
        })
        
        if session['role'] == 'coach':
            return redirect(url_for('coach_face'))
        return redirect(url_for('student_face'))
    except Exception as e:
        print(f"Login Error: {e}")
        return "Login Failed. Please check your credentials."

@app.route('/student')
def student_face():
    if 'user_id' not in session: return redirect(url_for('index'))
    
    # CONNECTION: Pull only coaches that are PAID and VERIFIED
    query = supabase.table('profiles').select('*').eq('role', 'coach').eq('is_verified', True)
    
    # Filter logic
    sport = request.args.get('sport')
    loc = request.args.get('location')
    if sport: query = query.eq('sport_category', sport)
    if loc: query = query.eq('location_district', loc)
    
    coaches = query.execute().data

    # Dynamic filter lists for the dropdowns
    all_verified = supabase.table('profiles').select('sport_category, location_district').eq('role', 'coach').eq('is_verified', True).execute().data
    sports = sorted(list(set(c['sport_category'] for c in all_verified if c['sport_category'])))
    locations = sorted(list(set(c['location_district'] for c in all_verified if c['location_district'])))

    return render_template('student.html', coaches=coaches, sports=sports, locations=locations, role=get_role())

@app.route('/coach', methods=['GET', 'POST'])
def coach_face():
    if 'user_id' not in session: return redirect(url_for('index'))
    
    # Prevent Admin from trying to save a coach profile for the dummy UUID
    is_admin = session.get('role') == 'admin'

    if request.method == 'POST' and not is_admin:
        file = request.files.get('profile_image')
        img_url = request.form.get('existing_url')
        
        if file and file.filename != '':
            filename = secure_filename(f"{session['user_id']}_{file.filename}")
            # Use /tmp for Render hosting compatibility
            temp_path = os.path.join('/tmp', filename)
            file.save(temp_path)
            with open(temp_path, 'rb') as f:
                supabase.storage.from_('coaches').upload(f"photos/{filename}", f, {"upsert": "true"})
            img_url = supabase.storage.from_('coaches').get_public_url(f"photos/{filename}")

        # CONNECTION: Update data and set status to 'submitted'
        # This makes the coach appear on the Admin's pending list
        update_data = {
            "full_name": request.form.get('full_name'),
            "sport_category": request.form.get('sport_category'),
            "location_district": request.form.get('location_district'),
            "contact_number": request.form.get('contact_number'),
            "profile_pic_url": img_url,
            "bio": request.form.get('bio'),
            "payment_status": "submitted", # Trigger for Admin Page
            "is_verified": False           # Keep hidden from Student Page
        }
        supabase.table('profiles').update(update_data).eq('id', session['user_id']).execute()
        return redirect(url_for('coach_face'))

    # Fetch current profile data to display in the form
    profile = {}
    if not is_admin:
        p_data = supabase.table('profiles').select('*').eq('id', session['user_id']).execute()
        profile = p_data.data[0] if p_data.data else {}
    else:
        profile = {"full_name": "Admin Preview"}

    return render_template('coach.html', profile=profile, role=get_role())

@app.route('/admin')
def admin_face():
    if session.get('role') != 'admin': return redirect(url_for('index'))
    
    # CONNECTION: Fetch ONLY coaches who have submitted but are not verified yet
    pending = supabase.table('profiles').select('*').eq('role', 'coach').eq('is_verified', False).eq('payment_status', 'submitted').execute().data
    
    return render_template('admin.html', pending=pending, role='admin')

@app.route('/admin/mark_paid/<coach_id>')
def mark_paid(coach_id):
    if session.get('role') != 'admin': return "Unauthorized", 403
    
    # CONNECTION: Flip the switches to move coach to Student Page
    supabase.table('profiles').update({
        "is_verified": True, 
        "payment_status": "paid"
    }).eq('id', coach_id).execute()
    
    return redirect(url_for('admin_face'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Bind to PORT for Render deployment
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
