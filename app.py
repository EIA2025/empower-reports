# app.py - Empower Reports: Flask + PostgreSQL Version
import os
import hashlib
import base64
import json
import io
import re
import zipfile
from datetime import datetime
from functools import wraps
from pathlib import Path

import csv
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, send_file, jsonify, abort)
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import requests

from models import (Base, User, Student, AcademicTerm, Mark, ComponentMark,
                    DisciplineReport, ReportDesign, AuditLog, ClassroomBehavior,
                    BehaviorComponent, ClassroomBehaviorResponse,
                    StudentDecision, VisitationDay, Message)
from pdf_generator import generate_pdf_report, generate_discipline_pdf
from dotenv import load_dotenv

load_dotenv()

# ── App setup ────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'empower-secret-key-change-in-production')

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://localhost/empower')
# Normalise legacy postgres:// scheme (Render, Heroku)
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

# Supabase Transaction Pooler (pgBouncer) requirements:
#  • use postgresql+psycopg2 driver
#  • SSL required  → ?sslmode=require in URL or connect_args
#  • Prepared statements must be disabled (DEALLOCATE ALL breaks pgBouncer)
#  • pool_size=0 + NullPool avoids holding server-side connections open
#    between requests (transaction mode resets state anyway)
from sqlalchemy.pool import NullPool

# Append sslmode if not already present and URL points to Supabase
_is_supabase = 'supabase.com' in DATABASE_URL or 'pooler.supabase' in DATABASE_URL
if _is_supabase and 'sslmode' not in DATABASE_URL:
    DATABASE_URL += ('&' if '?' in DATABASE_URL else '?') + 'sslmode=require'

engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,          # no persistent pool — correct for pgBouncer transaction mode
    connect_args={
        "options": "-c statement_timeout=30000 -c lock_timeout=10000",
    },
    echo=False,
)
SessionLocal = sessionmaker(bind=engine, autoflush=True, autocommit=False)

# ── Init DB ───────────────────────────────────────────────────────────────────
def init_db():
    # Step 1: create all tables (safe to run repeatedly — CREATE TABLE IF NOT EXISTS)
    Base.metadata.create_all(engine)

    # Step 2: seed default data using raw SQL (ORM .add() is unreliable with NullPool)
    db = SessionLocal()
    try:
        # Seed default behavior components
        count = db.execute(text('SELECT COUNT(*) FROM behavior_components')).scalar()
        if count == 0:
            defaults = [
                ("punctuality",            "Punctuality",              0),
                ("attendance",             "Attendance",               1),
                ("manners",                "Manners",                  2),
                ("general_behavior",       "General Behavior",         3),
                ("organisational_skills",  "Organisational Skills",    4),
                ("adherence_to_uniform",   "Adherence to Uniform",     5),
                ("leadership_skills",      "Leadership Skills",        6),
                ("commitment_to_school",   "Commitment to School",     7),
                ("cooperation_with_peers", "Cooperation with Peers",   8),
                ("cooperation_with_staff", "Cooperation with Staff",   9),
                ("participation_in_lessons","Participation in Lessons",10),
                ("completion_of_homework", "Completion of Homework",   11),
            ]
            for name, label, order in defaults:
                db.execute(text("""
                    INSERT INTO behavior_components (name, display_label, display_order, active)
                    VALUES (:n, :l, :o, true)
                """), {'n': name, 'l': label, 'o': order})
            db.commit()

        # Seed default report design
        count = db.execute(text('SELECT COUNT(*) FROM report_designs')).scalar()
        if count == 0:
            db.execute(text("""
                INSERT INTO report_designs (school_name, primary_color)
                VALUES ('Empower International Academy', '#3a3a9c')
            """))
            db.commit()

        # Seed default admin user
        existing = db.execute(text(
            "SELECT id FROM users WHERE email='admin' LIMIT 1")).fetchone()
        if not existing:
            db.execute(text("""
                INSERT INTO users (name, email, role, password_hash,
                    subjects_taught, class_teacher_for, gender, phone_number)
                VALUES ('Administrator', 'admin', 'admin', :pw, '', '', '', '')
            """), {'pw': hashlib.sha256(b'admin123').hexdigest()})
            db.commit()

    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

# ── Grading ───────────────────────────────────────────────────────────────────
def get_grade(avg):
    if avg is None:
        return "U"
    try:
        avg = float(avg)
    except (TypeError, ValueError):
        return "U"
    if avg >= 90: return "A*"
    elif avg >= 80: return "A"
    elif avg >= 70: return "B"
    elif avg >= 60: return "C"
    elif avg >= 50: return "D"
    elif avg >= 40: return "E"
    return "U"

def convert_to_base(score, total, base):
    if not total or not score:
        return 0
    return round((float(score) / float(total)) * base, 1)

def compute_total(cw20, mt20, et60):
    return round(float(cw20 or 0) + float(mt20 or 0) + float(et60 or 0), 1)

