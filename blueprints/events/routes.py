from flask import Blueprint, render_template, redirect, url_for, session
events_bp = Blueprint('events', __name__, template_folder='templates')

@events_bp.route('/')
def index():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    return render_template('events/stub.html')

@events_bp.route('/calendar')
def calendar():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    return render_template('events/stub.html')
