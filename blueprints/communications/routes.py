from flask import Blueprint, render_template, redirect, url_for, session, request, flash
from datetime import datetime
from db import SessionLocal
from sqlalchemy import text

communications_bp = Blueprint('communications', __name__, template_folder='templates')

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


@communications_bp.route('/')
@login_required
def index():
    return redirect(url_for('communications.inbox'))


@communications_bp.route('/inbox')
@login_required
def inbox():
    user_id = session.get('user_id')
    school_id = get_school_id()
    db = SessionLocal()
    try:
        # Personal messages received
        messages = db.execute(text("""
            SELECT m.*, u.first_name || ' ' || u.last_name AS sender_name
            FROM messages m
            LEFT JOIN users u ON u.id=m.sender_id
            WHERE m.school_id=:sid AND m.recipient_id=:uid AND m.is_broadcast=false
            ORDER BY m.created_at DESC LIMIT 100
        """), {'sid': school_id, 'uid': user_id}).fetchall()

        # Broadcasts for this role
        role = session.get('role', '')
        broadcasts = db.execute(text("""
            SELECT m.*, u.first_name || ' ' || u.last_name AS sender_name
            FROM messages m
            LEFT JOIN users u ON u.id=m.sender_id
            WHERE m.school_id=:sid AND m.is_broadcast=true
              AND (m.target_role='all' OR m.target_role=:role)
            ORDER BY m.created_at DESC LIMIT 50
        """), {'sid': school_id, 'role': role}).fetchall()

        unread_count = db.execute(text(
            "SELECT COUNT(*) FROM messages WHERE school_id=:sid AND recipient_id=:uid AND is_broadcast=false AND read=false"
        ), {'sid': school_id, 'uid': user_id}).scalar()

        return render_template('communications/inbox.html',
            messages=messages, broadcasts=broadcasts, unread_count=unread_count)
    finally:
        db.close()


@communications_bp.route('/compose', methods=['GET', 'POST'])
@login_required
def compose():
    user_id = session.get('user_id')
    school_id = get_school_id()
    db = SessionLocal()
    try:
        users = db.execute(text(
            "SELECT id, first_name, last_name, role FROM users WHERE school_id=:sid AND is_active=true ORDER BY last_name, first_name"
        ), {'sid': school_id}).fetchall()

        if request.method == 'POST':
            is_broadcast = bool(request.form.get('is_broadcast'))
            if is_broadcast:
                db.execute(text("""
                    INSERT INTO messages (school_id, sender_id, subject, body, is_broadcast, target_role, target_class, read, created_at)
                    VALUES (:sid, :sndr, :subj, :body, true, :tr, :tc, false, NOW())
                """), {
                    'sid': school_id, 'sndr': user_id,
                    'subj': request.form.get('subject', ''),
                    'body': request.form.get('body', ''),
                    'tr': request.form.get('target_role', 'all'),
                    'tc': request.form.get('target_class', ''),
                })
                flash('Broadcast sent.', 'success')
            else:
                recipient_ids = request.form.getlist('recipient_ids')
                for rid in recipient_ids:
                    db.execute(text("""
                        INSERT INTO messages (school_id, sender_id, recipient_id, subject, body, is_broadcast, read, created_at)
                        VALUES (:sid, :sndr, :rid, :subj, :body, false, false, NOW())
                    """), {
                        'sid': school_id, 'sndr': user_id, 'rid': int(rid),
                        'subj': request.form.get('subject', ''),
                        'body': request.form.get('body', ''),
                    })
                flash(f'Message sent to {len(recipient_ids)} recipient(s).', 'success')
            db.commit()
            return redirect(url_for('communications.inbox'))

        reply_to = request.args.get('reply_to')
        original = None
        if reply_to:
            original = db.execute(text(
                "SELECT m.*, u.first_name || ' ' || u.last_name AS sender_name FROM messages m LEFT JOIN users u ON u.id=m.sender_id WHERE m.id=:id"
            ), {'id': int(reply_to)}).fetchone()

        classes = db.execute(text(
            "SELECT DISTINCT class_name FROM students WHERE school_id=:sid ORDER BY class_name"
        ), {'sid': school_id}).fetchall()

        return render_template('communications/compose.html',
            users=users, classes=classes, original=original)
    finally:
        db.close()


@communications_bp.route('/message/<int:msg_id>')
@login_required
def view_message(msg_id):
    user_id = session.get('user_id')
    school_id = get_school_id()
    db = SessionLocal()
    try:
        msg = db.execute(text("""
            SELECT m.*, u.first_name || ' ' || u.last_name AS sender_name,
                r.first_name || ' ' || r.last_name AS recipient_name
            FROM messages m
            LEFT JOIN users u ON u.id=m.sender_id
            LEFT JOIN users r ON r.id=m.recipient_id
            WHERE m.id=:id AND m.school_id=:sid
        """), {'id': msg_id, 'sid': school_id}).fetchone()

        if not msg:
            flash('Message not found.', 'danger')
            return redirect(url_for('communications.inbox'))

        # Mark as read
        if msg.recipient_id == user_id and not msg.read:
            db.execute(text(
                "UPDATE messages SET read=true, read_at=NOW() WHERE id=:id"
            ), {'id': msg_id})
            db.commit()

        return render_template('communications/view_message.html', msg=msg)
    finally:
        db.close()


@communications_bp.route('/message/<int:msg_id>/delete', methods=['POST'])
@login_required
def delete_message(msg_id):
    school_id = get_school_id()
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM messages WHERE id=:id AND school_id=:sid"),
                   {'id': msg_id, 'sid': school_id})
        db.commit()
        flash('Message deleted.', 'success')
    finally:
        db.close()
    return redirect(url_for('communications.inbox'))
