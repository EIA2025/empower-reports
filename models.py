# models.py — Empower School Administration System
# All SQLAlchemy models for every module
from sqlalchemy import (Column, Integer, String, Float, Text, ForeignKey,
                        DateTime, Boolean, Date, Numeric)
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

# ── SYSTEM / MULTI-SCHOOL ─────────────────────────────────────────────────────

class School(Base):
    """One row per school — supports multi-school deployment."""
    __tablename__ = 'schools'
    id              = Column(Integer, primary_key=True)
    name            = Column(String(200), nullable=False)
    subtitle        = Column(String(200))
    address         = Column(Text)
    po_box          = Column(String(100))
    phone           = Column(String(50))
    email           = Column(String(100))
    website         = Column(String(150))
    logo_data       = Column(Text)          # base64 PNG stored in DB
    motto           = Column(String(300))
    primary_color   = Column(String(20), default='#1e3a8a')
    report_footer   = Column(Text)
    country         = Column(String(100))
    currency        = Column(String(10), default='UGX')
    plan            = Column(String(50), default='trial')
    plan_expires    = Column(String(20))
    max_students    = Column(Integer, default=500)
    max_staff       = Column(Integer, default=50)
    notes           = Column(Text)
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.now)


class SystemUser(Base):
    """Master admin accounts — can manage all schools."""
    __tablename__ = 'system_users'
    id              = Column(Integer, primary_key=True)
    name            = Column(String(200))
    email           = Column(String(200), unique=True)
    password_hash   = Column(String(256))
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.now)
    last_login      = Column(DateTime)


class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id          = Column(Integer, primary_key=True)
    school_id   = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    user_id     = Column(Integer)
    user_role   = Column(String(50))
    action      = Column(String(200))
    details     = Column(Text)
    ip_address  = Column(String(50))
    timestamp   = Column(DateTime, default=datetime.now)


# ── PEOPLE MODULE ─────────────────────────────────────────────────────────────

class User(Base):
    """Login account for any role: admin, teacher, parent, student, bursar."""
    __tablename__ = 'users'
    id                  = Column(Integer, primary_key=True)
    school_id           = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    name                = Column(String(200), nullable=False)
    email               = Column(String(200))           # used as username
    phone               = Column(String(30))
    role                = Column(String(30), nullable=False)  # admin|teacher|parent|student|bursar
    password_hash       = Column(String(256))
    profile_photo       = Column(Text)                  # base64
    gender              = Column(String(20))
    date_of_birth       = Column(String(20))
    address             = Column(Text)
    national_id         = Column(String(50))
    is_active           = Column(Boolean, default=True)
    must_change_pw      = Column(Boolean, default=True)
    recovery_phone      = Column(String(30))
    recovery_city       = Column(String(100))
    recovery_nickname   = Column(String(100))
    created_at          = Column(DateTime, default=datetime.now)
    last_login          = Column(DateTime)


class Student(Base):
    __tablename__ = 'students'
    id                  = Column(Integer, primary_key=True)
    school_id           = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    user_id             = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))  # portal login
    admission_number    = Column(String(50))
    name                = Column(String(200), nullable=False)
    gender              = Column(String(20))
    date_of_birth       = Column(String(20))
    nationality         = Column(String(100))
    religion            = Column(String(100))
    photo               = Column(Text)                  # base64
    class_name          = Column(String(100))
    stream              = Column(String(50))            # e.g. A, B, West
    year                = Column(Integer)
    subjects            = Column(Text)                  # JSON list
    enrolment_date      = Column(String(20))
    enrolment_status    = Column(String(30), default='active')  # active|alumni|transferred|withdrawn
    previous_school     = Column(String(200))
    medical_notes       = Column(Text)
    created_at          = Column(DateTime, default=datetime.now)


class Guardian(Base):
    """Parent or guardian — can be linked to multiple students."""
    __tablename__ = 'guardians'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    user_id         = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))  # portal login
    name            = Column(String(200), nullable=False)
    relationship    = Column(String(50))    # Mother|Father|Uncle|Guardian|etc
    phone           = Column(String(30))
    alt_phone       = Column(String(30))
    email           = Column(String(150))
    address         = Column(Text)
    occupation      = Column(String(150))
    national_id     = Column(String(50))
    is_primary      = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.now)


