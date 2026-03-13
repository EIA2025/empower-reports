# models.py - SQLAlchemy ORM models (PostgreSQL compatible)
from sqlalchemy import (Column, Integer, String, Float, Text, ForeignKey,
                         DateTime, Boolean)
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String(200))
    email = Column(String(200), unique=True)
    role = Column(String(50))          # admin, teacher, master_admin
    password_hash = Column(String(256))
    subjects_taught = Column(Text)
    class_teacher_for = Column(Text)
    gender = Column(String(20))
    phone_number = Column(String(30))
    recovery_nickname = Column(String(200), nullable=True)
    recovery_phone = Column(String(30), nullable=True)
    recovery_city = Column(String(100), nullable=True)


class Student(Base):
    __tablename__ = 'students'
    id = Column(Integer, primary_key=True)
    name = Column(String(200))
    year = Column(Integer)
    class_name = Column(String(100))
    registration_number = Column(String(100))
    subjects = Column(Text)            # JSON array
    subject_history = Column(Text)
    gender = Column(String(20))
    enrollment_date = Column(String(50))


class AcademicTerm(Base):
    __tablename__ = 'academic_terms'
    id = Column(Integer, primary_key=True)
    year = Column(Integer)
    term_number = Column(Integer)
    term_name = Column(String(100))
    start_date = Column(String(50))
    end_date = Column(String(50))
    next_term_begins = Column(String(50))
    is_active = Column(Boolean, default=False)


class ComponentMark(Base):
    __tablename__ = 'component_marks'
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    subject = Column(String(100))
    term_id = Column(Integer, ForeignKey('academic_terms.id', ondelete='CASCADE'))
    component_type = Column(String(50))   # coursework / midterm / endterm
    component_name = Column(String(100))  # Test 1, Paper 1, etc.
    score = Column(Float)
    total = Column(Float)
    submitted_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    submitted_at = Column(String(50), default=lambda: datetime.now().isoformat())


class Mark(Base):
    __tablename__ = 'marks'
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    subject = Column(String(100))
    term_id = Column(Integer, ForeignKey('academic_terms.id', ondelete='CASCADE'))
    coursework_score = Column(Float)
    coursework_total = Column(Float)
    coursework_out_of_20 = Column(Float)
    midterm_score = Column(Float)
    midterm_total = Column(Float)
    midterm_out_of_20 = Column(Float)
    endterm_score = Column(Float)
    endterm_total = Column(Float)
    endterm_out_of_60 = Column(Float)
    total = Column(Float)
    grade = Column(String(10))
    comment = Column(Text)
    submitted_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    submitted_at = Column(String(50), default=lambda: datetime.now().isoformat())


class DisciplineReport(Base):
    __tablename__ = 'discipline_reports'
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    reported_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    incident_date = Column(String(50))
    incident_type = Column(String(100))
    description = Column(Text)
    action_taken = Column(Text)
    status = Column(String(50), default='Pending')
    admin_notes = Column(Text)
    created_at = Column(String(50), default=lambda: datetime.now().isoformat())


class ReportDesign(Base):
    __tablename__ = 'report_design'
    id = Column(Integer, primary_key=True)
    school_name = Column(String(200), default='EMPOWER INTERNATIONAL ACADEMY')
    school_subtitle = Column(String(300), default='A Christian Boarding International School')
    school_address = Column(String(300), default='Nswanjere - Off Kampala-Mityana Road')
    school_po_box = Column(String(200), default='P.O BOX 1030, Kampala-Uganda')
    school_phone = Column(String(50), default='')
    school_email = Column(String(100), default='')
    school_website = Column(String(200), default='')
    logo_data = Column(Text)           # base64 encoded
    primary_color = Column(String(20), default='#8B4513')
    report_footer = Column(Text, default='')


class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    action = Column(String(200))
    details = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)


class ClassroomBehavior(Base):
    """Legacy table kept for migration compatibility."""
    __tablename__ = 'classroom_behavior'
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    term_id = Column(Integer, ForeignKey('academic_terms.id', ondelete='CASCADE'))
    evaluated_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    punctuality = Column(String(50))
    attendance = Column(String(50))
    manners = Column(String(50))
    general_behavior = Column(String(50))
    organisational_skills = Column(String(50))
    adherence_to_uniform = Column(String(50))
    leadership_skills = Column(String(50))
    commitment_to_school = Column(String(50))
    cooperation_with_peers = Column(String(50))
    cooperation_with_staff = Column(String(50))
    participation_in_lessons = Column(String(50))
    completion_of_homework = Column(String(50))
    evaluated_at = Column(String(50), default=lambda: datetime.now().isoformat())


class BehaviorComponent(Base):
    __tablename__ = 'behavior_components'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True)
    display_label = Column(String(200))
    display_order = Column(Integer, default=0)
    active = Column(Boolean, default=True)


class ClassroomBehaviorResponse(Base):
    __tablename__ = 'classroom_behavior_responses'
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    term_id = Column(Integer, ForeignKey('academic_terms.id', ondelete='CASCADE'))
    component_id = Column(Integer, ForeignKey('behavior_components.id', ondelete='CASCADE'))
    value = Column(String(50))
    evaluated_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    evaluated_at = Column(String(50), default=lambda: datetime.now().isoformat())


class StudentDecision(Base):
    __tablename__ = 'student_decisions'
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    term_id = Column(Integer, ForeignKey('academic_terms.id', ondelete='CASCADE'))
    decision = Column(String(100))   # Promoted, Repeated, etc.
    decision_made_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    decision_date = Column(String(50), default=lambda: datetime.now().isoformat())
    notes = Column(Text)


class VisitationDay(Base):
    __tablename__ = 'visitation_days'
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey('students.id', ondelete='CASCADE'))
    term_id = Column(Integer, ForeignKey('academic_terms.id', ondelete='CASCADE'))
    visitation_date = Column(String(50))
    parent_attended = Column(Boolean, default=False)
    report_given = Column(Boolean, default=False)
    notes = Column(Text)
    created_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(String(50), default=lambda: datetime.now().isoformat())


class Message(Base):
    __tablename__ = 'messages'
    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    recipient_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    subject = Column(String(300))
    body = Column(Text)
    is_broadcast = Column(Boolean, default=False)
    read = Column(Boolean, default=False)
    created_at = Column(String(50), default=lambda: datetime.now().isoformat())
    message_type = Column(String(50), default='message')
    related_report_id = Column(Integer, nullable=True)
