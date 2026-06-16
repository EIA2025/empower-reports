from flask import Blueprint, render_template, redirect, url_for, session, request, flash, jsonify
from datetime import datetime
from db import SessionLocal
from sqlalchemy import text
import os

materials_bp = Blueprint('materials', __name__, template_folder='templates')

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


@materials_bp.route('/')
@login_required
def index():
    return redirect(url_for('materials.learning_materials'))


@materials_bp.route('/materials')
@login_required
def learning_materials():
    """List learning materials"""
    school_id = get_school_id()
    search = request.args.get('q', '')
    file_type = request.args.get('type', '')
    db = SessionLocal()
    try:
        query = """
            SELECT lm.id, lm.title, lm.description, lm.file_type, 
                   s.name as subject, c.name as class_name, st.name as teacher,
                   lm.download_count, lm.file_size, lm.created_at
            FROM learning_materials lm
            LEFT JOIN subjects s ON lm.subject_id = s.id
            LEFT JOIN classes c ON lm.class_id = c.id
            LEFT JOIN staff st ON lm.teacher_id = st.id
            WHERE lm.school_id = :sid AND lm.is_active = true
        """
        params = {'sid': school_id}
        
        if search:
            query += " AND (lm.title ILIKE :q OR lm.description ILIKE :q)"
            params['q'] = f'%{search}%'
        
        if file_type:
            query += " AND lm.file_type = :ftype"
            params['ftype'] = file_type
        
        query += " ORDER BY lm.created_at DESC LIMIT 500"
        materials_data = db.execute(text(query), params).fetchall()
        
        return render_template('materials/learning_materials.html', 
                             materials=materials_data, search=search, file_type=file_type)
    finally:
        db.close()