class StudentGuardian(Base):
    """Many-to-many: students ↔ guardians."""
    __tablename__ = 'student_guardians'
    id          = Column(Integer, primary_key=True)
    student_id  = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    guardian_id = Column(Integer, ForeignKey('guardians.id', ondelete='CASCADE'))
    is_primary  = Column(Boolean, default=False)


class Staff(Base):
    __tablename__ = 'staff'
    id                  = Column(Integer, primary_key=True)
    school_id           = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    user_id             = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    employee_number     = Column(String(50))
    name                = Column(String(200), nullable=False)
    gender              = Column(String(20))
    date_of_birth       = Column(String(20))
    phone               = Column(String(30))
    email               = Column(String(150))
    address             = Column(Text)
    national_id         = Column(String(50))
    photo               = Column(Text)                  # base64
    department          = Column(String(100))
    job_title           = Column(String(150))
    subjects_taught     = Column(Text)                  # comma-separated
    classes_taught      = Column(Text)                  # comma-separated
    class_teacher_for   = Column(String(100))
    employment_type     = Column(String(50))            # permanent|contract|part-time
    employment_date     = Column(String(20))
    qualification       = Column(Text)
    is_active           = Column(Boolean, default=True)
    created_at          = Column(DateTime, default=datetime.now)


class Class(Base):
    """A class definition — e.g. S1 West, P3 A."""
    __tablename__ = 'classes'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    name            = Column(String(100), nullable=False)
    stream          = Column(String(50))
    level           = Column(String(50))            # Primary|Secondary|A-Level
    class_teacher   = Column(Integer, ForeignKey('staff.id', ondelete='SET NULL'))
    capacity        = Column(Integer)
    room            = Column(String(50))
    is_active       = Column(Boolean, default=True)


# ── ACADEMICS MODULE ──────────────────────────────────────────────────────────

class AcademicYear(Base):
    __tablename__ = 'academic_years'
    id          = Column(Integer, primary_key=True)
    school_id   = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    name        = Column(String(100))       # e.g. "2025"
    start_date  = Column(String(20))
    end_date    = Column(String(20))
    is_active   = Column(Boolean, default=False)


class Term(Base):
    __tablename__ = 'terms'
    id                  = Column(Integer, primary_key=True)
    school_id           = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    academic_year_id    = Column(Integer, ForeignKey('academic_years.id', ondelete='CASCADE'))
    name                = Column(String(100))       # e.g. "Term 1 2025"
    term_number         = Column(Integer)
    start_date          = Column(String(20))
    end_date            = Column(String(20))
    next_term_begins    = Column(String(20))
    is_active           = Column(Boolean, default=False)


class Subject(Base):
    __tablename__ = 'subjects'
    id          = Column(Integer, primary_key=True)
    school_id   = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    name        = Column(String(150), nullable=False)
    code        = Column(String(20))
    level       = Column(String(50))
    is_active   = Column(Boolean, default=True)


class Timetable(Base):
    __tablename__ = 'timetable'
    id          = Column(Integer, primary_key=True)
    school_id   = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    class_id    = Column(Integer, ForeignKey('classes.id', ondelete='CASCADE'))
    term_id     = Column(Integer, ForeignKey('terms.id', ondelete='CASCADE'))
    staff_id    = Column(Integer, ForeignKey('staff.id', ondelete='SET NULL'))
    subject_id  = Column(Integer, ForeignKey('subjects.id', ondelete='CASCADE'))
    day_of_week = Column(String(10))        # Monday–Friday
    start_time  = Column(String(10))
    end_time    = Column(String(10))
    room        = Column(String(50))


class Attendance(Base):
    __tablename__ = 'attendance'
    id          = Column(Integer, primary_key=True)
    school_id   = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    student_id  = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    term_id     = Column(Integer, ForeignKey('terms.id', ondelete='CASCADE'))
    date        = Column(String(20))
    status      = Column(String(20))    # present|absent|late|excused
    notes       = Column(Text)
    recorded_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))


