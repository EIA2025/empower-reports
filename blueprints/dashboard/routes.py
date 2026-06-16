"""
Role-Specific Dashboard Routes for Empower Reports
"""
from flask import Blueprint, render_template, session, redirect, url_for, request, flash
from datetime import datetime, date, timedelta
from db import SessionLocal
from sqlalchemy import text
from decorators import (
    login_required, role_required, admin_required, master_required,
    teacher_required, student_required, parent_required, get_current_user_role,
    librarian_required
)

dashboard_bp = Blueprint('dashboard', __name__, template_folder='templates')


def get_school_id():
    return session.get('school_id', 1)


def get_user_role():
    return session.get('role', 'guest').lower()


# ── MAIN DASHBOARD REDIRECT ──────────────────────────────────────────────────

@dashboard_bp.route('/')
@login_required
def index():
    """Redirect to role-specific dashboard"""
    role = get_user_role()
    
    if role == 'master':
        return redirect(url_for('dashboard.master_admin_dashboard'))
    elif role == 'admin':
        return redirect(url_for('dashboard.admin_dashboard'))
    elif role == 'teacher':
        return redirect(url_for('dashboard.teacher_dashboard'))
    elif role == 'student':
        return redirect(url_for('dashboard.student_dashboard'))
    elif role == 'parent':
        return redirect(url_for('dashboard.parent_dashboard'))
    elif role in ('accountant', 'bursar'):
        return redirect(url_for('dashboard.accountant_dashboard'))
    elif role == 'librarian':
        return redirect(url_for('dashboard.librarian_dashboard'))
    else:
        return redirect(url_for('dashboard.general_dashboard'))


# ── SYSTEM ADMIN DASHBOARD ───────────────────────────────────────────────────

@dashboard_bp.route('/admin/system')
@master_required
def master_admin_dashboard():
    """System admin dashboard with multi-school statistics"""
    db = SessionLocal()
    try:
        # Get statistics
        total_schools = db.execute(text("SELECT COUNT(*) as count FROM schools")).fetchone().count
        total_users = db.execute(text("SELECT COUNT(*) as count FROM users")).fetchone().count
        total_students = db.execute(text("SELECT COUNT(*) as count FROM students")).fetchone().count
        total_teachers = db.execute(text("SELECT COUNT(*) as count FROM users WHERE role='teacher'")).fetchone().count
        
        # Recent activities
        recent_users = db.execute(text("""
            SELECT id, name, email, created_at FROM users 
            ORDER BY created_at DESC LIMIT 10
        """)).fetchall()
        
        # Schools list
        schools = db.execute(text("""
            SELECT id, name, 
                (SELECT COUNT(*) FROM users WHERE school_id=schools.id) as user_count,
                (SELECT COUNT(*) FROM students WHERE school_id=schools.id) as student_count
            FROM schools
            ORDER BY created_at DESC
            LIMIT 10
        """)).fetchall()
        
        return render_template('dashboard/master_admin.html',
                             total_schools=total_schools,
                             total_users=total_users,
                             total_students=total_students,
                             total_teachers=total_teachers,
                             recent_users=recent_users,
                             schools=schools)
    finally:
        db.close()


# ── SCHOOL ADMIN DASHBOARD ──────────────────────────────────────────────────