@materials_bp.route('/material/add', methods=['GET', 'POST'])
@login_required
def add_material():
    """Add learning material"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            db.execute(text("""
                INSERT INTO learning_materials 
                (school_id, title, description, subject_id, class_id, teacher_id, 
                 file_path, file_name, file_size, file_type, is_active, created_at)
                VALUES (:sid, :title, :desc, :subj, :cls, :teacher, :path, :fname, :size, :ftype, true, :now)
            """), {
                'sid': school_id,
                'title': request.form.get('title'),
                'desc': request.form.get('description'),
                'subj': request.form.get('subject_id'),
                'cls': request.form.get('class_id'),
                'teacher': session.get('user_id'),
                'path': request.form.get('file_path'),
                'fname': request.form.get('file_name'),
                'size': request.form.get('file_size', 0),
                'ftype': request.form.get('file_type'),
                'now': datetime.now()
            })
            db.commit()
            flash('Learning material added successfully', 'success')
            return redirect(url_for('materials.learning_materials'))
        
        subjects = db.execute(text(
            "SELECT id, name FROM subjects WHERE school_id = :sid ORDER BY name"
        ), {'sid': school_id}).fetchall()
        
        classes = db.execute(text(
            "SELECT id, name FROM classes WHERE school_id = :sid ORDER BY name"
        ), {'sid': school_id}).fetchall()
        
        return render_template('materials/add_material.html', subjects=subjects, classes=classes)
    finally:
        db.close()


@materials_bp.route('/assignments')
@login_required
def assignments():
    """List assignments"""
    school_id = get_school_id()
    search = request.args.get('q', '')
    status = request.args.get('status', '')
    db = SessionLocal()
    try:
        query = """
            SELECT a.id, a.title, a.due_date, s.name as subject, c.name as class_name,
                   st.name as teacher, a.max_score, a.status, a.created_at,
                   COUNT(DISTINCT asub.id) as submissions
            FROM assignments a
            LEFT JOIN subjects s ON a.subject_id = s.id
            LEFT JOIN classes c ON a.class_id = c.id
            LEFT JOIN staff st ON a.teacher_id = st.id
            LEFT JOIN assignment_submissions asub ON a.id = asub.assignment_id
            WHERE a.school_id = :sid
        """
        params = {'sid': school_id}
        
        if search:
            query += " AND a.title ILIKE :q"
            params['q'] = f'%{search}%'
        
        if status:
            query += " AND a.status = :status"
            params['status'] = status
        
        query += " GROUP BY a.id, a.title, a.due_date, s.name, c.name, st.name, a.max_score, a.status, a.created_at"
        query += " ORDER BY a.due_date DESC LIMIT 500"
        assignments_data = db.execute(text(query), params).fetchall()
        
        return render_template('materials/assignments.html', 
                             assignments=assignments_data, search=search, status=status)
    finally:
        db.close()


@materials_bp.route('/assignment/add', methods=['GET', 'POST'])
@login_required
def add_assignment():
    """Add assignment"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            db.execute(text("""
                INSERT INTO assignments 
                (school_id, title, instructions, subject_id, class_id, teacher_id, 
                 due_date, max_score, attachment_path, file_name, file_size, status, created_at)
                VALUES (:sid, :title, :instr, :subj, :cls, :teacher, :due, :max_score, 
                        :path, :fname, :size, :status, :now)
            """), {
                'sid': school_id,
                'title': request.form.get('title'),
                'instr': request.form.get('instructions'),
                'subj': request.form.get('subject_id'),
                'cls': request.form.get('class_id'),
                'teacher': session.get('user_id'),
                'due': request.form.get('due_date'),
                'max_score': request.form.get('max_score', 100),
                'path': request.form.get('attachment_path'),
                'fname': request.form.get('file_name'),
                'size': request.form.get('file_size', 0),
                'status': 'active',
                'now': datetime.now()
            })
            db.commit()
            flash('Assignment added successfully', 'success')
            return redirect(url_for('materials.assignments'))
        
        subjects = db.execute(text(
            "SELECT id, name FROM subjects WHERE school_id = :sid ORDER BY name"
        ), {'sid': school_id}).fetchall()
        
        classes = db.execute(text(
            "SELECT id, name FROM classes WHERE school_id = :sid ORDER BY name"
        ), {'sid': school_id}).fetchall()
        
        return render_template('materials/add_assignment.html', subjects=subjects, classes=classes)
    finally:
        db.close()


@materials_bp.route('/assignment/<int:assignment_id>')
@login_required
def assignment_detail(assignment_id):
    """View assignment details and submissions"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        assignment = db.execute(text("""
            SELECT a.*, s.name as subject, c.name as class_name, st.name as teacher
            FROM assignments a
            LEFT JOIN subjects s ON a.subject_id = s.id
            LEFT JOIN classes c ON a.class_id = c.id
            LEFT JOIN staff st ON a.teacher_id = st.id
            WHERE a.id = :id AND a.school_id = :sid
        """), {'id': assignment_id, 'sid': school_id}).fetchone()
        
        if not assignment:
            flash('Assignment not found', 'danger')
            return redirect(url_for('materials.assignments'))
        
        submissions = db.execute(text("""
            SELECT asub.id, s.name, s.admission_number, asub.submitted_at, 
                   asub.status, asub.score, asub.teacher_comments
            FROM assignment_submissions asub
            LEFT JOIN students s ON asub.student_id = s.id
            WHERE asub.assignment_id = :aid
            ORDER BY asub.submitted_at DESC
        """), {'aid': assignment_id}).fetchall()
        
        return render_template('materials/assignment_detail.html', 
                             assignment=assignment, submissions=submissions)
    finally:
        db.close()


@materials_bp.route('/lesson-plan/add', methods=['GET', 'POST'])
@login_required
def add_lesson_plan():
    """Add lesson plan"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            db.execute(text("""
                INSERT INTO lesson_plans 
                (school_id, title, subject_id, class_id, teacher_id, lesson_date, 
                 duration_minutes, objectives, activities, resources, homework, status, created_at)
                VALUES (:sid, :title, :subj, :cls, :teacher, :date, :duration, 
                        :obj, :act, :res, :hw, :status, :now)
            """), {
                'sid': school_id,
                'title': request.form.get('title'),
                'subj': request.form.get('subject_id'),
                'cls': request.form.get('class_id'),
                'teacher': session.get('user_id'),
                'date': request.form.get('lesson_date'),
                'duration': request.form.get('duration_minutes', 60),
                'obj': request.form.get('objectives'),
                'act': request.form.get('activities'),
                'res': request.form.get('resources'),
                'hw': request.form.get('homework'),
                'status': 'draft',
                'now': datetime.now()
            })
            db.commit()
            flash('Lesson plan added successfully', 'success')
            return redirect(url_for('materials.lesson_plans'))
        
        subjects = db.execute(text(
            "SELECT id, name FROM subjects WHERE school_id = :sid ORDER BY name"
        ), {'sid': school_id}).fetchall()
        
        classes = db.execute(text(
            "SELECT id, name FROM classes WHERE school_id = :sid ORDER BY name"
        ), {'sid': school_id}).fetchall()
        
        return render_template('materials/add_lesson_plan.html', subjects=subjects, classes=classes)
    finally:
        db.close()


@materials_bp.route('/lesson-plans')
@login_required
def lesson_plans():
    """List lesson plans"""
    school_id = get_school_id()
    search = request.args.get('q', '')
    db = SessionLocal()
    try:
        query = """
            SELECT lp.id, lp.title, lp.lesson_date, lp.duration_minutes, 
                   s.name as subject, c.name as class_name, st.name as teacher, lp.status, lp.created_at
            FROM lesson_plans lp
            LEFT JOIN subjects s ON lp.subject_id = s.id
            LEFT JOIN classes c ON lp.class_id = c.id
            LEFT JOIN staff st ON lp.teacher_id = st.id
            WHERE lp.school_id = :sid
        """
        params = {'sid': school_id}
        
        if search:
            query += " AND lp.title ILIKE :q"
            params['q'] = f'%{search}%'
        
        query += " ORDER BY lp.lesson_date DESC LIMIT 500"
        plans_data = db.execute(text(query), params).fetchall()
        
        return render_template('materials/lesson_plans.html', lesson_plans=plans_data, search=search)
    finally:
        db.close()


@materials_bp.route('/scheme-of-work')
@login_required
def schemes():
    """List schemes of work"""
    school_id = get_school_id()
    search = request.args.get('q', '')
    db = SessionLocal()
    try:
        query = """
            SELECT sw.id, sw.topic, sw.subtopic, sw.week_number, sw.teaching_date,
                   s.name as subject, c.name as class_name, t.name as term, st.name as teacher, sw.status, sw.created_at
            FROM schemes_of_work sw
            LEFT JOIN subjects s ON sw.subject_id = s.id
            LEFT JOIN classes c ON sw.class_id = c.id
            LEFT JOIN terms t ON sw.term_id = t.id
            LEFT JOIN staff st ON sw.teacher_id = st.id
            WHERE sw.school_id = :sid
        """
        params = {'sid': school_id}
        
        if search:
            query += " AND (sw.topic ILIKE :q OR sw.subtopic ILIKE :q)"
            params['q'] = f'%{search}%'
        
        query += " ORDER BY sw.week_number, sw.teaching_date DESC LIMIT 500"
        schemes_data = db.execute(text(query), params).fetchall()
        
        return render_template('materials/schemes.html', schemes=schemes_data, search=search)
    finally:
        db.close()


@materials_bp.route('/scheme/add', methods=['GET', 'POST'])
@login_required
def add_scheme():
    """Add scheme of work"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            db.execute(text("""
                INSERT INTO schemes_of_work 
                (school_id, subject_id, class_id, teacher_id, term_id, topic, subtopic, 
                 week_number, teaching_date, status, created_at)
                VALUES (:sid, :subj, :cls, :teacher, :term, :topic, :subtopic, 
                        :week, :date, :status, :now)
            """), {
                'sid': school_id,
                'subj': request.form.get('subject_id'),
                'cls': request.form.get('class_id'),
                'teacher': session.get('user_id'),
                'term': request.form.get('term_id'),
                'topic': request.form.get('topic'),
                'subtopic': request.form.get('subtopic'),
                'week': request.form.get('week_number'),
                'date': request.form.get('teaching_date'),
                'status': 'pending',
                'now': datetime.now()
            })
            db.commit()
            flash('Scheme of work added successfully', 'success')
            return redirect(url_for('materials.schemes'))
        
        subjects = db.execute(text(
            "SELECT id, name FROM subjects WHERE school_id = :sid ORDER BY name"
        ), {'sid': school_id}).fetchall()
        
        classes = db.execute(text(
            "SELECT id, name FROM classes WHERE school_id = :sid ORDER BY name"
        ), {'sid': school_id}).fetchall()
        
        terms = db.execute(text(
            "SELECT id, name FROM terms WHERE school_id = :sid ORDER BY name DESC"
        ), {'sid': school_id}).fetchall()
        
        return render_template('materials/add_scheme.html', 
                             subjects=subjects, classes=classes, terms=terms)
    finally:
        db.close()


@materials_bp.route('/gradebook')
@login_required
def gradebook():
    """View gradebook entries"""
    school_id = get_school_id()
    search = request.args.get('q', '')
    db = SessionLocal()
    try:
        query = """
            SELECT ge.id, ge.student_id, s.name as student, ge.assessment_type, ge.title,
                   ge.score, ge.max_score, subj.name as subject, c.name as class_name,
                   st.name as teacher, ge.date_recorded, ge.comments
            FROM gradebook_entries ge
            LEFT JOIN students s ON ge.student_id = s.id
            LEFT JOIN subjects subj ON ge.subject_id = subj.id
            LEFT JOIN classes c ON ge.class_id = c.id
            LEFT JOIN staff st ON ge.teacher_id = st.id
            WHERE ge.school_id = :sid
        """
        params = {'sid': school_id}
        
        if search:
            query += " AND (s.name ILIKE :q OR ge.assessment_type ILIKE :q)"
            params['q'] = f'%{search}%'
        
        query += " ORDER BY ge.date_recorded DESC LIMIT 500"
        entries = db.execute(text(query), params).fetchall()
        
        return render_template('materials/gradebook.html', entries=entries, search=search)
    finally:
        db.close()


@materials_bp.route('/gradebook/add', methods=['GET', 'POST'])
@login_required
def add_gradebook_entry():
    """Add gradebook entry"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            db.execute(text("""
                INSERT INTO gradebook_entries 
                (school_id, student_id, subject_id, teacher_id, class_id, assessment_type, 
                 title, score, max_score, comments, date_recorded, created_at)
                VALUES (:sid, :stud, :subj, :teacher, :cls, :type, :title, :score, :max_score, 
                        :comments, :date, :now)
            """), {
                'sid': school_id,
                'stud': request.form.get('student_id'),
                'subj': request.form.get('subject_id'),
                'teacher': session.get('user_id'),
                'cls': request.form.get('class_id'),
                'type': request.form.get('assessment_type'),
                'title': request.form.get('title'),
                'score': request.form.get('score'),
                'max_score': request.form.get('max_score', 100),
                'comments': request.form.get('comments'),
                'date': request.form.get('date_recorded'),
                'now': datetime.now()
            })
            db.commit()
            flash('Gradebook entry added successfully', 'success')
            return redirect(url_for('materials.gradebook'))
        
        students = db.execute(text(
            "SELECT id, name FROM students WHERE school_id = :sid ORDER BY name LIMIT 500"
        ), {'sid': school_id}).fetchall()
        
        subjects = db.execute(text(
            "SELECT id, name FROM subjects WHERE school_id = :sid ORDER BY name"
        ), {'sid': school_id}).fetchall()
        
        classes = db.execute(text(
            "SELECT id, name FROM classes WHERE school_id = :sid ORDER BY name"
        ), {'sid': school_id}).fetchall()
        
        return render_template('materials/add_gradebook_entry.html',
                             students=students, subjects=subjects, classes=classes)
    finally:
        db.close()
