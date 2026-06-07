# blueprints/people/routes.py — Students, Staff, Guardians, User Accounts
import hashlib
import json
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, flash, jsonify)
from sqlalchemy import text
from db import SessionLocal
from auth import login_required, roles_required, school_required

people_bp = Blueprint('people', __name__, template_folder='templates')


def school_id():
    return session.get('school_id')


def uid():
    return session.get('user_id')


def log_action(db, action, details=''):
    db.execute(text("""
        INSERT INTO audit_logs (school_id, user_id, user_role, action, details)
        VALUES (:sid, :uid, :role, :act, :det)
    """), {
        'sid': school_id(), 'uid': uid(),
        'role': session.get('user_role'),
        'act': action, 'det': details
    })


# ── DASHBOARD ─────────────────────────────────────────────────────────────────

@people_bp.route('/')
@login_required
@school_required
def index():
    db = SessionLocal()
    try:
        sid = school_id()
        stats = {
            'students': db.execute(text(
                "SELECT COUNT(*) FROM students WHERE school_id=:s AND enrolment_status='active'"
            ), {'s': sid}).scalar(),
            'staff': db.execute(text(
                "SELECT COUNT(*) FROM staff WHERE school_id=:s AND is_active=true"
            ), {'s': sid}).scalar(),
            'guardians': db.execute(text(
                "SELECT COUNT(*) FROM guardians WHERE school_id=:s"
            ), {'s': sid}).scalar(),
            'classes': db.execute(text(
                "SELECT COUNT(*) FROM classes WHERE school_id=:s AND is_active=true"
            ), {'s': sid}).scalar(),
        }

        # Students per class
        class_counts = db.execute(text("""
            SELECT class_name, COUNT(*) as cnt
            FROM students WHERE school_id=:s AND enrolment_status='active'
            AND class_name IS NOT NULL AND class_name != ''
            GROUP BY class_name ORDER BY class_name
        """), {'s': sid}).fetchall()

        # Recent enrolments
        recent = db.execute(text("""
            SELECT name, class_name, enrolment_date, admission_number
            FROM students WHERE school_id=:s
            ORDER BY created_at DESC LIMIT 8
        """), {'s': sid}).fetchall()

        return render_template('people/index.html',
                               stats=stats,
                               class_counts=class_counts,
                               recent=recent)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# STUDENTS
# ═══════════════════════════════════════════════════════════════════════════════

@people_bp.route('/students')
@login_required
@school_required
def students():
    db = SessionLocal()
    try:
        sid   = school_id()
        q     = request.args.get('q', '')
        cls   = request.args.get('class_name', '')
        status = request.args.get('status', 'active')
        page  = int(request.args.get('page', 1))
        per   = 25

        filters = "WHERE school_id=:s"
        params  = {'s': sid}

        if q:
            filters += " AND (name ILIKE :q OR admission_number ILIKE :q)"
            params['q'] = f'%{q}%'
        if cls:
            filters += " AND class_name=:cls"
            params['cls'] = cls
        if status:
            filters += " AND enrolment_status=:status"
            params['status'] = status

        total = db.execute(text(
            f"SELECT COUNT(*) FROM students {filters}"
        ), params).scalar()

        params['limit']  = per
        params['offset'] = (page - 1) * per
        rows = db.execute(text(
            f"SELECT * FROM students {filters} ORDER BY class_name, name "
            "LIMIT :limit OFFSET :offset"
        ), params).fetchall()

        classes = db.execute(text(
            "SELECT DISTINCT class_name FROM students WHERE school_id=:s "
            "AND class_name IS NOT NULL AND class_name != '' ORDER BY class_name"
        ), {'s': sid}).fetchall()

        return render_template('people/students.html',
                               students=rows, total=total,
                               page=page, per=per, pages=(total + per - 1) // per,
                               classes=[c.class_name for c in classes],
                               q=q, selected_class=cls, selected_status=status)
    finally:
        db.close()


