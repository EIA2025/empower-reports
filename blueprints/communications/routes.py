from flask import Blueprint, render_template, redirect, url_for, session
communications_bp = Blueprint('communications', __name__, template_folder='templates')

@communications_bp.route('/')
def index():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    return render_template('communications/stub.html')

@communications_bp.route('/inbox')
def inbox():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    return render_template('communications/stub.html')
