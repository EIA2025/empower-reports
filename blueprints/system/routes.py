from flask import Blueprint, render_template, redirect, url_for, session
system_bp = Blueprint('system', __name__, template_folder='templates')

@system_bp.route('/overview')
def overview():
    if session.get('user_role') != 'master_admin':
        return redirect(url_for('dashboard'))
    return render_template('system/overview.html')
