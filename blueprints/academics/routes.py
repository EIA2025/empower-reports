from flask import Blueprint, render_template, redirect, url_for, session, request, flash
from datetime import datetime, date
from db import SessionLocal
from sqlalchemy import text

academics_bp = Blueprint('academics', __name__, template_folder='templates')

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

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@academics_bp.route('/')
@login_required
def index():
    return redirect(url_for('academics.terms'))


# ── TERMS ────────────────────────────────────────────────────────────────────

@academics_bp.route('/terms')
@login_required
def terms():
    school_id = get_school_id()
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT t.*, ay.name as year_label
            FROM terms t
            LEFT JOIN academic_years ay ON ay.id = t.academic_year_id
            WHERE t.school_id = :sid
            ORDER BY ay.name DESC, t.term_number ASC
        """), {'sid': school_id}).fetchall()

        years = db.execute(text(
            "SELECT * FROM academic_years WHERE school_id=:sid ORDER BY name DESC"
        ), {'sid': school_id}).fetchall()

        return render_template('academics/terms.html', terms=rows, years=years)
    finally:
        db.close()


@academics_bp.route('/terms/add', methods=['GET', 'POST'])
@login_required
def add_term():
    if session.get('role') not in ('admin', 'master'):
        flash('Access denied.', 'danger')
        return redirect(url_for('academics.terms'))

    school_id = get_school_id()
    db = SessionLocal()
    try:
        years = db.execute(text(
            "SELECT * FROM academic_years WHERE school_id=:sid ORDER BY name DESC"
        ), {'sid': school_id}).fetchall()

        if request.method == 'POST':
            # Create academic year if needed
            year_name = request.form.get('year_label', '').strip()
            ay = db.execute(text(
                "SELECT id FROM academic_years WHERE school_id=:sid AND name=:y"
            ), {'sid': school_id, 'y': year_name}).fetchone()
            if not ay:
                db.execute(text(
                    "INSERT INTO academic_years (school_id, name) VALUES (:sid, :y)"
                ), {'sid': school_id, 'y': year_name})
                db.commit()
                ay = db.execute(text(
                    "SELECT id FROM academic_years WHERE school_id=:sid AND name=:y"
                ), {'sid': school_id, 'y': year_name}).fetchone()

            # Deactivate all if setting active
            is_active = bool(request.form.get('is_active'))
            if is_active:
                db.execute(text(
                    "UPDATE terms SET is_active=false WHERE school_id=:sid"
                ), {'sid': school_id})

            db.execute(text("""
                INSERT INTO terms (school_id, academic_year_id, name, term_number,
                    start_date, end_date, next_term_begins, is_active)
                VALUES (:sid, :ayid, :name, :tn, :sd, :ed, :ntb, :ia)
            """), {
                'sid': school_id, 'ayid': ay.id,
                'name': request.form.get('name', '').strip(),
                'tn': int(request.form.get('term_number', 1)),
                'sd': request.form.get('start_date', ''),
                'ed': request.form.get('end_date', ''),
                'ntb': request.form.get('next_term_begins', ''),
                'ia': is_active,
            })
            db.commit()
            flash('Term created successfully.', 'success')
            return redirect(url_for('academics.terms'))

        current_year = datetime.now().year
        return render_template('academics/term_form.html', term=None, years=years,
                               current_year=current_year, editing=False)
    finally:
        db.close()


@academics_bp.route('/terms/<int:term_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_term(term_id):
    if session.get('role') not in ('admin', 'master'):
        flash('Access denied.', 'danger')
        return redirect(url_for('academics.terms'))
    school_id = get_school_id()
    db = SessionLocal()
    try:
        term = db.execute(text(
            "SELECT t.*, ay.name as year_label FROM terms t LEFT JOIN academic_years ay ON ay.id=t.academic_year_id WHERE t.id=:tid AND t.school_id=:sid"
        ), {'tid': term_id, 'sid': school_id}).fetchone()
        if not term:
            flash('Term not found.', 'danger')
            return redirect(url_for('academics.terms'))

        years = db.execute(text(
            "SELECT * FROM academic_years WHERE school_id=:sid ORDER BY name DESC"
        ), {'sid': school_id}).fetchall()

        if request.method == 'POST':
            is_active = bool(request.form.get('is_active'))
            if is_active:
                db.execute(text("UPDATE terms SET is_active=false WHERE school_id=:sid"), {'sid': school_id})
            db.execute(text("""
                UPDATE terms SET name=:name, term_number=:tn, start_date=:sd,
                    end_date=:ed, next_term_begins=:ntb, is_active=:ia
                WHERE id=:tid AND school_id=:sid
            """), {
                'name': request.form.get('name', '').strip(),
                'tn': int(request.form.get('term_number', 1)),
                'sd': request.form.get('start_date', ''),
                'ed': request.form.get('end_date', ''),
                'ntb': request.form.get('next_term_begins', ''),
                'ia': is_active,
                'tid': term_id, 'sid': school_id,
            })
            db.commit()
            flash('Term updated.', 'success')
            return redirect(url_for('academics.terms'))

        current_year = datetime.now().year
        return render_template('academics/term_form.html', term=term, years=years,
                               current_year=current_year, editing=True)
    finally:
        db.close()


@academics_bp.route('/terms/<int:term_id>/delete', methods=['POST'])
@login_required
def delete_term(term_id):
    school_id = get_school_id()
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM terms WHERE id=:tid AND school_id=:sid"), {'tid': term_id, 'sid': school_id})
        db.commit()
        flash('Term deleted.', 'success')
    finally:
        db.close()
    return redirect(url_for('academics.terms'))


@academics_bp.route('/terms/<int:term_id>/activate', methods=['POST'])
@login_required
def activate_term(term_id):
    school_id = get_school_id()
    db = SessionLocal()
    try:
        db.execute(text("UPDATE terms SET is_active=false WHERE school_id=:sid"), {'sid': school_id})
        db.execute(text("UPDATE terms SET is_active=true WHERE id=:tid AND school_id=:sid"), {'tid': term_id, 'sid': school_id})
        db.commit()
        flash('Term activated.', 'success')
    finally:
        db.close()
    return redirect(url_for('academics.terms'))


# ── SUBJECTS ─────────────────────────────────────────────────────────────────

@academics_bp.route('/subjects')
@login_required
def subjects():
    school_id = get_school_id()
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT * FROM subjects WHERE school_id=:sid ORDER BY name"
        ), {'sid': school_id}).fetchall()
        return render_template('academics/subjects.html', subjects=rows)
    finally:
        db.close()


@academics_bp.route('/subjects/add', methods=['POST'])
@login_required
def add_subject():
    school_id = get_school_id()
    db = SessionLocal()
    try:
        db.execute(text("""
            INSERT INTO subjects (school_id, name, code, level, is_active)
            VALUES (:sid, :name, :code, :level, true)
        """), {
            'sid': school_id,
            'name': request.form.get('name', '').strip(),
            'code': request.form.get('code', '').strip(),
            'level': request.form.get('level', '').strip(),
        })
        db.commit()
        flash('Subject added.', 'success')
    finally:
        db.close()
    return redirect(url_for('academics.subjects'))


@academics_bp.route('/subjects/<int:sub_id>/delete', methods=['POST'])
@login_required
def delete_subject(sub_id):
    school_id = get_school_id()
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM subjects WHERE id=:sid AND school_id=:schid"),
                   {'sid': sub_id, 'schid': school_id})
        db.commit()
        flash('Subject deleted.', 'success')
    finally:
        db.close()
    return redirect(url_for('academics.subjects'))


# ── MARKS ────────────────────────────────────────────────────────────────────

@academics_bp.route('/marks')
@login_required
def marks():
    school_id = get_school_id()
    role = session.get('role')
    db = SessionLocal()
    try:
        active_term = db.execute(text(
            "SELECT * FROM terms WHERE school_id=:sid AND is_active=true LIMIT 1"
        ), {'sid': school_id}).fetchone()

        all_terms = db.execute(text(
            "SELECT * FROM terms WHERE school_id=:sid ORDER BY id DESC"
        ), {'sid': school_id}).fetchall()

        term_id = int(request.args.get('term_id', active_term.id if active_term else 0) or 0)
        class_name = request.args.get('class_name', '')
        subject = request.args.get('subject', '')

        classes = db.execute(text(
            "SELECT DISTINCT class_name FROM students WHERE school_id=:sid AND enrolment_status='active' ORDER BY class_name"
        ), {'sid': school_id}).fetchall()

        # Teacher sees only their subjects
        if role == 'teacher':
            staff_row = db.execute(text(
                "SELECT subjects_taught FROM staff WHERE user_id=:uid AND school_id=:sid"
            ), {'uid': session.get('user_id'), 'sid': school_id}).fetchone()
            teacher_subjects = [s.strip() for s in (staff_row.subjects_taught or '').split(',') if s.strip()] if staff_row else []
        else:
            teacher_subjects = None

        students = []
        existing_marks = {}
        all_subjects = []

        if term_id and class_name:
            students = db.execute(text(
                "SELECT id, name, admission_number FROM students WHERE school_id=:sid AND class_name=:cn AND enrolment_status='active' ORDER BY name"
            ), {'sid': school_id, 'cn': class_name}).fetchall()

            all_marks = db.execute(text(
                "SELECT * FROM marks WHERE school_id=:sid AND term_id=:tid AND student_id IN (SELECT id FROM students WHERE class_name=:cn AND school_id=:sid)"
            ), {'sid': school_id, 'tid': term_id, 'cn': class_name}).fetchall()

            for m in all_marks:
                existing_marks[(m.student_id, m.subject)] = m
                if m.subject not in all_subjects:
                    all_subjects.append(m.subject)

            # Also add teacher's own subjects not yet in marks
            if teacher_subjects:
                for ts in teacher_subjects:
                    if ts not in all_subjects:
                        all_subjects.append(ts)
            else:
                # Admin: pull from subjects table + existing marks
                sub_rows = db.execute(text(
                    "SELECT name FROM subjects WHERE school_id=:sid AND is_active=true ORDER BY name"
                ), {'sid': school_id}).fetchall()
                for sr in sub_rows:
                    if sr.name not in all_subjects:
                        all_subjects.append(sr.name)

        return render_template('academics/marks.html',
            all_terms=all_terms, active_term=active_term, selected_term_id=term_id,
            classes=classes, class_name=class_name, subject=subject,
            students=students, existing_marks=existing_marks,
            all_subjects=all_subjects, teacher_subjects=teacher_subjects,
            role=role)
    finally:
        db.close()


@academics_bp.route('/marks/save', methods=['POST'])
@login_required
def save_marks():
    school_id = get_school_id()
    term_id = int(request.form.get('term_id', 0))
    class_name = request.form.get('class_name', '')
    subject = request.form.get('subject', '')
    db = SessionLocal()
    try:
        student_ids = request.form.getlist('student_ids')
        for sid in student_ids:
            sid = int(sid)
            cw = float(request.form.get(f'cw_{sid}', 0) or 0)
            mt = float(request.form.get(f'mt_{sid}', 0) or 0)
            et = float(request.form.get(f'et_{sid}', 0) or 0)
            cw_total = float(request.form.get(f'cw_total_{sid}', 20) or 20)
            mt_total = float(request.form.get(f'mt_total_{sid}', 20) or 20)
            et_total = float(request.form.get(f'et_total_{sid}', 60) or 60)

            cw20 = round((cw / cw_total * 20), 2) if cw_total else 0
            mt20 = round((mt / mt_total * 20), 2) if mt_total else 0
            et60 = round((et / et_total * 60), 2) if et_total else 0
            total = round(cw20 + mt20 + et60, 2)

            def grade(t):
                if t >= 80: return 'A'
                if t >= 70: return 'B'
                if t >= 60: return 'C'
                if t >= 50: return 'D'
                if t >= 40: return 'E'
                return 'F'

            existing = db.execute(text(
                "SELECT id FROM marks WHERE school_id=:schid AND student_id=:stid AND term_id=:tid AND subject=:sub"
            ), {'schid': school_id, 'stid': sid, 'tid': term_id, 'sub': subject}).fetchone()

            if existing:
                db.execute(text("""
                    UPDATE marks SET coursework_score=:cw, coursework_total=:cwt,
                        coursework_out_of_20=:cw20, midterm_score=:mt, midterm_total=:mtt,
                        midterm_out_of_20=:mt20, endterm_score=:et, endterm_total=:ett,
                        endterm_out_of_60=:et60, total_mark=:tot, grade=:gr
                    WHERE id=:mid
                """), {'cw': cw, 'cwt': cw_total, 'cw20': cw20, 'mt': mt, 'mtt': mt_total,
                       'mt20': mt20, 'et': et, 'ett': et_total, 'et60': et60,
                       'tot': total, 'gr': grade(total), 'mid': existing.id})
            else:
                db.execute(text("""
                    INSERT INTO marks (school_id, student_id, term_id, subject,
                        coursework_score, coursework_total, coursework_out_of_20,
                        midterm_score, midterm_total, midterm_out_of_20,
                        endterm_score, endterm_total, endterm_out_of_60,
                        total_mark, grade)
                    VALUES (:schid, :stid, :tid, :sub, :cw, :cwt, :cw20, :mt, :mtt,
                        :mt20, :et, :ett, :et60, :tot, :gr)
                """), {'schid': school_id, 'stid': sid, 'tid': term_id, 'sub': subject,
                       'cw': cw, 'cwt': cw_total, 'cw20': cw20, 'mt': mt, 'mtt': mt_total,
                       'mt20': mt20, 'et': et, 'ett': et_total, 'et60': et60,
                       'tot': total, 'gr': grade(total)})

        db.commit()
        flash(f'Marks saved for {subject}.', 'success')
    finally:
        db.close()
    return redirect(url_for('academics.marks', term_id=term_id, class_name=class_name, subject=subject))


# ── ATTENDANCE ────────────────────────────────────────────────────────────────

@academics_bp.route('/attendance')
@login_required
def attendance():
    school_id = get_school_id()
    db = SessionLocal()
    try:
        active_term = db.execute(text(
            "SELECT * FROM terms WHERE school_id=:sid AND is_active=true LIMIT 1"
        ), {'sid': school_id}).fetchone()
        all_terms = db.execute(text(
            "SELECT * FROM terms WHERE school_id=:sid ORDER BY id DESC"
        ), {'sid': school_id}).fetchall()

        term_id = int(request.args.get('term_id', active_term.id if active_term else 0) or 0)
        class_name = request.args.get('class_name', '')
        att_date = request.args.get('date', date.today().isoformat())

        classes = db.execute(text(
            "SELECT DISTINCT class_name FROM students WHERE school_id=:sid AND enrolment_status='active' ORDER BY class_name"
        ), {'sid': school_id}).fetchall()

        students = []
        attendance_map = {}

        if class_name and term_id:
            students = db.execute(text(
                "SELECT id, name, admission_number FROM students WHERE school_id=:sid AND class_name=:cn AND enrolment_status='active' ORDER BY name"
            ), {'sid': school_id, 'cn': class_name}).fetchall()

            att_rows = db.execute(text(
                "SELECT * FROM attendance WHERE school_id=:sid AND term_id=:tid AND date=:dt AND student_id IN (SELECT id FROM students WHERE class_name=:cn AND school_id=:sid)"
            ), {'sid': school_id, 'tid': term_id, 'dt': att_date, 'cn': class_name}).fetchall()

            for a in att_rows:
                attendance_map[a.student_id] = a

        # Attendance summary per student
        summary = {}
        if class_name and term_id:
            summary_rows = db.execute(text("""
                SELECT student_id,
                    SUM(CASE WHEN status='present' THEN 1 ELSE 0 END) AS present_days,
                    SUM(CASE WHEN status='absent' THEN 1 ELSE 0 END) AS absent_days,
                    COUNT(*) AS total_days
                FROM attendance
                WHERE school_id=:sid AND term_id=:tid
                    AND student_id IN (SELECT id FROM students WHERE class_name=:cn AND school_id=:sid)
                GROUP BY student_id
            """), {'sid': school_id, 'tid': term_id, 'cn': class_name}).fetchall()
            for r in summary_rows:
                summary[r.student_id] = r

        return render_template('academics/attendance.html',
            all_terms=all_terms, active_term=active_term,
            selected_term_id=term_id, classes=classes,
            class_name=class_name, att_date=att_date,
            students=students, attendance_map=attendance_map, summary=summary)
    finally:
        db.close()


@academics_bp.route('/attendance/save', methods=['POST'])
@login_required
def save_attendance():
    school_id = get_school_id()
    term_id = int(request.form.get('term_id', 0))
    class_name = request.form.get('class_name', '')
    att_date = request.form.get('date', '')
    db = SessionLocal()
    try:
        student_ids = request.form.getlist('student_ids')
        for sid in student_ids:
            sid = int(sid)
            status = request.form.get(f'status_{sid}', 'present')
            notes = request.form.get(f'notes_{sid}', '')
            existing = db.execute(text(
                "SELECT id FROM attendance WHERE school_id=:schid AND student_id=:stid AND term_id=:tid AND date=:dt"
            ), {'schid': school_id, 'stid': sid, 'tid': term_id, 'dt': att_date}).fetchone()
            if existing:
                db.execute(text(
                    "UPDATE attendance SET status=:s, notes=:n, recorded_by=:rb WHERE id=:id"
                ), {'s': status, 'n': notes, 'rb': session.get('user_id'), 'id': existing.id})
            else:
                db.execute(text("""
                    INSERT INTO attendance (school_id, student_id, term_id, date, status, notes, recorded_by)
                    VALUES (:schid, :stid, :tid, :dt, :s, :n, :rb)
                """), {'schid': school_id, 'stid': sid, 'tid': term_id,
                       'dt': att_date, 's': status, 'n': notes, 'rb': session.get('user_id')})
        db.commit()
        flash('Attendance saved.', 'success')
    finally:
        db.close()
    return redirect(url_for('academics.attendance', term_id=term_id, class_name=class_name, date=att_date))


# ── BEHAVIOUR ─────────────────────────────────────────────────────────────────

@academics_bp.route('/behaviour')
@login_required
def behaviour():
    school_id = get_school_id()
    db = SessionLocal()
    try:
        active_term = db.execute(text(
            "SELECT * FROM terms WHERE school_id=:sid AND is_active=true LIMIT 1"
        ), {'sid': school_id}).fetchone()
        all_terms = db.execute(text(
            "SELECT * FROM terms WHERE school_id=:sid ORDER BY id DESC"
        ), {'sid': school_id}).fetchall()

        term_id = int(request.args.get('term_id', active_term.id if active_term else 0) or 0)
        class_name = request.args.get('class_name', '')

        classes = db.execute(text(
            "SELECT DISTINCT class_name FROM students WHERE school_id=:sid AND enrolment_status='active' ORDER BY class_name"
        ), {'sid': school_id}).fetchall()

        components = db.execute(text(
            "SELECT * FROM behavior_components WHERE school_id=:sid ORDER BY name"
        ), {'sid': school_id}).fetchall()

        students = []
        behaviour_map = {}

        if class_name and term_id:
            students = db.execute(text(
                "SELECT id, name, admission_number FROM students WHERE school_id=:sid AND class_name=:cn AND enrolment_status='active' ORDER BY name"
            ), {'sid': school_id, 'cn': class_name}).fetchall()

            b_rows = db.execute(text(
                "SELECT * FROM behavior_records WHERE school_id=:sid AND term_id=:tid AND student_id IN (SELECT id FROM students WHERE class_name=:cn AND school_id=:sid)"
            ), {'sid': school_id, 'tid': term_id, 'cn': class_name}).fetchall()
            for b in b_rows:
                behaviour_map[(b.student_id, b.component_id)] = b.value

        return render_template('academics/behaviour.html',
            all_terms=all_terms, active_term=active_term,
            selected_term_id=term_id, classes=classes, class_name=class_name,
            components=components, students=students, behaviour_map=behaviour_map)
    finally:
        db.close()


@academics_bp.route('/behaviour/save', methods=['POST'])
@login_required
def save_behaviour():
    school_id = get_school_id()
    term_id = int(request.form.get('term_id', 0))
    class_name = request.form.get('class_name', '')
    db = SessionLocal()
    try:
        student_ids = request.form.getlist('student_ids')
        component_ids = request.form.getlist('component_ids')
        for sid in student_ids:
            sid = int(sid)
            for cid in component_ids:
                cid = int(cid)
                val = request.form.get(f'beh_{sid}_{cid}', '')
                if not val:
                    continue
                existing = db.execute(text(
                    "SELECT id FROM behavior_records WHERE school_id=:schid AND student_id=:stid AND term_id=:tid AND component_id=:cid"
                ), {'schid': school_id, 'stid': sid, 'tid': term_id, 'cid': cid}).fetchone()
                if existing:
                    db.execute(text(
                        "UPDATE behavior_records SET value=:v, evaluated_by=:rb WHERE id=:id"
                    ), {'v': val, 'rb': session.get('user_id'), 'id': existing.id})
                else:
                    db.execute(text("""
                        INSERT INTO behavior_records (school_id, student_id, term_id, component_id, value, evaluated_by)
                        VALUES (:schid, :stid, :tid, :cid, :v, :rb)
                    """), {'schid': school_id, 'stid': sid, 'tid': term_id,
                           'cid': cid, 'v': val, 'rb': session.get('user_id')})
        db.commit()
        flash('Behaviour records saved.', 'success')
    finally:
        db.close()
    return redirect(url_for('academics.behaviour', term_id=term_id, class_name=class_name))


# ── TIMETABLE ─────────────────────────────────────────────────────────────────

@academics_bp.route('/timetable')
@login_required
def timetable():
    school_id = get_school_id()
    db = SessionLocal()
    try:
        active_term = db.execute(text(
            "SELECT * FROM terms WHERE school_id=:sid AND is_active=true LIMIT 1"
        ), {'sid': school_id}).fetchone()
        all_terms = db.execute(text(
            "SELECT * FROM terms WHERE school_id=:sid ORDER BY id DESC"
        ), {'sid': school_id}).fetchall()
        term_id = int(request.args.get('term_id', active_term.id if active_term else 0) or 0)

        classes = db.execute(text(
            "SELECT * FROM classes WHERE school_id=:sid ORDER BY name"
        ), {'sid': school_id}).fetchall()
        class_id = int(request.args.get('class_id', classes[0].id if classes else 0) or 0)

        subjects = db.execute(text(
            "SELECT * FROM subjects WHERE school_id=:sid AND is_active=true ORDER BY name"
        ), {'sid': school_id}).fetchall()
        staff_list = db.execute(text(
            "SELECT s.id, u.first_name, u.last_name FROM staff s JOIN users u ON u.id=s.user_id WHERE s.school_id=:sid ORDER BY u.last_name"
        ), {'sid': school_id}).fetchall()

        entries = []
        if term_id and class_id:
            entries = db.execute(text("""
                SELECT t.*, s.name AS subject_name, u.first_name || ' ' || u.last_name AS teacher_name
                FROM timetable t
                LEFT JOIN subjects s ON s.id=t.subject_id
                LEFT JOIN staff sf ON sf.id=t.staff_id
                LEFT JOIN users u ON u.id=sf.user_id
                WHERE t.school_id=:sid AND t.term_id=:tid AND t.class_id=:cid
                ORDER BY CASE t.day_of_week WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 WHEN 'Wednesday' THEN 3 WHEN 'Thursday' THEN 4 ELSE 5 END, t.start_time
            """), {'sid': school_id, 'tid': term_id, 'cid': class_id}).fetchall()

        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        timetable_grid = {day: [] for day in days}
        for e in entries:
            timetable_grid[e.day_of_week].append(e)

        return render_template('academics/timetable.html',
            all_terms=all_terms, active_term=active_term, selected_term_id=term_id,
            classes=classes, class_id=class_id, subjects=subjects, staff_list=staff_list,
            timetable_grid=timetable_grid, days=days, entries=entries)
    finally:
        db.close()


@academics_bp.route('/timetable/add', methods=['POST'])
@login_required
def add_timetable_entry():
    school_id = get_school_id()
    db = SessionLocal()
    try:
        db.execute(text("""
            INSERT INTO timetable (school_id, class_id, term_id, subject_id, staff_id, day_of_week, start_time, end_time, room)
            VALUES (:sid, :cid, :tid, :subid, :stfid, :day, :st, :et, :room)
        """), {
            'sid': school_id,
            'cid': int(request.form.get('class_id', 0)),
            'tid': int(request.form.get('term_id', 0)),
            'subid': int(request.form.get('subject_id', 0)) or None,
            'stfid': int(request.form.get('staff_id', 0)) or None,
            'day': request.form.get('day_of_week', ''),
            'st': request.form.get('start_time', ''),
            'et': request.form.get('end_time', ''),
            'room': request.form.get('room', ''),
        })
        db.commit()
        flash('Timetable entry added.', 'success')
    finally:
        db.close()
    return redirect(url_for('academics.timetable',
        term_id=request.form.get('term_id'), class_id=request.form.get('class_id')))


@academics_bp.route('/timetable/<int:entry_id>/delete', methods=['POST'])
@login_required
def delete_timetable_entry(entry_id):
    school_id = get_school_id()
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM timetable WHERE id=:id AND school_id=:sid"),
                   {'id': entry_id, 'sid': school_id})
        db.commit()
        flash('Entry removed.', 'success')
    finally:
        db.close()
    return redirect(request.referrer or url_for('academics.timetable'))


# ── REPORTS ───────────────────────────────────────────────────────────────────

@academics_bp.route('/reports')
@login_required
def reports():
    school_id = get_school_id()
    db = SessionLocal()
    try:
        active_term = db.execute(text(
            "SELECT * FROM terms WHERE school_id=:sid AND is_active=true LIMIT 1"
        ), {'sid': school_id}).fetchone()
        all_terms = db.execute(text(
            "SELECT * FROM terms WHERE school_id=:sid ORDER BY id DESC"
        ), {'sid': school_id}).fetchall()
        term_id = int(request.args.get('term_id', active_term.id if active_term else 0) or 0)
        class_name = request.args.get('class_name', '')

        classes = db.execute(text(
            "SELECT DISTINCT class_name FROM students WHERE school_id=:sid AND enrolment_status='active' ORDER BY class_name"
        ), {'sid': school_id}).fetchall()

        students = []
        if class_name and term_id:
            students = db.execute(text(
                "SELECT s.*, (SELECT COUNT(*) FROM marks m WHERE m.student_id=s.id AND m.term_id=:tid) AS subject_count FROM students s WHERE s.school_id=:sid AND s.class_name=:cn AND s.enrolment_status='active' ORDER BY s.name"
            ), {'sid': school_id, 'tid': term_id, 'cn': class_name}).fetchall()

        return render_template('academics/reports.html',
            all_terms=all_terms, active_term=active_term,
            selected_term_id=term_id, classes=classes,
            class_name=class_name, students=students)
    finally:
        db.close()


# ── PARENT & STUDENT VIEWS ────────────────────────────────────────────────────

@academics_bp.route('/parent_results')
@login_required
def parent_results():
    if session.get('role') != 'parent':
        return redirect(url_for('dashboard'))
    school_id = get_school_id()
    db = SessionLocal()
    try:
        children = db.execute(text("""
            SELECT s.* FROM students s
            JOIN student_guardians sg ON sg.student_id=s.id
            JOIN guardians g ON g.id=sg.guardian_id
            WHERE g.user_id=:uid AND s.school_id=:sid
        """), {'uid': session.get('user_id'), 'sid': school_id}).fetchall()

        student_id = int(request.args.get('student_id', children[0].id if children else 0) or 0)
        all_terms = db.execute(text(
            "SELECT * FROM terms WHERE school_id=:sid ORDER BY id DESC"
        ), {'sid': school_id}).fetchall()
        term_id = int(request.args.get('term_id', all_terms[0].id if all_terms else 0) or 0)

        marks = []
        if student_id and term_id:
            marks = db.execute(text(
                "SELECT * FROM marks WHERE student_id=:stid AND term_id=:tid ORDER BY subject"
            ), {'stid': student_id, 'tid': term_id}).fetchall()

        return render_template('academics/parent_results.html',
            children=children, student_id=student_id,
            all_terms=all_terms, term_id=term_id, marks=marks)
    finally:
        db.close()


@academics_bp.route('/student_results')
@login_required
def student_results():
    if session.get('role') != 'student':
        return redirect(url_for('dashboard'))
    school_id = get_school_id()
    db = SessionLocal()
    try:
        student = db.execute(text(
            "SELECT * FROM students WHERE user_id=:uid AND school_id=:sid LIMIT 1"
        ), {'uid': session.get('user_id'), 'sid': school_id}).fetchone()

        all_terms = db.execute(text(
            "SELECT * FROM terms WHERE school_id=:sid ORDER BY id DESC"
        ), {'sid': school_id}).fetchall()
        term_id = int(request.args.get('term_id', all_terms[0].id if all_terms else 0) or 0)

        marks = []
        if student and term_id:
            marks = db.execute(text(
                "SELECT * FROM marks WHERE student_id=:stid AND term_id=:tid ORDER BY subject"
            ), {'stid': student.id, 'tid': term_id}).fetchall()

        return render_template('academics/student_results.html',
            student=student, all_terms=all_terms, term_id=term_id, marks=marks)
    finally:
        db.close()


@academics_bp.route('/student_timetable')
@login_required
def student_timetable():
    if session.get('role') != 'student':
        return redirect(url_for('dashboard'))
    school_id = get_school_id()
    db = SessionLocal()
    try:
        student = db.execute(text(
            "SELECT * FROM students WHERE user_id=:uid AND school_id=:sid LIMIT 1"
        ), {'uid': session.get('user_id'), 'sid': school_id}).fetchone()

        active_term = db.execute(text(
            "SELECT * FROM terms WHERE school_id=:sid AND is_active=true LIMIT 1"
        ), {'sid': school_id}).fetchone()

        entries = []
        timetable_grid = {}
        if student and active_term:
            cls = db.execute(text(
                "SELECT id FROM classes WHERE school_id=:sid AND name=:cn LIMIT 1"
            ), {'sid': school_id, 'cn': student.class_name}).fetchone()
            if cls:
                entries = db.execute(text("""
                    SELECT t.*, s.name AS subject_name, u.first_name || ' ' || u.last_name AS teacher_name
                    FROM timetable t
                    LEFT JOIN subjects s ON s.id=t.subject_id
                    LEFT JOIN staff sf ON sf.id=t.staff_id
                    LEFT JOIN users u ON u.id=sf.user_id
                    WHERE t.school_id=:sid AND t.term_id=:tid AND t.class_id=:cid
                    ORDER BY CASE t.day_of_week WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 WHEN 'Wednesday' THEN 3 WHEN 'Thursday' THEN 4 ELSE 5 END, t.start_time
                """), {'sid': school_id, 'tid': active_term.id, 'cid': cls.id}).fetchall()

        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        timetable_grid = {day: [] for day in days}
        for e in entries:
            timetable_grid[e.day_of_week].append(e)

        return render_template('academics/student_timetable.html',
            student=student, active_term=active_term,
            timetable_grid=timetable_grid, days=days)
    finally:
        db.close()


@academics_bp.route('/reports/<int:student_id>/pdf')
@login_required
def generate_report_pdf(student_id):
    school_id = get_school_id()
    term_id = int(request.args.get('term_id', 0))
    db = SessionLocal()
    try:
        student = db.execute(text(
            "SELECT * FROM students WHERE id=:id AND school_id=:sid"
        ), {'id': student_id, 'sid': school_id}).fetchone()

        if not student:
            flash('Student not found.', 'danger')
            return redirect(url_for('academics.reports'))

        marks = db.execute(text(
            "SELECT * FROM marks WHERE student_id=:stid AND term_id=:tid ORDER BY subject"
        ), {'stid': student_id, 'tid': term_id}).fetchall()

        term = db.execute(text(
            "SELECT t.*, ay.name as year_label FROM terms t LEFT JOIN academic_years ay ON ay.id=t.academic_year_id WHERE t.id=:tid"
        ), {'tid': term_id}).fetchone()

        school = db.execute(text("SELECT * FROM schools WHERE id=:sid"), {'sid': school_id}).fetchone()
        behaviour = db.execute(text("""
            SELECT bc.name, br.value FROM behavior_records br
            JOIN behavior_components bc ON bc.id=br.component_id
            WHERE br.student_id=:stid AND br.term_id=:tid ORDER BY bc.name
        """), {'stid': student_id, 'tid': term_id}).fetchall()

        return render_template('academics/report_card.html',
            student=student, marks=marks, term=term,
            school=school, behaviour=behaviour)
    finally:
        db.close()


@academics_bp.route('/reports/generate_all', methods=['POST'])
@login_required
def generate_all_reports():
    term_id = request.form.get('term_id')
    class_name = request.form.get('class_name')
    flash('Bulk PDF generation — open individual reports using the "View Report" button per student.', 'info')
    return redirect(url_for('academics.reports', term_id=term_id, class_name=class_name))
