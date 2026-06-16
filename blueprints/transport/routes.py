from flask import Blueprint, render_template, redirect, url_for, session, request, flash, jsonify
from datetime import datetime
from db import SessionLocal
from sqlalchemy import text

transport_bp = Blueprint('transport', __name__, template_folder='templates')

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


@transport_bp.route('/')
@login_required
def index():
    return redirect(url_for('transport.routes'))


@transport_bp.route('/routes')
@login_required
def routes():
    """List all bus routes"""
    school_id = get_school_id()
    search = request.args.get('q', '')
    db = SessionLocal()
    try:
        query = """
            SELECT r.id, r.name, r.description, r.departure_time, r.arrival_time, 
                   COUNT(DISTINCT s.stop_id) as stops_count,
                   COUNT(DISTINCT ba.id) as assigned_students
            FROM bus_routes r
            LEFT JOIN bus_stops s ON r.id = s.route_id
            LEFT JOIN bus_assignments ba ON r.id = ba.route_id
            WHERE r.school_id = :sid
        """
        params = {'sid': school_id}
        
        if search:
            query += " AND r.name ILIKE :q"
            params['q'] = f'%{search}%'
        
        query += " GROUP BY r.id, r.name, r.description, r.departure_time, r.arrival_time ORDER BY r.name"
        routes_data = db.execute(text(query), params).fetchall()
        
        return render_template('transport/routes.html', routes=routes_data, search=search)
    finally:
        db.close()


@transport_bp.route('/route/add', methods=['GET', 'POST'])
@login_required
def add_route():
    """Add new bus route"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            db.execute(text("""
                INSERT INTO bus_routes 
                (school_id, name, description, departure_time, arrival_time, is_active, created_at)
                VALUES (:sid, :name, :desc, :depart, :arrive, :active, :now)
            """), {
                'sid': school_id,
                'name': request.form.get('name'),
                'desc': request.form.get('description'),
                'depart': request.form.get('departure_time'),
                'arrive': request.form.get('arrival_time'),
                'active': request.form.get('is_active') == 'on',
                'now': datetime.now()
            })
            db.commit()
            flash(f'Bus route added successfully', 'success')
            return redirect(url_for('transport.routes'))
        
        buses = db.execute(text(
            "SELECT id, bus_number FROM buses WHERE school_id = :sid AND is_active = true ORDER BY bus_number"
        ), {'sid': school_id}).fetchall()
        
        return render_template('transport/add_route.html', buses=buses)
    finally:
        db.close()


@transport_bp.route('/route/<int:route_id>')
@login_required
def route_detail(route_id):
    """View route details"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        route = db.execute(text(
            "SELECT * FROM bus_routes WHERE id = :id AND school_id = :sid"
        ), {'id': route_id, 'sid': school_id}).fetchone()
        
        if not route:
            flash('Route not found', 'danger')
            return redirect(url_for('transport.routes'))
        
        stops = db.execute(text(
            "SELECT * FROM bus_stops WHERE route_id = :rid ORDER BY stop_number ASC"
        ), {'rid': route_id}).fetchall()
        
        assignments = db.execute(text("""
            SELECT ba.id, s.name, s.admission_number, s.class_name, bs1.stop_name as pickup, bs2.stop_name as dropoff
            FROM bus_assignments ba
            LEFT JOIN students s ON ba.student_id = s.id
            LEFT JOIN bus_stops bs1 ON ba.pickup_stop_id = bs1.id
            LEFT JOIN bus_stops bs2 ON ba.dropoff_stop_id = bs2.id
            WHERE ba.route_id = :rid AND ba.is_active = true
            ORDER BY s.name
        """), {'rid': route_id}).fetchall()
        
        return render_template('transport/route_detail.html', route=route, stops=stops, assignments=assignments)
    finally:
        db.close()