# ── Auth helpers ──────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('user_role') not in ('admin', 'master_admin'):
            flash('Admin access required.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

def log_audit(db, user_id, action, details=""):
    db.execute(text("INSERT INTO audit_logs (user_id, action, details) VALUES (:uid,:act,:det)"),
               {'uid':user_id,'act':action,'det':details})
    db.commit()

def validate_phone(phone):
    p = re.sub(r'[\s\-()]+', '', (phone or '').strip())
    if re.fullmatch(r'\+256\d{9}', p): return True, p
    if re.fullmatch(r'256\d{9}', p): return True, '+' + p
    if re.fullmatch(r'0\d{9}', p): return True, '+256' + p[1:]
    if re.fullmatch(r'\d{9}', p): return True, '+256' + p
    return False, 'Phone must be +256XXXXXXXXX format'

# ── Routes: Auth ─────────────────────────────────────────────────────────────
@app.route('/', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    db = SessionLocal()
    design = db.execute(text('SELECT * FROM report_designs LIMIT 1')).fetchone()
    logo_b64 = design.logo_data if design else None
    school_name = design.school_name if design else "Empower International Academy"
    db.close()

    if request.method == 'POST':
        action = request.form.get('action', 'login')

        if action == 'master_admin':
            pw = request.form.get('master_password', '')
            if hashlib.sha256(pw.encode()).hexdigest() == hashlib.sha256(b'@mikaelJ46').hexdigest():
                session['user_id'] = None
                session['user_role'] = 'master_admin'
                session['username'] = 'Master Admin'
                return redirect(url_for('dashboard'))
            flash('Incorrect master admin password.', 'error')

        elif action == 'forgot':
            email = request.form.get('recover_email', '').strip()
            method = request.form.get('recover_method', '')
            answer = request.form.get('recover_answer', '').strip().lower()
            new_pw = request.form.get('new_password', '')
            confirm_pw = request.form.get('confirm_password', '')
            if new_pw != confirm_pw:
                flash('Passwords do not match.', 'error')
            else:
                db2 = SessionLocal()
                u = db2.query(User).filter_by(email=email).first()
                if not u:
                    flash('No account found with that email.', 'error')
                else:
                    ok = False
                    if method == 'phone' and u.recovery_phone:
                        ok = u.recovery_phone.strip().lower() == answer
                    elif method == 'city' and u.recovery_city:
                        ok = u.recovery_city.strip().lower() == answer
                    elif method == 'nickname' and u.recovery_nickname:
                        ok = u.recovery_nickname.strip().lower() == answer
                    if ok:
                        u.password_hash = hashlib.sha256(new_pw.encode()).hexdigest()
                        db2.commit()
                        flash('Password reset! Please login.', 'success')
                    else:
                        flash('Recovery information did not match.', 'error')
                db2.close()

        else:  # normal login
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            db2 = SessionLocal()
            user = db2.query(User).filter_by(email=username).first()
            db2.close()
            if user and user.password_hash == hashlib.sha256(password.encode()).hexdigest():
                session['user_id'] = user.id
                session['user_role'] = user.role
                session['username'] = user.name
                return redirect(url_for('dashboard'))
            flash('Invalid username or password.', 'error')

    return render_template('login.html', logo_b64=logo_b64, school_name=school_name)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ── Routes: Dashboard ─────────────────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    db = SessionLocal()
    try:
        design = db.execute(text('SELECT * FROM report_designs LIMIT 1')).fetchone()
        active_term = db.execute(text('SELECT * FROM academic_terms WHERE is_active=true LIMIT 1')).fetchone()
        total_students = db.execute(text('SELECT COUNT(*) FROM students')).scalar()
        total_teachers = db.execute(text("SELECT COUNT(*) FROM users WHERE role='teacher'")).scalar()
        total_marks = db.execute(text('SELECT COUNT(*) FROM marks')).scalar()

        # Notifications for current user
        notifs = []
        if session.get('user_id'):
            uid = session['user_id']
            notifs = db.execute(text("""
                SELECT m.id, m.subject, m.body, m.read, m.message_type, m.created_at,
                       u.name as sender_name
                FROM messages m LEFT JOIN users u ON m.sender_id = u.id
                WHERE (m.is_broadcast = TRUE OR m.recipient_id = :uid)
                ORDER BY m.created_at DESC LIMIT 8
            """), {'uid': uid}).fetchall()

        top_students = []
        grade_dist = []
        if active_term:
            rows = db.execute(text("""
                SELECT s.name, s.class_name, AVG(m.total) as avg_total
                FROM marks m JOIN students s ON m.student_id = s.id
                WHERE m.term_id = :tid
                GROUP BY s.id, s.name, s.class_name
                ORDER BY avg_total DESC LIMIT 5
            """), {'tid': active_term.id}).fetchall()
            top_students = [{'name': r.name, 'class_name': r.class_name,
                              'avg': round(r.avg_total, 1)} for r in rows]

            gr = db.execute(text("""
                SELECT grade, COUNT(*) as cnt
                FROM marks WHERE term_id = :tid
                GROUP BY grade ORDER BY grade
            """), {'tid': active_term.id}).fetchall()
            grade_dist = [{'grade': r.grade, 'count': r.cnt} for r in gr]

        return render_template('dashboard.html',
            design=design, active_term=active_term,
            total_students=total_students, total_teachers=total_teachers,
            total_marks=total_marks, top_students=top_students,
            grade_dist=grade_dist, notifs=notifs)
    finally:
        db.close()


def _get_all_known_subjects(db):
    """Return sorted list of all subjects known in the system:
       collected from teachers' subjects_taught + existing marks."""
    known = set()
    # From teachers
    rows = db.execute(text("SELECT subjects_taught FROM users WHERE subjects_taught IS NOT NULL AND subjects_taught != ''")).fetchall()
    for r in rows:
        for s in r.subjects_taught.split(','):
            s = s.strip()
            if s:
                known.add(s)
    # From existing marks (in case some were entered differently)
    rows2 = db.execute(text("SELECT DISTINCT subject FROM marks WHERE subject IS NOT NULL")).fetchall()
    for r in rows2:
        if r.subject:
            known.add(r.subject.strip())
    return sorted(known)


# ── Routes: Students ──────────────────────────────────────────────────────────
@app.route('/students')
@login_required
@admin_required
def students():
    db = SessionLocal()
    students = db.execute(text('SELECT * FROM students ORDER BY class_name, name')).fetchall()
    db.close()
    return render_template('students.html', students=students)


@app.route('/students/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_student():
    if request.method == 'POST':
        db = SessionLocal()
        try:
            subjects = request.form.getlist('subjects')
            db.execute(text("""
                INSERT INTO students (name, year, class_name, registration_number, subjects, gender, enrollment_date)
                VALUES (:name,:year,:cls,:reg,:subs,:gender,:enroll)
            """), {
                'name': request.form['name'],
                'year': int(request.form.get('year',0) or 0),
                'cls':  request.form['class_name'],
                'reg':  request.form['registration_number'],
                'subs': json.dumps(subjects),
                'gender': request.form.get('gender',''),
                'enroll': request.form.get('enrollment_date',''),
            })
            db.commit()
            log_audit(db, session.get('user_id'), 'add_student', s.name)
            flash(f'Student {s.name} added.', 'success')
        except Exception as e:
            db.rollback()
            flash(f'Error: {e}', 'error')
        finally:
            db.close()
        return redirect(url_for('students'))
    db = SessionLocal()
    try:
        all_subjects = _get_all_known_subjects(db)
    finally:
        db.close()
    return render_template('student_form.html', student=None, subjects=[], all_subjects=all_subjects)


@app.route('/students/<int:sid>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_student(sid):
    db = SessionLocal()
    s = db.execute(text('SELECT * FROM students WHERE id=:id'),{'id':sid}).fetchone()
    if not s:
        db.close()
        abort(404)
    if request.method == 'POST':
        try:
            s.name = request.form['name']
            s.year = int(request.form.get('year', 0) or 0)
            s.class_name = request.form['class_name']
            s.registration_number = request.form['registration_number']
            s.subjects = json.dumps(request.form.getlist('subjects'))
            s.gender = request.form.get('gender', '')
            db.commit()
            log_audit(db, session.get('user_id'), 'edit_student', s.name)
            flash('Student updated.', 'success')
        except Exception as e:
            db.rollback()
            flash(f'Error: {e}', 'error')
        finally:
            db.close()
        return redirect(url_for('students'))
    subjects = json.loads(s.subjects) if s.subjects else []
    all_subjects = _get_all_known_subjects(db)
    db.close()
    return render_template('student_form.html', student=s, subjects=subjects, all_subjects=all_subjects)


@app.route('/students/<int:sid>/delete', methods=['POST'])
@login_required
@admin_required
def delete_student(sid):
    db = SessionLocal()
    s = db.execute(text('SELECT * FROM students WHERE id=:id'),{'id':sid}).fetchone()
    if s:
        db.delete(s)
        db.commit()
        flash('Student deleted.', 'success')
    db.close()
    return redirect(url_for('students'))


# ── Routes: Staff ─────────────────────────────────────────────────────────────
@app.route('/staff')
@login_required
@admin_required
def staff():
    db = SessionLocal()
    users = db.execute(text("SELECT * FROM users WHERE role!='master_admin' ORDER BY name")).fetchall()
    db.close()
    return render_template('staff.html', users=users)


@app.route('/staff/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_staff():
    if request.method == 'POST':
        db = SessionLocal()
        try:
            subjects = request.form.getlist('subjects_taught')
            ok, phone_or_err = validate_phone(request.form.get('phone_number', ''))
            if not ok:
                flash(phone_or_err, 'error')
                db.close()
                return render_template('staff_form.html', user=None)
            name = request.form['name']
            db.execute(text("""
                INSERT INTO users (name,email,role,password_hash,subjects_taught,class_teacher_for,gender,phone_number)
                VALUES (:name,:email,:role,:pw,:subs,:cls,:gender,:phone)
            """), {
                'name': name, 'email': request.form['email'],
                'role': request.form['role'],
                'pw':   hashlib.sha256(request.form['password'].encode()).hexdigest(),
                'subs': ','.join(subjects),
                'cls':  request.form.get('class_teacher_for',''),
                'gender': request.form.get('gender',''),
                'phone': phone_or_err,
            })
            db.commit()
            log_audit(db, session.get('user_id'), 'add_staff', name)
            flash(f'Staff {name} added.', 'success')
        except Exception as e:
            db.rollback()
            flash(f'Error: {e}', 'error')
        finally:
            db.close()
        return redirect(url_for('staff'))
    return render_template('staff_form.html', user=None)


@app.route('/staff/<int:uid>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_staff(uid):
    db = SessionLocal()
    u = db.execute(text('SELECT * FROM users WHERE id=:id'),{'id':uid}).fetchone()
    if not u:
        db.close()
        abort(404)
    if request.method == 'POST':
        try:
            u.name = request.form['name']
            u.email = request.form['email']
            u.role = request.form['role']
            u.subjects_taught = ','.join(request.form.getlist('subjects_taught'))
            u.class_teacher_for = request.form.get('class_teacher_for', '')
            u.gender = request.form.get('gender', '')
            if request.form.get('password'):
                u.password_hash = hashlib.sha256(request.form['password'].encode()).hexdigest()
            db.commit()
            log_audit(db, session.get('user_id'), 'edit_staff', u.name)
            flash('Staff updated.', 'success')
        except Exception as e:
            db.rollback()
            flash(f'Error: {e}', 'error')
        finally:
            db.close()
        return redirect(url_for('staff'))
    db.close()
    return render_template('staff_form.html', user=u)


@app.route('/staff/<int:uid>/delete', methods=['POST'])
@login_required
@admin_required
def delete_staff(uid):
    db = SessionLocal()
    u = db.execute(text('SELECT * FROM users WHERE id=:id'),{'id':uid}).fetchone()
    if u:
        db.delete(u)
        db.commit()
        flash('Staff deleted.', 'success')
    db.close()
    return redirect(url_for('staff'))


# ── Routes: Academic Terms ────────────────────────────────────────────────────
@app.route('/terms')
@login_required
@admin_required
def terms():
    db = SessionLocal()
    terms = db.execute(text('SELECT * FROM academic_terms ORDER BY year DESC, term_number')).fetchall()
    db.close()
    return render_template('terms.html', terms=terms)


@app.route('/terms/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_term():
    if request.method == 'POST':
        db = SessionLocal()
        try:
            is_active = 'is_active' in request.form
            if is_active:
                db.execute(text("UPDATE academic_terms SET is_active=false"))
            db.execute(text("""
                INSERT INTO academic_terms (year, term_number, term_name, start_date, end_date, next_term_begins, is_active)
                VALUES (:yr,:tn,:nm,:sd,:ed,:ntb,:act)
            """), {
                'yr':  int(request.form['year']),
                'tn':  int(request.form['term_number']),
                'nm':  request.form['term_name'],
                'sd':  request.form['start_date'],
                'ed':  request.form['end_date'],
                'ntb': request.form.get('next_term_begins',''),
                'act': is_active,
            })
            db.commit()
            flash('Term added successfully.', 'success')
        except Exception as e:
            db.rollback()
            flash(f'Error adding term: {e}', 'error')
        finally:
            db.close()
        return redirect(url_for('terms'))
    from datetime import datetime
    return render_template('term_form.html', term=None, current_year=datetime.now().year)


@app.route('/terms/<int:tid>/activate', methods=['POST'])
@login_required
@admin_required
def activate_term(tid):
    db = SessionLocal()
    db.execute(text("UPDATE academic_terms SET is_active=false"))
    t = db.execute(text('SELECT * FROM academic_terms WHERE id=:id'),{'id':tid}).fetchone()
    if t:
        t.is_active = True
        db.commit()
        flash(f'{t.term_name} set as active term.', 'success')
    db.close()
    return redirect(url_for('terms'))


@app.route('/terms/<int:tid>/delete', methods=['POST'])
@login_required
@admin_required
def delete_term(tid):
    db = SessionLocal()
    t = db.execute(text('SELECT * FROM academic_terms WHERE id=:id'),{'id':tid}).fetchone()
    if t:
        db.delete(t)
        db.commit()
        flash('Term deleted.', 'success')
    db.close()
    return redirect(url_for('terms'))


# ── Routes: Marks / Results ───────────────────────────────────────────────────
@app.route('/marks', methods=['GET', 'POST'])
@login_required
def marks():
    db = SessionLocal()
    try:
        role = session['user_role']
        uid = session.get('user_id')
        user = db.execute(text("SELECT * FROM users WHERE id=:id"), {'id': uid}).fetchone()
        terms = db.execute(text("SELECT * FROM academic_terms ORDER BY year DESC, term_number")).fetchall()
        active_term = db.execute(text("SELECT * FROM academic_terms WHERE is_active=true LIMIT 1")).fetchone()

        # Classes and subjects this user can access
        if role == 'admin':
            classes = [r[0] for r in db.execute(text("SELECT DISTINCT class_name FROM students ORDER BY class_name")).fetchall()]
            subjects_filter = None  # admin sees all subjects
        else:
            # Teacher: subjects_taught comma list, class_teacher_for comma list
            raw_subjects = [s.strip() for s in (user.subjects_taught or '').split(',') if s.strip()]
            raw_classes  = [c.strip() for c in (user.class_teacher_for or '').split(',') if c.strip()]
            subjects_filter = raw_subjects if raw_subjects else None
            if raw_classes:
                classes = raw_classes
            else:
                # Fall back to all classes (so they can at least see something)
                classes = [r[0] for r in db.execute(text("SELECT DISTINCT class_name FROM students ORDER BY class_name")).fetchall()]

        selected_class   = request.args.get('class_name') or (classes[0] if classes else None)
        selected_term_id = request.args.get('term_id') or (str(active_term.id) if active_term else None)
        selected_subject = request.args.get('subject') or None  # which subject tab is open

        students_list = []
        marks_data    = {}
        all_subjects  = []   # subjects available for this class (filtered if teacher)

        if selected_class and selected_term_id:
            rows = db.execute(text(
                "SELECT id, name, registration_number, subjects FROM students "
                "WHERE class_name=:cls ORDER BY name"), {'cls': selected_class}).fetchall()

            for r in rows:
                subs = json.loads(r.subjects) if r.subjects else []
                students_list.append({'id': r.id, 'name': r.name,
                                      'reg': r.registration_number, 'subjects': subs})
                for s in subs:
                    if s not in all_subjects:
                        all_subjects.append(s)

        # Apply subject filter for teachers — case-insensitive match
        if subjects_filter:
            sf_lower = [s.lower() for s in subjects_filter]
            # Keep subjects that match teacher's list (case-insensitive)
            matched = [s for s in all_subjects if s.lower() in sf_lower]
            # Also add any teacher subjects not yet in class list (so tabs always show)
            for sf in subjects_filter:
                if sf.lower() not in [m.lower() for m in matched]:
                    matched.append(sf)
            all_subjects = matched if matched else subjects_filter

            if not selected_subject or selected_subject not in all_subjects:
                selected_subject = all_subjects[0] if all_subjects else None

            # Fetch existing marks for this class + term
            if students_list:
                mrows = db.execute(text("""
                    SELECT m.student_id, m.subject, m.coursework_out_of_20,
                           m.midterm_out_of_20, m.endterm_out_of_60, m.total, m.grade, m.comment
                    FROM marks m
                    WHERE m.term_id=:tid
                    AND m.student_id IN (SELECT id FROM students WHERE class_name=:cls)
                """), {'tid': int(selected_term_id), 'cls': selected_class}).fetchall()
                for r in mrows:
                    marks_data[(r.student_id, r.subject)] = dict(r._mapping)

        # ── BULK SAVE ──────────────────────────────────────────────────────────
        if request.method == 'POST':
            term_id    = int(request.form['term_id'])
            saved      = 0
            errors     = []
            form       = request.form

            # Form fields are named: cw_{student_id}, mt_{student_id}, et_{student_id}
            # for the current subject (also posted as hidden field 'subject')
            subject = form.get('subject', '')

            # Collect all student ids submitted
            student_ids = [int(k.split('_')[1]) for k in form if k.startswith('cw_')]

            for sid in student_ids:
                try:
                    cw_score = float(form.get(f'cw_{sid}') or 0)
                    cw_total = float(form.get(f'cwt_{sid}') or 20)
                    mt_score = float(form.get(f'mt_{sid}') or 0)
                    mt_total = float(form.get(f'mtt_{sid}') or 20)
                    et_score = float(form.get(f'et_{sid}') or 0)
                    et_total = float(form.get(f'ett_{sid}') or 60)

                    # Save/update component marks (coursework)
                    for comp_type, score, total in [
                        ('coursework', cw_score, cw_total),
                        ('midterm',    mt_score, mt_total),
                        ('endterm',    et_score, et_total),
                    ]:
                        existing_cm = db.execute(text("""
                            SELECT id FROM component_marks
                            WHERE student_id=:sid AND subject=:sub AND term_id=:tid
                            AND component_type=:ct AND component_name=:cn
                        """), {'sid': sid, 'sub': subject, 'tid': term_id,
                               'ct': comp_type, 'cn': comp_type.title()}).fetchone()

                        if existing_cm:
                            db.execute(text("""
                                UPDATE component_marks SET score=:sc, total=:tot
                                WHERE id=:id
                            """), {'sc': score, 'tot': total, 'id': existing_cm.id})
                        else:
                            db.execute(text("""
                                INSERT INTO component_marks
                                (student_id, subject, term_id, component_type, component_name, score, total, submitted_by)
                                VALUES (:sid,:sub,:tid,:ct,:cn,:sc,:tot,:uid)
                            """), {'sid': sid, 'sub': subject, 'tid': term_id,
                                   'ct': comp_type, 'cn': comp_type.title(),
                                   'sc': score, 'tot': total, 'uid': uid})

                    db.commit()
                    _recompile_mark(db, sid, subject, term_id, uid)
                    saved += 1
                except Exception as e:
                    db.rollback()
                    errors.append(str(e))

            if errors:
                flash(f'Saved {saved} records. Errors: {"; ".join(errors[:3])}', 'warning')
            else:
                flash(f'✓ Marks saved for {saved} student(s) in {subject}.', 'success')

            return redirect(url_for('marks',
                class_name=form.get('selected_class', selected_class),
                term_id=term_id,
                subject=subject))

        return render_template('marks.html',
            classes=classes, terms=terms,
            selected_class=selected_class,
            selected_term_id=selected_term_id,
            students_list=students_list,
            marks_data=marks_data,
            all_subjects=all_subjects,
            selected_subject=selected_subject,
            subjects_filter=subjects_filter,
            role=role)
    finally:
        db.close()


def _recompile_mark(db, student_id, subject, term_id, submitted_by=None):
    def _sum(comp_type):
        rows = db.execute(text("""
            SELECT score, total FROM component_marks
            WHERE student_id=:sid AND subject=:sub AND term_id=:tid AND component_type=:ct
        """), {'sid': student_id, 'sub': subject, 'tid': term_id, 'ct': comp_type}).fetchall()
        s = sum(r.score or 0 for r in rows)
        t = sum(r.total or 0 for r in rows)
        return s, t

    cw_s, cw_t = _sum('coursework')
    mt_s, mt_t = _sum('midterm')
    et_s, et_t = _sum('endterm')

    cw20  = convert_to_base(cw_s, cw_t, 20)
    mt20  = convert_to_base(mt_s, mt_t, 20)
    et60  = convert_to_base(et_s, et_t, 60)
    total = compute_total(cw20, mt20, et60)
    grade = get_grade(total)
    now   = datetime.now().isoformat()

    existing = db.execute(text("""
        SELECT id FROM marks WHERE student_id=:sid AND subject=:sub AND term_id=:tid
    """), {'sid': student_id, 'sub': subject, 'tid': term_id}).fetchone()

    if existing:
        params = {
            'cw_s': cw_s, 'cw_t': cw_t, 'cw20': cw20,
            'mt_s': mt_s, 'mt_t': mt_t, 'mt20': mt20,
            'et_s': et_s, 'et_t': et_t, 'et60': et60,
            'total': total, 'grade': grade, 'now': now,
            'id': existing.id,
        }
        if submitted_by:
            params['sb'] = submitted_by
            sb_clause = ', submitted_by=:sb'
        else:
            sb_clause = ''
        db.execute(text(
            "UPDATE marks SET "
            "coursework_score=:cw_s, coursework_total=:cw_t, coursework_out_of_20=:cw20, "
            "midterm_score=:mt_s, midterm_total=:mt_t, midterm_out_of_20=:mt20, "
            "endterm_score=:et_s, endterm_total=:et_t, endterm_out_of_60=:et60, "
            "total=:total, grade=:grade, submitted_at=:now" + sb_clause +
            " WHERE id=:id"
        ), params)
    else:
        db.execute(text("""
            INSERT INTO marks
                (student_id, subject, term_id,
                 coursework_score, coursework_total, coursework_out_of_20,
                 midterm_score, midterm_total, midterm_out_of_20,
                 endterm_score, endterm_total, endterm_out_of_60,
                 total, grade, submitted_by, submitted_at)
            VALUES
                (:sid, :sub, :tid,
                 :cw_s, :cw_t, :cw20,
                 :mt_s, :mt_t, :mt20,
                 :et_s, :et_t, :et60,
                 :total, :grade, :sb, :now)
        """), {
            'sid': student_id, 'sub': subject, 'tid': term_id,
            'cw_s': cw_s, 'cw_t': cw_t, 'cw20': cw20,
            'mt_s': mt_s, 'mt_t': mt_t, 'mt20': mt20,
            'et_s': et_s, 'et_t': et_t, 'et60': et60,
            'total': total, 'grade': grade, 'sb': submitted_by, 'now': now
        })
    db.commit()


# ── Routes: Behavior ──────────────────────────────────────────────────────────
@app.route('/behavior', methods=['GET', 'POST'])
@login_required
def behavior():
    db = SessionLocal()
    try:
        uid = session.get('user_id')
        terms = db.execute(text('SELECT * FROM academic_terms ORDER BY year DESC, term_number')).fetchall()
        active_term = db.execute(text('SELECT * FROM academic_terms WHERE is_active=true LIMIT 1')).fetchone()
        components = db.execute(text('SELECT * FROM behavior_components WHERE active=true ORDER BY display_order')).fetchall()

        role = session['user_role']
        if role == 'admin':
            classes = [r[0] for r in db.execute(text("SELECT DISTINCT class_name FROM students ORDER BY class_name")).fetchall()]
        else:
            u = db.execute(text('SELECT * FROM users WHERE id=:id'),{'id':uid}).fetchone()
            classes = [c.strip() for c in (u.class_teacher_for or '').split(',') if c.strip()] if u else []
            if not classes:
                classes = [r[0] for r in db.execute(text("SELECT DISTINCT class_name FROM students ORDER BY class_name")).fetchall()]

        selected_class = request.args.get('class_name') or (classes[0] if classes else None)
        selected_term_id = request.args.get('term_id') or (str(active_term.id) if active_term else None)

        students_list = []
        behavior_data = {}
        if selected_class and selected_term_id:
            rows = db.execute(text("SELECT id, name FROM students WHERE class_name=:c ORDER BY name"),
                               {'c': selected_class}).fetchall()
            students_list = [{'id': r.id, 'name': r.name} for r in rows]
            for s in students_list:
                brows = db.execute(text("""
                    SELECT bc.name as comp_name, cbr.value
                    FROM classroom_behavior_responses cbr
                    JOIN behavior_components bc ON cbr.component_id = bc.id
                    WHERE cbr.student_id=:sid AND cbr.term_id=:tid
                """), {'sid': s['id'], 'tid': int(selected_term_id)}).fetchall()
                behavior_data[s['id']] = {r.comp_name: r.value for r in brows}

        if request.method == 'POST':
            try:
                student_id = int(request.form['student_id'])
                term_id = int(request.form['term_id'])
                for comp in components:
                    val = request.form.get(f'comp_{comp.id}')
                    if val:
                        existing = db.execute(text("""
                            SELECT id FROM classroom_behavior_responses
                            WHERE student_id=:sid AND term_id=:tid AND component_id=:cid
                        """), {'sid': student_id, 'tid': term_id, 'cid': comp.id}).fetchone()
                        if existing:
                            db.execute(text("""
                                UPDATE classroom_behavior_responses SET value=:val
                                WHERE id=:id
                            """), {'val': val, 'id': existing.id})
                        else:
                            db.execute(text("""
                                INSERT INTO classroom_behavior_responses
                                (student_id, term_id, component_id, value, evaluated_by)
                                VALUES (:sid, :tid, :cid, :val, :uid)
                            """), {'sid': student_id, 'tid': term_id,
                                   'cid': comp.id, 'val': val, 'uid': uid})
                db.commit()
                flash('Behavior saved.', 'success')
            except Exception as e:
                db.rollback()
                flash(f'Error: {e}', 'error')
            return redirect(url_for('behavior', class_name=selected_class, term_id=selected_term_id))

        return render_template('behavior.html', classes=classes, terms=terms,
                                selected_class=selected_class, selected_term_id=selected_term_id,
                                students_list=students_list, behavior_data=behavior_data,
                                components=components)
    finally:
        db.close()


# ── Routes: Behavior Components (admin) ───────────────────────────────────────
@app.route('/behavior-components', methods=['GET', 'POST'])
@login_required
@admin_required
def behavior_components():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'add':
                name = re.sub(r'\s+', '_', request.form['display_label'].strip().lower())
                db.execute(text("""
                    INSERT INTO behavior_components (name,display_label,display_order,active)
                    VALUES (:n,:l,:o,true)
                """), {'n':name,'l':request.form['display_label'],'o':int(request.form.get('display_order',99))})
                db.commit()
                flash('Component added.', 'success')
            elif action == 'toggle':
                cid = int(request.form['component_id'])
                c = db.execute(text('SELECT * FROM behavior_components WHERE id=:id'),{'id':cid}).fetchone()
                if c:
                    c.active = not c.active
                    db.commit()
            elif action == 'delete':
                cid = int(request.form['component_id'])
                c = db.execute(text('SELECT * FROM behavior_components WHERE id=:id'),{'id':cid}).fetchone()
                if c:
                    db.delete(c)
                    db.commit()
            return redirect(url_for('behavior_components'))
        comps = db.execute(text('SELECT * FROM behavior_components ORDER BY display_order')).fetchall()
        return render_template('behavior_components.html', components=comps)
    finally:
        db.close()


# ── Routes: Discipline ────────────────────────────────────────────────────────
@app.route('/discipline', methods=['GET', 'POST'])
@login_required
def discipline():
    db = SessionLocal()
    try:
        uid = session.get('user_id')
        role = session['user_role']
        terms = db.execute(text('SELECT * FROM academic_terms ORDER BY year DESC, term_number')).fetchall()
        students_all = db.execute(text('SELECT * FROM students ORDER BY class_name, name')).fetchall()

        if request.method == 'POST':
            action = request.form.get('action', 'add')
            if action == 'add':
                db.execute(text("""
                    INSERT INTO discipline_reports
                        (student_id,reported_by,incident_date,incident_type,description,action_taken,status)
                    VALUES (:sid,:uid,:idate,:itype,:desc,:action,'Pending')
                """), {
                    'sid':int(request.form['student_id']),'uid':uid,
                    'idate':request.form['incident_date'],'itype':request.form['incident_type'],
                    'desc':request.form['description'],'action':request.form.get('action_taken',''),
                })
                db.commit()
                flash('Discipline report filed.', 'success')
            elif action == 'update_status' and role == 'admin':
                rid = int(request.form['report_id'])
                r = db.execute(text('SELECT * FROM discipline_reports WHERE id=:id'),{'id':rid}).fetchone()
                if r:
                    r.status = request.form['status']
                    r.admin_notes = request.form.get('admin_notes', '')
                    db.commit()
                    flash('Report updated.', 'success')
            return redirect(url_for('discipline'))

        # Fetch reports with student and reporter names
        reports = db.execute(text("""
            SELECT dr.id, dr.incident_date, dr.incident_type, dr.description,
                   dr.action_taken, dr.status, dr.admin_notes, dr.created_at,
                   s.name as student_name, s.class_name,
                   u.name as reporter_name
            FROM discipline_reports dr
            JOIN students s ON dr.student_id = s.id
            LEFT JOIN users u ON dr.reported_by = u.id
            ORDER BY dr.created_at DESC
        """)).fetchall()

        return render_template('discipline.html', reports=reports,
                                students=students_all, terms=terms, role=role)
    finally:
        db.close()


# ── Routes: Communications ────────────────────────────────────────────────────
@app.route('/communications', methods=['GET', 'POST'])
@login_required
def communications():
    db = SessionLocal()
    try:
        uid = session.get('user_id')
        users_all = db.execute(text("SELECT * FROM users WHERE role!='master_admin'")).fetchall()

        if request.method == 'POST':
            action = request.form.get('action', 'send')
            if action == 'send':
                is_broadcast = 'broadcast' in request.form
                recipient_id = None if is_broadcast else int(request.form.get('recipient_id', 0))
                db.execute(text("""
                    INSERT INTO messages (sender_id,recipient_id,subject,body,is_broadcast,read)
                    VALUES (:sid,:rid,:subj,:body,:bcast,false)
                """), {
                    'sid':uid,'rid':None if is_broadcast else recipient_id,
                    'subj':request.form['subject'],'body':request.form['body'],
                    'bcast':is_broadcast,
                })
                db.commit()
                flash('Message sent.', 'success')
            elif action == 'mark_read':
                mid = int(request.form['message_id'])
                m = db.execute(text('SELECT * FROM messages WHERE id=:id'),{'id':mid}).fetchone()
                if m:
                    m.read = True
                    db.commit()
            return redirect(url_for('communications'))

        inbox = db.execute(text("""
            SELECT m.id, m.subject, m.body, m.read, m.is_broadcast, m.created_at,
                   u.name as sender_name
            FROM messages m LEFT JOIN users u ON m.sender_id = u.id
            WHERE (m.is_broadcast = TRUE OR m.recipient_id = :uid)
            AND LOWER(COALESCE(m.subject,'')) NOT LIKE '%discipline%'
            ORDER BY m.created_at DESC
        """), {'uid': uid}).fetchall()

        return render_template('communications.html', inbox=inbox, users=users_all)
    finally:
        db.close()


# ── Routes: Student Decisions ─────────────────────────────────────────────────
@app.route('/decisions', methods=['GET', 'POST'])
@login_required
def decisions():
    db = SessionLocal()
    try:
        uid = session.get('user_id')
        terms = db.execute(text('SELECT * FROM academic_terms ORDER BY year DESC, term_number')).fetchall()
        active_term = db.execute(text('SELECT * FROM academic_terms WHERE is_active=true LIMIT 1')).fetchone()

        role = session['user_role']
        if role == 'admin':
            classes = [r[0] for r in db.execute(text("SELECT DISTINCT class_name FROM students ORDER BY class_name")).fetchall()]
        else:
            u = db.execute(text('SELECT * FROM users WHERE id=:id'),{'id':uid}).fetchone()
            classes = [c.strip() for c in (u.class_teacher_for or '').split(',') if c.strip()] if u else []
            if not classes:
                classes = [r[0] for r in db.execute(text("SELECT DISTINCT class_name FROM students ORDER BY class_name")).fetchall()]

        selected_class = request.args.get('class_name') or (classes[0] if classes else None)
        selected_term_id = request.args.get('term_id') or (str(active_term.id) if active_term else None)

        students_list = []
        decisions_data = {}
        if selected_class and selected_term_id:
            rows = db.execute(text("SELECT id, name FROM students WHERE class_name=:c ORDER BY name"), {'c': selected_class}).fetchall()
            students_list = [{'id': r.id, 'name': r.name} for r in rows]
            for s in students_list:
                d = db.execute(text('SELECT * FROM student_decisions WHERE student_id=:sid AND term_id=:tid'),{'sid':s['id'],'tid':int(selected_term_id)}).fetchone()
                if d:
                    decisions_data[s['id']] = {'decision': d.decision, 'notes': d.notes}

        if request.method == 'POST':
            try:
                student_id = int(request.form['student_id'])
                term_id = int(request.form['term_id'])
                decision_val = request.form['decision']
                notes = request.form.get('notes', '')
                existing = db.execute(text('SELECT id FROM student_decisions WHERE student_id=:sid AND term_id=:tid'),{'sid':student_id,'tid':term_id}).fetchone()
                if existing:
                    db.execute(text('UPDATE student_decisions SET decision=:dec,notes=:notes WHERE id=:id'),
                               {'dec':decision_val,'notes':notes,'id':existing.id})
                else:
                    db.execute(text("""
                        INSERT INTO student_decisions (student_id,term_id,decision,notes,decision_made_by,decision_date)
                        VALUES (:sid,:tid,:dec,:notes,:uid,:dd)
                    """), {'sid':student_id,'tid':term_id,'dec':decision_val,
                             'notes':notes,'uid':uid,'dd':datetime.now().isoformat()})
                db.commit()
                flash('Decision saved.', 'success')
            except Exception as e:
                db.rollback()
                flash(f'Error: {e}', 'error')
            return redirect(url_for('decisions', class_name=selected_class, term_id=selected_term_id))

        return render_template('decisions.html', classes=classes, terms=terms,
                                selected_class=selected_class, selected_term_id=selected_term_id,
                                students_list=students_list, decisions_data=decisions_data)
    finally:
        db.close()


# ── Routes: Visitation Day ────────────────────────────────────────────────────
@app.route('/visitation', methods=['GET', 'POST'])
@login_required
@admin_required
def visitation():
    db = SessionLocal()
    try:
        uid = session.get('user_id')
        terms = db.execute(text('SELECT * FROM academic_terms ORDER BY year DESC, term_number')).fetchall()
        active_term = db.execute(text('SELECT * FROM academic_terms WHERE is_active=true LIMIT 1')).fetchone()
        classes = [r[0] for r in db.execute(text("SELECT DISTINCT class_name FROM students ORDER BY class_name")).fetchall()]

        selected_class = request.args.get('class_name') or (classes[0] if classes else None)
        selected_term_id = request.args.get('term_id') or (str(active_term.id) if active_term else None)

        students_list = []
        vd_data = {}
        if selected_class and selected_term_id:
            rows = db.execute(text("SELECT id, name FROM students WHERE class_name=:c ORDER BY name"), {'c': selected_class}).fetchall()
            students_list = [{'id': r.id, 'name': r.name} for r in rows]
            for s in students_list:
                v = db.execute(text('SELECT * FROM visitation_days WHERE student_id=:sid AND term_id=:tid'),{'sid':s['id'],'tid':int(selected_term_id)}).fetchone()
                if v:
                    vd_data[s['id']] = {'date': v.visitation_date, 'parent_attended': v.parent_attended, 'report_given': v.report_given, 'notes': v.notes}

        if request.method == 'POST':
            try:
                student_id = int(request.form['student_id'])
                term_id = int(request.form['term_id'])
                existing = db.execute(text('SELECT id FROM visitation_days WHERE student_id=:sid AND term_id=:tid'),{'sid':student_id,'tid':term_id}).fetchone()
                if existing:
                    db.execute(text("""
                        UPDATE visitation_days SET visitation_date=:vd,parent_attended=:pa,
                        report_given=:rg,notes=:notes WHERE id=:id
                    """), {'vd':request.form.get('visitation_date',''),
                             'pa':'parent_attended' in request.form,
                             'rg':'report_given' in request.form,
                             'notes':request.form.get('notes',''),'id':existing.id})
                else:
                    db.execute(text("""
                        INSERT INTO visitation_days
                            (student_id,term_id,visitation_date,parent_attended,report_given,notes,created_by)
                        VALUES (:sid,:tid,:vd,:pa,:rg,:notes,:uid)
                    """), {'sid':student_id,'tid':term_id,
                             'vd':request.form.get('visitation_date',''),
                             'pa':'parent_attended' in request.form,
                             'rg':'report_given' in request.form,
                             'notes':request.form.get('notes',''),'uid':uid})
                db.commit()
                flash('Visitation record saved.', 'success')
            except Exception as e:
                db.rollback()
                flash(f'Error: {e}', 'error')
            return redirect(url_for('visitation', class_name=selected_class, term_id=selected_term_id))

        return render_template('visitation.html', classes=classes, terms=terms,
                                selected_class=selected_class, selected_term_id=selected_term_id,
                                students_list=students_list, vd_data=vd_data)
    finally:
        db.close()


# ── Routes: Report Design ─────────────────────────────────────────────────────
@app.route('/report-design', methods=['GET', 'POST'])
@login_required
@admin_required
def report_design():
    db = SessionLocal()
    try:
        design = db.execute(text('SELECT * FROM report_designs LIMIT 1')).fetchone()
        if not design:
            db.execute(text("INSERT INTO report_designs (school_name,primary_color) VALUES ('Empower International Academy','#3a3a9c')"))
            db.commit()
            design = db.execute(text('SELECT * FROM report_designs LIMIT 1')).fetchone()

        if request.method == 'POST':
            _design_updates = {
                'sname':   request.form.get('school_name', design.school_name),
                'ssub':    request.form.get('school_subtitle',''),
                'saddr':   request.form.get('school_address',''),
                'spob':    request.form.get('school_po_box',''),
                'sphone':  request.form.get('school_phone',''),
                'semail':  request.form.get('school_email',''),
                'sweb':    request.form.get('school_website',''),
                'scolor':  request.form.get('primary_color','#8B4513'),
                'sfooter': request.form.get('report_footer',''),
                'did':     design.id,
            }

            logo_file = request.files.get('logo')
            if logo_file and logo_file.filename:
                logo_bytes = logo_file.read()
                design.logo_data = base64.b64encode(logo_bytes).decode('utf-8')

            logo_url = request.form.get('logo_url', '').strip()
            if logo_url:
                try:
                    resp = requests.get(logo_url, timeout=10)
                    design.logo_data = base64.b64encode(resp.content).decode('utf-8')
                except Exception as e:
                    flash(f'Could not download logo: {e}', 'error')

            db.commit()
            log_audit(db, session.get('user_id'), 'update_report_design', '')
            flash('Report design updated.', 'success')
            return redirect(url_for('report_design'))

        return render_template('report_design.html', design=design)
    finally:
        db.close()


# ── Routes: Generate Reports (PDF) ────────────────────────────────────────────
@app.route('/generate-reports', methods=['GET', 'POST'])
@login_required
def generate_reports():
    db = SessionLocal()
    try:
        terms = db.execute(text('SELECT * FROM academic_terms ORDER BY year DESC, term_number')).fetchall()
        active_term = db.execute(text('SELECT * FROM academic_terms WHERE is_active=true LIMIT 1')).fetchone()
        classes = [r[0] for r in db.execute(text("SELECT DISTINCT class_name FROM students ORDER BY class_name")).fetchall()]
        design = db.execute(text('SELECT * FROM report_designs LIMIT 1')).fetchone()

        if request.method == 'POST':
            term_id = int(request.form['term_id'])
            report_type = request.form.get('report_type', 'end_term')
            selected_class = request.form.get('class_name')
            student_id = request.form.get('student_id')

            term = db.execute(text('SELECT * FROM academic_terms WHERE id=:id'),{'id':term_id}).fetchone()
            if not term:
                flash('Term not found.', 'error')
                return redirect(url_for('generate_reports'))

            term_data = {
                'id': term.id, 'year': term.year, 'term_number': term.term_number,
                'term_name': term.term_name, 'next_term_begins': term.next_term_begins or ''
            }

            is_vd = report_type == 'visitation_day'

            if student_id:
                # Single student PDF
                s = db.execute(text('SELECT * FROM students WHERE id=:id'),{'id':int(student_id)}).fetchone()
                if not s:
                    flash('Student not found.', 'error')
                    return redirect(url_for('generate_reports'))

                marks_list = _get_marks_list(db, s.id, term_id)
                behavior = _get_behavior_dict(db, s.id, term_id)
                decision = _get_decision(db, s.id, term_id)
                student_data = {'id': s.id, 'name': s.name, 'class_name': s.class_name,
                                 'registration_number': s.registration_number}
                pdf_bytes = generate_pdf_report(student_data, term_data, marks_list, design,
                                                  behavior_data=behavior, decision_data=decision,
                                                  is_vd_report=is_vd)
                fname = f"{s.name.replace(' ','_')}_report.pdf"
                return send_file(io.BytesIO(pdf_bytes), download_name=fname, as_attachment=True,
                                  mimetype='application/pdf')
            else:
                # Whole class ZIP
                students = db.execute(text(
                    "SELECT id, name, class_name, registration_number FROM students "
                    "WHERE class_name=:c ORDER BY name"), {'c': selected_class}).fetchall()
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for s in students:
                        marks_list = _get_marks_list(db, s.id, term_id)
                        behavior = _get_behavior_dict(db, s.id, term_id)
                        decision = _get_decision(db, s.id, term_id)
                        student_data = {'id': s.id, 'name': s.name, 'class_name': s.class_name,
                                         'registration_number': s.registration_number}
                        try:
                            pdf_bytes = generate_pdf_report(student_data, term_data, marks_list, design,
                                                              behavior_data=behavior, decision_data=decision,
                                                              is_vd_report=is_vd)
                            zf.writestr(f"{s.name.replace(' ','_')}_report.pdf", pdf_bytes)
                        except Exception:
                            pass
                zip_buf.seek(0)
                fname = f"{selected_class}_reports.zip"
                return send_file(zip_buf, download_name=fname, as_attachment=True,
                                  mimetype='application/zip')

        students_all = db.execute(text('SELECT * FROM students ORDER BY class_name, name')).fetchall()
        return render_template('generate_reports.html', terms=terms, active_term=active_term,
                                classes=classes, students=students_all, design=design)
    finally:
        db.close()


def _get_marks_list(db, student_id, term_id):
    """Return marks as a plain list of dicts (no pandas needed)."""
    rows = db.execute(text("""
        SELECT m.subject, m.coursework_out_of_20, m.midterm_out_of_20,
               m.endterm_out_of_60, m.total, m.grade, m.comment,
               u.name as teacher_name
        FROM marks m LEFT JOIN users u ON m.submitted_by = u.id
        WHERE m.student_id=:sid AND m.term_id=:tid
        ORDER BY m.subject
    """), {'sid': student_id, 'tid': term_id}).fetchall()
    return [dict(r._mapping) for r in rows]


def _get_behavior_dict(db, student_id, term_id):
    rows = db.execute(text("""
        SELECT bc.name as component_name, bc.display_label, cbr.value
        FROM classroom_behavior_responses cbr
        JOIN behavior_components bc ON cbr.component_id = bc.id
        WHERE cbr.student_id=:sid AND cbr.term_id=:tid
    """), {'sid': student_id, 'tid': term_id}).fetchall()
    if not rows:
        return None
    result = {}
    mapping = {
        'Punctuality': 'punctuality', 'Attendance': 'attendance',
        'Manners': 'manners', 'General Behavior': 'general_behavior',
        'Organisation': 'organisational_skills', 'Adherence to Uniform': 'adherence_to_uniform',
        'Leadership': 'leadership_skills', 'Commitment to School': 'commitment_to_school',
        'Cooperation with Peers': 'cooperation_with_peers',
        'Cooperation with Staff': 'cooperation_with_staff',
        'Participation': 'participation_in_lessons',
        'Homework Completion': 'completion_of_homework',
    }
    for r in rows:
        result[r.component_name] = r.value
        if r.display_label:
            result[r.display_label] = r.value
            result[r.display_label.lower().replace(' ', '_')] = r.value
            legacy = mapping.get(r.display_label)
            if legacy:
                result[legacy] = r.value
    return result or None


def _get_decision(db, student_id, term_id):
    d = db.execute(text('SELECT * FROM student_decisions WHERE student_id=:sid AND term_id=:tid'),{'sid':student_id,'tid':term_id}).fetchone()
    if not d:
        return None
    return {'decision': d.decision, 'notes': d.notes}


# ── Routes: Performance Analytics ────────────────────────────────────────────
@app.route('/analytics')
@login_required
@admin_required
def analytics():
    db = SessionLocal()
    try:
        terms = db.execute(text('SELECT * FROM academic_terms ORDER BY year DESC, term_number')).fetchall()
        active_term = db.execute(text('SELECT * FROM academic_terms WHERE is_active=true LIMIT 1')).fetchone()
        classes = [r[0] for r in db.execute(text("SELECT DISTINCT class_name FROM students ORDER BY class_name")).fetchall()]

        selected_class = request.args.get('class_name') or (classes[0] if classes else None)
        selected_term_id = request.args.get('term_id') or (str(active_term.id) if active_term else None)

        performance = None
        top_students = []
        grade_dist = []
        subject_avgs = []

        if selected_class and selected_term_id:
            tid = int(selected_term_id)

            # All aggregations done in SQL — no pandas needed
            agg = db.execute(text("""
                SELECT
                    ROUND(AVG(m.total)::numeric, 1)               AS avg_total,
                    ROUND(AVG(m.coursework_out_of_20)::numeric, 1) AS avg_cw,
                    ROUND(AVG(m.midterm_out_of_20)::numeric, 1)    AS avg_mt,
                    ROUND(AVG(m.endterm_out_of_60)::numeric, 1)    AS avg_et,
                    COUNT(DISTINCT m.student_id)                   AS total_students
                FROM marks m JOIN students s ON m.student_id = s.id
                WHERE s.class_name=:cls AND m.term_id=:tid
            """), {'cls': selected_class, 'tid': tid}).fetchone()

            if agg and agg.total_students:
                performance = {
                    'avg_total':    float(agg.avg_total or 0),
                    'avg_cw':       float(agg.avg_cw or 0),
                    'avg_mt':       float(agg.avg_mt or 0),
                    'avg_et':       float(agg.avg_et or 0),
                    'total_students': int(agg.total_students),
                }

                gd_rows = db.execute(text("""
                    SELECT m.grade, COUNT(*) AS cnt
                    FROM marks m JOIN students s ON m.student_id = s.id
                    WHERE s.class_name=:cls AND m.term_id=:tid
                    GROUP BY m.grade ORDER BY m.grade
                """), {'cls': selected_class, 'tid': tid}).fetchall()
                grade_dist = [{'grade': r.grade, 'count': int(r.cnt)} for r in gd_rows]

                sa_rows = db.execute(text("""
                    SELECT m.subject, ROUND(AVG(m.total)::numeric, 1) AS avg
                    FROM marks m JOIN students s ON m.student_id = s.id
                    WHERE s.class_name=:cls AND m.term_id=:tid
                    GROUP BY m.subject ORDER BY m.subject
                """), {'cls': selected_class, 'tid': tid}).fetchall()
                subject_avgs = [{'subject': r.subject, 'avg': float(r.avg or 0)} for r in sa_rows]

            top_rows = db.execute(text("""
                SELECT s.name, s.class_name, AVG(m.total) as avg_total
                FROM marks m JOIN students s ON m.student_id = s.id
                WHERE s.class_name=:cls AND m.term_id=:tid
                GROUP BY s.id, s.name, s.class_name ORDER BY avg_total DESC LIMIT 5
            """), {'cls': selected_class, 'tid': tid}).fetchall()
            top_students = [{'name': r.name, 'avg': round(r.avg_total, 1)} for r in top_rows]

        return render_template('analytics.html', terms=terms, classes=classes,
                                selected_class=selected_class, selected_term_id=selected_term_id,
                                performance=performance, top_students=top_students,
                                grade_dist=json.dumps(grade_dist),
                                subject_avgs=json.dumps(subject_avgs))
    finally:
        db.close()


# ── Routes: Data Export ───────────────────────────────────────────────────────
@app.route('/export')
@login_required
@admin_required
def data_export():
    db = SessionLocal()
    try:
        export_type = request.args.get('type', 'students')

        if export_type == 'students':
            rows = db.execute(text(
                "SELECT id, name, class_name, registration_number, gender, enrollment_date "
                "FROM students ORDER BY class_name, name")).fetchall()
            headers = ['id', 'name', 'class_name', 'registration_number', 'gender', 'enrollment_date']

        elif export_type == 'marks':
            rows = db.execute(text("""
                SELECT s.name AS student, s.class_name, m.subject,
                       m.coursework_out_of_20, m.midterm_out_of_20,
                       m.endterm_out_of_60, m.total, m.grade, t.term_name
                FROM marks m
                JOIN students s ON m.student_id=s.id
                JOIN academic_terms t ON m.term_id=t.id
                ORDER BY s.class_name, s.name, t.term_name
            """)).fetchall()
            headers = ['student', 'class_name', 'subject', 'coursework_out_of_20',
                       'midterm_out_of_20', 'endterm_out_of_60', 'total', 'grade', 'term_name']

        elif export_type == 'discipline':
            rows = db.execute(text("""
                SELECT dr.incident_date, dr.incident_type, dr.description,
                       dr.action_taken, dr.status, dr.created_at,
                       s.name AS student, s.class_name, u.name AS reporter
                FROM discipline_reports dr
                JOIN students s ON dr.student_id=s.id
                LEFT JOIN users u ON dr.reported_by=u.id
                ORDER BY dr.created_at DESC
            """)).fetchall()
            headers = ['incident_date', 'incident_type', 'description', 'action_taken',
                       'status', 'created_at', 'student', 'class_name', 'reporter']
        else:
            rows = []
            headers = []

        # Build CSV in memory using stdlib csv — no pandas required
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(headers)
        for r in rows:
            writer.writerow([getattr(r, h, '') for h in headers])

        output = io.BytesIO(buf.getvalue().encode('utf-8'))
        output.seek(0)
        fname = f"{export_type}_export.csv"
        return send_file(output, download_name=fname, as_attachment=True, mimetype='text/csv')
    finally:
        db.close()


# ── Routes: Change Login Details ─────────────────────────────────────────────
@app.route('/change-login', methods=['GET', 'POST'])
@login_required
def change_login():
    db = SessionLocal()
    try:
        uid = session.get('user_id')
        if not uid:
            flash('Please log in first.', 'error')
            return redirect(url_for('login'))
        user = db.execute(text('SELECT * FROM users WHERE id=:id'),{'id':uid}).fetchone()
        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            current_pw = request.form.get('current_password', '')
            new_email = request.form.get('new_email', '').strip()
            new_pw = request.form.get('new_password', '')
            confirm_pw = request.form.get('confirm_password', '')
            r_phone = request.form.get('recovery_phone', '').strip()
            r_city = request.form.get('recovery_city', '').strip()
            r_nick = request.form.get('recovery_nickname', '').strip()

            if user.password_hash != hashlib.sha256(current_pw.encode()).hexdigest():
                flash('Current password is incorrect.', 'error')
            elif new_pw and new_pw != confirm_pw:
                flash('New passwords do not match.', 'error')
            elif not (r_phone or r_city or r_nick):
                flash('Provide at least one recovery detail.', 'error')
            else:
                # Check email uniqueness
                conflict = db.execute(text('SELECT id FROM users WHERE email=:em AND id!=:uid'),{'em':new_email,'uid':uid}).fetchone()
                if conflict:
                    flash('Email already taken.', 'error')
                else:
                    user.email = new_email
                    if new_pw:
                        user.password_hash = hashlib.sha256(new_pw.encode()).hexdigest()
                    if r_phone:
                        ok, val = validate_phone(r_phone)
                        if ok:
                            user.recovery_phone = val
                        else:
                            flash(val, 'error')
                            db.close()
                            return render_template('change_login.html', user=user)
                    user.recovery_city = r_city or None
                    user.recovery_nickname = r_nick or None
                    db.commit()
                    log_audit(db, uid, 'change_login', new_email)
                    flash('Login details updated.', 'success')
                    session.clear()
                    return redirect(url_for('login'))

        return render_template('change_login.html', user=user)
    finally:
        db.close()


# ── Routes: Admin Management ──────────────────────────────────────────────────
@app.route('/admin-management', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_management():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'add_admin':
                db.execute(text("""
                    INSERT INTO users (name,email,role,password_hash,subjects_taught,class_teacher_for,gender,phone_number)
                    VALUES (:name,:email,'admin',:pw,'','','','')
                """), {'name':request.form['name'],'email':request.form['email'],
                         'pw':hashlib.sha256(request.form['password'].encode()).hexdigest()})
                db.commit()
                flash('Admin added.', 'success')
            return redirect(url_for('admin_management'))

        admins = db.execute(text("SELECT * FROM users WHERE role='admin'")).fetchall()
        audit_logs = db.execute(text('SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 50')).fetchall()
        return render_template('admin_management.html', admins=admins, audit_logs=audit_logs)
    finally:
        db.close()


# ── Routes: Master Admin ──────────────────────────────────────────────────────
@app.route('/master-admin', methods=['GET', 'POST'])
@login_required
def master_admin():
    if session.get('user_role') != 'master_admin':
        abort(403)
    db = SessionLocal()
    try:
        if request.method == 'POST':
            action = request.form.get('action')
            confirm_pw = request.form.get('master_password', '')
            master_hash = hashlib.sha256(b'@mikaelJ46').hexdigest()

            if hashlib.sha256(confirm_pw.encode()).hexdigest() != master_hash:
                flash('Incorrect master admin password.', 'error')
                return redirect(url_for('master_admin'))

            if action == 'reset_admin_pw':
                admin = db.execute(text("SELECT * FROM users WHERE email='admin' LIMIT 1")).fetchone()
                if not admin:
                    admin = db.execute(text("SELECT * FROM users WHERE role='admin' LIMIT 1")).fetchone()
                if admin:
                    admin.password_hash = hashlib.sha256(b'admin123').hexdigest()
                    db.commit()
                    flash('Admin password reset to admin123.', 'success')
                else:
                    flash('No admin user found.', 'error')

            elif action == 'factory_reset':
                confirm_text = request.form.get('confirm_text', '')
                if confirm_text == 'DELETE ALL DATA':
                    Base.metadata.drop_all(engine)
                    Base.metadata.create_all(engine)
                    init_db()
                    flash('Database reset complete. Default admin: admin / admin123', 'success')
                    session.clear()
                    return redirect(url_for('login'))
                else:
                    flash('Confirmation text did not match.', 'error')

        total_users = db.execute(text('SELECT COUNT(*) FROM users')).scalar()
        total_students = db.execute(text('SELECT COUNT(*) FROM students')).scalar()
        total_terms = db.execute(text('SELECT COUNT(*) FROM academic_terms')).scalar()
        return render_template('master_admin.html', total_users=total_users,
                                total_students=total_students, total_terms=total_terms)
    finally:
        db.close()


# ── Routes: Comments ──────────────────────────────────────────────────────────
@app.route('/comments', methods=['GET', 'POST'])
@login_required
def comments():
    db = SessionLocal()
    try:
        uid = session.get('user_id')
        role = session['user_role']
        terms = db.execute(text('SELECT * FROM academic_terms ORDER BY year DESC, term_number')).fetchall()
        active_term = db.execute(text('SELECT * FROM academic_terms WHERE is_active=true LIMIT 1')).fetchone()

        if role == 'admin':
            classes = [r[0] for r in db.execute(text("SELECT DISTINCT class_name FROM students ORDER BY class_name")).fetchall()]
        else:
            u = db.execute(text('SELECT * FROM users WHERE id=:id'),{'id':uid}).fetchone()
            classes = [r[0] for r in db.execute(text("SELECT DISTINCT class_name FROM students ORDER BY class_name")).fetchall()]

        selected_class = request.args.get('class_name') or (classes[0] if classes else None)
        selected_term_id = request.args.get('term_id') or (str(active_term.id) if active_term else None)

        if request.method == 'POST':
            student_id = int(request.form['student_id'])
            term_id = int(request.form['term_id'])
            subject = request.form['subject']
            comment_text = request.form['comment']
            mark = db.execute(text('SELECT id FROM marks WHERE student_id=:sid AND term_id=:tid AND subject=:sub'),{'sid':student_id,'tid':term_id,'sub':subject}).fetchone()
            if mark:
                mark.comment = comment_text
                db.commit()
                flash('Comment saved.', 'success')
            else:
                flash('Mark record not found - please enter marks first.', 'error')
            return redirect(url_for('comments', class_name=selected_class, term_id=selected_term_id))

        marks_rows = []
        if selected_class and selected_term_id:
            rows = db.execute(text("""
                SELECT s.id as student_id, s.name as student_name, m.subject, m.comment
                FROM marks m JOIN students s ON m.student_id=s.id
                WHERE s.class_name=:cls AND m.term_id=:tid
                ORDER BY s.name, m.subject
            """), {'cls': selected_class, 'tid': int(selected_term_id)}).fetchall()
            marks_rows = [dict(r._mapping) for r in rows]

        return render_template('comments.html', classes=classes, terms=terms,
                                selected_class=selected_class, selected_term_id=selected_term_id,
                                marks_rows=marks_rows)
    finally:
        db.close()


# ── App entry point ───────────────────────────────────────────────────────────
# init_db() must run whether started via gunicorn OR python app.py directly.
# Gunicorn imports this module — it never hits __main__ — so we call init_db
# unconditionally at module level, wrapped in app_context.
with app.app_context():
    try:
        init_db()
    except Exception as _init_err:
        # Log clearly so Render's log shows the real error
        import traceback
        print("STARTUP ERROR — init_db() failed:")
        traceback.print_exc()
        raise  # re-raise so gunicorn marks the worker as failed immediately

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