class Mark(Base):
    __tablename__ = 'marks'
    id                      = Column(Integer, primary_key=True)
    school_id               = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    student_id              = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    term_id                 = Column(Integer, ForeignKey('terms.id', ondelete='CASCADE'))
    subject                 = Column(String(150))
    coursework_score        = Column(Float, default=0)
    coursework_total        = Column(Float, default=20)
    coursework_out_of_20    = Column(Float, default=0)
    midterm_score           = Column(Float, default=0)
    midterm_total           = Column(Float, default=20)
    midterm_out_of_20       = Column(Float, default=0)
    endterm_score           = Column(Float, default=0)
    endterm_total           = Column(Float, default=60)
    endterm_out_of_60       = Column(Float, default=0)
    total                   = Column(Float, default=0)
    grade                   = Column(String(5))
    comment                 = Column(Text)
    submitted_by            = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    submitted_at            = Column(String(50))


class BehaviorComponent(Base):
    __tablename__ = 'behavior_components'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    name            = Column(String(100))
    display_label   = Column(String(200))
    display_order   = Column(Integer, default=99)
    active          = Column(Boolean, default=True)


class BehaviorRecord(Base):
    __tablename__ = 'behavior_records'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    student_id      = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    term_id         = Column(Integer, ForeignKey('terms.id', ondelete='CASCADE'))
    component_id    = Column(Integer, ForeignKey('behavior_components.id', ondelete='CASCADE'))
    value           = Column(String(50))    # Excellent|Good|Satisfactory|Cause of Concern
    evaluated_by    = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))


class StudentDecision(Base):
    __tablename__ = 'student_decisions'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    student_id      = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    term_id         = Column(Integer, ForeignKey('terms.id', ondelete='CASCADE'))
    decision        = Column(String(50))    # Promoted|Repeated|Transferred|Withdrawn|Graduated
    notes           = Column(Text)
    decided_by      = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    decided_at      = Column(String(50))


class DisciplineReport(Base):
    __tablename__ = 'discipline_reports'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    student_id      = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    reported_by     = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    incident_date   = Column(String(20))
    incident_type   = Column(String(100))
    description     = Column(Text)
    action_taken    = Column(Text)
    admin_notes     = Column(Text)
    status          = Column(String(30), default='Pending')
    created_at      = Column(DateTime, default=datetime.now)


class ReportDesign(Base):
    __tablename__ = 'report_designs'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    school_name     = Column(String(200))
    school_subtitle = Column(String(200))
    school_address  = Column(Text)
    school_po_box   = Column(String(100))
    school_phone    = Column(String(50))
    school_email    = Column(String(100))
    school_website  = Column(String(150))
    primary_color   = Column(String(20), default='#1e3a8a')
    report_footer   = Column(Text)
    logo_data       = Column(Text)


# ── FINANCE MODULE ────────────────────────────────────────────────────────────

class FeeStructure(Base):
    __tablename__ = 'fee_structures'
    id          = Column(Integer, primary_key=True)
    school_id   = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    term_id     = Column(Integer, ForeignKey('terms.id', ondelete='CASCADE'))
    class_name  = Column(String(100))
    item_name   = Column(String(200))   # Tuition|Lunch|Transport|etc
    amount      = Column(Numeric(12,2))
    is_optional = Column(Boolean, default=False)
    created_at  = Column(DateTime, default=datetime.now)


class Invoice(Base):
    __tablename__ = 'invoices'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    student_id      = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    term_id         = Column(Integer, ForeignKey('terms.id', ondelete='CASCADE'))
    invoice_number  = Column(String(50))
    total_amount    = Column(Numeric(12,2), default=0)
    paid_amount     = Column(Numeric(12,2), default=0)
    balance         = Column(Numeric(12,2), default=0)
    status          = Column(String(20), default='unpaid')  # unpaid|partial|paid
    due_date        = Column(String(20))
    notes           = Column(Text)
    created_at      = Column(DateTime, default=datetime.now)


class InvoiceItem(Base):
    __tablename__ = 'invoice_items'
    id          = Column(Integer, primary_key=True)
    invoice_id  = Column(Integer, ForeignKey('invoices.id', ondelete='CASCADE'))
    description = Column(String(200))
    amount      = Column(Numeric(12,2))


