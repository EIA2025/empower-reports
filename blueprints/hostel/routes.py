from flask import Blueprint, render_template, redirect, url_for, session, request, flash, jsonify
from datetime import datetime
from db import SessionLocal
from sqlalchemy import text

hostel_bp = Blueprint('hostel', __name__, template_folder='templates')

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


@hostel_bp.route('/')
@login_required
def index():
    return redirect(url_for('hostel.dormitories'))


@hostel_bp.route('/dormitories')
@login_required
def dormitories():
    """List all dormitories"""
    school_id = get_school_id()
    search = request.args.get('q', '')
    db = SessionLocal()
    try:
        query = """
            SELECT d.id, d.name, d.block, d.total_rooms,
                   COUNT(DISTINCT r.id) as rooms_created,
                   COUNT(DISTINCT b.id) as total_beds,
                   COUNT(DISTINCT CASE WHEN ha.is_active = true THEN ha.id END) as occupied_beds
            FROM dormitories d
            LEFT JOIN rooms r ON d.id = r.dormitory_id
            LEFT JOIN beds b ON r.id = b.room_id
            LEFT JOIN hostel_allocations ha ON b.id = ha.bed_id
            WHERE d.school_id = :sid
        """
        params = {'sid': school_id}
        
        if search:
            query += " AND d.name ILIKE :q"
            params['q'] = f'%{search}%'
        
        query += " GROUP BY d.id, d.name, d.block, d.total_rooms ORDER BY d.name"
        dorms_data = db.execute(text(query), params).fetchall()
        
        return render_template('hostel/dormitories.html', dormitories=dorms_data, search=search)
    finally:
        db.close()


@hostel_bp.route('/dormitory/add', methods=['GET', 'POST'])
@login_required
def add_dormitory():
    """Add new dormitory"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            db.execute(text("""
                INSERT INTO dormitories 
                (school_id, name, block, total_rooms, created_at)
                VALUES (:sid, :name, :block, :total, :now)
            """), {
                'sid': school_id,
                'name': request.form.get('name'),
                'block': request.form.get('block'),
                'total': request.form.get('total_rooms'),
                'now': datetime.now()
            })
            db.commit()
            flash(f'Dormitory added successfully', 'success')
            return redirect(url_for('hostel.dormitories'))
        
        return render_template('hostel/add_dormitory.html')
    finally:
        db.close()


@hostel_bp.route('/dormitory/<int:dorm_id>')
@login_required
def dormitory_detail(dorm_id):
    """View dormitory details"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        dorm = db.execute(text(
            "SELECT * FROM dormitories WHERE id = :id AND school_id = :sid"
        ), {'id': dorm_id, 'sid': school_id}).fetchone()
        
        if not dorm:
            flash('Dormitory not found', 'danger')
            return redirect(url_for('hostel.dormitories'))
        
        rooms = db.execute(text("""
            SELECT r.id, r.room_number, r.capacity,
                   COUNT(DISTINCT b.id) as total_beds,
                   COUNT(DISTINCT CASE WHEN ha.is_active = true THEN ha.id END) as occupied_beds
            FROM rooms r
            LEFT JOIN beds b ON r.id = b.room_id
            LEFT JOIN hostel_allocations ha ON b.id = ha.bed_id
            WHERE r.dormitory_id = :did
            GROUP BY r.id, r.room_number, r.capacity
            ORDER BY r.room_number
        """), {'did': dorm_id}).fetchall()
        
        return render_template('hostel/dormitory_detail.html', dormitory=dorm, rooms=rooms)
    finally:
        db.close()


@hostel_bp.route('/room/add/<int:dorm_id>', methods=['GET', 'POST'])
@login_required
def add_room(dorm_id):
    """Add room to dormitory"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        dorm = db.execute(text(
            "SELECT * FROM dormitories WHERE id = :id AND school_id = :sid"
        ), {'id': dorm_id, 'sid': school_id}).fetchone()
        
        if not dorm:
            flash('Dormitory not found', 'danger')
            return redirect(url_for('hostel.dormitories'))
        
        if request.method == 'POST':
            db.execute(text("""
                INSERT INTO rooms 
                (dormitory_id, room_number, capacity, created_at)
                VALUES (:did, :room_num, :capacity, :now)
            """), {
                'did': dorm_id,
                'room_num': request.form.get('room_number'),
                'capacity': request.form.get('capacity', 2),
                'now': datetime.now()
            })
            room_id = db.lastrowid
            
            # Create beds
            capacity = int(request.form.get('capacity', 2))
            for i in range(1, capacity + 1):
                db.execute(text("""
                    INSERT INTO beds 
                    (room_id, bed_number, is_occupied, created_at)
                    VALUES (:rid, :bed_num, false, :now)
                """), {
                    'rid': room_id,
                    'bed_num': f'Bed {i}',
                    'now': datetime.now()
                })
            
            db.commit()
            flash(f'Room added successfully with {capacity} beds', 'success')
            return redirect(url_for('hostel.dormitory_detail', dorm_id=dorm_id))
        
        return render_template('hostel/add_room.html', dormitory=dorm)
    finally:
        db.close()


@hostel_bp.route('/room/<int:room_id>')
@login_required
def room_detail(room_id):
    """View room details"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        room = db.execute(text(
            "SELECT r.*, d.name as dorm_name FROM rooms r LEFT JOIN dormitories d ON r.dormitory_id = d.id WHERE r.id = :id"
        ), {'id': room_id}).fetchone()
        
        if not room:
            flash('Room not found', 'danger')
            return redirect(url_for('hostel.dormitories'))
        
        beds = db.execute(text("""
            SELECT b.id, b.bed_number, b.is_occupied, s.name as student_name, s.admission_number
            FROM beds b
            LEFT JOIN hostel_allocations ha ON b.id = ha.bed_id AND ha.is_active = true
            LEFT JOIN students s ON ha.student_id = s.id
            WHERE b.room_id = :rid
            ORDER BY b.bed_number
        """), {'rid': room_id}).fetchall()
        
        return render_template('hostel/room_detail.html', room=room, beds=beds)
    finally:
        db.close()


