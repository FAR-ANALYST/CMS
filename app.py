@app.route('/admin')
def admin_face():
    # Security Check
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    # Fetch unused codes from the database
    codes_query = supabase.table('coach_codes').select('*').eq('is_used', False).order('created_at', desc=True).execute()
    
    return render_template('admin.html', codes=codes_query.data)

@app.route('/admin/generate-code', methods=['POST'])
def generate_code_route():
    if session.get('role') != 'admin':
        return "Unauthorized", 403
        
    sport_abbr = request.form.get('sport_abbr').upper()
    
    try:
        # Call the SQL function we created in Supabase
        supabase.rpc('generate_coach_code', {'sport_abbr': sport_abbr}).execute()
        return redirect(url_for('admin_face'))
    except Exception as e:
        return f"Error: {str(e)}"