class Payment(Base):
    __tablename__ = 'payments'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    invoice_id      = Column(Integer, ForeignKey('invoices.id', ondelete='CASCADE'))
    student_id      = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    receipt_number  = Column(String(50))
    amount          = Column(Numeric(12,2))
    payment_method  = Column(String(50))    # cash|mobile_money|bank|cheque
    reference       = Column(String(100))
    paid_by         = Column(String(200))   # Name of payer
    received_by     = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    notes           = Column(Text)
    paid_at         = Column(DateTime, default=datetime.now)


# ── COMMUNICATIONS MODULE ─────────────────────────────────────────────────────

class Message(Base):
    __tablename__ = 'messages'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    sender_id       = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    recipient_id    = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    subject         = Column(String(300))
    body            = Column(Text)
    is_broadcast    = Column(Boolean, default=False)
    target_role     = Column(String(30))    # all|admin|teacher|parent|student
    target_class    = Column(String(100))
    read            = Column(Boolean, default=False)
    read_at         = Column(DateTime)
    created_at      = Column(DateTime, default=datetime.now)


class Announcement(Base):
    __tablename__ = 'announcements'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    created_by      = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    title           = Column(String(300))
    body            = Column(Text)
    target_roles    = Column(String(200))   # comma list: parent,student,teacher
    target_classes  = Column(String(500))   # comma list or 'all'
    is_pinned       = Column(Boolean, default=False)
    expires_at      = Column(String(20))
    created_at      = Column(DateTime, default=datetime.now)


# ── LIBRARY MODULE ────────────────────────────────────────────────────────────

class Book(Base):
    __tablename__ = 'books'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    title           = Column(String(300), nullable=False)
    author          = Column(String(200))
    isbn            = Column(String(50))
    publisher       = Column(String(200))
    year_published  = Column(String(10))
    category        = Column(String(100))
    total_copies    = Column(Integer, default=1)
    available_copies= Column(Integer, default=1)
    location        = Column(String(100))
    added_at        = Column(DateTime, default=datetime.now)


class BookBorrowing(Base):
    __tablename__ = 'book_borrowings'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    book_id         = Column(Integer, ForeignKey('books.id', ondelete='CASCADE'))
    borrower_id     = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    borrower_name   = Column(String(200))
    borrowed_at     = Column(DateTime, default=datetime.now)
    due_date        = Column(String(20))
    returned_at     = Column(DateTime)
    fine_amount     = Column(Numeric(10,2), default=0)
    fine_paid       = Column(Boolean, default=False)
    status          = Column(String(20), default='borrowed')  # borrowed|returned|overdue


# ── EVENTS MODULE ─────────────────────────────────────────────────────────────

class Event(Base):
    __tablename__ = 'events'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    created_by      = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    title           = Column(String(300))
    description     = Column(Text)
    event_type      = Column(String(50))    # academic|sports|cultural|holiday|exam|meeting
    start_date      = Column(String(20))
    end_date        = Column(String(20))
    start_time      = Column(String(10))
    end_time        = Column(String(10))
    location        = Column(String(200))
    target_classes  = Column(String(500))   # 'all' or comma list
    is_public       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.now)


# ── SYSTEM TABLES ─────────────────────────────────────────────────────────────

class SystemAnnouncement(Base):
    __tablename__ = 'system_announcements'
    id          = Column(Integer, primary_key=True)
    created_by  = Column(Integer)
    title       = Column(String(300), nullable=False)
    body        = Column(Text)
    target      = Column(String(50), default='all')   # all|admin|teacher
    is_active   = Column(Boolean, default=True)
    expires_at  = Column(String(20))
    created_at  = Column(DateTime, default=datetime.now)


class SystemSetting(Base):
    __tablename__ = 'system_settings'
    id         = Column(Integer, primary_key=True)
    key        = Column(String(100), unique=True, nullable=False)
    value      = Column(Text)
    updated_at = Column(DateTime, default=datetime.now)


# ── HEALTH & MEDICAL MODULE ──────────────────────────────────────────────────

class StudentAllergy(Base):
    """Student allergies"""
    __tablename__ = 'student_allergies'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    student_id      = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    allergen        = Column(String(100), nullable=False)
    severity        = Column(String(50), default='mild')  # mild, moderate, severe
    symptoms        = Column(Text)
    treatment       = Column(Text)
    notes           = Column(Text)
    created_at      = Column(DateTime, default=datetime.now)


