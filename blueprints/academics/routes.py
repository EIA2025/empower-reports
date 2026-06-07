from flask import Blueprint, render_template, redirect, url_for, session
academics_bp = Blueprint('academics', __name__, template_folder='templates')

@academics_bp.route('/')
def index():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    return render_template('academics/stub.html')

@academics_bp.route('/terms')
def terms():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    return render_template('academics/stub.html')

@academics_bp.route('/marks')
def marks():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    return render_template('academics/stub.html')

@academics_bp.route('/attendance')
def attendance():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    return render_template('academics/stub.html')

@academics_bp.route('/behaviour')
def behaviour():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    return render_template('academics/stub.html')

@academics_bp.route('/reports')
def reports():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    return render_template('academics/stub.html')

@academics_bp.route('/timetable')
def timetable():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    return render_template('academics/stub.html')

@academics_bp.route('/parent_results')
def parent_results():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    return render_template('academics/stub.html')

@academics_bp.route('/student_results')
def student_results():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    return render_template('academics/stub.html')

@academics_bp.route('/student_timetable')
def student_timetable():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    return render_template('academics/stub.html')
