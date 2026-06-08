# auth.py — Authentication for all roles
import hashlib
from functools import wraps
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, flash)
from db import SessionLocal
from sqlalchemy import text

auth_bp = Blueprint('auth', __name__)


# ── Decorators ────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get('user_id'):
                return redirect(url_for('auth.login'))
            if session.get('user_role') not in roles:
                flash('You do not have permission to access that page.', 'error')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated
    return decorator


def school_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('auth.login'))
        if not session.get('school_id') and session.get('user_role') != 'master_admin':
            flash('No school associated with your account.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


# ── LOGIN ─────────────────────────────────────────────────────────────────────
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # Already logged in → go to dashboard
    if session.get('user_id'):
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        action = request.form.get('action', 'login')

        if action == 'master_login':
            return _master_login()

        elif action == 'login':
            return _user_login()

        elif action == 'forgot':
            _forgot_password()
            return redirect(url_for('auth.login'))

    # GET — show login page with school info
    db = SessionLocal()
    try:
        school = db.execute(text(
            "SELECT name, logo_data, primary_color FROM schools WHERE is_active=true LIMIT 1"
        )).fetchone()
    finally:
        db.close()

    return render_template('login.html', school=school)


def _master_login():
    """Handle master admin login — returns a redirect response."""
    email = request.form.get('master_email', '').strip()
    pw    = request.form.get('master_password', '').strip()

    if not email or not pw:
        flash('Please enter email and password.', 'error')
        return redirect(url_for('auth.login'))

    db = SessionLocal()
    try:
        u = db.execute(text(
            "SELECT * FROM system_users WHERE email=:e AND is_active=true LIMIT 1"
        ), {'e': email}).fetchone()

        if u and u.password_hash == hashlib.sha256(pw.encode()).hexdigest():
            session.clear()
            session['user_id']   = f'sys_{u.id}'
            session['user_role'] = 'master_admin'
            session['username']  = u.name
            session['school_name'] = 'System Administration'
            db.execute(text(
                "UPDATE system_users SET last_login=CURRENT_TIMESTAMP WHERE id=:id"
            ), {'id': u.id})
            db.commit()
            return redirect(url_for('system.overview'))
        else:
            flash('Invalid master admin credentials.', 'error')
            return redirect(url_for('auth.login'))
    finally:
        db.close()


def _user_login():
    """Handle school user login — returns a redirect response."""
    email = request.form.get('email', '').strip()
    pw    = request.form.get('password', '').strip()

    if not email or not pw:
        flash('Please enter your email and password.', 'error')
        return redirect(url_for('auth.login'))

    db = SessionLocal()
    try:
        u = db.execute(text(
            "SELECT * FROM users WHERE email=:e AND is_active=true LIMIT 1"
        ), {'e': email}).fetchone()

        if not u:
            flash('Invalid email or password.', 'error')
            return redirect(url_for('auth.login'))

        if u.password_hash != hashlib.sha256(pw.encode()).hexdigest():
            flash('Invalid email or password.', 'error')
            return redirect(url_for('auth.login'))

        # Credentials correct — get school info
        school = db.execute(text(
            "SELECT * FROM schools WHERE id=:id LIMIT 1"
        ), {'id': u.school_id}).fetchone()

        session.clear()
        session['user_id']    = u.id
        session['user_role']  = u.role
        session['username']   = u.name
        session['school_id']  = u.school_id
        session['school_name'] = school.name if school else 'Unknown School'

        db.execute(text(
            "UPDATE users SET last_login=CURRENT_TIMESTAMP WHERE id=:id"
        ), {'id': u.id})
        db.commit()

        if u.must_change_pw:
            flash('Please change your password before continuing.', 'warning')
            return redirect(url_for('auth.change_password'))

        return redirect(url_for('dashboard'))

    finally:
        db.close()


def _forgot_password():
    """Handle password reset via recovery questions."""
    email  = request.form.get('recover_email', '').strip()
    method = request.form.get('recover_method', 'phone')
    answer = request.form.get('recover_answer', '').strip().lower()
    new_pw = request.form.get('new_password', '').strip()
    conf   = request.form.get('confirm_password', '').strip()

    if new_pw != conf:
        flash('Passwords do not match.', 'error')
        return
    if len(new_pw) < 6:
        flash('Password must be at least 6 characters.', 'error')
        return

    db = SessionLocal()
    try:
        u = db.execute(text(
            "SELECT * FROM users WHERE email=:e LIMIT 1"
        ), {'e': email}).fetchone()

        if not u:
            flash('No account found with that email.', 'error')
            return

        ok = False
        if method == 'phone'    and u.recovery_phone    and u.recovery_phone.strip().lower() == answer:
            ok = True
        elif method == 'city'   and u.recovery_city     and u.recovery_city.strip().lower() == answer:
            ok = True
        elif method == 'nickname' and u.recovery_nickname and u.recovery_nickname.strip().lower() == answer:
            ok = True

        if ok:
            db.execute(text(
                "UPDATE users SET password_hash=:pw WHERE id=:id"
            ), {'pw': hashlib.sha256(new_pw.encode()).hexdigest(), 'id': u.id})
            db.commit()
            flash('Password reset successfully. Please log in.', 'success')
        else:
            flash('Recovery information did not match.', 'error')
    finally:
        db.close()


# ── CHANGE PASSWORD ───────────────────────────────────────────────────────────
@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current = request.form.get('current_password', '')
        new_pw  = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')

        if new_pw != confirm:
            flash('New passwords do not match.', 'error')
            return render_template('change_password.html')
        if len(new_pw) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('change_password.html')

        db = SessionLocal()
        try:
            u = db.execute(text(
                "SELECT * FROM users WHERE id=:id LIMIT 1"
            ), {'id': session['user_id']}).fetchone()

            if not u:
                flash('User not found.', 'error')
                return redirect(url_for('auth.login'))

            if u.password_hash != hashlib.sha256(current.encode()).hexdigest():
                flash('Current password is incorrect.', 'error')
                return render_template('change_password.html')

            db.execute(text(
                "UPDATE users SET password_hash=:pw, must_change_pw=false WHERE id=:id"
            ), {'pw': hashlib.sha256(new_pw.encode()).hexdigest(), 'id': u.id})
            db.commit()
            flash('Password changed successfully!', 'success')
            return redirect(url_for('dashboard'))
        finally:
            db.close()

    return render_template('change_password.html')


# ── LOGOUT ────────────────────────────────────────────────────────────────────
@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