class StudentMedicalCondition(Base):
    """Student medical conditions"""
    __tablename__ = 'student_medical_conditions'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    student_id      = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    condition       = Column(String(100), nullable=False)
    diagnosed_date  = Column(String(20))
    description     = Column(Text)
    medication      = Column(Text)
    restrictions    = Column(Text)
    notes           = Column(Text)
    created_at      = Column(DateTime, default=datetime.now)


class EmergencyContact(Base):
    """Student emergency contacts"""
    __tablename__ = 'emergency_contacts'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    student_id      = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    name            = Column(String(100), nullable=False)
    relationship    = Column(String(50), nullable=False)
    phone           = Column(String(20), nullable=False)
    email           = Column(String(120))
    address         = Column(Text)
    is_primary      = Column(Boolean, default=False)
    notes           = Column(Text)
    created_at      = Column(DateTime, default=datetime.now)


class VaccinationRecord(Base):
    """Student vaccination records"""
    __tablename__ = 'vaccination_records'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    student_id      = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    vaccine_name    = Column(String(100), nullable=False)
    vaccination_date= Column(String(20), nullable=False)
    batch_number    = Column(String(50))
    administered_by = Column(String(100))
    facility        = Column(String(100))
    next_dose_date  = Column(String(20))
    certificate_uploaded = Column(Boolean, default=False)
    notes           = Column(Text)
    created_at      = Column(DateTime, default=datetime.now)


class ClinicVisit(Base):
    """Clinic visit records"""
    __tablename__ = 'clinic_visits'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    student_id      = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    visit_date      = Column(String(20), nullable=False)
    complaint       = Column(Text, nullable=False)
    diagnosis       = Column(Text)
    treatment_given = Column(Text)
    referred        = Column(Boolean, default=False)
    referred_to     = Column(String(100))
    follow_up_date  = Column(String(20))
    notes           = Column(Text)
    created_at      = Column(DateTime, default=datetime.now)


class MedicationAdministration(Base):
    """Medication administration records"""
    __tablename__ = 'medication_administration'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    student_id      = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    medication_name = Column(String(100), nullable=False)
    dosage          = Column(String(100))
    frequency       = Column(String(50))
    start_date      = Column(String(20))
    end_date        = Column(String(20))
    prescribed_by   = Column(String(100))
    given_by        = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    notes           = Column(Text)
    created_at      = Column(DateTime, default=datetime.now)


# ── TRANSPORT MODULE ──────────────────────────────────────────────────────────

class Bus(Base):
    """School bus"""
    __tablename__ = 'buses'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    bus_number      = Column(String(20), nullable=False)
    plate_number    = Column(String(20))
    model           = Column(String(100))
    capacity        = Column(Integer, default=50)
    driver_id       = Column(Integer, ForeignKey('drivers.id', ondelete='SET NULL'))
    is_active       = Column(Boolean, default=True)
    notes           = Column(Text)
    created_at      = Column(DateTime, default=datetime.now)


class Driver(Base):
    """Bus driver"""
    __tablename__ = 'drivers'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    name            = Column(String(100), nullable=False)
    phone           = Column(String(20))
    license_number  = Column(String(50))
    license_expiry  = Column(String(20))
    address         = Column(Text)
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.now)


class BusRoute(Base):
    """Bus route"""
    __tablename__ = 'bus_routes'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    bus_id          = Column(Integer, ForeignKey('buses.id', ondelete='SET NULL'))
    name            = Column(String(100), nullable=False)
    description     = Column(Text)
    departure_time  = Column(String(10))
    arrival_time    = Column(String(10))
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.now)


class BusStop(Base):
    """Stop on a bus route"""
    __tablename__ = 'bus_stops'
    id              = Column(Integer, primary_key=True)
    route_id        = Column(Integer, ForeignKey('bus_routes.id', ondelete='CASCADE'))
    stop_number     = Column(Integer, default=1)
    stop_name       = Column(String(100), nullable=False)
    stop_location   = Column(String(255))
    arrival_time    = Column(String(10))
    created_at      = Column(DateTime, default=datetime.now)


