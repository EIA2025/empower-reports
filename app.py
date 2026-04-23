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
    poolclass=NullPool,                    # no persistent connection pool — safe for pgBouncer
    connect_args={
        "options": "-c statement_timeout=30000 -c lock_timeout=10000",
    },
    # Disable SQLAlchemy server-side prepared statements so pgBouncer stays happy
    execution_options={"no_parameters": False},
    echo=False,
)
SessionLocal = sessionmaker(bind=engine, autoflush=True, autocommit=False)

# ── Init DB ───────────────────────────────────────────────────────────────────
def init_db():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        # Seed default behavior components
        if db.query(BehaviorComponent).count() == 0:
            defaults = [
                ("punctuality","Punctuality"),("attendance","Attendance"),
                ("manners","Manners"),("general_behavior","General Behavior"),
                ("organisational_skills","Organisational Skills"),
                ("adherence_to_uniform","Adherence to Uniform"),
                ("leadership_skills","Leadership Skills"),
                ("commitment_to_school","Commitment to School"),
                ("cooperation_with_peers","Cooperation with Peers"),
                ("cooperation_with_staff","Cooperation with Staff"),
                ("participation_in_lessons","Participation in Lessons"),
                ("completion_of_homework","Completion of Homework"),
            ]
            for idx,(name,label) in enumerate(defaults):
                db.add(BehaviorComponent(name=name, display_label=label,
                                         display_order=idx, active=True))
            db.commit()
        # Seed default report design
        if db.query(ReportDesign).count() == 0:
            db.add(ReportDesign())
            db.commit()
        # Seed default admin
        if not db.query(User).filter_by(email='admin').first():
            db.add(User(name='Administrator', email='admin', role='admin',
                        password_hash=hashlib.sha256(b'admin123').hexdigest(),
                        subjects_taught='', class_teacher_for='',
                        gender='', phone_number=''))
            db.commit()
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
    db.add(AuditLog(user_id=user_id, action=action, details=details))
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
    design = db.query(ReportDesign).first()
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
        design = db.query(ReportDesign).first()
        active_term = db.query(AcademicTerm).filter_by(is_active=True).first()
        total_students = db.query(Student).count()
        total_teachers = db.query(User).filter_by(role='teacher').count()
        total_marks = db.query(Mark).count()

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


# ── Routes: Students ──────────────────────────────────────────────────────────
@app.route('/students')
@login_required
@admin_required
def students():
    db = SessionLocal()
    students = db.query(Student).order_by(Student.class_name, Student.name).all()
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
            s = Student(
                name=request.form['name'],
                year=int(request.form.get('year', 0) or 0),
                class_name=request.form['class_name'],
                registration_number=request.form['registration_number'],
                subjects=json.dumps(subjects),
                gender=request.form.get('gender', ''),
                enrollment_date=request.form.get('enrollment_date', ''),
            )
            db.add(s)
            db.commit()
            log_audit(db, session.get('user_id'), 'add_student', s.name)
            flash(f'Student {s.name} added.', 'success')
        except Exception as e:
            db.rollback()
            flash(f'Error: {e}', 'error')
        finally:
            db.close()
        return redirect(url_for('students'))
    return render_template('student_form.html', student=None)