@hostel_bp.route('/allocation/add/<int:student_id>', methods=['GET', 'POST'])
@login_required
def allocate_student(student_id):
    """Allocate student to hostel"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        student = db.execute(text(
            "SELECT * FROM students WHERE id = :id AND school_id = :sid"
        ), {'id': student_id, 'sid': school_id}).fetchone()
        
        if not student:
            flash('Student not found', 'danger')
            return redirect(url_for('hostel.dormitories'))
        
        if request.method == 'POST':
            bed_id = request.form.get('bed_id')
            
            # Check if bed is available
            existing = db.execute(text(
                "SELECT id FROM hostel_allocations WHERE bed_id = :bid AND is_active = true"
            ), {'bid': bed_id}).fetchone()
            
            if existing:
                flash('Selected bed is already occupied', 'danger')
            else:
                db.execute(text("""
                    INSERT INTO hostel_allocations 
                    (student_id, bed_id, allocation_date, is_active, created_at)
                    VALUES (:sid, :bid, :date, true, :now)
                """), {
                    'sid': student_id,
                    'bid': bed_id,
                    'date': request.form.get('allocation_date'),
                    'now': datetime.now()
                })
                
                db.execute(text("UPDATE beds SET is_occupied = true WHERE id = :bid"), {'bid': bed_id})
                db.commit()
                
                flash(f'Student allocated to hostel successfully', 'success')
                return redirect(url_for('hostel.dormitories'))
        
        # Get available beds
        available_beds = db.execute(text("""
            SELECT b.id, b.bed_number, r.room_number, d.name as dorm_name
            FROM beds b
            LEFT JOIN rooms r ON b.room_id = r.id
            LEFT JOIN dormitories d ON r.dormitory_id = d.id
            WHERE b.is_occupied = false AND d.school_id = :sid
            ORDER BY d.name, r.room_number, b.bed_number
        """), {'sid': school_id}).fetchall()
        
        return render_template('hostel/allocate_student.html', student=student, available_beds=available_beds)
    finally:
        db.close()


@hostel_bp.route('/allocation/<int:allocation_id>/release', methods=['POST'])
@login_required
def release_allocation(allocation_id):
    """Release student from hostel"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        allocation = db.execute(text(
            "SELECT * FROM hostel_allocations WHERE id = :id"
        ), {'id': allocation_id}).fetchone()
        
        if not allocation:
            flash('Allocation not found', 'danger')
            return redirect(url_for('hostel.dormitories'))
        
        db.execute(text("""
            UPDATE hostel_allocations 
            SET is_active = false, release_date = :date
            WHERE id = :id
        """), {
            'id': allocation_id,
            'date': request.form.get('release_date')
        })
        
        db.execute(text(
            "UPDATE beds SET is_occupied = false WHERE id = :bid"
        ), {'bid': allocation.bed_id})
        
        db.commit()
        flash('Student released from hostel successfully', 'success')
        return redirect(url_for('hostel.dormitories'))
    finally:
        db.close()


@hostel_bp.route('/occupancy')
@login_required
def occupancy():
    """View hostel occupancy statistics"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        stats = db.execute(text("""
            SELECT 
                COUNT(DISTINCT d.id) as total_dorms,
                COUNT(DISTINCT r.id) as total_rooms,
                COUNT(DISTINCT b.id) as total_beds,
                COUNT(DISTINCT CASE WHEN ha.is_active = true THEN ha.id END) as occupied_beds,
                ROUND(100.0 * COUNT(DISTINCT CASE WHEN ha.is_active = true THEN ha.id END) / 
                      NULLIF(COUNT(DISTINCT b.id), 0), 2) as occupancy_rate
            FROM dormitories d
            LEFT JOIN rooms r ON d.id = r.dormitory_id
            LEFT JOIN beds b ON r.id = b.room_id
            LEFT JOIN hostel_allocations ha ON b.id = ha.bed_id
            WHERE d.school_id = :sid
        """), {'sid': school_id}).fetchone()
        
        dorm_stats = db.execute(text("""
            SELECT d.name, d.block,
                   COUNT(DISTINCT r.id) as rooms,
                   COUNT(DISTINCT b.id) as total_beds,
                   COUNT(DISTINCT CASE WHEN ha.is_active = true THEN ha.id END) as occupied,
                   ROUND(100.0 * COUNT(DISTINCT CASE WHEN ha.is_active = true THEN ha.id END) / 
                         NULLIF(COUNT(DISTINCT b.id), 0), 2) as rate
            FROM dormitories d
            LEFT JOIN rooms r ON d.id = r.dormitory_id
            LEFT JOIN beds b ON r.id = b.room_id
            LEFT JOIN hostel_allocations ha ON b.id = ha.bed_id
            WHERE d.school_id = :sid
            GROUP BY d.id, d.name, d.block
            ORDER BY d.name
        """), {'sid': school_id}).fetchall()
        
        return render_template('hostel/occupancy.html', stats=stats, dorm_stats=dorm_stats)
    finally:
        db.close()
