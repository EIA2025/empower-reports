# db.py — Database setup and initialization
import os
import re
import time
import hashlib
import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://localhost/empower_school')

# Normalize postgres:// → postgresql://
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

# Append sslmode for Supabase
_is_supabase = 'supabase.com' in DATABASE_URL or 'pooler.supabase' in DATABASE_URL
if _is_supabase and 'sslmode' not in DATABASE_URL:
    DATABASE_URL += ('&' if '?' in DATABASE_URL else '?') + 'sslmode=require'

engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,
    connect_args={"options": "-c statement_timeout=30000 -c lock_timeout=10000"},
    echo=False,
)
SessionLocal = sessionmaker(bind=engine, autoflush=True, autocommit=False)


def get_raw_conn():
    """Raw psycopg2 connection — bypasses NullPool routing for DDL."""
    url_clean = re.sub(r'[?&]sslmode=\w+', '', DATABASE_URL)
    return psycopg2.connect(url_clean, sslmode='require' if _is_supabase else 'prefer')


def init_db():
    """Create all tables and seed data using a single raw connection."""
    for attempt in range(5):
        try:
            conn = get_raw_conn()
            break
        except psycopg2.OperationalError as e:
            if attempt == 4:
                raise
            print(f"DB connect attempt {attempt+1} failed, retrying: {e}")
            time.sleep(3)

    cur = conn.cursor()
    try:
        _create_tables(cur)
        conn.commit()
        print("✓ Tables created")

        _seed_data(cur, conn)
        print("✓ Seed data OK")

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()