@dashboard_bp.route('/admin')
@admin_required
def admin_dashboard():
    """School admin dashboard"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        # School info
        school = db.execute(text(
            "SELECT * FROM schools WHERE id=:sid"
        ), {'sid': school_id}).fetchone()
        
        # Statistics
        student_count = db.execute(text(
            "SELECT COUNT(*) as count FROM students WHERE school_id=:sid"
        ), {'sid': school_id}).fetchone().count
        
        teacher_count = db.execute(text(
            "SELECT COUNT(*) as count FROM users WHERE school_id=:sid AND role='teacher'"
        ), {'sid': school_id}).fetchone().count
        
        staff_count = db.execute(text(
            "SELECT COUNT(*) as count FROM users WHERE school_id=:sid AND role IN ('admin','staff')"
        ), {'sid': school_id}).fetchone().count
        
        attendance_today = db.execute(text("""
            SELECT COUNT(DISTINCT student_id) as count 
            FROM attendance 
            WHERE school_id=:sid AND DATE(date) = CURDATE()
        """), {'sid': school_id}).fetchone().count or 0
        
        # Pending tasks
        pending_fees = db.execute(text("""
            SELECT COUNT(*) as count FROM fees 
            WHERE school_id=:sid AND paid_date IS NULL
        """), {'sid': school_id}).fetchone().count or 0
        
        overdue_library = db.execute(text("""
            SELECT COUNT(*) as count FROM borrowings 
            WHERE school_id=:sid AND return_date IS NULL 
            AND due_date < CURDATE()
        """), {'sid': school_id}).fetchone().count or 0
        
        # Recent activities
        recent_students = db.execute(text("""
            SELECT id, name, admission_number, class_name 
            FROM students 
            WHERE school_id=:sid
            ORDER BY created_at DESC 
            LIMIT 5
        """), {'sid': school_id}).fetchall()
        
        return render_template('dashboard/admin.html',
                             school=school,
                             student_count=student_count,
                             teacher_count=teacher_count,
                             staff_count=staff_count,
                             attendance_today=attendance_today,
                             pending_fees=pending_fees,
                             overdue_library=overdue_library,
                             recent_students=recent_students)
    finally:
        db.close()


# ── TEACHER DASHBOARD ────────────────────────────────────────────────────────

@dashboard_bp.route('/teacher')
@teacher_required
def teacher_dashboard():
    """Teacher dashboard"""
    school_id = get_school_id()
    teacher_id = session.get('user_id')
    db = SessionLocal()
    try:
        # Get teacher info
        teacher = db.execute(text(
            "SELECT * FROM users WHERE id=:tid AND school_id=:sid"
        ), {'tid': teacher_id, 'sid': school_id}).fetchone()
        
        # Assigned classes
        classes = db.execute(text("""
            SELECT DISTINCT class_name 
            FROM students 
            WHERE class_name IS NOT NULL 
            AND school_id=:sid
            LIMIT 5
        """), {'sid': school_id}).fetchall()
        
        # Today's timetable
        today = date.today().strftime('%A').lower()
        timetable = db.execute(text("""
            SELECT * FROM timetables 
            WHERE day=:day AND school_id=:sid
            LIMIT 10
        """), {'day': today, 'sid': school_id}).fetchall()
        
        # Pending grading
        pending_marks = db.execute(text("""
            SELECT COUNT(*) as count FROM exam_marks 
            WHERE teacher_id=:tid AND marks IS NULL
        """), {'tid': teacher_id}).fetchone().count or 0
        
        # Pending attendance
        today_str = date.today().isoformat()
        pending_attendance = db.execute(text("""
            SELECT COUNT(DISTINCT class_name) as count 
            FROM students 
            WHERE school_id=:sid 
            AND class_name NOT IN (
                SELECT DISTINCT class_name FROM attendance 
                WHERE school_id=:sid AND DATE(date)=:today
            )
        """), {'sid': school_id, 'today': today_str}).fetchone().count or 0
        
        # Recent assignments
        recent_assignments = db.execute(text("""
            SELECT id, name, due_date, class_name
            FROM assignments
            WHERE teacher_id=:tid AND school_id=:sid
            ORDER BY created_at DESC
            LIMIT 5
        """), {'tid': teacher_id, 'sid': school_id}).fetchall()
        
        return render_template('dashboard/teacher.html',
                             teacher=teacher,
                             classes=classes,
                             timetable=timetable,
                             pending_marks=pending_marks,
                             pending_attendance=pending_attendance,
                             recent_assignments=recent_assignments)
    finally:
        db.close()


# ── STUDENT DASHBOARD ────────────────────────────────────────────────────────

@dashboard_bp.route('/student')
@student_required
def student_dashboard():
    """Student dashboard"""
    school_id = get_school_id()
    student_id = session.get('user_id')
    db = SessionLocal()
    try:
        # Get student info
        student = db.execute(text(
            "SELECT * FROM students WHERE id=:sid AND school_id=:scid"
        ), {'sid': student_id, 'scid': school_id}).fetchone()
        
        if not student:
            flash('Student not found.', 'danger')
            return redirect(url_for('dashboard.general_dashboard'))
        
        # Current term
        current_term = db.execute(text(
            "SELECT * FROM terms WHERE is_active=true AND school_id=:sid LIMIT 1"
        ), {'sid': school_id}).fetchone()
        
        # Get latest results
        latest_results = db.execute(text("""
            SELECT subject_name, marks, max_marks, grade, date_recorded
            FROM exam_marks
            WHERE student_id=:sid AND school_id=:scid
            ORDER BY date_recorded DESC
            LIMIT 5
        """), {'sid': student_id, 'scid': school_id}).fetchall()
        
        # Attendance percentage
        total_days = db.execute(text("""
            SELECT COUNT(DISTINCT DATE(date)) as count 
            FROM attendance
            WHERE school_id=:sid AND student_id=:sid
        """), {'scid': school_id, 'sid': student_id}).fetchone().count or 1
        
        present_days = db.execute(text("""
            SELECT COUNT(DISTINCT DATE(date)) as count 
            FROM attendance
            WHERE school_id=:sid AND student_id=:sid AND status='present'
        """), {'scid': school_id, 'sid': student_id}).fetchone().count or 0
        
        attendance_percentage = round((present_days / total_days) * 100) if total_days > 0 else 0
        
        # Pending assignments
        pending_assignments = db.execute(text("""
            SELECT id, name, subject_name, due_date
            FROM assignments
            WHERE class_name=:class AND school_id=:sid AND due_date >= CURDATE()
            ORDER BY due_date ASC
            LIMIT 5
        """), {'class': student.class_name, 'sid': school_id}).fetchall()
        
        # Fee status
        fees = db.execute(text("""
            SELECT SUM(amount) as total, SUM(CASE WHEN paid_date IS NOT NULL THEN amount ELSE 0 END) as paid
            FROM fees
            WHERE student_id=:sid AND school_id=:scid
        """), {'sid': student_id, 'scid': school_id}).fetchone()
        
        fees_balance = (fees.total or 0) - (fees.paid or 0) if fees else 0
        
        return render_template('dashboard/student.html',
                             student=student,
                             current_term=current_term,
                             latest_results=latest_results,
                             attendance_percentage=attendance_percentage,
                             pending_assignments=pending_assignments,
                             fees_balance=fees_balance)
    finally:
        db.close()


# ── PARENT DASHBOARD ─────────────────────────────────────────────────────────

@dashboard_bp.route('/parent')
@parent_required
def parent_dashboard():
    """Parent dashboard with children overview"""
    school_id = get_school_id()
    parent_id = session.get('user_id')
    db = SessionLocal()
    try:
        # Get parent info
        parent = db.execute(text(
            "SELECT * FROM users WHERE id=:pid AND school_id=:sid"
        ), {'pid': parent_id, 'sid': school_id}).fetchone()
        
        # Get children
        children = db.execute(text("""
            SELECT id, name, admission_number, class_name, date_of_birth
            FROM students
            WHERE parent_id=:pid AND school_id=:sid
        """), {'pid': parent_id, 'sid': school_id}).fetchall()
        
        # Summary for each child
        children_summary = []
        for child in children:
            # Latest results
            latest_result = db.execute(text("""
                SELECT marks, max_marks, grade, subject_name
                FROM exam_marks
                WHERE student_id=:cid AND school_id=:sid
                ORDER BY date_recorded DESC
                LIMIT 1
            """), {'cid': child.id, 'sid': school_id}).fetchone()
            
            # Fee status
            fees = db.execute(text("""
                SELECT SUM(amount) as total, SUM(CASE WHEN paid_date IS NOT NULL THEN amount ELSE 0 END) as paid
                FROM fees
                WHERE student_id=:cid AND school_id=:sid
            """), {'cid': child.id, 'sid': school_id}).fetchone()
            
            fees_balance = (fees.total or 0) - (fees.paid or 0) if fees else 0
            
            children_summary.append({
                'child': child,
                'latest_result': latest_result,
                'fees_balance': fees_balance
            })
        
        # Announcements
        announcements = db.execute(text("""
            SELECT id, title, content, created_at
            FROM announcements
            WHERE school_id=:sid
            ORDER BY created_at DESC
            LIMIT 5
        """), {'sid': school_id}).fetchall()
        
        return render_template('dashboard/parent.html',
                             parent=parent,
                             children_summary=children_summary,
                             announcements=announcements)
    finally:
        db.close()


# ── ACCOUNTANT DASHBOARD ─────────────────────────────────────────────────────

@dashboard_bp.route('/accountant')
@role_required('accountant', 'bursar')
def accountant_dashboard():
    """Accountant/Bursar dashboard"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        # Total fees
        fees_summary = db.execute(text("""
            SELECT 
                SUM(amount) as total_fees,
                SUM(CASE WHEN paid_date IS NOT NULL THEN amount ELSE 0 END) as collected,
                SUM(CASE WHEN paid_date IS NULL THEN amount ELSE 0 END) as outstanding
            FROM fees
            WHERE school_id=:sid
        """), {'sid': school_id}).fetchone()
        
        # Today's collections
        today_collection = db.execute(text("""
            SELECT SUM(amount) as total FROM fees
            WHERE school_id=:sid AND DATE(paid_date)=CURDATE()
        """), {'sid': school_id}).fetchone()
        
        # Student count
        student_count = db.execute(text(
            "SELECT COUNT(*) as count FROM students WHERE school_id=:sid"
        ), {'sid': school_id}).fetchone().count
        
        # Collection rate
        collection_rate = 0
        if fees_summary.total_fees and fees_summary.total_fees > 0:
            collection_rate = round((fees_summary.collected or 0) / fees_summary.total_fees * 100)
        
        # Outstanding accounts
        outstanding = db.execute(text("""
            SELECT 
                s.id, s.name, s.admission_number, s.class_name,
                SUM(f.amount) as total_owed,
                SUM(CASE WHEN f.paid_date IS NOT NULL THEN f.amount ELSE 0 END) as paid
            FROM students s
            LEFT JOIN fees f ON f.student_id=s.id AND f.school_id=:sid
            WHERE s.school_id=:sid
            GROUP BY s.id, s.name, s.admission_number, s.class_name
            HAVING total_owed > paid
            ORDER BY total_owed DESC
            LIMIT 10
        """), {'sid': school_id}).fetchall()
        
        return render_template('dashboard/accountant.html',
                             total_fees=fees_summary.total_fees or 0,
                             collected=fees_summary.collected or 0,
                             outstanding=fees_summary.outstanding or 0,
                             today_collection=today_collection.total or 0,
                             collection_rate=collection_rate,
                             student_count=student_count,
                             outstanding_accounts=outstanding)
    finally:
        db.close()