@people_bp.route('/students/add', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'master_admin')
@school_required
def add_student():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            subjects = request.form.getlist('subjects')
            # Auto-generate admission number
            count = db.execute(text(
                "SELECT COUNT(*) FROM students WHERE school_id=:s"
            ), {'s': school_id()}).scalar()
            adm = f"EIA/{datetime.now().year}/{(count+1):04d}"

            db.execute(text("""
                INSERT INTO students
                    (school_id, admission_number, name, gender, date_of_birth,
                     nationality, religion, class_name, stream, year, subjects,
                     enrolment_date, enrolment_status, previous_school, medical_notes)
                VALUES
                    (:sid,:adm,:name,:gender,:dob,:nat,:rel,:cls,:stream,:yr,:subs,
                     :enroll,:status,:prev,:med)
            """), {
                'sid': school_id(), 'adm': adm,
                'name':   request.form['name'],
                'gender': request.form.get('gender', ''),
                'dob':    request.form.get('date_of_birth', ''),
                'nat':    request.form.get('nationality', ''),
                'rel':    request.form.get('religion', ''),
                'cls':    request.form.get('class_name', ''),
                'stream': request.form.get('stream', ''),
                'yr':     request.form.get('year') or None,
                'subs':   json.dumps(subjects),
                'enroll': request.form.get('enrolment_date', ''),
                'status': request.form.get('enrolment_status', 'active'),
                'prev':   request.form.get('previous_school', ''),
                'med':    request.form.get('medical_notes', ''),
            })
            db.commit()
            log_action(db, 'add_student', request.form['name'])
            db.commit()
            flash(f'Student {request.form["name"]} enrolled. Admission No: {adm}', 'success')
            return redirect(url_for('people.students'))

        known_subjects = _get_known_subjects(db)
        classes = _get_classes(db)
        return render_template('people/student_form.html',
                               student=None, subjects=[],
                               known_subjects=known_subjects,
                               classes=classes)
    except Exception as e:
        db.rollback()
        flash(f'Error: {e}', 'error')
        return redirect(url_for('people.students'))
    finally:
        db.close()


@people_bp.route('/students/<int:sid_>/edit', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'master_admin')
@school_required
def edit_student(sid_):
    db = SessionLocal()
    try:
        s = db.execute(text(
            "SELECT * FROM students WHERE id=:id AND school_id=:s"
        ), {'id': sid_, 's': school_id()}).fetchone()
        if not s:
            flash('Student not found.', 'error')
            return redirect(url_for('people.students'))

        if request.method == 'POST':
            subjects = request.form.getlist('subjects')
            db.execute(text("""
                UPDATE students SET
                    name=:name, gender=:gender, date_of_birth=:dob,
                    nationality=:nat, religion=:rel, class_name=:cls,
                    stream=:stream, year=:yr, subjects=:subs,
                    enrolment_date=:enroll, enrolment_status=:status,
                    previous_school=:prev, medical_notes=:med
                WHERE id=:id AND school_id=:school
            """), {
                'name':   request.form['name'],
                'gender': request.form.get('gender', ''),
                'dob':    request.form.get('date_of_birth', ''),
                'nat':    request.form.get('nationality', ''),
                'rel':    request.form.get('religion', ''),
                'cls':    request.form.get('class_name', ''),
                'stream': request.form.get('stream', ''),
                'yr':     request.form.get('year') or None,
                'subs':   json.dumps(subjects),
                'enroll': request.form.get('enrolment_date', ''),
                'status': request.form.get('enrolment_status', 'active'),
                'prev':   request.form.get('previous_school', ''),
                'med':    request.form.get('medical_notes', ''),
                'id': sid_, 'school': school_id(),
            })
            db.commit()
            log_action(db, 'edit_student', request.form['name'])
            db.commit()
            flash('Student updated.', 'success')
            return redirect(url_for('people.student_detail', sid_=sid_))

        subjects  = json.loads(s.subjects) if s.subjects else []
        known_subjects = _get_known_subjects(db)
        classes   = _get_classes(db)
        guardians = db.execute(text("""
            SELECT g.*, sg.is_primary FROM guardians g
            JOIN student_guardians sg ON sg.guardian_id=g.id
            WHERE sg.student_id=:id
        """), {'id': sid_}).fetchall()

        return render_template('people/student_form.html',
                               student=s, subjects=subjects,
                               known_subjects=known_subjects,
                               classes=classes, guardians=guardians)
    finally:
        db.close()