@transport_bp.route('/stop/add/<int:route_id>', methods=['GET', 'POST'])
@login_required
def add_stop(route_id):
    """Add bus stop to route"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        route = db.execute(text(
            "SELECT * FROM bus_routes WHERE id = :id AND school_id = :sid"
        ), {'id': route_id, 'sid': school_id}).fetchone()
        
        if not route:
            flash('Route not found', 'danger')
            return redirect(url_for('transport.routes'))
        
        if request.method == 'POST':
            max_stop = db.execute(text(
                "SELECT MAX(stop_number) FROM bus_stops WHERE route_id = :rid"
            ), {'rid': route_id}).scalar()
            
            next_stop_num = (max_stop or 0) + 1
            
            db.execute(text("""
                INSERT INTO bus_stops 
                (route_id, stop_number, stop_name, stop_location, arrival_time, created_at)
                VALUES (:rid, :num, :name, :location, :arrival, :now)
            """), {
                'rid': route_id,
                'num': next_stop_num,
                'name': request.form.get('stop_name'),
                'location': request.form.get('stop_location'),
                'arrival': request.form.get('arrival_time'),
                'now': datetime.now()
            })
            db.commit()
            flash(f'Bus stop added successfully', 'success')
            return redirect(url_for('transport.route_detail', route_id=route_id))
        
        return render_template('transport/add_stop.html', route=route)
    finally:
        db.close()


@transport_bp.route('/buses')
@login_required
def buses():
    """List all buses"""
    school_id = get_school_id()
    search = request.args.get('q', '')
    db = SessionLocal()
    try:
        query = """
            SELECT b.id, b.bus_number, b.plate_number, b.model, b.capacity, 
                   d.name as driver_name, COUNT(DISTINCT ba.id) as students_assigned
            FROM buses b
            LEFT JOIN drivers d ON b.driver_id = d.id
            LEFT JOIN bus_assignments ba ON (SELECT route_id FROM bus_routes br WHERE br.bus_id = b.id LIMIT 1) = ba.route_id
            WHERE b.school_id = :sid AND b.is_active = true
        """
        params = {'sid': school_id}
        
        if search:
            query += " AND (b.bus_number ILIKE :q OR b.plate_number ILIKE :q OR d.name ILIKE :q)"
            params['q'] = f'%{search}%'
        
        query += " GROUP BY b.id, b.bus_number, b.plate_number, b.model, b.capacity, d.name ORDER BY b.bus_number"
        buses_data = db.execute(text(query), params).fetchall()
        
        return render_template('transport/buses.html', buses=buses_data, search=search)
    finally:
        db.close()


@transport_bp.route('/bus/add', methods=['GET', 'POST'])
@login_required
def add_bus():
    """Add new bus"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            db.execute(text("""
                INSERT INTO buses 
                (school_id, bus_number, plate_number, model, capacity, is_active, created_at)
                VALUES (:sid, :bus_num, :plate, :model, :capacity, :active, :now)
            """), {
                'sid': school_id,
                'bus_num': request.form.get('bus_number'),
                'plate': request.form.get('plate_number'),
                'model': request.form.get('model'),
                'capacity': request.form.get('capacity', 50),
                'active': request.form.get('is_active') == 'on',
                'now': datetime.now()
            })
            db.commit()
            flash(f'Bus added successfully', 'success')
            return redirect(url_for('transport.buses'))
        
        return render_template('transport/add_bus.html')
    finally:
        db.close()


@transport_bp.route('/drivers')
@login_required
def drivers():
    """List all drivers"""
    school_id = get_school_id()
    search = request.args.get('q', '')
    db = SessionLocal()
    try:
        query = """
            SELECT d.id, d.name, d.phone, d.license_number, d.license_expiry,
                   COUNT(DISTINCT b.id) as buses_assigned
            FROM drivers d
            LEFT JOIN buses b ON d.id = b.driver_id
            WHERE d.school_id = :sid AND d.is_active = true
        """
        params = {'sid': school_id}
        
        if search:
            query += " AND (d.name ILIKE :q OR d.phone ILIKE :q OR d.license_number ILIKE :q)"
            params['q'] = f'%{search}%'
        
        query += " GROUP BY d.id, d.name, d.phone, d.license_number, d.license_expiry ORDER BY d.name"
        drivers_data = db.execute(text(query), params).fetchall()
        
        return render_template('transport/drivers.html', drivers=drivers_data, search=search)
    finally:
        db.close()


@transport_bp.route('/driver/add', methods=['GET', 'POST'])
@login_required
def add_driver():
    """Add new driver"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            db.execute(text("""
                INSERT INTO drivers 
                (school_id, name, phone, license_number, license_expiry, address, is_active, created_at)
                VALUES (:sid, :name, :phone, :license, :expiry, :address, :active, :now)
            """), {
                'sid': school_id,
                'name': request.form.get('name'),
                'phone': request.form.get('phone'),
                'license': request.form.get('license_number'),
                'expiry': request.form.get('license_expiry'),
                'address': request.form.get('address'),
                'active': request.form.get('is_active') == 'on',
                'now': datetime.now()
            })
            db.commit()
            flash(f'Driver added successfully', 'success')
            return redirect(url_for('transport.drivers'))
        
        return render_template('transport/add_driver.html')
    finally:
        db.close()


@transport_bp.route('/assignment/add/<int:student_id>', methods=['GET', 'POST'])
@login_required
def assign_student(student_id):
    """Assign student to bus route"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        student = db.execute(text(
            "SELECT * FROM students WHERE id = :id AND school_id = :sid"
        ), {'id': student_id, 'sid': school_id}).fetchone()
        
        if not student:
            flash('Student not found', 'danger')
            return redirect(url_for('transport.routes'))
        
        if request.method == 'POST':
            db.execute(text("""
                INSERT INTO bus_assignments 
                (student_id, route_id, pickup_stop_id, dropoff_stop_id, is_active, created_at)
                VALUES (:sid, :rid, :pickup, :dropoff, :active, :now)
            """), {
                'sid': student_id,
                'rid': request.form.get('route_id'),
                'pickup': request.form.get('pickup_stop_id'),
                'dropoff': request.form.get('dropoff_stop_id'),
                'active': True,
                'now': datetime.now()
            })
            db.commit()
            flash(f'Student assigned to route successfully', 'success')
            return redirect(url_for('transport.routes'))
        
        routes = db.execute(text(
            "SELECT id, name FROM bus_routes WHERE school_id = :sid AND is_active = true ORDER BY name"
        ), {'sid': school_id}).fetchall()
        
        return render_template('transport/assign_student.html', student=student, routes=routes)
    finally:
        db.close()


