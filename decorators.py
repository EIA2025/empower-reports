"""
Role-Based Access Control Decorators for Empower Reports
"""
from functools import wraps
from flask import session, redirect, url_for, flash
from typing import List


def login_required(f):
    """Decorator to check if user is logged in"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please log in first.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def role_required(*roles):
    """Decorator to check if user has one of the required roles
    
    Usage:
        @role_required('admin', 'master')
        def my_route():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get('user_id'):
                flash('Please log in first.', 'warning')
                return redirect(url_for('auth.login'))
            
            user_role = session.get('role', '').lower()
            
            # Master admin can access everything
            if user_role == 'master':
                return f(*args, **kwargs)
            
            # Check if user has required role
            if user_role not in [r.lower() for r in roles]:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('dashboard.index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_required(f):
    """Decorator for routes that require admin or master role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_role = session.get('role', '').lower()
        if user_role not in ('admin', 'master'):
            flash('You must be an administrator to access this page.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function


def master_required(f):
    """Decorator for routes that require master admin (super admin) role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_role = session.get('role', '').lower()
        if user_role != 'master':
            flash('You must be a system administrator to access this page.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function


def teacher_required(f):
    """Decorator for routes that require teacher role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_role = session.get('role', '').lower()
        if user_role not in ('teacher', 'admin', 'master'):
            flash('This page is for teachers only.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function


def student_required(f):
    """Decorator for routes that require student role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_role = session.get('role', '').lower()
        if user_role not in ('student', 'admin', 'master'):
            flash('This page is for students only.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function


def parent_required(f):
    """Decorator for routes that require parent role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_role = session.get('role', '').lower()
        if user_role not in ('parent', 'admin', 'master'):
            flash('This page is for parents only.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function


def accountant_required(f):
    """Decorator for routes that require accountant/bursar role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_role = session.get('role', '').lower()
        if user_role not in ('accountant', 'bursar', 'admin', 'master'):
            flash('This page is for accountants only.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function


def librarian_required(f):
    """Decorator for routes that require librarian role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_role = session.get('role', '').lower()
        if user_role not in ('librarian', 'admin', 'master'):
            flash('This page is for librarians only.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function


def get_current_user_role():
    """Get the current user's role from session"""
    return session.get('role', 'guest').lower()


def has_role(user_role, *required_roles):
    """Check if user_role matches any of the required_roles"""
    user_role = user_role.lower()
    required_roles = [r.lower() for r in required_roles]
    
    # Master admin has all roles
    if user_role == 'master':
        return True
    
    return user_role in required_roles


def is_admin():
    """Check if current user is admin or master"""
    return get_current_user_role() in ('admin', 'master')


def is_master():
    """Check if current user is master admin"""
    return get_current_user_role() == 'master'


def is_teacher():
    """Check if current user is teacher or admin"""
    return get_current_user_role() in ('teacher', 'admin', 'master')


def is_student():
    """Check if current user is student or admin"""
    return get_current_user_role() in ('student', 'admin', 'master')


def is_parent():
    """Check if current user is parent or admin"""
    return get_current_user_role() in ('parent', 'admin', 'master')
