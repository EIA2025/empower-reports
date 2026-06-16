from flask import Blueprint, render_template, redirect, url_for, session, request, flash, jsonify
from datetime import datetime
from db import SessionLocal
from sqlalchemy import text
import json

health_bp = Blueprint('health', __name__, template_folder='templates')

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


@health_bp.route('/')
@login_required
def index():
    return redirect(url_for('health.students'))


@health_bp.route('/students')
@login_required
def students():
    """List all students with health records"""
    school_id = get_school_id()
    search = request.args.get('q', '')
    db = SessionLocal()
    try:
        query = """
            SELECT DISTINCT s.id, s.name, u.email, s.class_name, 
                   COUNT(CASE WHEN sa.id IS NOT NULL THEN 1 END) as allergy_count,
                   COUNT(CASE WHEN smc.id IS NOT NULL THEN 1 END) as condition_count,
                   COUNT(CASE WHEN cv.id IS NOT NULL THEN 1 END) as clinic_visits
            FROM students s
            LEFT JOIN users u ON s.user_id = u.id
            LEFT JOIN student_allergies sa ON s.id = sa.student_id
            LEFT JOIN student_medical_conditions smc ON s.id = smc.student_id
            LEFT JOIN clinic_visits cv ON s.id = cv.student_id
            WHERE s.school_id = :sid
        """
        params = {'sid': school_id}
        
        if search:
            query += " AND (s.name ILIKE :q OR u.email ILIKE :q OR s.admission_number ILIKE :q)"
            params['q'] = f'%{search}%'
        
        query += " GROUP BY s.id, s.name, u.email, s.class_name ORDER BY s.name LIMIT 500"
        students_data = db.execute(text(query), params).fetchall()
        
        return render_template('health/students.html', students=students_data, search=search)
    finally:
        db.close()