class BusAssignment(Base):
    """Student assigned to a bus route"""
    __tablename__ = 'bus_assignments'
    id              = Column(Integer, primary_key=True)
    student_id      = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    route_id        = Column(Integer, ForeignKey('bus_routes.id', ondelete='CASCADE'))
    pickup_stop_id  = Column(Integer, ForeignKey('bus_stops.id', ondelete='SET NULL'))
    dropoff_stop_id = Column(Integer, ForeignKey('bus_stops.id', ondelete='SET NULL'))
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.now)


class BusAttendance(Base):
    """Bus attendance record per trip"""
    __tablename__ = 'bus_attendance'
    id              = Column(Integer, primary_key=True)
    assignment_id   = Column(Integer, ForeignKey('bus_assignments.id', ondelete='CASCADE'))
    date            = Column(String(20), nullable=False)
    trip_type       = Column(String(10), default='morning')
    status          = Column(String(20), default='present')
    notes           = Column(Text)
    created_at      = Column(DateTime, default=datetime.now)


# ── HOSTEL MODULE ─────────────────────────────────────────────────────────────

class Dormitory(Base):
    """Dormitory"""
    __tablename__ = 'dormitories'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    name            = Column(String(100), nullable=False)
    block           = Column(String(10))
    total_rooms     = Column(Integer)
    created_at      = Column(DateTime, default=datetime.now)


class Room(Base):
    """Hostel room"""
    __tablename__ = 'rooms'
    id              = Column(Integer, primary_key=True)
    dormitory_id    = Column(Integer, ForeignKey('dormitories.id', ondelete='CASCADE'))
    room_number     = Column(String(20), nullable=False)
    capacity        = Column(Integer, default=2)
    created_at      = Column(DateTime, default=datetime.now)


class Bed(Base):
    """Bed in hostel room"""
    __tablename__ = 'beds'
    id              = Column(Integer, primary_key=True)
    room_id         = Column(Integer, ForeignKey('rooms.id', ondelete='CASCADE'))
    bed_number      = Column(String(10))
    is_occupied     = Column(Boolean, default=False)
    created_at      = Column(DateTime, default=datetime.now)


class HostelAllocation(Base):
    """Student hostel allocation"""
    __tablename__ = 'hostel_allocations'
    id              = Column(Integer, primary_key=True)
    student_id      = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    bed_id          = Column(Integer, ForeignKey('beds.id', ondelete='CASCADE'))
    allocation_date = Column(String(20), default=datetime.now)
    release_date    = Column(String(20))
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.now)


# ── LEARNING MATERIALS MODULE ────────────────────────────────────────────────

class LearningMaterial(Base):
    """Learning Material uploaded by teacher"""
    __tablename__ = 'learning_materials'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    title           = Column(String(255), nullable=False)
    description     = Column(Text)
    subject_id      = Column(Integer, ForeignKey('subjects.id', ondelete='SET NULL'))
    class_id        = Column(Integer, ForeignKey('classes.id', ondelete='SET NULL'))
    teacher_id      = Column(Integer, ForeignKey('staff.id', ondelete='SET NULL'))
    file_path       = Column(String(500))
    file_name       = Column(String(255))
    file_size       = Column(Integer, default=0)
    file_type       = Column(String(50))  # pdf, video, pptx, worksheet, notes
    download_count  = Column(Integer, default=0)
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.now)


class Assignment(Base):
    """Student Assignment"""
    __tablename__ = 'assignments'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    title           = Column(String(255), nullable=False)
    instructions    = Column(Text)
    subject_id      = Column(Integer, ForeignKey('subjects.id', ondelete='SET NULL'))
    class_id        = Column(Integer, ForeignKey('classes.id', ondelete='SET NULL'))
    teacher_id      = Column(Integer, ForeignKey('staff.id', ondelete='SET NULL'))
    due_date        = Column(String(20))
    max_score       = Column(Float, default=100)
    attachment_path = Column(String(500))
    file_name       = Column(String(255))
    file_size       = Column(Integer, default=0)
    download_count  = Column(Integer, default=0)
    status          = Column(String(50), default='active')  # active, closed
    created_at      = Column(DateTime, default=datetime.now)


