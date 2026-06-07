# app.py — Empower School Administration System
import os
import traceback
from flask import Flask, render_template, redirect, url_for, session, request
from dotenv import load_dotenv

load_dotenv()


def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')

    # ── Register blueprints ───────────────────────────────────────────────────
    from blueprints.people.routes    import people_bp
    from blueprints.academics.routes import academics_bp
    from blueprints.finance.routes   import finance_bp
    from blueprints.communications.routes import comms_bp
    from blueprints.library.routes   import library_bp
    from blueprints.events.routes    import events_bp
    from blueprints.system.routes    import system_bp
    from auth                        import auth_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(people_bp,    url_prefix='/people')
    app.register_blueprint(academics_bp, url_prefix='/academics')
    app.register_blueprint(finance_bp,   url_prefix='/finance')
    app.register_blueprint(comms_bp,     url_prefix='/communications')
    app.register_blueprint(library_bp,   url_prefix='/library')
    app.register_blueprint(events_bp,    url_prefix='/events')
    app.register_blueprint(system_bp,    url_prefix='/system')

    # ── Root redirect ─────────────────────────────────────────────────────────
    @app.route('/')
    def index():
        if session.get('user_id'):
            return redirect(url_for('dashboard'))
        return redirect(url_for('auth.login'))

    @app.route('/dashboard')
    def dashboard():
        if not session.get('user_id'):
            return redirect(url_for('auth.login'))
        role = session.get('user_role')
        if role == 'master_admin':
            return redirect(url_for('system.overview'))
        return render_template('dashboard.html',
                               role=role,
                               school_name=session.get('school_name',''))

    # ── Error handlers ────────────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html', error=str(e)), 500

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    return app


app = create_app()

# ── Startup ───────────────────────────────────────────────────────────────────
with app.app_context():
    try:
        from db import init_db
        init_db()
    except Exception:
        print("STARTUP ERROR — init_db() failed:")
        traceback.print_exc()
        raise

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0',
            port=int(os.environ.get('PORT', 5000)))
