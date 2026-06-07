from flask import Blueprint, render_template, redirect, url_for, session
finance_bp = Blueprint('finance', __name__, template_folder='templates')

@finance_bp.route('/')
def index():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    return render_template('finance/stub.html')

@finance_bp.route('/invoices')
def invoices():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    return render_template('finance/stub.html')

@finance_bp.route('/payments')
def payments():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    return render_template('finance/stub.html')

@finance_bp.route('/fee_structure')
def fee_structure():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    return render_template('finance/stub.html')

@finance_bp.route('/my_fees')
def my_fees():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    return render_template('finance/stub.html')