@people_bp.route('/students/<int:sid_>')
@login_required
@school_required
def student_detail(sid_):
    db = SessionLocal()
    try:
        s = db.execute(text(
            "SELECT * FROM students WHERE id=:id AND school_id=:s"
        ), {'id': sid_, 's': school_id()}).fetchone()
        if not s:
            flash('Student not found.', 'error')
            return redirect(url_for('people.students'))

        guardians = db.execute(text("""
            SELECT g.*, sg.is_primary FROM guardians g
            JOIN student_guardians sg ON sg.guardian_id=g.id
            WHERE sg.student_id=:id
        """), {'id': sid_}).fetchall()

        # Recent marks
        marks = db.execute(text("""
            SELECT m.*, t.name as term_name FROM marks m
            JOIN terms t ON t.id=m.term_id
            WHERE m.student_id=:id AND m.school_id=:s
            ORDER BY t.id DESC LIMIT 20
        """), {'id': sid_, 's': school_id()}).fetchall()

        # Attendance summary
        att = db.execute(text("""
            SELECT status, COUNT(*) as cnt FROM attendance
            WHERE student_id=:id AND school_id=:s
            GROUP BY status
        """), {'id': sid_, 's': school_id()}).fetchall()

        # Fee balance
        balance = db.execute(text("""
            SELECT COALESCE(SUM(balance),0) as total_balance FROM invoices
            WHERE student_id=:id AND school_id=:s AND status != 'paid'
        """), {'id': sid_, 's': school_id()}).scalar()

        subjects = json.loads(s.subjects) if s.subjects else []
        return render_template('people/student_detail.html',
                               student=s, guardians=guardians,
                               marks=marks, attendance=att,
                               balance=balance, subjects=subjects)
    finally:
        db.close()


