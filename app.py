import os
from flask import Flask, render_template, request, redirect, url_for, session
from supabase import create_client, Client
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "farouk_final_2026")

supabase: Client = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_ANON_KEY"))

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    login_id, password = request.form.get('login_id', '').strip(), request.form.get('password', '')
    if login_id == "FAROUK" and password == "FAROUK2020":
        session.update({'user_id': "admin_bypass", 'role': "admin"}); return redirect(url_for('student_face'))
    try:
        user = supabase.table('profiles').select('*').or_(f"username.eq.{login_id},email.eq.{login_id}").execute().data[0]
        auth = supabase.auth.sign_in_with_password({"email": user['email'], "password": password})
        session.update({'user_id': auth.user.id, 'role': user.get('role', 'student')})
        return redirect(url_for('student_face'))
    except: return "Login Failed."

@app.route('/student')
def student_face():
    if 'user_id' not in session: return redirect(url_for('index'))
    # Only show verified coaches
    coaches = supabase.table('profiles').select('*').eq('role', 'coach').eq('is_verified', True).execute().data
    return render_template('student.html', coaches=coaches, role=session.get('role'))

@app.route('/coach', methods=['GET', 'POST'])
def coach_face():
    if 'user_id' not in session: return redirect(url_for('index'))
    
    if request.method == 'POST':
        # HANDLE IMAGE UPLOAD (Camera or Local)
        file = request.files.get('profile_image')
        image_url = request.form.get('existing_url') # fallback
        
        if file and file.filename != '':
            filename = secure_filename(f"{session['user_id']}_{file.filename}")
            temp_path = os.path.join('/tmp', filename)
            file.save(temp_path)
            
            with open(temp_path, 'rb') as f:
                supabase.storage.from_('coaches').upload(f"photos/{filename}", f, {"upsert": "true"})
            
            image_url = supabase.storage.from_('coaches').get_public_url(f"photos/{filename}")

        # Update Profile & Set Status to Submitted
        data = {
            "full_name": request.form.get('full_name'),
            "sport_category": request.form.get('sport_category'),
            "contact_number": request.form.get('contact_number'),
            "profile_pic_url": image_url,
            "bio": request.form.get('bio'),
            "payment_status": "submitted" # Alerts the Admin
        }
        supabase.table('profiles').update(data).eq('id', session['user_id']).execute()
        return redirect(url_for('coach_face'))

    profile = supabase.table('profiles').select('*').eq('id', session['user_id']).single().execute().data
    return render_template('coach.html', profile=profile, role=session.get('role'))

@app.route('/admin')
def admin_face():
    if session.get('role') != 'admin': return "Denied", 403
    # Show coaches waiting for verification
    pending = supabase.table('profiles').select('*').eq('payment_status', 'submitted').execute().data
    codes = supabase.table('coach_codes').select('*').eq('is_used', False).execute().data
    return render_template('admin.html', pending=pending, codes=codes)

@app.route('/admin/verify/<id>')
def verify_coach(id):
    if session.get('role') != 'admin': return "Denied", 403
    supabase.table('profiles').update({"is_verified": True, "payment_status": "verified"}).eq('id', id).execute()
    return redirect(url_for('admin'))

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