@app.route('/students/<int:sid>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_student(sid):
    db = SessionLocal()
    s = db.query(Student).get(sid)
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
    db.close()
    return render_template('student_form.html', student=s, subjects=subjects)


@app.route('/students/<int:sid>/delete', methods=['POST'])
@login_required
@admin_required
def delete_student(sid):
    db = SessionLocal()
    s = db.query(Student).get(sid)
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
    users = db.query(User).filter(User.role != 'master_admin').order_by(User.name).all()
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
            u = User(
                name=request.form['name'],
                email=request.form['email'],
                role=request.form['role'],
                password_hash=hashlib.sha256(request.form['password'].encode()).hexdigest(),
                subjects_taught=','.join(subjects),
                class_teacher_for=request.form.get('class_teacher_for', ''),
                gender=request.form.get('gender', ''),
                phone_number=phone_or_err,
            )
            db.add(u)
            db.commit()
            log_audit(db, session.get('user_id'), 'add_staff', u.name)
            flash(f'Staff {u.name} added.', 'success')
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
    u = db.query(User).get(uid)
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
    u = db.query(User).get(uid)
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
    terms = db.query(AcademicTerm).order_by(AcademicTerm.year.desc(), AcademicTerm.term_number).all()
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
                db.query(AcademicTerm).update({'is_active': False})
            t = AcademicTerm(
                year=int(request.form['year']),
                term_number=int(request.form['term_number']),
                term_name=request.form['term_name'],
                start_date=request.form['start_date'],
                end_date=request.form['end_date'],
                next_term_begins=request.form.get('next_term_begins', ''),
                is_active=is_active,
            )
            db.add(t)
            db.commit()
            flash('Term added.', 'success')
        except Exception as e:
            db.rollback()
            flash(f'Error: {e}', 'error')
        finally:
            db.close()
        return redirect(url_for('terms'))
    return render_template('term_form.html', term=None)


@app.route('/terms/<int:tid>/activate', methods=['POST'])
@login_required
@admin_required
def activate_term(tid):
    db = SessionLocal()
    db.query(AcademicTerm).update({'is_active': False})
    t = db.query(AcademicTerm).get(tid)
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
    t = db.query(AcademicTerm).get(tid)
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
        user = db.query(User).get(uid) if uid else None
        terms = db.query(AcademicTerm).order_by(AcademicTerm.year.desc(), AcademicTerm.term_number).all()
        active_term = db.query(AcademicTerm).filter_by(is_active=True).first()

        # Determine which classes/subjects the user can see
        if role == 'admin':
            classes = [r[0] for r in db.execute(text("SELECT DISTINCT class_name FROM students ORDER BY class_name")).fetchall()]
            subjects_filter = None
        elif user:
            classes = [c.strip() for c in (user.class_teacher_for or '').split(',') if c.strip()]
            subjects_filter = [s.strip() for s in (user.subjects_taught or '').split(',') if s.strip()]
            # Also include classes where user teaches subjects
            if not classes:
                classes = [r[0] for r in db.execute(text("SELECT DISTINCT class_name FROM students ORDER BY class_name")).fetchall()]
        else:
            classes = []
            subjects_filter = []

        selected_class = request.args.get('class_name') or (classes[0] if classes else None)
        selected_term_id = request.args.get('term_id') or (str(active_term.id) if active_term else None)

        students_list = []
        marks_data = {}
        if selected_class and selected_term_id:
            rows = db.execute(text(
                "SELECT id, name, registration_number, subjects FROM students "
                "WHERE class_name=:cls ORDER BY name"), {'cls': selected_class}).fetchall()
            for r in rows:
                subs = json.loads(r.subjects) if r.subjects else []
                students_list.append({'id': r.id, 'name': r.name,
                                       'reg': r.registration_number, 'subjects': subs})
            # Fetch existing marks
            mrows = db.execute(text("""
                SELECT m.student_id, m.subject, m.coursework_out_of_20, m.midterm_out_of_20,
                       m.endterm_out_of_60, m.total, m.grade, m.comment
                FROM marks m WHERE m.term_id=:tid
                AND m.student_id IN (SELECT id FROM students WHERE class_name=:cls)
            """), {'tid': int(selected_term_id), 'cls': selected_class}).fetchall()
            for r in mrows:
                marks_data[(r.student_id, r.subject)] = dict(r._mapping)

        if request.method == 'POST':
            try:
                student_id = int(request.form['student_id'])
                subject = request.form['subject']
                term_id = int(request.form['term_id'])
                comp_type = request.form['component_type']  # coursework/midterm/endterm
                score = float(request.form['score'])
                total = float(request.form['total'])
                comp_name = request.form.get('component_name', comp_type.title())

                # Save component mark
                existing = db.query(ComponentMark).filter_by(
                    student_id=student_id, subject=subject, term_id=term_id,
                    component_type=comp_type, component_name=comp_name).first()
                if existing:
                    existing.score = score
                    existing.total = total
                else:
                    db.add(ComponentMark(student_id=student_id, subject=subject,
                                          term_id=term_id, component_type=comp_type,
                                          component_name=comp_name, score=score,
                                          total=total, submitted_by=uid))
                db.commit()

                # Recompute compiled mark
                _recompile_mark(db, student_id, subject, term_id, uid)
                flash('Mark saved.', 'success')
            except Exception as e:
                db.rollback()
                flash(f'Error saving mark: {e}', 'error')
            return redirect(url_for('marks', class_name=selected_class, term_id=selected_term_id))

        return render_template('marks.html', classes=classes, terms=terms,
                                selected_class=selected_class,
                                selected_term_id=selected_term_id,
                                students_list=students_list, marks_data=marks_data,
                                subjects_filter=subjects_filter)
    finally:
        db.close()


def _recompile_mark(db, student_id, subject, term_id, submitted_by=None):
    def _sum(comp_type):
        rows = db.query(ComponentMark).filter_by(
            student_id=student_id, subject=subject,
            term_id=term_id, component_type=comp_type).all()
        s = sum(r.score or 0 for r in rows)
        t = sum(r.total or 0 for r in rows)
        return s, t

    cw_s, cw_t = _sum('coursework')
    mt_s, mt_t = _sum('midterm')
    et_s, et_t = _sum('endterm')

    cw20 = convert_to_base(cw_s, cw_t, 20)
    mt20 = convert_to_base(mt_s, mt_t, 20)
    et60 = convert_to_base(et_s, et_t, 60)
    total = compute_total(cw20, mt20, et60)
    grade = get_grade(total)

    existing = db.query(Mark).filter_by(student_id=student_id,
                                         subject=subject, term_id=term_id).first()
    if existing:
        existing.coursework_score = cw_s; existing.coursework_total = cw_t
        existing.coursework_out_of_20 = cw20
        existing.midterm_score = mt_s; existing.midterm_total = mt_t
        existing.midterm_out_of_20 = mt20
        existing.endterm_score = et_s; existing.endterm_total = et_t
        existing.endterm_out_of_60 = et60
        existing.total = total; existing.grade = grade
        existing.submitted_at = datetime.now().isoformat()
        if submitted_by:
            existing.submitted_by = submitted_by
    else:
        db.add(Mark(student_id=student_id, subject=subject, term_id=term_id,
                    coursework_score=cw_s, coursework_total=cw_t, coursework_out_of_20=cw20,
                    midterm_score=mt_s, midterm_total=mt_t, midterm_out_of_20=mt20,
                    endterm_score=et_s, endterm_total=et_t, endterm_out_of_60=et60,
                    total=total, grade=grade, submitted_by=submitted_by,
                    submitted_at=datetime.now().isoformat()))
    db.commit()


# ── Routes: Behavior ──────────────────────────────────────────────────────────
@app.route('/behavior', methods=['GET', 'POST'])
@login_required
def behavior():
    db = SessionLocal()
    try:
        uid = session.get('user_id')
        terms = db.query(AcademicTerm).order_by(AcademicTerm.year.desc()).all()
        active_term = db.query(AcademicTerm).filter_by(is_active=True).first()
        components = db.query(BehaviorComponent).filter_by(active=True).order_by(BehaviorComponent.display_order).all()

        role = session['user_role']
        if role == 'admin':
            classes = [r[0] for r in db.execute(text("SELECT DISTINCT class_name FROM students ORDER BY class_name")).fetchall()]
        else:
            u = db.query(User).get(uid)
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
                        existing = db.query(ClassroomBehaviorResponse).filter_by(
                            student_id=student_id, term_id=term_id, component_id=comp.id).first()
                        if existing:
                            existing.value = val
                        else:
                            db.add(ClassroomBehaviorResponse(
                                student_id=student_id, term_id=term_id,
                                component_id=comp.id, value=val, evaluated_by=uid))
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
                db.add(BehaviorComponent(name=name,
                                          display_label=request.form['display_label'],
                                          display_order=int(request.form.get('display_order', 99)),
                                          active=True))
                db.commit()
                flash('Component added.', 'success')
            elif action == 'toggle':
                cid = int(request.form['component_id'])
                c = db.query(BehaviorComponent).get(cid)
                if c:
                    c.active = not c.active
                    db.commit()
            elif action == 'delete':
                cid = int(request.form['component_id'])
                c = db.query(BehaviorComponent).get(cid)
                if c:
                    db.delete(c)
                    db.commit()
            return redirect(url_for('behavior_components'))
        comps = db.query(BehaviorComponent).order_by(BehaviorComponent.display_order).all()
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
        terms = db.query(AcademicTerm).order_by(AcademicTerm.year.desc()).all()
        students_all = db.query(Student).order_by(Student.class_name, Student.name).all()

        if request.method == 'POST':
            action = request.form.get('action', 'add')
            if action == 'add':
                db.add(DisciplineReport(
                    student_id=int(request.form['student_id']),
                    reported_by=uid,
                    incident_date=request.form['incident_date'],
                    incident_type=request.form['incident_type'],
                    description=request.form['description'],
                    action_taken=request.form.get('action_taken', ''),
                    status='Pending',
                ))
                db.commit()
                flash('Discipline report filed.', 'success')
            elif action == 'update_status' and role == 'admin':
                rid = int(request.form['report_id'])
                r = db.query(DisciplineReport).get(rid)
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
        users_all = db.query(User).filter(User.role != 'master_admin').all()

        if request.method == 'POST':
            action = request.form.get('action', 'send')
            if action == 'send':
                is_broadcast = 'broadcast' in request.form
                recipient_id = None if is_broadcast else int(request.form.get('recipient_id', 0))
                db.add(Message(
                    sender_id=uid,
                    recipient_id=None if is_broadcast else recipient_id,
                    subject=request.form['subject'],
                    body=request.form['body'],
                    is_broadcast=is_broadcast,
                    read=False,
                ))
                db.commit()
                flash('Message sent.', 'success')
            elif action == 'mark_read':
                mid = int(request.form['message_id'])
                m = db.query(Message).get(mid)
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
        terms = db.query(AcademicTerm).order_by(AcademicTerm.year.desc()).all()
        active_term = db.query(AcademicTerm).filter_by(is_active=True).first()

        role = session['user_role']
        if role == 'admin':
            classes = [r[0] for r in db.execute(text("SELECT DISTINCT class_name FROM students ORDER BY class_name")).fetchall()]
        else:
            u = db.query(User).get(uid)
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
                d = db.query(StudentDecision).filter_by(student_id=s['id'], term_id=int(selected_term_id)).first()
                if d:
                    decisions_data[s['id']] = {'decision': d.decision, 'notes': d.notes}

        if request.method == 'POST':
            try:
                student_id = int(request.form['student_id'])
                term_id = int(request.form['term_id'])
                decision_val = request.form['decision']
                notes = request.form.get('notes', '')
                existing = db.query(StudentDecision).filter_by(student_id=student_id, term_id=term_id).first()
                if existing:
                    existing.decision = decision_val; existing.notes = notes
                else:
                    db.add(StudentDecision(student_id=student_id, term_id=term_id,
                                            decision=decision_val, notes=notes,
                                            decision_made_by=uid,
                                            decision_date=datetime.now().isoformat()))
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
        terms = db.query(AcademicTerm).order_by(AcademicTerm.year.desc()).all()
        active_term = db.query(AcademicTerm).filter_by(is_active=True).first()
        classes = [r[0] for r in db.execute(text("SELECT DISTINCT class_name FROM students ORDER BY class_name")).fetchall()]

        selected_class = request.args.get('class_name') or (classes[0] if classes else None)
        selected_term_id = request.args.get('term_id') or (str(active_term.id) if active_term else None)

        students_list = []
        vd_data = {}
        if selected_class and selected_term_id:
            rows = db.execute(text("SELECT id, name FROM students WHERE class_name=:c ORDER BY name"), {'c': selected_class}).fetchall()
            students_list = [{'id': r.id, 'name': r.name} for r in rows]
            for s in students_list:
                v = db.query(VisitationDay).filter_by(student_id=s['id'], term_id=int(selected_term_id)).first()
                if v:
                    vd_data[s['id']] = {'date': v.visitation_date, 'parent_attended': v.parent_attended, 'report_given': v.report_given, 'notes': v.notes}

        if request.method == 'POST':
            try:
                student_id = int(request.form['student_id'])
                term_id = int(request.form['term_id'])
                existing = db.query(VisitationDay).filter_by(student_id=student_id, term_id=term_id).first()
                if existing:
                    existing.visitation_date = request.form.get('visitation_date', '')
                    existing.parent_attended = 'parent_attended' in request.form
                    existing.report_given = 'report_given' in request.form
                    existing.notes = request.form.get('notes', '')
                else:
                    db.add(VisitationDay(student_id=student_id, term_id=term_id,
                                          visitation_date=request.form.get('visitation_date', ''),
                                          parent_attended='parent_attended' in request.form,
                                          report_given='report_given' in request.form,
                                          notes=request.form.get('notes', ''),
                                          created_by=uid))
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
        design = db.query(ReportDesign).first()
        if not design:
            design = ReportDesign()
            db.add(design)
            db.commit()

        if request.method == 'POST':
            design.school_name = request.form.get('school_name', design.school_name)
            design.school_subtitle = request.form.get('school_subtitle', '')
            design.school_address = request.form.get('school_address', '')
            design.school_po_box = request.form.get('school_po_box', '')
            design.school_phone = request.form.get('school_phone', '')
            design.school_email = request.form.get('school_email', '')
            design.school_website = request.form.get('school_website', '')
            design.primary_color = request.form.get('primary_color', '#8B4513')
            design.report_footer = request.form.get('report_footer', '')

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
        terms = db.query(AcademicTerm).order_by(AcademicTerm.year.desc()).all()
        active_term = db.query(AcademicTerm).filter_by(is_active=True).first()
        classes = [r[0] for r in db.execute(text("SELECT DISTINCT class_name FROM students ORDER BY class_name")).fetchall()]
        design = db.query(ReportDesign).first()

        if request.method == 'POST':
            term_id = int(request.form['term_id'])
            report_type = request.form.get('report_type', 'end_term')
            selected_class = request.form.get('class_name')
            student_id = request.form.get('student_id')

            term = db.query(AcademicTerm).get(term_id)
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
                s = db.query(Student).get(int(student_id))
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

        students_all = db.query(Student).order_by(Student.class_name, Student.name).all()
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
    d = db.query(StudentDecision).filter_by(student_id=student_id, term_id=term_id).first()
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
        terms = db.query(AcademicTerm).order_by(AcademicTerm.year.desc()).all()
        active_term = db.query(AcademicTerm).filter_by(is_active=True).first()
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
        user = db.query(User).get(uid)
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
                conflict = db.query(User).filter(User.email == new_email, User.id != uid).first()
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
                new_admin = User(
                    name=request.form['name'],
                    email=request.form['email'],
                    role='admin',
                    password_hash=hashlib.sha256(request.form['password'].encode()).hexdigest(),
                    subjects_taught='', class_teacher_for='', gender='', phone_number=''
                )
                db.add(new_admin)
                db.commit()
                flash('Admin added.', 'success')
            return redirect(url_for('admin_management'))

        admins = db.query(User).filter_by(role='admin').all()
        audit_logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(50).all()
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
                admin = db.query(User).filter_by(email='admin').first()
                if not admin:
                    admin = db.query(User).filter_by(role='admin').first()
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

        total_users = db.query(User).count()
        total_students = db.query(Student).count()
        total_terms = db.query(AcademicTerm).count()
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
        terms = db.query(AcademicTerm).order_by(AcademicTerm.year.desc()).all()
        active_term = db.query(AcademicTerm).filter_by(is_active=True).first()

        if role == 'admin':
            classes = [r[0] for r in db.execute(text("SELECT DISTINCT class_name FROM students ORDER BY class_name")).fetchall()]
        else:
            u = db.query(User).get(uid)
            classes = [r[0] for r in db.execute(text("SELECT DISTINCT class_name FROM students ORDER BY class_name")).fetchall()]

        selected_class = request.args.get('class_name') or (classes[0] if classes else None)
        selected_term_id = request.args.get('term_id') or (str(active_term.id) if active_term else None)

        if request.method == 'POST':
            student_id = int(request.form['student_id'])
            term_id = int(request.form['term_id'])
            subject = request.form['subject']
            comment_text = request.form['comment']
            mark = db.query(Mark).filter_by(student_id=student_id, term_id=term_id, subject=subject).first()
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
if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
