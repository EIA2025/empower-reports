from flask import Blueprint, render_template, redirect, url_for, session, request, flash
from datetime import datetime
from db import SessionLocal
from sqlalchemy import text

events_bp = Blueprint('events', __name__, template_folder='templates')

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

def get_school_id():
    return session.get('school_id')


@events_bp.route('/')
@login_required
def index():
    return redirect(url_for('events.calendar'))


@events_bp.route('/calendar')
@login_required
def calendar():
    school_id = get_school_id()
    db = SessionLocal()
    try:
        upcoming = db.execute(text("""
            SELECT * FROM events
            WHERE school_id=:sid AND end_date >= CURRENT_DATE
            ORDER BY start_date ASC LIMIT 50
        """), {'sid': school_id}).fetchall()

        past = db.execute(text("""
            SELECT * FROM events
            WHERE school_id=:sid AND end_date < CURRENT_DATE
            ORDER BY start_date DESC LIMIT 20
        """), {'sid': school_id}).fetchall()

        categories = db.execute(text(
            "SELECT DISTINCT category FROM events WHERE school_id=:sid ORDER BY category"
        ), {'sid': school_id}).fetchall()

        return render_template('events/calendar.html',
            upcoming=upcoming, past=past, categories=categories)
    finally:
        db.close()


@events_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_event():
    if session.get('role') not in ('admin', 'teacher', 'master'):
        flash('Access denied.', 'danger')
        return redirect(url_for('events.calendar'))
    school_id = get_school_id()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            db.execute(text("""
                INSERT INTO events (school_id, title, description, category, location,
                    start_date, end_date, start_time, end_time, is_public, target_role, created_by)
                VALUES (:sid, :title, :desc, :cat, :loc, :sd, :ed, :st, :et, :pub, :tr, :cb)
            """), {
                'sid': school_id,
                'title': request.form.get('title', '').strip(),
                'desc': request.form.get('description', '').strip(),
                'cat': request.form.get('category', 'general'),
                'loc': request.form.get('location', '').strip(),
                'sd': request.form.get('start_date', ''),
                'ed': request.form.get('end_date', '') or request.form.get('start_date', ''),
                'st': request.form.get('start_time', '') or None,
                'et': request.form.get('end_time', '') or None,
                'pub': bool(request.form.get('is_public')),
                'tr': request.form.get('target_role', 'all'),
                'cb': session.get('user_id'),
            })
            db.commit()
            flash('Event created.', 'success')
            return redirect(url_for('events.calendar'))

        return render_template('events/event_form.html', event=None)
    finally:
        db.close()


@events_bp.route('/<int:event_id>')
@login_required
def event_detail(event_id):
    school_id = get_school_id()
    db = SessionLocal()
    try:
        event = db.execute(text(
            "SELECT e.*, u.first_name || ' ' || u.last_name AS created_by_name FROM events e LEFT JOIN users u ON u.id=e.created_by WHERE e.id=:id AND e.school_id=:sid"
        ), {'id': event_id, 'sid': school_id}).fetchone()
        if not event:
            flash('Event not found.', 'danger')
            return redirect(url_for('events.calendar'))
        return render_template('events/event_detail.html', event=event)
    finally:
        db.close()


@events_bp.route('/<int:event_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_event(event_id):
    if session.get('role') not in ('admin', 'teacher', 'master'):
        flash('Access denied.', 'danger')
        return redirect(url_for('events.calendar'))
    school_id = get_school_id()
    db = SessionLocal()
    try:
        event = db.execute(text(
            "SELECT * FROM events WHERE id=:id AND school_id=:sid"
        ), {'id': event_id, 'sid': school_id}).fetchone()
        if not event:
            flash('Event not found.', 'danger')
            return redirect(url_for('events.calendar'))

        if request.method == 'POST':
            db.execute(text("""
                UPDATE events SET title=:title, description=:desc, category=:cat, location=:loc,
                    start_date=:sd, end_date=:ed, start_time=:st, end_time=:et,
                    is_public=:pub, target_role=:tr WHERE id=:id AND school_id=:sid
            """), {
                'title': request.form.get('title', '').strip(),
                'desc': request.form.get('description', '').strip(),
                'cat': request.form.get('category', 'general'),
                'loc': request.form.get('location', '').strip(),
                'sd': request.form.get('start_date', ''),
                'ed': request.form.get('end_date', '') or request.form.get('start_date', ''),
                'st': request.form.get('start_time', '') or None,
                'et': request.form.get('end_time', '') or None,
                'pub': bool(request.form.get('is_public')),
                'tr': request.form.get('target_role', 'all'),
                'id': event_id, 'sid': school_id,
            })
            db.commit()
            flash('Event updated.', 'success')
            return redirect(url_for('events.calendar'))

        return render_template('events/event_form.html', event=event)
    finally:
        db.close()


@events_bp.route('/<int:event_id>/delete', methods=['POST'])
@login_required
def delete_event(event_id):
    school_id = get_school_id()
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM events WHERE id=:id AND school_id=:sid"),
                   {'id': event_id, 'sid': school_id})
        db.commit()
        flash('Event deleted.', 'success')
    finally:
        db.close()
    return redirect(url_for('events.calendar'))
