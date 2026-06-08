# blueprints/system/routes.py — Master Admin / System Management
import hashlib
from functools import wraps
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, flash)
from sqlalchemy import text
from db import SessionLocal

system_bp = Blueprint('system', __name__, template_folder='templates')


def master_only(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('user_role') != 'master_admin':
            flash('Access denied — Master Admin only.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


# ── OVERVIEW ──────────────────────────────────────────────────────────────────
@system_bp.route('/')
@system_bp.route('/overview')
@master_only
def overview():
    db = SessionLocal()
    try:
        schools        = db.execute(text("SELECT * FROM schools ORDER BY created_at DESC")).fetchall()
        total_users    = db.execute(text("SELECT COUNT(*) FROM users")).scalar()
        total_students = db.execute(text("SELECT COUNT(*) FROM students")).scalar()
        total_staff    = db.execute(text("SELECT COUNT(*) FROM staff")).scalar()
        active_schools = sum(1 for s in schools if s.is_active)
        recent_logs    = db.execute(text("""
            SELECT a.*, u.name as user_name, sc.name as school_name
            FROM audit_logs a
            LEFT JOIN users u ON u.id=a.user_id
            LEFT JOIN schools sc ON sc.id=a.school_id
            ORDER BY a.timestamp DESC LIMIT 15
        """)).fetchall()
        announcements = db.execute(text(
            "SELECT * FROM system_announcements WHERE is_active=true ORDER BY created_at DESC LIMIT 5"
        )).fetchall()
        return render_template('system/overview.html',
            schools=schools, total_users=total_users,
            total_students=total_students, total_staff=total_staff,
            active_schools=active_schools, recent_logs=recent_logs,
            announcements=announcements)
    finally:
        db.close()


# ── SCHOOL LIST ───────────────────────────────────────────────────────────────
@system_bp.route('/schools')
@master_only
def schools():
    db = SessionLocal()
    try:
        q = request.args.get('q','')
        status = request.args.get('status','')
        where = "WHERE 1=1"
        params = {}
        if q:
            where += " AND (s.name ILIKE :q OR s.email ILIKE :q OR s.country ILIKE :q)"
            params['q'] = f'%{q}%'
        if status == 'active':
            where += " AND s.is_active=true"
        elif status == 'inactive':
            where += " AND s.is_active=false"
        rows = db.execute(text(f"""
            SELECT s.*,
                (SELECT COUNT(*) FROM students st WHERE st.school_id=s.id) as student_count,
                (SELECT COUNT(*) FROM staff sf WHERE sf.school_id=s.id) as staff_count,
                (SELECT COUNT(*) FROM users u WHERE u.school_id=s.id AND u.role='admin') as admin_count
            FROM schools s {where} ORDER BY s.created_at DESC
        """), params).fetchall()
        return render_template('system/schools.html', schools=rows, q=q, selected_status=status)
    finally:
        db.close()


# ── ADD SCHOOL ────────────────────────────────────────────────────────────────
@system_bp.route('/schools/add', methods=['GET','POST'])
@master_only
def add_school():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            school_id = db.execute(text("""
                INSERT INTO schools
                    (name,subtitle,address,po_box,phone,email,website,
                     country,currency,primary_color,plan,plan_expires,
                     max_students,max_staff,notes,is_active)
                VALUES
                    (:name,:sub,:addr,:po,:phone,:email,:web,
                     :country,:curr,:color,:plan,:expires,
                     :maxst,:maxsf,:notes,true)
                RETURNING id
            """), {
                'name':    request.form['name'],
                'sub':     request.form.get('subtitle',''),
                'addr':    request.form.get('address',''),
                'po':      request.form.get('po_box',''),
                'phone':   request.form.get('phone',''),
                'email':   request.form.get('email',''),
                'web':     request.form.get('website',''),
                'country': request.form.get('country',''),
                'curr':    request.form.get('currency','UGX'),
                'color':   request.form.get('primary_color','#1e3a8a'),
                'plan':    request.form.get('plan','trial'),
                'expires': request.form.get('plan_expires',''),
                'maxst':   int(request.form.get('max_students',500) or 500),
                'maxsf':   int(request.form.get('max_staff',50) or 50),
                'notes':   request.form.get('notes',''),
            }).scalar()
            db.commit()

            # Default report design
            db.execute(text(
                "INSERT INTO report_designs (school_id,school_name,primary_color) VALUES (:s,:n,:c)"
            ), {'s':school_id,'n':request.form['name'],'c':request.form.get('primary_color','#1e3a8a')})

            # Default behavior components
            for i,(nm,lbl) in enumerate([
                ('punctuality','Punctuality'),('attendance','Attendance'),
                ('manners','Manners'),('general_behavior','General Behavior'),
                ('organisational_skills','Organisational Skills'),
                ('adherence_to_uniform','Adherence to Uniform'),
                ('leadership_skills','Leadership Skills'),
                ('commitment_to_school','Commitment to School'),
                ('cooperation_with_peers','Cooperation with Peers'),
                ('cooperation_with_staff','Cooperation with Staff'),
                ('participation_in_lessons','Participation in Lessons'),
                ('completion_of_homework','Completion of Homework'),
            ]):
                db.execute(text(
                    "INSERT INTO behavior_components (school_id,name,display_label,display_order,active) VALUES (:s,:n,:l,:o,true)"
                ), {'s':school_id,'n':nm,'l':lbl,'o':i})
            db.commit()

            # Admin account
            admin_email = request.form.get('admin_email','').strip()
            admin_pw    = request.form.get('admin_password','').strip()
            if admin_email and admin_pw:
                db.execute(text("""
                    INSERT INTO users (school_id,name,email,role,password_hash,must_change_pw,phone)
                    VALUES (:sid,:name,:email,'admin',:pw,false,:phone)
                """), {
                    'sid':   school_id,
                    'name':  request.form.get('admin_name','School Administrator'),
                    'email': admin_email,
                    'pw':    hashlib.sha256(admin_pw.encode()).hexdigest(),
                    'phone': request.form.get('admin_phone',''),
                })
                db.commit()
                flash(f'School created! Admin login: {admin_email} / {admin_pw}', 'success')
            else:
                flash(f'School created. Add an admin account from the school detail page.', 'success')
            return redirect(url_for('system.school_detail', school_id=school_id))
        return render_template('system/school_form.html', school=None)
    except Exception as e:
        db.rollback()
        flash(f'Error: {e}', 'error')
        return redirect(url_for('system.schools'))
    finally:
        db.close()


# ── SCHOOL DETAIL ─────────────────────────────────────────────────────────────
@system_bp.route('/schools/<int:school_id>')
@master_only
def school_detail(school_id):
    db = SessionLocal()
    try:
        school = db.execute(text("SELECT * FROM schools WHERE id=:id"), {'id':school_id}).fetchone()
        if not school:
            flash('School not found.', 'error')
            return redirect(url_for('system.schools'))
        admins = db.execute(text(
            "SELECT * FROM users WHERE school_id=:s AND role='admin' ORDER BY name"
        ), {'s':school_id}).fetchall()
        stats = {
            'students': db.execute(text("SELECT COUNT(*) FROM students WHERE school_id=:s"),{'s':school_id}).scalar(),
            'staff':    db.execute(text("SELECT COUNT(*) FROM staff WHERE school_id=:s"),{'s':school_id}).scalar(),
            'classes':  db.execute(text("SELECT COUNT(*) FROM classes WHERE school_id=:s"),{'s':school_id}).scalar(),
            'terms':    db.execute(text("SELECT COUNT(*) FROM terms WHERE school_id=:s"),{'s':school_id}).scalar(),
        }
        logs = db.execute(text("""
            SELECT a.*, u.name as user_name FROM audit_logs a
            LEFT JOIN users u ON u.id=a.user_id
            WHERE a.school_id=:s ORDER BY a.timestamp DESC LIMIT 20
        """), {'s':school_id}).fetchall()
        return render_template('system/school_detail.html',
            school=school, admins=admins, stats=stats, logs=logs)
    finally:
        db.close()


# ── EDIT SCHOOL ───────────────────────────────────────────────────────────────
@system_bp.route('/schools/<int:school_id>/edit', methods=['GET','POST'])
@master_only
def edit_school(school_id):
    db = SessionLocal()
    try:
        school = db.execute(text("SELECT * FROM schools WHERE id=:id"),{'id':school_id}).fetchone()
        if not school:
            flash('School not found.', 'error')
            return redirect(url_for('system.schools'))
        if request.method == 'POST':
            db.execute(text("""
                UPDATE schools SET name=:name,subtitle=:sub,address=:addr,po_box=:po,
                phone=:phone,email=:email,website=:web,country=:country,
                currency=:curr,primary_color=:color,plan=:plan,plan_expires=:expires,
                max_students=:maxst,max_staff=:maxsf,notes=:notes WHERE id=:id
            """), {
                'name':    request.form['name'],
                'sub':     request.form.get('subtitle',''),
                'addr':    request.form.get('address',''),
                'po':      request.form.get('po_box',''),
                'phone':   request.form.get('phone',''),
                'email':   request.form.get('email',''),
                'web':     request.form.get('website',''),
                'country': request.form.get('country',''),
                'curr':    request.form.get('currency','UGX'),
                'color':   request.form.get('primary_color','#1e3a8a'),
                'plan':    request.form.get('plan','trial'),
                'expires': request.form.get('plan_expires',''),
                'maxst':   int(request.form.get('max_students',500) or 500),
                'maxsf':   int(request.form.get('max_staff',50) or 50),
                'notes':   request.form.get('notes',''),
                'id':      school_id,
            })
            db.commit()
            flash('School updated.', 'success')
            return redirect(url_for('system.school_detail', school_id=school_id))
        return render_template('system/school_form.html', school=school)
    finally:
        db.close()


# ── TOGGLE / DELETE SCHOOL ────────────────────────────────────────────────────
@system_bp.route('/schools/<int:school_id>/toggle', methods=['POST'])
@master_only
def toggle_school(school_id):
    db = SessionLocal()
    try:
        s = db.execute(text("SELECT is_active,name FROM schools WHERE id=:id"),{'id':school_id}).fetchone()
        if s:
            db.execute(text("UPDATE schools SET is_active=:v WHERE id=:id"),{'v': not s.is_active,'id':school_id})
            db.commit()
            flash(f'{"Activated" if not s.is_active else "Deactivated"}: {s.name}', 'success')
    except Exception as e:
        db.rollback(); flash(f'Error: {e}', 'error')
    finally:
        db.close()
    return redirect(url_for('system.school_detail', school_id=school_id))


@system_bp.route('/schools/<int:school_id>/delete', methods=['POST'])
@master_only
def delete_school(school_id):
    db = SessionLocal()
    try:
        confirm = request.form.get('confirm_name','')
        school  = db.execute(text("SELECT name FROM schools WHERE id=:id"),{'id':school_id}).fetchone()
        if not school:
            flash('School not found.','error')
            return redirect(url_for('system.schools'))
        if confirm != school.name:
            flash('School name did not match. Deletion cancelled.','error')
            return redirect(url_for('system.school_detail', school_id=school_id))
        db.execute(text("DELETE FROM schools WHERE id=:id"),{'id':school_id})
        db.commit()
        flash(f'School "{school.name}" permanently deleted.','success')
    except Exception as e:
        db.rollback(); flash(f'Error: {e}','error')
    finally:
        db.close()
    return redirect(url_for('system.schools'))


# ── ADD SCHOOL ADMIN ──────────────────────────────────────────────────────────
@system_bp.route('/schools/<int:school_id>/admins/add', methods=['POST'])
@master_only
def add_school_admin(school_id):
    db = SessionLocal()
    try:
        email = request.form['email'].strip()
        pw    = request.form.get('password','admin123')
        existing = db.execute(text("SELECT id FROM users WHERE email=:e LIMIT 1"),{'e':email}).fetchone()
        if existing:
            flash(f'Email "{email}" is already in use.','error')
        else:
            db.execute(text("""
                INSERT INTO users (school_id,name,email,role,password_hash,must_change_pw,phone)
                VALUES (:sid,:name,:email,'admin',:pw,false,:phone)
            """), {
                'sid':   school_id,
                'name':  request.form['name'],
                'email': email,
                'pw':    hashlib.sha256(pw.encode()).hexdigest(),
                'phone': request.form.get('phone',''),
            })
            db.commit()
            flash(f'Admin created — login: {email} / {pw}','success')
    except Exception as e:
        db.rollback(); flash(f'Error: {e}','error')
    finally:
        db.close()
    return redirect(url_for('system.school_detail', school_id=school_id))


# ── USER RESET / TOGGLE ───────────────────────────────────────────────────────
@system_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@master_only
def reset_password(user_id):
    db = SessionLocal()
    try:
        new_pw = request.form.get('new_password','changeme123').strip()
        u = db.execute(text("SELECT name,school_id FROM users WHERE id=:id"),{'id':user_id}).fetchone()
        if u:
            db.execute(text("UPDATE users SET password_hash=:pw,must_change_pw=true WHERE id=:id"),
                       {'pw':hashlib.sha256(new_pw.encode()).hexdigest(),'id':user_id})
            db.commit()
            flash(f'Password for {u.name} reset to: {new_pw}','success')
            return redirect(url_for('system.school_detail', school_id=u.school_id))
    except Exception as e:
        db.rollback(); flash(f'Error: {e}','error')
    finally:
        db.close()
    return redirect(url_for('system.schools'))


@system_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@master_only
def toggle_user(user_id):
    db = SessionLocal()
    try:
        u = db.execute(text("SELECT is_active,name,school_id FROM users WHERE id=:id"),{'id':user_id}).fetchone()
        if u:
            db.execute(text("UPDATE users SET is_active=:v WHERE id=:id"),{'v': not u.is_active,'id':user_id})
            db.commit()
            flash(f'{"Enabled" if not u.is_active else "Disabled"}: {u.name}','success')
            return redirect(url_for('system.school_detail', school_id=u.school_id))
    except Exception as e:
        db.rollback(); flash(f'Error: {e}','error')
    finally:
        db.close()
    return redirect(url_for('system.schools'))


# ── SYSTEM SETTINGS ───────────────────────────────────────────────────────────
@system_bp.route('/settings', methods=['GET','POST'])
@master_only
def settings():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            for key, value in request.form.items():
                if key.startswith('setting_'):
                    k = key[8:]
                    existing = db.execute(text("SELECT id FROM system_settings WHERE key=:k"),{'k':k}).fetchone()
                    if existing:
                        db.execute(text("UPDATE system_settings SET value=:v,updated_at=CURRENT_TIMESTAMP WHERE key=:k"),{'v':value,'k':k})
                    else:
                        db.execute(text("INSERT INTO system_settings (key,value) VALUES (:k,:v)"),{'k':k,'v':value})
            db.commit()
            flash('Settings saved.','success')
            return redirect(url_for('system.settings'))
        rows = db.execute(text("SELECT key,value FROM system_settings")).fetchall()
        cfg = {r.key: r.value for r in rows}
        return render_template('system/settings.html', cfg=cfg)
    finally:
        db.close()


# ── AUDIT LOGS ────────────────────────────────────────────────────────────────
@system_bp.route('/audit-logs')
@master_only
def audit_logs():
    db = SessionLocal()
    try:
        school_filter = request.args.get('school_id','')
        action_filter = request.args.get('action','')
        page = int(request.args.get('page',1))
        per  = 50
        where = "WHERE 1=1"
        params = {}
        if school_filter:
            where += " AND a.school_id=:sid"
            params['sid'] = int(school_filter)
        if action_filter:
            where += " AND a.action ILIKE :act"
            params['act'] = f'%{action_filter}%'
        total = db.execute(text(f"SELECT COUNT(*) FROM audit_logs a {where}"),params).scalar()
        params['limit']  = per
        params['offset'] = (page-1)*per
        logs = db.execute(text(f"""
            SELECT a.*, u.name as user_name, sc.name as school_name
            FROM audit_logs a
            LEFT JOIN users u ON u.id=a.user_id
            LEFT JOIN schools sc ON sc.id=a.school_id
            {where} ORDER BY a.timestamp DESC LIMIT :limit OFFSET :offset
        """), params).fetchall()
        schools = db.execute(text("SELECT id,name FROM schools ORDER BY name")).fetchall()
        return render_template('system/audit_logs.html',
            logs=logs, total=total, page=page, per=per,
            pages=(total+per-1)//per, schools=schools,
            school_filter=school_filter, action_filter=action_filter)
    finally:
        db.close()


# ── ANNOUNCEMENTS ─────────────────────────────────────────────────────────────
@system_bp.route('/announcements', methods=['GET','POST'])
@master_only
def announcements():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            action = request.form.get('action','add')
            uid_str = session.get('user_id','')
            sys_uid = int(str(uid_str).replace('sys_','')) if 'sys_' in str(uid_str) else None
            if action == 'add':
                db.execute(text("""
                    INSERT INTO system_announcements (created_by,title,body,target,is_active,expires_at)
                    VALUES (:uid,:title,:body,:target,true,:expires)
                """), {
                    'uid':uid_str and sys_uid,
                    'title':request.form['title'],
                    'body':request.form['body'],
                    'target':request.form.get('target','all'),
                    'expires':request.form.get('expires_at',''),
                })
                db.commit()
                flash('Announcement published.','success')
            elif action == 'toggle':
                ann = db.execute(text("SELECT is_active FROM system_announcements WHERE id=:id"),
                                 {'id':int(request.form['ann_id'])}).fetchone()
                if ann:
                    db.execute(text("UPDATE system_announcements SET is_active=:v WHERE id=:id"),
                               {'v': not ann.is_active,'id':int(request.form['ann_id'])})
                    db.commit()
            elif action == 'delete':
                db.execute(text("DELETE FROM system_announcements WHERE id=:id"),
                           {'id':int(request.form['ann_id'])})
                db.commit()
                flash('Deleted.','success')
            return redirect(url_for('system.announcements'))
        rows = db.execute(text("SELECT * FROM system_announcements ORDER BY created_at DESC")).fetchall()
        return render_template('system/announcements.html', announcements=rows)
    finally:
        db.close()


# ── SYSTEM ADMIN ACCOUNTS ─────────────────────────────────────────────────────
@system_bp.route('/admins', methods=['GET','POST'])
@master_only
def system_admins():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'add':
                email = request.form['email'].strip()
                pw    = request.form.get('password','masteradmin123')
                if db.execute(text("SELECT id FROM system_users WHERE email=:e"),{'e':email}).fetchone():
                    flash(f'Email "{email}" already exists.','error')
                else:
                    db.execute(text("INSERT INTO system_users (name,email,password_hash,is_active) VALUES (:n,:e,:pw,true)"),
                               {'n':request.form['name'],'e':email,'pw':hashlib.sha256(pw.encode()).hexdigest()})
                    db.commit()
                    flash(f'Admin created: {email} / {pw}','success')
            elif action == 'toggle':
                u = db.execute(text("SELECT is_active FROM system_users WHERE id=:id"),{'id':int(request.form['uid'])}).fetchone()
                if u:
                    db.execute(text("UPDATE system_users SET is_active=:v WHERE id=:id"),
                               {'v': not u.is_active,'id':int(request.form['uid'])})
                    db.commit()
            elif action == 'reset_pw':
                new_pw = request.form.get('new_password','masteradmin123')
                db.execute(text("UPDATE system_users SET password_hash=:pw WHERE id=:id"),
                           {'pw':hashlib.sha256(new_pw.encode()).hexdigest(),'id':int(request.form['uid'])})
                db.commit()
                flash(f'Password reset to: {new_pw}','success')
            return redirect(url_for('system.system_admins'))
        admins = db.execute(text("SELECT * FROM system_users ORDER BY created_at")).fetchall()
        return render_template('system/admins.html', admins=admins)
    finally:
        db.close()