@people_bp.route('/students/<int:sid_>/delete', methods=['POST'])
@login_required
@roles_required('admin', 'master_admin')
@school_required
def delete_student(sid_):
    db = SessionLocal()
    try:
        s = db.execute(text(
            "SELECT name FROM students WHERE id=:id AND school_id=:s"
        ), {'id': sid_, 's': school_id()}).fetchone()
        if s:
            db.execute(text(
                "DELETE FROM students WHERE id=:id AND school_id=:s"
            ), {'id': sid_, 's': school_id()})
            db.commit()
            log_action(db, 'delete_student', s.name)
            db.commit()
            flash('Student deleted.', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Error: {e}', 'error')
    finally:
        db.close()
    return redirect(url_for('people.students'))


# ═══════════════════════════════════════════════════════════════════════════════
# STAFF
# ═══════════════════════════════════════════════════════════════════════════════

@people_bp.route('/staff')
@login_required
@school_required
def staff():
    db = SessionLocal()
    try:
        sid = school_id()
        q   = request.args.get('q', '')
        dep = request.args.get('department', '')

        filters = "WHERE school_id=:s"
        params  = {'s': sid}
        if q:
            filters += " AND (name ILIKE :q OR employee_number ILIKE :q OR job_title ILIKE :q)"
            params['q'] = f'%{q}%'
        if dep:
            filters += " AND department=:dep"
            params['dep'] = dep

        rows = db.execute(text(
            f"SELECT * FROM staff {filters} ORDER BY name"
        ), params).fetchall()

        departments = db.execute(text(
            "SELECT DISTINCT department FROM staff WHERE school_id=:s "
            "AND department IS NOT NULL AND department != '' ORDER BY department"
        ), {'s': sid}).fetchall()

        return render_template('people/staff.html',
                               staff=rows, q=q, selected_dept=dep,
                               departments=[d.department for d in departments])
    finally:
        db.close()


@people_bp.route('/staff/add', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'master_admin')
@school_required
def add_staff():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            subjects = ','.join(request.form.getlist('subjects_taught'))
            classes  = ','.join(request.form.getlist('classes_taught'))
            pw       = request.form.get('password', 'staff123')

            # Generate employee number
            count = db.execute(text(
                "SELECT COUNT(*) FROM staff WHERE school_id=:s"
            ), {'s': school_id()}).scalar()
            emp_num = f"EMP/{datetime.now().year}/{(count+1):03d}"

            # Create login account
            role = request.form.get('role', 'teacher')
            user_id = db.execute(text("""
                INSERT INTO users (school_id, name, email, role, password_hash, must_change_pw, phone)
                VALUES (:sid, :name, :email, :role, :pw, true, :phone)
                RETURNING id
            """), {
                'sid':   school_id(),
                'name':  request.form['name'],
                'email': request.form.get('email', ''),
                'role':  role,
                'pw':    hashlib.sha256(pw.encode()).hexdigest(),
                'phone': request.form.get('phone', ''),
            }).scalar()

            db.execute(text("""
                INSERT INTO staff
                    (school_id, user_id, employee_number, name, gender, date_of_birth,
                     phone, email, address, national_id, department, job_title,
                     subjects_taught, classes_taught, class_teacher_for,
                     employment_type, employment_date, qualification)
                VALUES
                    (:sid,:uid,:emp,:name,:gender,:dob,:phone,:email,:addr,:nid,
                     :dept,:title,:subs,:cls,:cls_teacher,:emp_type,:emp_date,:qual)
            """), {
                'sid': school_id(), 'uid': user_id, 'emp': emp_num,
                'name':       request.form['name'],
                'gender':     request.form.get('gender', ''),
                'dob':        request.form.get('date_of_birth', ''),
                'phone':      request.form.get('phone', ''),
                'email':      request.form.get('email', ''),
                'addr':       request.form.get('address', ''),
                'nid':        request.form.get('national_id', ''),
                'dept':       request.form.get('department', ''),
                'title':      request.form.get('job_title', ''),
                'subs':       subjects,
                'cls':        classes,
                'cls_teacher': request.form.get('class_teacher_for', ''),
                'emp_type':   request.form.get('employment_type', ''),
                'emp_date':   request.form.get('employment_date', ''),
                'qual':       request.form.get('qualification', ''),
            })
            db.commit()
            log_action(db, 'add_staff', request.form['name'])
            db.commit()
            flash(f'Staff added. Employee No: {emp_num}. Default password: {pw}', 'success')
            return redirect(url_for('people.staff'))

        known_subjects = _get_known_subjects(db)
        classes = _get_classes(db)
        return render_template('people/staff_form.html',
                               staff=None,
                               known_subjects=known_subjects,
                               classes=classes)
    except Exception as e:
        db.rollback()
        flash(f'Error: {e}', 'error')
        return redirect(url_for('people.staff'))
    finally:
        db.close()


@people_bp.route('/staff/<int:staff_id>/edit', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'master_admin')
@school_required
def edit_staff(staff_id):
    db = SessionLocal()
    try:
        sf = db.execute(text(
            "SELECT * FROM staff WHERE id=:id AND school_id=:s"
        ), {'id': staff_id, 's': school_id()}).fetchone()
        if not sf:
            flash('Staff member not found.', 'error')
            return redirect(url_for('people.staff'))

        if request.method == 'POST':
            subjects = ','.join(request.form.getlist('subjects_taught'))
            classes  = ','.join(request.form.getlist('classes_taught'))
            db.execute(text("""
                UPDATE staff SET
                    name=:name, gender=:gender, date_of_birth=:dob,
                    phone=:phone, email=:email, address=:addr,
                    national_id=:nid, department=:dept, job_title=:title,
                    subjects_taught=:subs, classes_taught=:cls,
                    class_teacher_for=:cls_teacher, employment_type=:emp_type,
                    employment_date=:emp_date, qualification=:qual
                WHERE id=:id AND school_id=:school
            """), {
                'name':       request.form['name'],
                'gender':     request.form.get('gender', ''),
                'dob':        request.form.get('date_of_birth', ''),
                'phone':      request.form.get('phone', ''),
                'email':      request.form.get('email', ''),
                'addr':       request.form.get('address', ''),
                'nid':        request.form.get('national_id', ''),
                'dept':       request.form.get('department', ''),
                'title':      request.form.get('job_title', ''),
                'subs':       subjects,
                'cls':        classes,
                'cls_teacher': request.form.get('class_teacher_for', ''),
                'emp_type':   request.form.get('employment_type', ''),
                'emp_date':   request.form.get('employment_date', ''),
                'qual':       request.form.get('qualification', ''),
                'id': staff_id, 'school': school_id(),
            })
            # Update linked user
            if sf.user_id:
                updates = {'name': request.form['name'],
                           'email': request.form.get('email',''),
                           'phone': request.form.get('phone',''),
                           'role': request.form.get('role', 'teacher'),
                           'id': sf.user_id}
                db.execute(text(
                    "UPDATE users SET name=:name,email=:email,phone=:phone,role=:role WHERE id=:id"
                ), updates)
                if request.form.get('new_password'):
                    db.execute(text(
                        "UPDATE users SET password_hash=:pw WHERE id=:id"
                    ), {'pw': hashlib.sha256(request.form['new_password'].encode()).hexdigest(),
                        'id': sf.user_id})
            db.commit()
            log_action(db, 'edit_staff', request.form['name'])
            db.commit()
            flash('Staff updated.', 'success')
            return redirect(url_for('people.staff'))

        known_subjects = _get_known_subjects(db)
        classes = _get_classes(db)
        return render_template('people/staff_form.html',
                               staff=sf,
                               known_subjects=known_subjects,
                               classes=classes)
    finally:
        db.close()


@people_bp.route('/staff/<int:staff_id>/delete', methods=['POST'])
@login_required
@roles_required('admin', 'master_admin')
@school_required
def delete_staff(staff_id):
    db = SessionLocal()
    try:
        sf = db.execute(text(
            "SELECT name, user_id FROM staff WHERE id=:id AND school_id=:s"
        ), {'id': staff_id, 's': school_id()}).fetchone()
        if sf:
            if sf.user_id:
                db.execute(text(
                    "DELETE FROM users WHERE id=:id"
                ), {'id': sf.user_id})
            db.execute(text(
                "DELETE FROM staff WHERE id=:id AND school_id=:s"
            ), {'id': staff_id, 's': school_id()})
            db.commit()
            log_action(db, 'delete_staff', sf.name)
            db.commit()
            flash('Staff member deleted.', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Error: {e}', 'error')
    finally:
        db.close()
    return redirect(url_for('people.staff'))


# ═══════════════════════════════════════════════════════════════════════════════
# GUARDIANS
# ═══════════════════════════════════════════════════════════════════════════════

@people_bp.route('/guardians')
@login_required
@school_required
def guardians():
    db = SessionLocal()
    try:
        q      = request.args.get('q', '')
        params = {'s': school_id()}
        where  = "WHERE g.school_id=:s"
        if q:
            where += " AND (g.name ILIKE :q OR g.phone ILIKE :q OR g.email ILIKE :q)"
            params['q'] = f'%{q}%'

        rows = db.execute(text(f"""
            SELECT g.*,
                   STRING_AGG(s.name, ', ') as children
            FROM guardians g
            LEFT JOIN student_guardians sg ON sg.guardian_id=g.id
            LEFT JOIN students s ON s.id=sg.student_id
            {where}
            GROUP BY g.id
            ORDER BY g.name
        """), params).fetchall()

        return render_template('people/guardians.html', guardians=rows, q=q)
    finally:
        db.close()


@people_bp.route('/guardians/add', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'master_admin')
@school_required
def add_guardian():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            # Create login account for parent portal
            email = request.form.get('email', '').strip()
            pw    = request.form.get('password', 'parent123')
            user_id = None
            if email:
                user_id = db.execute(text("""
                    INSERT INTO users (school_id, name, email, role, password_hash, must_change_pw, phone)
                    VALUES (:sid, :name, :email, 'parent', :pw, true, :phone)
                    RETURNING id
                """), {
                    'sid':   school_id(),
                    'name':  request.form['name'],
                    'email': email,
                    'pw':    hashlib.sha256(pw.encode()).hexdigest(),
                    'phone': request.form.get('phone', ''),
                }).scalar()

            guardian_id = db.execute(text("""
                INSERT INTO guardians
                    (school_id, user_id, name, relationship, phone, alt_phone,
                     email, address, occupation, national_id)
                VALUES (:sid,:uid,:name,:rel,:phone,:alt,:email,:addr,:occ,:nid)
                RETURNING id
            """), {
                'sid':  school_id(), 'uid': user_id,
                'name': request.form['name'],
                'rel':  request.form.get('relationship', ''),
                'phone': request.form.get('phone', ''),
                'alt':  request.form.get('alt_phone', ''),
                'email': email,
                'addr': request.form.get('address', ''),
                'occ':  request.form.get('occupation', ''),
                'nid':  request.form.get('national_id', ''),
            }).scalar()

            # Link to selected students
            for student_id in request.form.getlist('student_ids'):
                db.execute(text("""
                    INSERT INTO student_guardians (student_id, guardian_id, is_primary)
                    VALUES (:sid, :gid, :primary)
                    ON CONFLICT DO NOTHING
                """), {'sid': student_id, 'gid': guardian_id,
                       'primary': request.form.get('is_primary') == '1'})

            db.commit()
            flash(f'Guardian added{" with portal access" if email else ""}.', 'success')
            return redirect(url_for('people.guardians'))

        # Students for linking
        students = db.execute(text(
            "SELECT id, name, class_name FROM students WHERE school_id=:s "
            "AND enrolment_status='active' ORDER BY class_name, name"
        ), {'s': school_id()}).fetchall()
        return render_template('people/guardian_form.html',
                               guardian=None, linked_students=[],
                               all_students=students)
    except Exception as e:
        db.rollback()
        flash(f'Error: {e}', 'error')
        return redirect(url_for('people.guardians'))
    finally:
        db.close()


@people_bp.route('/guardians/<int:gid>/edit', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'master_admin')
@school_required
def edit_guardian(gid):
    db = SessionLocal()
    try:
        g = db.execute(text(
            "SELECT * FROM guardians WHERE id=:id AND school_id=:s"
        ), {'id': gid, 's': school_id()}).fetchone()
        if not g:
            flash('Guardian not found.', 'error')
            return redirect(url_for('people.guardians'))

        if request.method == 'POST':
            db.execute(text("""
                UPDATE guardians SET
                    name=:name, relationship=:rel, phone=:phone,
                    alt_phone=:alt, email=:email, address=:addr,
                    occupation=:occ, national_id=:nid
                WHERE id=:id AND school_id=:s
            """), {
                'name': request.form['name'],
                'rel':  request.form.get('relationship',''),
                'phone':request.form.get('phone',''),
                'alt':  request.form.get('alt_phone',''),
                'email':request.form.get('email',''),
                'addr': request.form.get('address',''),
                'occ':  request.form.get('occupation',''),
                'nid':  request.form.get('national_id',''),
                'id': gid, 's': school_id(),
            })
            # Update linked user name/phone
            if g.user_id:
                db.execute(text(
                    "UPDATE users SET name=:n,email=:e,phone=:p WHERE id=:id"
                ), {'n': request.form['name'], 'e': request.form.get('email',''),
                    'p': request.form.get('phone',''), 'id': g.user_id})
            db.commit()
            flash('Guardian updated.', 'success')
            return redirect(url_for('people.guardians'))

        linked = db.execute(text("""
            SELECT s.id, s.name, s.class_name, sg.is_primary
            FROM students s JOIN student_guardians sg ON sg.student_id=s.id
            WHERE sg.guardian_id=:gid
        """), {'gid': gid}).fetchall()

        all_students = db.execute(text(
            "SELECT id, name, class_name FROM students WHERE school_id=:s "
            "AND enrolment_status='active' ORDER BY class_name, name"
        ), {'s': school_id()}).fetchall()

        return render_template('people/guardian_form.html',
                               guardian=g, linked_students=linked,
                               all_students=all_students)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@people_bp.route('/classes')
@login_required
@school_required
def classes():
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT c.*,
                   s.name as teacher_name,
                   COUNT(st.id) as student_count
            FROM classes c
            LEFT JOIN staff s ON s.id=c.class_teacher
            LEFT JOIN students st ON st.class_name=c.name
                AND st.school_id=c.school_id AND st.enrolment_status='active'
            WHERE c.school_id=:s
            GROUP BY c.id, s.name
            ORDER BY c.name
        """), {'s': school_id()}).fetchall()
        return render_template('people/classes.html', classes=rows)
    finally:
        db.close()


@people_bp.route('/classes/add', methods=['GET', 'POST'])
@login_required
@roles_required('admin', 'master_admin')
@school_required
def add_class():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            db.execute(text("""
                INSERT INTO classes (school_id, name, stream, level, class_teacher, capacity, room)
                VALUES (:sid,:name,:stream,:level,:teacher,:cap,:room)
            """), {
                'sid':    school_id(),
                'name':   request.form['name'],
                'stream': request.form.get('stream',''),
                'level':  request.form.get('level',''),
                'teacher':request.form.get('class_teacher') or None,
                'cap':    request.form.get('capacity') or None,
                'room':   request.form.get('room',''),
            })
            db.commit()
            flash('Class added.', 'success')
            return redirect(url_for('people.classes'))

        staff_list = db.execute(text(
            "SELECT id, name FROM staff WHERE school_id=:s AND is_active=true ORDER BY name"
        ), {'s': school_id()}).fetchall()
        return render_template('people/class_form.html', cls=None, staff=staff_list)
    except Exception as e:
        db.rollback()
        flash(f'Error: {e}', 'error')
        return redirect(url_for('people.classes'))
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# USER ACCOUNTS
# ═══════════════════════════════════════════════════════════════════════════════

@people_bp.route('/users')
@login_required
@roles_required('admin', 'master_admin')
@school_required
def users():
    db = SessionLocal()
    try:
        role_filter = request.args.get('role', '')
        params = {'s': school_id()}
        where  = "WHERE school_id=:s"
        if role_filter:
            where += " AND role=:role"
            params['role'] = role_filter

        rows = db.execute(text(
            f"SELECT * FROM users {where} ORDER BY role, name"
        ), params).fetchall()
        return render_template('people/users.html', users=rows,
                               selected_role=role_filter)
    finally:
        db.close()


@people_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@login_required
@roles_required('admin', 'master_admin')
@school_required
def toggle_user(user_id):
    db = SessionLocal()
    try:
        u = db.execute(text(
            "SELECT is_active FROM users WHERE id=:id AND school_id=:s"
        ), {'id': user_id, 's': school_id()}).fetchone()
        if u:
            db.execute(text(
                "UPDATE users SET is_active=:v WHERE id=:id"
            ), {'v': not u.is_active, 'id': user_id})
            db.commit()
            flash('User account updated.', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Error: {e}', 'error')
    finally:
        db.close()
    return redirect(url_for('people.users'))


@people_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@roles_required('admin', 'master_admin')
@school_required
def reset_user_password(user_id):
    db = SessionLocal()
    try:
        new_pw = request.form.get('new_password', 'changeme123')
        db.execute(text(
            "UPDATE users SET password_hash=:pw, must_change_pw=true WHERE id=:id AND school_id=:s"
        ), {'pw': hashlib.sha256(new_pw.encode()).hexdigest(),
            'id': user_id, 's': school_id()})
        db.commit()
        flash(f'Password reset to: {new_pw}', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Error: {e}', 'error')
    finally:
        db.close()
    return redirect(url_for('people.users'))


# ═══════════════════════════════════════════════════════════════════════════════
# API helpers (used by JS)
# ═══════════════════════════════════════════════════════════════════════════════

@people_bp.route('/api/subjects')
@login_required
def api_subjects():
    db = SessionLocal()
    try:
        subjects = _get_known_subjects(db)
        return jsonify(subjects)
    finally:
        db.close()


@people_bp.route('/api/classes')
@login_required
def api_classes():
    db = SessionLocal()
    try:
        classes = _get_classes(db)
        return jsonify(classes)
    finally:
        db.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_known_subjects(db):
    """All known subjects from staff assignments + existing marks."""
    known = set()
    rows = db.execute(text(
        "SELECT subjects_taught FROM staff WHERE school_id=:s "
        "AND subjects_taught IS NOT NULL AND subjects_taught != ''"
    ), {'s': school_id()}).fetchall()
    for r in rows:
        for s in r.subjects_taught.split(','):
            s = s.strip()
            if s:
                known.add(s)
    rows2 = db.execute(text(
        "SELECT DISTINCT subject FROM marks WHERE school_id=:s AND subject IS NOT NULL"
    ), {'s': school_id()}).fetchall()
    for r in rows2:
        if r.subject:
            known.add(r.subject.strip())
    return sorted(known)


def _get_classes(db):
    """List of class names in this school."""
    rows = db.execute(text(
        "SELECT DISTINCT name FROM classes WHERE school_id=:s AND is_active=true ORDER BY name"
    ), {'s': school_id()}).fetchall()
    if not rows:
        rows2 = db.execute(text(
            "SELECT DISTINCT class_name FROM students WHERE school_id=:s "
            "AND class_name IS NOT NULL AND class_name != '' ORDER BY class_name"
        ), {'s': school_id()}).fetchall()
        return [r.class_name for r in rows2]
    return [r.name for r in rows]


@people_bp.route('/parent-portal')
@login_required
def parent_portal():
    """Parent's view of their linked children."""
    db = SessionLocal()
    try:
        uid_val = uid()
        guardian = db.execute(text(
            "SELECT * FROM guardians WHERE user_id=:uid AND school_id=:s LIMIT 1"
        ), {'uid': uid_val, 's': school_id()}).fetchone()

        children = []
        if guardian:
            children = db.execute(text("""
                SELECT s.* FROM students s
                JOIN student_guardians sg ON sg.student_id=s.id
                WHERE sg.guardian_id=:gid
            """), {'gid': guardian.id}).fetchall()

        return render_template('people/parent_portal.html',
                               guardian=guardian, children=children)
    finally:
        db.close()