# ── LIBRARIAN DASHBOARD ──────────────────────────────────────────────────────

@dashboard_bp.route('/librarian')
@librarian_required
def librarian_dashboard():
    """Librarian dashboard"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        # Library statistics
        total_books = db.execute(text(
            "SELECT COUNT(*) as count FROM books WHERE school_id=:sid"
        ), {'sid': school_id}).fetchone().count
        
        issued_today = db.execute(text("""
            SELECT COUNT(*) as count FROM borrowings
            WHERE school_id=:sid AND DATE(borrow_date)=CURDATE()
        """), {'sid': school_id}).fetchone().count or 0
        
        overdue_books = db.execute(text("""
            SELECT COUNT(*) as count FROM borrowings
            WHERE school_id=:sid AND return_date IS NULL 
            AND due_date < CURDATE()
        """), {'sid': school_id}).fetchone().count or 0
        
        pending_returns = db.execute(text("""
            SELECT COUNT(*) as count FROM borrowings
            WHERE school_id=:sid AND return_date IS NULL
            AND due_date <= CURDATE() + INTERVAL 2 DAY
        """), {'sid': school_id}).fetchone().count or 0
        
        # Most borrowed books
        popular_books = db.execute(text("""
            SELECT b.id, b.title, b.isbn, COUNT(*) as borrow_count
            FROM books b
            LEFT JOIN borrowings br ON br.book_id=b.id AND br.school_id=:sid
            WHERE b.school_id=:sid
            GROUP BY b.id, b.title, b.isbn
            ORDER BY borrow_count DESC
            LIMIT 5
        """), {'sid': school_id}).fetchall()
        
        return render_template('dashboard/librarian.html',
                             total_books=total_books,
                             issued_today=issued_today,
                             overdue_books=overdue_books,
                             pending_returns=pending_returns,
                             popular_books=popular_books)
    finally:
        db.close()


# ── GENERAL DASHBOARD ────────────────────────────────────────────────────────

@dashboard_bp.route('/general')
def general_dashboard():
    """General dashboard for users without specific role"""
    return render_template('dashboard/general.html')