class AssignmentSubmission(Base):
    """Student submission for an assignment"""
    __tablename__ = 'assignment_submissions'
    id              = Column(Integer, primary_key=True)
    assignment_id   = Column(Integer, ForeignKey('assignments.id', ondelete='CASCADE'))
    student_id      = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    submitted_at    = Column(String(20))
    file_path       = Column(String(500))
    content         = Column(Text)
    score           = Column(Float)
    teacher_comments= Column(Text)
    status          = Column(String(50), default='submitted')  # submitted, graded, late, missing
    created_at      = Column(DateTime, default=datetime.now)


class LessonPlan(Base):
    """Lesson Plan"""
    __tablename__ = 'lesson_plans'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    title           = Column(String(255), nullable=False)
    subject_id      = Column(Integer, ForeignKey('subjects.id', ondelete='SET NULL'))
    class_id        = Column(Integer, ForeignKey('classes.id', ondelete='SET NULL'))
    teacher_id      = Column(Integer, ForeignKey('staff.id', ondelete='SET NULL'))
    lesson_date     = Column(String(20))
    duration_minutes= Column(Integer, default=60)
    objectives      = Column(Text)
    activities      = Column(Text)
    resources       = Column(Text)
    homework        = Column(Text)
    status          = Column(String(50), default='draft')  # draft, approved, completed
    file_name       = Column(String(255))
    file_size       = Column(Integer, default=0)
    download_count  = Column(Integer, default=0)
    created_at      = Column(DateTime, default=datetime.now)


class SchemeOfWork(Base):
    """Scheme of Work"""
    __tablename__ = 'schemes_of_work'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    subject_id      = Column(Integer, ForeignKey('subjects.id', ondelete='SET NULL'))
    class_id        = Column(Integer, ForeignKey('classes.id', ondelete='SET NULL'))
    teacher_id      = Column(Integer, ForeignKey('staff.id', ondelete='SET NULL'))
    term_id         = Column(Integer, ForeignKey('terms.id', ondelete='SET NULL'))
    topic           = Column(String(255), nullable=False)
    subtopic        = Column(String(255))
    week_number     = Column(Integer)
    teaching_date   = Column(String(20))
    status          = Column(String(50), default='pending')  # pending, in_progress, completed
    file_name       = Column(String(255))
    file_size       = Column(Integer, default=0)
    download_count  = Column(Integer, default=0)
    created_at      = Column(DateTime, default=datetime.now)


class GradeBookEntry(Base):
    """Gradebook entry for continuous assessment"""
    __tablename__ = 'gradebook_entries'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    student_id      = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    subject_id      = Column(Integer, ForeignKey('subjects.id', ondelete='SET NULL'))
    teacher_id      = Column(Integer, ForeignKey('staff.id', ondelete='SET NULL'))
    class_id        = Column(Integer, ForeignKey('classes.id', ondelete='SET NULL'))
    assessment_type = Column(String(100))  # Homework, Quiz, CAT, Midterm, Final, Coursework, Project
    title           = Column(String(255))
    score           = Column(Float)
    max_score       = Column(Float, default=100)
    comments        = Column(Text)
    date_recorded   = Column(String(20))
    created_at      = Column(DateTime, default=datetime.now)


# ── ENHANCED EXAM & GRADING ───────────────────────────────────────────────────

class Exam(Base):
    """Exam with workflow state"""
    __tablename__ = 'exams'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    term_id         = Column(Integer, ForeignKey('terms.id', ondelete='CASCADE'))
    subject_id      = Column(Integer, ForeignKey('subjects.id', ondelete='SET NULL'))
    name            = Column(String(100), nullable=False)
    exam_type       = Column(String(50))  # midterm, final, unit_test
    grading_system  = Column(String(50), default='percentage')  # percentage, gpa, cambridge, ib
    total_marks     = Column(Float, default=100.0)
    passing_marks   = Column(Float, default=40.0)
    scheduled_date  = Column(String(20))
    created_by      = Column(Integer, ForeignKey('staff.id', ondelete='SET NULL'))
    is_locked       = Column(Boolean, default=False)
    is_approved     = Column(Boolean, default=False)
    is_published    = Column(Boolean, default=False)
    locked_at       = Column(String(20))
    approved_at     = Column(String(20))
    published_at    = Column(String(20))
    created_at      = Column(DateTime, default=datetime.now)