@transport_bp.route('/attendance/record/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
def record_attendance(assignment_id):
    """Record bus attendance"""
    school_id = get_school_id()
    db = SessionLocal()
    try:
        assignment = db.execute(text("""
            SELECT ba.id, ba.student_id, s.name, r.name as route_name, br.departure_time
            FROM bus_assignments ba
            LEFT JOIN students s ON ba.student_id = s.id
            LEFT JOIN bus_routes r ON ba.route_id = r.id
            LEFT JOIN bus_routes br ON ba.route_id = br.id
            WHERE ba.id = :aid
        """), {'aid': assignment_id}).fetchone()
        
        if not assignment:
            flash('Assignment not found', 'danger')
            return redirect(url_for('transport.routes'))
        
        if request.method == 'POST':
            db.execute(text("""
                INSERT INTO bus_attendance 
                (assignment_id, date, trip_type, status, notes, created_at)
                VALUES (:aid, :date, :trip, :status, :notes, :now)
            """), {
                'aid': assignment_id,
                'date': request.form.get('date'),
                'trip': request.form.get('trip_type', 'morning'),
                'status': request.form.get('status', 'present'),
                'notes': request.form.get('notes'),
                'now': datetime.now()
            })
            db.commit()
            flash(f'Attendance recorded successfully', 'success')
            return redirect(url_for('transport.routes'))
        
        return render_template('transport/record_attendance.html', assignment=assignment)
    finally:
        db.close()