@health_bp.route('/student/<int:student_id>')
@login_required
def student_health_profile(student_id):
    """View student health profile"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        student = db.execute(text(
            "SELECT * FROM students WHERE id = :id AND school_id = :sid"
        ), {'id': student_id, 'sid': school_id}).fetchone()
        
        if not student:
            flash('Student not found', 'danger')
            return redirect(url_for('health.students'))
        
        allergies = db.execute(text(
            "SELECT * FROM student_allergies WHERE student_id = :sid ORDER BY created_at DESC"
        ), {'sid': student_id}).fetchall()
        
        conditions = db.execute(text(
            "SELECT * FROM student_medical_conditions WHERE student_id = :sid ORDER BY created_at DESC"
        ), {'sid': student_id}).fetchall()
        
        emergency_contacts = db.execute(text(
            "SELECT * FROM emergency_contacts WHERE student_id = :sid ORDER BY is_primary DESC, created_at DESC"
        ), {'sid': student_id}).fetchall()
        
        vaccinations = db.execute(text(
            "SELECT * FROM vaccination_records WHERE student_id = :sid ORDER BY vaccination_date DESC"
        ), {'sid': student_id}).fetchall()
        
        clinic_visits = db.execute(text(
            "SELECT * FROM clinic_visits WHERE student_id = :sid ORDER BY visit_date DESC LIMIT 20"
        ), {'sid': student_id}).fetchall()
        
        medications = db.execute(text(
            "SELECT * FROM medication_administration WHERE student_id = :sid ORDER BY created_at DESC LIMIT 20"
        ), {'sid': student_id}).fetchall()
        
        return render_template('health/profile.html', 
                             student=student, 
                             allergies=allergies,
                             conditions=conditions,
                             emergency_contacts=emergency_contacts,
                             vaccinations=vaccinations,
                             clinic_visits=clinic_visits,
                             medications=medications)
    finally:
        db.close()


@health_bp.route('/allergy/add/<int:student_id>', methods=['GET', 'POST'])
@login_required
def add_allergy(student_id):
    """Add student allergy"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            db.execute(text("""
                INSERT INTO student_allergies 
                (school_id, student_id, allergen, severity, symptoms, treatment, notes, created_at)
                VALUES (:sid, :stid, :allergen, :severity, :symptoms, :treatment, :notes, :now)
            """), {
                'sid': school_id,
                'stid': student_id,
                'allergen': request.form.get('allergen'),
                'severity': request.form.get('severity', 'mild'),
                'symptoms': request.form.get('symptoms'),
                'treatment': request.form.get('treatment'),
                'notes': request.form.get('notes'),
                'now': datetime.now()
            })
            db.commit()
            flash(f'Allergy recorded successfully', 'success')
            return redirect(url_for('health.student_health_profile', student_id=student_id))
        
        student = db.execute(text(
            "SELECT * FROM students WHERE id = :id AND school_id = :sid"
        ), {'id': student_id, 'sid': school_id}).fetchone()
        
        if not student:
            flash('Student not found', 'danger')
            return redirect(url_for('health.students'))
        
        return render_template('health/add_allergy.html', student=student)
    finally:
        db.close()


@health_bp.route('/condition/add/<int:student_id>', methods=['GET', 'POST'])
@login_required
def add_condition(student_id):
    """Add student medical condition"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            db.execute(text("""
                INSERT INTO student_medical_conditions 
                (school_id, student_id, condition, diagnosed_date, description, medication, restrictions, notes, created_at)
                VALUES (:sid, :stid, :condition, :diagnosed_date, :description, :medication, :restrictions, :notes, :now)
            """), {
                'sid': school_id,
                'stid': student_id,
                'condition': request.form.get('condition'),
                'diagnosed_date': request.form.get('diagnosed_date'),
                'description': request.form.get('description'),
                'medication': request.form.get('medication'),
                'restrictions': request.form.get('restrictions'),
                'notes': request.form.get('notes'),
                'now': datetime.now()
            })
            db.commit()
            flash(f'Medical condition recorded successfully', 'success')
            return redirect(url_for('health.student_health_profile', student_id=student_id))
        
        student = db.execute(text(
            "SELECT * FROM students WHERE id = :id AND school_id = :sid"
        ), {'id': student_id, 'sid': school_id}).fetchone()
        
        if not student:
            flash('Student not found', 'danger')
            return redirect(url_for('health.students'))
        
        return render_template('health/add_condition.html', student=student)
    finally:
        db.close()


@health_bp.route('/emergency-contact/add/<int:student_id>', methods=['GET', 'POST'])
@login_required
def add_emergency_contact(student_id):
    """Add emergency contact"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            db.execute(text("""
                INSERT INTO emergency_contacts 
                (school_id, student_id, name, relationship, phone, email, address, is_primary, notes, created_at)
                VALUES (:sid, :stid, :name, :rel, :phone, :email, :address, :is_primary, :notes, :now)
            """), {
                'sid': school_id,
                'stid': student_id,
                'name': request.form.get('name'),
                'rel': request.form.get('relationship'),
                'phone': request.form.get('phone'),
                'email': request.form.get('email'),
                'address': request.form.get('address'),
                'is_primary': request.form.get('is_primary') == 'on',
                'notes': request.form.get('notes'),
                'now': datetime.now()
            })
            db.commit()
            flash(f'Emergency contact added successfully', 'success')
            return redirect(url_for('health.student_health_profile', student_id=student_id))
        
        student = db.execute(text(
            "SELECT * FROM students WHERE id = :id AND school_id = :sid"
        ), {'id': student_id, 'sid': school_id}).fetchone()
        
        if not student:
            flash('Student not found', 'danger')
            return redirect(url_for('health.students'))
        
        return render_template('health/add_emergency_contact.html', student=student)
    finally:
        db.close()


@health_bp.route('/vaccination/add/<int:student_id>', methods=['GET', 'POST'])
@login_required
def add_vaccination(student_id):
    """Add vaccination record"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            db.execute(text("""
                INSERT INTO vaccination_records 
                (school_id, student_id, vaccine_name, vaccination_date, batch_number, 
                 administered_by, facility, next_dose_date, certificate_uploaded, notes, created_at)
                VALUES (:sid, :stid, :vname, :vdate, :batch, :admin, :facility, :next, :cert, :notes, :now)
            """), {
                'sid': school_id,
                'stid': student_id,
                'vname': request.form.get('vaccine_name'),
                'vdate': request.form.get('vaccination_date'),
                'batch': request.form.get('batch_number'),
                'admin': request.form.get('administered_by'),
                'facility': request.form.get('facility'),
                'next': request.form.get('next_dose_date'),
                'cert': request.form.get('certificate_uploaded') == 'on',
                'notes': request.form.get('notes'),
                'now': datetime.now()
            })
            db.commit()
            flash(f'Vaccination record added successfully', 'success')
            return redirect(url_for('health.student_health_profile', student_id=student_id))
        
        student = db.execute(text(
            "SELECT * FROM students WHERE id = :id AND school_id = :sid"
        ), {'id': student_id, 'sid': school_id}).fetchone()
        
        if not student:
            flash('Student not found', 'danger')
            return redirect(url_for('health.students'))
        
        return render_template('health/add_vaccination.html', student=student)
    finally:
        db.close()


@health_bp.route('/clinic-visit/add/<int:student_id>', methods=['GET', 'POST'])
@login_required
def add_clinic_visit(student_id):
    """Record clinic visit"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            db.execute(text("""
                INSERT INTO clinic_visits 
                (school_id, student_id, visit_date, complaint, diagnosis, treatment_given, 
                 referred, referred_to, follow_up_date, notes, created_at)
                VALUES (:sid, :stid, :vdate, :complaint, :diagnosis, :treatment, :referred, 
                        :referred_to, :follow_up, :notes, :now)
            """), {
                'sid': school_id,
                'stid': student_id,
                'vdate': request.form.get('visit_date'),
                'complaint': request.form.get('complaint'),
                'diagnosis': request.form.get('diagnosis'),
                'treatment': request.form.get('treatment_given'),
                'referred': request.form.get('referred') == 'on',
                'referred_to': request.form.get('referred_to'),
                'follow_up': request.form.get('follow_up_date'),
                'notes': request.form.get('notes'),
                'now': datetime.now()
            })
            db.commit()
            flash(f'Clinic visit recorded successfully', 'success')
            return redirect(url_for('health.student_health_profile', student_id=student_id))
        
        student = db.execute(text(
            "SELECT * FROM students WHERE id = :id AND school_id = :sid"
        ), {'id': student_id, 'sid': school_id}).fetchone()
        
        if not student:
            flash('Student not found', 'danger')
            return redirect(url_for('health.students'))
        
        return render_template('health/add_clinic_visit.html', student=student)
    finally:
        db.close()


@health_bp.route('/medication/add/<int:student_id>', methods=['GET', 'POST'])
@login_required
def add_medication(student_id):
    """Add medication record"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            db.execute(text("""
                INSERT INTO medication_administration 
                (school_id, student_id, medication_name, dosage, frequency, start_date, 
                 end_date, prescribed_by, given_by, notes, created_at)
                VALUES (:sid, :stid, :mname, :dosage, :freq, :start, :end, :prescribed, :given, :notes, :now)
            """), {
                'sid': school_id,
                'stid': student_id,
                'mname': request.form.get('medication_name'),
                'dosage': request.form.get('dosage'),
                'freq': request.form.get('frequency'),
                'start': request.form.get('start_date'),
                'end': request.form.get('end_date'),
                'prescribed': request.form.get('prescribed_by'),
                'given': session.get('user_id'),
                'notes': request.form.get('notes'),
                'now': datetime.now()
            })
            db.commit()
            flash(f'Medication record added successfully', 'success')
            return redirect(url_for('health.student_health_profile', student_id=student_id))
        
        student = db.execute(text(
            "SELECT * FROM students WHERE id = :id AND school_id = :sid"
        ), {'id': student_id, 'sid': school_id}).fetchone()
        
        if not student:
            flash('Student not found', 'danger')
            return redirect(url_for('health.students'))
        
        return render_template('health/add_medication.html', student=student)
    finally:
        db.close()


@health_bp.route('/allergy/delete/<int:allergy_id>', methods=['POST'])
@login_required
def delete_allergy(allergy_id):
    """Delete allergy record"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        allergy = db.execute(text(
            "SELECT student_id FROM student_allergies WHERE id = :id AND school_id = :sid"
        ), {'id': allergy_id, 'sid': school_id}).fetchone()
        
        if not allergy:
            return jsonify({'error': 'Not found'}), 404
        
        student_id = allergy[0]
        db.execute(text(
            "DELETE FROM student_allergies WHERE id = :id"
        ), {'id': allergy_id})
        db.commit()
        
        flash('Allergy record deleted', 'success')
        return redirect(url_for('health.student_health_profile', student_id=student_id))
    finally:
        db.close()


@health_bp.route('/condition/delete/<int:condition_id>', methods=['POST'])
@login_required
def delete_condition(condition_id):
    """Delete condition record"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        condition = db.execute(text(
            "SELECT student_id FROM student_medical_conditions WHERE id = :id AND school_id = :sid"
        ), {'id': condition_id, 'sid': school_id}).fetchone()
        
        if not condition:
            return jsonify({'error': 'Not found'}), 404
        
        student_id = condition[0]
        db.execute(text(
            "DELETE FROM student_medical_conditions WHERE id = :id"
        ), {'id': condition_id})
        db.commit()
        
        flash('Medical condition deleted', 'success')
        return redirect(url_for('health.student_health_profile', student_id=student_id))
    finally:
        db.close()
