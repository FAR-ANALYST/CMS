import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, flash
from supabase import create_client, Client
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "uganda_sports_secret_2026")

# --- SUPABASE CONFIGURATION ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CONSTANTS ---
SPORTS = ["Football", "Basketball", "Athletics", "Boxing", "Netball", "Rugby", "Tennis", "Swimming", "Fitness & Gym"]

# --- AUTHENTICATION HELPER ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_db():
    return supabase

# --- ROUTES ---

@app.route("/")
def index():
    return render_template("login.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        
        try:
            res = supabase.auth.sign_in_with_password({"email": email, "password": password})
            session['user_id'] = res.user.id
            
            # Check user role from profiles table
            user_data = supabase.table("profiles").select("role").eq("id", res.user.id).single().execute()
            session['role'] = user_data.data.get('role', 'student')
            
            if session['role'] == 'admin':
                return redirect(url_for('admin_panel'))
            elif session['role'] == 'coach':
                return redirect(url_for('coach_face'))
            return redirect(url_for('student_directory'))
        except Exception as e:
            flash("Invalid login credentials")
    return render_template("login.html")

# --- STUDENT DIRECTORY (Filtered Logic) ---
@app.route("/student")
@login_required
def student_directory():
    selected_sport = request.args.get('sport')
    selected_location = request.args.get('location')
    
    # LOGIC: Only fetch coaches who are marked as 'paid'
    query = supabase.table("profiles").select("*").eq("payment_status", "paid")
    
    if selected_sport:
        query = query.eq("sport_category", selected_sport)
    if selected_location:
        query = query.eq("location_district", selected_location)
        
    coaches = query.execute().data
    
    # Extract unique locations from all paid profiles for the dropdown
    all_paid = supabase.table("profiles").select("location_district").eq("payment_status", "paid").execute().data
    locations = sorted(list(set([p['location_district'] for p in all_paid if p.get('location_district')])))
    
    return render_template("student.html", 
                           coaches=coaches, 
                           locations=locations,
                           sports=SPORTS,
                           selected_sport=selected_sport,
                           selected_location=selected_location,
                           role=session.get('role'))

# --- COACH INTERFACE (Submission Logic) ---
@app.route("/coach")
@login_required
def coach_face():
    profile = supabase.table("profiles").select("*").eq("id", session['user_id']).single().execute().data
    return render_template("coach.html", profile=profile, sports=SPORTS)

@app.route("/coach/update", methods=["POST"])
@login_required
def coach_update_profile():
    # PATH A: Coach self-submits. Logic sets status to 'submitted'
    data = {
        "full_name": request.form.get("full_name"),
        "sport_category": request.form.get("sport_category"),
        "location_district": request.form.get("location_district"),
        "contact_number": request.form.get("contact_number"),
        "bio": request.form.get("bio"),
        "payment_status": "submitted"  # Becomes 'Pending' on Admin Panel
    }
    
    # Handle image upload logic here if using Supabase Storage
    
    supabase.table("profiles").update(data).eq("id", session['user_id']).execute()
    flash("Profile updated and submitted for admin verification.")
    return redirect(url_for('coach_face'))

# --- ADMIN CONTROL (Management Logic) ---
@app.route("/admin")
@login_required
def admin_panel():
    if session.get('role') != 'admin':
        return "Unauthorized", 403
        
    # Fetch data for the stats and lists
    all_profiles = supabase.table("profiles").select("*").execute().data
    pending = [p for p in all_profiles if p.get('payment_status') == 'submitted']
    verified = [p for p in all_profiles if p.get('payment_status') == 'paid']
    
    return render_template("admin.html", pending=pending, verified=verified, sports=SPORTS)

@app.route("/admin/add_coach", methods=["POST"])
@login_required
def admin_add_coach():
    if session.get('role') != 'admin': return "Unauthorized", 403
    
    # PATH B: Admin adds directly. Logic sets status to 'paid' instantly
    data = {
        "id": str(uuid.uuid4()), 
        "full_name": request.form.get("full_name"),
        "sport_category": request.form.get("sport_category"),
        "location_district": request.form.get("location_district"),
        "contact_number": request.form.get("contact_number"),
        "bio": request.form.get("bio"),
        "payment_status": "paid", # Direct bypass
        "role": "coach"
    }
    
    supabase.table("profiles").insert(data).execute()
    flash("Coach added and published to directory instantly.")
    return redirect(url_for('admin_panel'))

@app.route("/admin/mark_paid/<coach_id>")
@login_required
def mark_paid(coach_id):
    if session.get('role') != 'admin': return "Unauthorized", 403
    
    # Flip the status from 'submitted' to 'paid'
    supabase.table("profiles").update({"payment_status": "paid"}).eq("id", coach_id).execute()
    flash("Payment verified. Coach is now live!")
    return redirect(url_for('admin_panel'))

@app.route("/admin/remove/<coach_id>")
@login_required
def remove_coach(coach_id):
    if session.get('role') != 'admin': return "Unauthorized", 403
    
    # Logic: Set back to 'submitted' or 'pending' to hide from directory
    supabase.table("profiles").update({"payment_status": "pending"}).eq("id", coach_id).execute()
    flash("Coach removed from live directory.")
    return redirect(url_for('admin_panel'))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == "__main__":
    app.run(debug=True)