def _create_tables(cur):
    cur.execute("""
    CREATE TABLE IF NOT EXISTS schools (
        id SERIAL PRIMARY KEY,
        name VARCHAR(200) NOT NULL,
        subtitle VARCHAR(200),
        address TEXT,
        po_box VARCHAR(100),
        phone VARCHAR(50),
        email VARCHAR(100),
        website VARCHAR(150),
        logo_data TEXT,
        primary_color VARCHAR(20) DEFAULT '#1e3a8a',
        report_footer TEXT,
        country VARCHAR(100),
        currency VARCHAR(10) DEFAULT 'UGX',
        is_active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS system_users (
        id SERIAL PRIMARY KEY,
        name VARCHAR(200),
        email VARCHAR(200) UNIQUE,
        password_hash VARCHAR(256),
        is_active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        user_id INTEGER,
        user_role VARCHAR(50),
        action VARCHAR(200),
        details TEXT,
        ip_address VARCHAR(50),
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        name VARCHAR(200) NOT NULL,
        email VARCHAR(200),
        phone VARCHAR(30),
        role VARCHAR(30) NOT NULL,
        password_hash VARCHAR(256),
        profile_photo TEXT,
        gender VARCHAR(20),
        date_of_birth VARCHAR(20),
        address TEXT,
        national_id VARCHAR(50),
        is_active BOOLEAN DEFAULT true,
        must_change_pw BOOLEAN DEFAULT true,
        recovery_phone VARCHAR(30),
        recovery_city VARCHAR(100),
        recovery_nickname VARCHAR(100),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        admission_number VARCHAR(50),
        name VARCHAR(200) NOT NULL,
        gender VARCHAR(20),
        date_of_birth VARCHAR(20),
        nationality VARCHAR(100),
        religion VARCHAR(100),
        photo TEXT,
        class_name VARCHAR(100),
        stream VARCHAR(50),
        year INTEGER,
        subjects TEXT,
        enrolment_date VARCHAR(20),
        enrolment_status VARCHAR(30) DEFAULT 'active',
        previous_school VARCHAR(200),
        medical_notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS guardians (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        name VARCHAR(200) NOT NULL,
        relationship VARCHAR(50),
        phone VARCHAR(30),
        alt_phone VARCHAR(30),
        email VARCHAR(150),
        address TEXT,
        occupation VARCHAR(150),
        national_id VARCHAR(50),
        is_primary BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS student_guardians (
        id SERIAL PRIMARY KEY,
        student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
        guardian_id INTEGER REFERENCES guardians(id) ON DELETE CASCADE,
        is_primary BOOLEAN DEFAULT false
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS staff (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        employee_number VARCHAR(50),
        name VARCHAR(200) NOT NULL,
        gender VARCHAR(20),
        date_of_birth VARCHAR(20),
        phone VARCHAR(30),
        email VARCHAR(150),
        address TEXT,
        national_id VARCHAR(50),
        photo TEXT,
        department VARCHAR(100),
        job_title VARCHAR(150),
        subjects_taught TEXT,
        classes_taught TEXT,
        class_teacher_for VARCHAR(100),
        employment_type VARCHAR(50),
        employment_date VARCHAR(20),
        qualification TEXT,
        is_active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS classes (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        name VARCHAR(100) NOT NULL,
        stream VARCHAR(50),
        level VARCHAR(50),
        class_teacher INTEGER REFERENCES staff(id) ON DELETE SET NULL,
        capacity INTEGER,
        room VARCHAR(50),
        is_active BOOLEAN DEFAULT true
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS academic_years (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        name VARCHAR(100),
        start_date VARCHAR(20),
        end_date VARCHAR(20),
        is_active BOOLEAN DEFAULT false
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS terms (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        academic_year_id INTEGER REFERENCES academic_years(id) ON DELETE CASCADE,
        name VARCHAR(100),
        term_number INTEGER,
        start_date VARCHAR(20),
        end_date VARCHAR(20),
        next_term_begins VARCHAR(20),
        is_active BOOLEAN DEFAULT false
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS subjects (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        name VARCHAR(150) NOT NULL,
        code VARCHAR(20),
        level VARCHAR(50),
        is_active BOOLEAN DEFAULT true
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS timetable (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        class_id INTEGER REFERENCES classes(id) ON DELETE CASCADE,
        term_id INTEGER REFERENCES terms(id) ON DELETE CASCADE,
        staff_id INTEGER REFERENCES staff(id) ON DELETE SET NULL,
        subject_id INTEGER REFERENCES subjects(id) ON DELETE CASCADE,
        day_of_week VARCHAR(10),
        start_time VARCHAR(10),
        end_time VARCHAR(10),
        room VARCHAR(50)
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
        term_id INTEGER REFERENCES terms(id) ON DELETE CASCADE,
        date VARCHAR(20),
        status VARCHAR(20),
        notes TEXT,
        recorded_by INTEGER REFERENCES users(id) ON DELETE SET NULL
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS marks (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
        term_id INTEGER REFERENCES terms(id) ON DELETE CASCADE,
        subject VARCHAR(150),
        coursework_score FLOAT DEFAULT 0,
        coursework_total FLOAT DEFAULT 20,
        coursework_out_of_20 FLOAT DEFAULT 0,
        midterm_score FLOAT DEFAULT 0,
        midterm_total FLOAT DEFAULT 20,
        midterm_out_of_20 FLOAT DEFAULT 0,
        endterm_score FLOAT DEFAULT 0,
        endterm_total FLOAT DEFAULT 60,
        endterm_out_of_60 FLOAT DEFAULT 0,
        total FLOAT DEFAULT 0,
        grade VARCHAR(5),
        comment TEXT,
        submitted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        submitted_at VARCHAR(50)
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS behavior_components (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        name VARCHAR(100),
        display_label VARCHAR(200),
        display_order INTEGER DEFAULT 99,
        active BOOLEAN DEFAULT true
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS behavior_records (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
        term_id INTEGER REFERENCES terms(id) ON DELETE CASCADE,
        component_id INTEGER REFERENCES behavior_components(id) ON DELETE CASCADE,
        value VARCHAR(50),
        evaluated_by INTEGER REFERENCES users(id) ON DELETE SET NULL
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS student_decisions (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
        term_id INTEGER REFERENCES terms(id) ON DELETE CASCADE,
        decision VARCHAR(50),
        notes TEXT,
        decided_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        decided_at VARCHAR(50)
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS discipline_reports (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
        reported_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        incident_date VARCHAR(20),
        incident_type VARCHAR(100),
        description TEXT,
        action_taken TEXT,
        admin_notes TEXT,
        status VARCHAR(30) DEFAULT 'Pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS report_designs (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        school_name VARCHAR(200),
        school_subtitle VARCHAR(200),
        school_address TEXT,
        school_po_box VARCHAR(100),
        school_phone VARCHAR(50),
        school_email VARCHAR(100),
        school_website VARCHAR(150),
        primary_color VARCHAR(20) DEFAULT '#1e3a8a',
        report_footer TEXT,
        logo_data TEXT
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS fee_structures (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        term_id INTEGER REFERENCES terms(id) ON DELETE CASCADE,
        class_name VARCHAR(100),
        item_name VARCHAR(200),
        amount NUMERIC(12,2),
        is_optional BOOLEAN DEFAULT false,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS invoices (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
        term_id INTEGER REFERENCES terms(id) ON DELETE CASCADE,
        invoice_number VARCHAR(50),
        total_amount NUMERIC(12,2) DEFAULT 0,
        paid_amount NUMERIC(12,2) DEFAULT 0,
        balance NUMERIC(12,2) DEFAULT 0,
        status VARCHAR(20) DEFAULT 'unpaid',
        due_date VARCHAR(20),
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS invoice_items (
        id SERIAL PRIMARY KEY,
        invoice_id INTEGER REFERENCES invoices(id) ON DELETE CASCADE,
        description VARCHAR(200),
        amount NUMERIC(12,2)
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        invoice_id INTEGER REFERENCES invoices(id) ON DELETE CASCADE,
        student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
        receipt_number VARCHAR(50),
        amount NUMERIC(12,2),
        payment_method VARCHAR(50),
        reference VARCHAR(100),
        paid_by VARCHAR(200),
        received_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        notes TEXT,
        paid_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        sender_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        recipient_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        subject VARCHAR(300),
        body TEXT,
        is_broadcast BOOLEAN DEFAULT false,
        target_role VARCHAR(30),
        target_class VARCHAR(100),
        read BOOLEAN DEFAULT false,
        read_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS announcements (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        title VARCHAR(300),
        body TEXT,
        target_roles VARCHAR(200),
        target_classes VARCHAR(500),
        is_pinned BOOLEAN DEFAULT false,
        expires_at VARCHAR(20),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS books (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        title VARCHAR(300) NOT NULL,
        author VARCHAR(200),
        isbn VARCHAR(50),
        publisher VARCHAR(200),
        year_published VARCHAR(10),
        category VARCHAR(100),
        total_copies INTEGER DEFAULT 1,
        available_copies INTEGER DEFAULT 1,
        location VARCHAR(100),
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS book_borrowings (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
        borrower_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        borrower_name VARCHAR(200),
        borrowed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        due_date VARCHAR(20),
        returned_at TIMESTAMP,
        fine_amount NUMERIC(10,2) DEFAULT 0,
        fine_paid BOOLEAN DEFAULT false,
        status VARCHAR(20) DEFAULT 'borrowed'
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id SERIAL PRIMARY KEY,
        school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
        created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        title VARCHAR(300),
        description TEXT,
        event_type VARCHAR(50),
        start_date VARCHAR(20),
        end_date VARCHAR(20),
        start_time VARCHAR(10),
        end_time VARCHAR(10),
        location VARCHAR(200),
        target_classes VARCHAR(500),
        is_public BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")


def _seed_data(cur, conn):
    # Seed master admin
    cur.execute("SELECT COUNT(*) FROM system_users")
    if cur.fetchone()[0] == 0:
        pw = hashlib.sha256(b'masteradmin123').hexdigest()
        cur.execute(
            "INSERT INTO system_users (name, email, password_hash) VALUES (%s,%s,%s)",
            ('Master Administrator', 'master@empower.sch', pw))
        conn.commit()
        print("  Seeded master admin: master@empower.sch / masteradmin123")

    # Seed demo school
    cur.execute("SELECT COUNT(*) FROM schools")
    if cur.fetchone()[0] == 0:
        cur.execute("""
            INSERT INTO schools (name, subtitle, primary_color, currency, country)
            VALUES (%s,%s,%s,%s,%s) RETURNING id""",
            ('Empower International Academy', 'Excellence · Integrity · Action',
             '#1e3a8a', 'UGX', 'Uganda'))
        school_id = cur.fetchone()[0]
        conn.commit()

        # Seed school admin
        pw = hashlib.sha256(b'admin123').hexdigest()
        cur.execute("""
            INSERT INTO users (school_id, name, email, role, password_hash, must_change_pw)
            VALUES (%s,%s,%s,%s,%s,false) RETURNING id""",
            (school_id, 'School Administrator', 'admin', 'admin', pw))
        conn.commit()

        # Seed default behavior components
        components = [
            ('punctuality','Punctuality',0), ('attendance','Attendance',1),
            ('manners','Manners',2), ('general_behavior','General Behavior',3),
            ('organisational_skills','Organisational Skills',4),
            ('adherence_to_uniform','Adherence to Uniform',5),
            ('leadership_skills','Leadership Skills',6),
            ('commitment_to_school','Commitment to School',7),
            ('cooperation_with_peers','Cooperation with Peers',8),
            ('cooperation_with_staff','Cooperation with Staff',9),
            ('participation_in_lessons','Participation in Lessons',10),
            ('completion_of_homework','Completion of Homework',11),
        ]
        for name, label, order in components:
            cur.execute(
                "INSERT INTO behavior_components (school_id,name,display_label,display_order,active) VALUES (%s,%s,%s,%s,true)",
                (school_id, name, label, order))

        # Seed report design
        cur.execute(
            "INSERT INTO report_designs (school_id,school_name,primary_color) VALUES (%s,%s,%s)",
            (school_id, 'Empower International Academy', '#1e3a8a'))
        conn.commit()
        print(f"  Seeded demo school (id={school_id}): admin / admin123")
