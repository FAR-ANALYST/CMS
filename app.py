import os
from flask import Flask, render_template, request, redirect, url_for, session
from supabase import create_client, Client
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Load local environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "farouk_uganda_2026_final_v2")

# --- SUPABASE CONFIG ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    login_id = request.form.get('login_id', '').strip()
    password = request.form.get('password', '')

    # Admin Override
    if login_id == "FAROUK" and password == "FAROUK2020":
        session.update({'user_id': "admin_bypass_static", 'role': "admin", 'username': "FAROUK"})
        return redirect(url_for('student_face'))

    try:
        # Lookup user
        user_query = supabase.table('profiles').select('*').or_(f"username.eq.{login_id},email.eq.{login_id}").execute()
        if not user_query.data:
            return "User not found. Please register."

        user_info = user_query.data[0]
        # Auth
        auth_res = supabase.auth.sign_in_with_password({"email": user_info['email'], "password": password})
        
        session.update({
            'user_id': auth_res.user.id,
            'role': user_info.get('role', 'student'),
            'username': user_info.get('username')
        })
        return redirect(url_for('student_face'))
    except Exception as e:
        return f"Login failed: {str(e)}"

@app.route('/student')
def student_face():
    if 'user_id' not in session: return redirect(url_for('index'))
    # Show only verified coaches to students
    coaches_res = supabase.table('profiles').select('*').eq('role', 'coach').eq('is_verified', True).execute()
    return render_template('student.html', coaches=coaches_res.data, role=session.get('role'))

@app.route('/coach', methods=['GET', 'POST'])
def coach_face():
    if 'user_id' not in session: return redirect(url_for('index'))
    
    # 1. ADMIN BYPASS LOGIC (Prevents UUID Crashes)
    if session.get('user_id') == "admin_bypass_static":
        profile = {"full_name": "FAROUK (Admin)", "is_verified": True, "role": "admin"}
    else:
        try:
            # Fetch or Auto-Create Profile
            profile_res = supabase.table('profiles').select('*').eq('id', session['user_id']).execute()
            if not profile_res.data:
                new_profile = {"id": session['user_id'], "role": "coach", "is_verified": False}
                supabase.table('profiles').insert(new_profile).execute()
                profile = new_profile
            else:
                profile = profile_res.data[0]
        except Exception as e:
            return f"Database Error: {str(e)}"

    # 2. HANDLE FORM SUBMISSION (Only for real coaches)
    if request.method == 'POST' and session.get('user_id') != "admin_bypass_static":
        try:
            # Handle Image Upload
            file = request.files.get('profile_image')
            image_url = request.form.get('existing_url')
            
            if file and file.filename != '':
                filename = secure_filename(f"{session['user_id']}_{file.filename}")
                temp_path = os.path.join('/tmp', filename)
                file.save(temp_path)
                
                with open(temp_path, 'rb') as f:
                    # Uploading to 'coaches' bucket
                    supabase.storage.from_('coaches').upload(f"photos/{filename}", f, {"upsert": "true"})
                
                image_url = supabase.storage.from_('coaches').get_public_url(f"photos/{filename}")

            # Update Profile Data
            update_data = {
                "full_name": request.form.get('full_name'),
                "sport_category": request.form.get('sport_category'),
                "contact_number": request.form.get('contact_number'),
                "profile_pic_url": image_url,
                "bio": request.form.get('bio'),
                "payment_status": "submitted" # Marks it for Admin Review
            }
            supabase.table('profiles').update(update_data).eq('id', session['user_id']).execute()
            return redirect(url_for('coach_face'))

        except Exception as e:
            return f"Submit Error: {str(e)}. (Check if 'coaches' bucket is created in Supabase Storage)"

    return render_template('coach.html', profile=profile, role=session.get('role'))

@app.route('/admin')
def admin_face():
    if session.get('role') != 'admin': return "Access Denied", 403
    # Get coaches waiting for verification
    pending = supabase.table('profiles').select('*').eq('payment_status', 'submitted').execute()
    # Get unused access codes
    codes = supabase.table('coach_codes').select('*').eq('is_used', False).order('created_at', desc=True).execute()
    return render_template('admin.html', pending=pending.data, codes=codes.data)

@app.route('/admin/verify/<id>')
def verify_coach(id):
    if session.get('role') != 'admin': return "Access Denied", 403
    try:
        supabase.table('profiles').update({"is_verified": True, "payment_status": "verified"}).eq('id', id).execute()
        return redirect(url_for('admin_face'))
    except Exception as e:
        return f"Verification Error: {str(e)}"

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