class ExamMark(Base):
    """Student exam marks"""
    __tablename__ = 'exam_marks'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    exam_id         = Column(Integer, ForeignKey('exams.id', ondelete='CASCADE'))
    student_id      = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    class_id        = Column(Integer, ForeignKey('classes.id', ondelete='SET NULL'))
    marks_obtained  = Column(Float)
    is_absent       = Column(Boolean, default=False)
    comments        = Column(Text)
    created_at      = Column(DateTime, default=datetime.now)


# ── ENHANCED FINANCE ──────────────────────────────────────────────────────────

class Scholarship(Base):
    """Scholarship"""
    __tablename__ = 'scholarships'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    student_id      = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    name            = Column(String(100), nullable=False)
    percentage      = Column(Float)
    amount          = Column(Numeric(12, 2))
    start_date      = Column(String(20), nullable=False)
    end_date        = Column(String(20))
    reason          = Column(Text)
    created_at      = Column(DateTime, default=datetime.now)


class Receipt(Base):
    """Payment receipt"""
    __tablename__ = 'receipts'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    payment_id      = Column(Integer, ForeignKey('payments.id', ondelete='CASCADE'))
    receipt_number  = Column(String(50), nullable=False)
    receipt_date    = Column(String(20), default=datetime.now)
    issued_by       = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    amount          = Column(Numeric(12, 2), nullable=False)
    payment_method  = Column(String(50))
    reference_number= Column(String(100))
    currency        = Column(String(3), default='UGX')
    email_sent      = Column(Boolean, default=False)
    email_sent_date = Column(String(20))
    notes           = Column(Text)
    created_at      = Column(DateTime, default=datetime.now)


class FinancialReport(Base):
    """Financial reports"""
    __tablename__ = 'financial_reports'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    academic_year_id= Column(Integer, ForeignKey('academic_years.id', ondelete='SET NULL'))
    report_type     = Column(String(50))  # revenue, outstanding, collection, cash_flow, summary
    generated_date  = Column(String(20), default=datetime.now)
    generated_by    = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    period_start    = Column(String(20))
    period_end      = Column(String(20))
    total_invoiced  = Column(Numeric(12, 2), default=0)
    total_collected = Column(Numeric(12, 2), default=0)
    total_outstanding=Column(Numeric(12, 2), default=0)
    total_discounts = Column(Numeric(12, 2), default=0)
    collection_rate = Column(Float)
    report_data     = Column(Text)  # JSON
    currency        = Column(String(3), default='UGX')
    notes           = Column(Text)
    created_at      = Column(DateTime, default=datetime.now)


# ── REPORT CARD & PERFORMANCE ────────────────────────────────────────────────

class ReportCard(Base):
    """Student Report Card"""
    __tablename__ = 'report_cards'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    student_id      = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    term_id         = Column(Integer, ForeignKey('terms.id', ondelete='CASCADE'))
    class_teacher_id= Column(Integer, ForeignKey('staff.id', ondelete='SET NULL'))
    teacher_comment = Column(Text)
    head_teacher_comment = Column(Text)
    principal_comment= Column(Text)
    conduct         = Column(String(50))  # Excellent, Good, Fair, Poor
    attendance_days = Column(Integer)
    days_present    = Column(Integer)
    position_in_class=Column(Integer)
    total_students  = Column(Integer)
    overall_average = Column(Float)
    status          = Column(String(50), default='draft')  # draft, submitted, approved, published
    submitted_at    = Column(String(20))
    approved_at     = Column(String(20))
    approved_by_id  = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'))
    generated_at    = Column(String(20))
    created_at      = Column(DateTime, default=datetime.now)


class Subscription(Base):
    """Subscription for recurring payments"""
    __tablename__ = 'subscriptions'
    id              = Column(Integer, primary_key=True)
    school_id       = Column(Integer, ForeignKey('schools.id', ondelete='CASCADE'))
    student_id      = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    service_name    = Column(String(100), nullable=False)
    amount          = Column(Numeric(12, 2), nullable=False)
    frequency       = Column(String(50))  # monthly, quarterly, annual
    start_date      = Column(String(20))
    end_date        = Column(String(20))
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.now)
