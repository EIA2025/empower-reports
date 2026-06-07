from flask import Blueprint, render_template, redirect, url_for, session
library_bp = Blueprint('library', __name__, template_folder='templates')

@library_bp.route('/')
def index():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    return render_template('library/stub.html')

@library_bp.route('/catalogue')
def catalogue():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    return render_template('library/stub.html')
