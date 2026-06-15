from flask import Blueprint, render_template, redirect, url_for, session, request, flash
from datetime import datetime
from db import SessionLocal
from sqlalchemy import text

finance_bp = Blueprint('finance', __name__, template_folder='templates')

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


@finance_bp.route('/')
@login_required
def index():
    return redirect(url_for('finance.invoices'))


# ── FEE STRUCTURE ─────────────────────────────────────────────────────────────

@finance_bp.route('/fee_structure')
@login_required
def fee_structure():
    school_id = get_school_id()
    db = SessionLocal()
    try:
        all_terms = db.execute(text(
            "SELECT * FROM terms WHERE school_id=:sid ORDER BY id DESC"
        ), {'sid': school_id}).fetchall()
        term_id = int(request.args.get('term_id', all_terms[0].id if all_terms else 0) or 0)

        fees = db.execute(text(
            "SELECT * FROM fee_structures WHERE school_id=:sid AND term_id=:tid ORDER BY class_name, item_name"
        ), {'sid': school_id, 'tid': term_id}).fetchall()

        classes = db.execute(text(
            "SELECT DISTINCT class_name FROM students WHERE school_id=:sid ORDER BY class_name"
        ), {'sid': school_id}).fetchall()

        return render_template('finance/fee_structure.html',
            all_terms=all_terms, selected_term_id=term_id, fees=fees, classes=classes)
    finally:
        db.close()


@finance_bp.route('/fee_structure/add', methods=['POST'])
@login_required
def add_fee():
    school_id = get_school_id()
    db = SessionLocal()
    try:
        db.execute(text("""
            INSERT INTO fee_structures (school_id, term_id, class_name, item_name, amount, is_optional)
            VALUES (:sid, :tid, :cn, :item, :amt, :opt)
        """), {
            'sid': school_id,
            'tid': int(request.form.get('term_id', 0)),
            'cn': request.form.get('class_name', ''),
            'item': request.form.get('item_name', ''),
            'amt': float(request.form.get('amount', 0)),
            'opt': bool(request.form.get('is_optional')),
        })
        db.commit()
        flash('Fee item added.', 'success')
    finally:
        db.close()
    return redirect(url_for('finance.fee_structure', term_id=request.form.get('term_id')))


@finance_bp.route('/fee_structure/<int:fee_id>/delete', methods=['POST'])
@login_required
def delete_fee(fee_id):
    school_id = get_school_id()
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM fee_structures WHERE id=:id AND school_id=:sid"),
                   {'id': fee_id, 'sid': school_id})
        db.commit()
        flash('Fee item deleted.', 'success')
    finally:
        db.close()
    return redirect(request.referrer or url_for('finance.fee_structure'))


# ── INVOICES ──────────────────────────────────────────────────────────────────

@finance_bp.route('/invoices')
@login_required
def invoices():
    school_id = get_school_id()
    db = SessionLocal()
    try:
        all_terms = db.execute(text(
            "SELECT * FROM terms WHERE school_id=:sid ORDER BY id DESC"
        ), {'sid': school_id}).fetchall()
        term_id = int(request.args.get('term_id', all_terms[0].id if all_terms else 0) or 0)
        status_filter = request.args.get('status', '')
        search = request.args.get('q', '')

        query = """
            SELECT i.*, s.first_name || ' ' || s.last_name AS student_name, s.class_name, s.student_number
            FROM invoices i
            JOIN students s ON s.id=i.student_id
            WHERE i.school_id=:sid
        """
        params = {'sid': school_id}
        if term_id:
            query += " AND i.term_id=:tid"
            params['tid'] = term_id
        if status_filter:
            query += " AND i.status=:st"
            params['st'] = status_filter
        if search:
            query += " AND (s.first_name ILIKE :q OR s.last_name ILIKE :q OR s.student_number ILIKE :q OR i.invoice_number ILIKE :q)"
            params['q'] = f'%{search}%'
        query += " ORDER BY i.created_at DESC LIMIT 200"

        inv_rows = db.execute(text(query), params).fetchall()

        # Summary stats
        stats = db.execute(text("""
            SELECT
                SUM(total_amount) AS total_billed,
                SUM(paid_amount) AS total_paid,
                SUM(balance) AS total_balance,
                COUNT(*) FILTER (WHERE status='unpaid') AS unpaid_count,
                COUNT(*) FILTER (WHERE status='partial') AS partial_count,
                COUNT(*) FILTER (WHERE status='paid') AS paid_count
            FROM invoices WHERE school_id=:sid AND term_id=:tid
        """), {'sid': school_id, 'tid': term_id}).fetchone() if term_id else None

        return render_template('finance/invoices.html',
            all_terms=all_terms, selected_term_id=term_id,
            invoices=inv_rows, stats=stats,
            status_filter=status_filter, search=search)
    finally:
        db.close()


@finance_bp.route('/invoices/generate', methods=['POST'])
@login_required
def generate_invoices():
    """Bulk-generate invoices from fee structure for a class/term."""
    school_id = get_school_id()
    term_id = int(request.form.get('term_id', 0))
    class_name = request.form.get('class_name', '')
    db = SessionLocal()
    try:
        fees = db.execute(text(
            "SELECT * FROM fee_structures WHERE school_id=:sid AND term_id=:tid AND class_name=:cn"
        ), {'sid': school_id, 'tid': term_id, 'cn': class_name}).fetchall()

        if not fees:
            flash('No fee structure found for this class/term. Please set up fees first.', 'warning')
            return redirect(url_for('finance.fee_structure', term_id=term_id))

        students = db.execute(text(
            "SELECT * FROM students WHERE school_id=:sid AND class_name=:cn AND status='active'"
        ), {'sid': school_id, 'cn': class_name}).fetchall()

        created = 0
        for st in students:
            exists = db.execute(text(
                "SELECT id FROM invoices WHERE school_id=:sid AND student_id=:stid AND term_id=:tid"
            ), {'sid': school_id, 'stid': st.id, 'tid': term_id}).fetchone()
            if exists:
                continue
            total = sum(float(f.amount) for f in fees)
            inv_num = f"INV-{term_id}-{st.id:04d}"
            db.execute(text("""
                INSERT INTO invoices (school_id, student_id, term_id, invoice_number, total_amount, paid_amount, balance, status, due_date, created_at)
                VALUES (:sid, :stid, :tid, :num, :tot, 0, :tot, 'unpaid', :dd, NOW())
            """), {'sid': school_id, 'stid': st.id, 'tid': term_id,
                   'num': inv_num, 'tot': total, 'dd': request.form.get('due_date', '')})
            inv = db.execute(text("SELECT id FROM invoices WHERE invoice_number=:n AND school_id=:sid"),
                             {'n': inv_num, 'sid': school_id}).fetchone()
            for f in fees:
                db.execute(text(
                    "INSERT INTO invoice_items (invoice_id, description, amount) VALUES (:iid, :desc, :amt)"
                ), {'iid': inv.id, 'desc': f.item_name, 'amt': float(f.amount)})
            created += 1

        db.commit()
        flash(f'Generated {created} invoices for {class_name}.', 'success')
    finally:
        db.close()
    return redirect(url_for('finance.invoices', term_id=term_id))


@finance_bp.route('/invoices/<int:inv_id>')
@login_required
def invoice_detail(inv_id):
    school_id = get_school_id()
    db = SessionLocal()
    try:
        inv = db.execute(text("""
            SELECT i.*, s.first_name || ' ' || s.last_name AS student_name,
                s.class_name, s.student_number
            FROM invoices i JOIN students s ON s.id=i.student_id
            WHERE i.id=:id AND i.school_id=:sid
        """), {'id': inv_id, 'sid': school_id}).fetchone()
        if not inv:
            flash('Invoice not found.', 'danger')
            return redirect(url_for('finance.invoices'))

        items = db.execute(text(
            "SELECT * FROM invoice_items WHERE invoice_id=:id"
        ), {'id': inv_id}).fetchall()

        payments = db.execute(text(
            "SELECT p.*, u.first_name || ' ' || u.last_name AS received_by_name FROM payments p LEFT JOIN users u ON u.id=p.received_by WHERE p.invoice_id=:id ORDER BY p.paid_at DESC"
        ), {'id': inv_id}).fetchall()

        return render_template('finance/invoice_detail.html',
            invoice=inv, items=items, payments=payments)
    finally:
        db.close()


# ── PAYMENTS ──────────────────────────────────────────────────────────────────

@finance_bp.route('/payments')
@login_required
def payments():
    school_id = get_school_id()
    db = SessionLocal()
    try:
        all_terms = db.execute(text(
            "SELECT * FROM terms WHERE school_id=:sid ORDER BY id DESC"
        ), {'sid': school_id}).fetchall()
        term_id = int(request.args.get('term_id', all_terms[0].id if all_terms else 0) or 0)
        search = request.args.get('q', '')

        query = """
            SELECT p.*, s.first_name || ' ' || s.last_name AS student_name,
                s.student_number, s.class_name
            FROM payments p
            JOIN students s ON s.id=p.student_id
            WHERE p.school_id=:sid
        """
        params = {'sid': school_id}
        if term_id:
            query += " AND p.invoice_id IN (SELECT id FROM invoices WHERE term_id=:tid)"
            params['tid'] = term_id
        if search:
            query += " AND (s.first_name ILIKE :q OR s.last_name ILIKE :q OR p.receipt_number ILIKE :q)"
            params['q'] = f'%{search}%'
        query += " ORDER BY p.paid_at DESC LIMIT 200"

        pay_rows = db.execute(text(query), params).fetchall()

        return render_template('finance/payments.html',
            all_terms=all_terms, selected_term_id=term_id,
            payments=pay_rows, search=search)
    finally:
        db.close()


@finance_bp.route('/invoices/<int:inv_id>/pay', methods=['POST'])
@login_required
def record_payment(inv_id):
    school_id = get_school_id()
    db = SessionLocal()
    try:
        inv = db.execute(text(
            "SELECT * FROM invoices WHERE id=:id AND school_id=:sid"
        ), {'id': inv_id, 'sid': school_id}).fetchone()
        if not inv:
            flash('Invoice not found.', 'danger')
            return redirect(url_for('finance.invoices'))

        amount = float(request.form.get('amount', 0))
        receipt_num = f"RCP-{inv_id}-{int(datetime.now().timestamp())}"
        db.execute(text("""
            INSERT INTO payments (school_id, invoice_id, student_id, receipt_number, amount, payment_method, reference, paid_by, received_by, notes, paid_at)
            VALUES (:sid, :iid, :stid, :rn, :amt, :pm, :ref, :pb, :rb, :notes, NOW())
        """), {
            'sid': school_id, 'iid': inv_id, 'stid': inv.student_id,
            'rn': receipt_num, 'amt': amount,
            'pm': request.form.get('payment_method', 'cash'),
            'ref': request.form.get('reference', ''),
            'pb': request.form.get('paid_by', ''),
            'rb': session.get('user_id'),
            'notes': request.form.get('notes', ''),
        })

        new_paid = float(inv.paid_amount or 0) + amount
        new_balance = float(inv.total_amount or 0) - new_paid
        status = 'paid' if new_balance <= 0 else 'partial'
        db.execute(text("""
            UPDATE invoices SET paid_amount=:pa, balance=:bal, status=:st WHERE id=:id
        """), {'pa': new_paid, 'bal': max(new_balance, 0), 'st': status, 'id': inv_id})
        db.commit()
        flash(f'Payment of {amount:,.0f} recorded. Receipt: {receipt_num}', 'success')
    finally:
        db.close()
    return redirect(url_for('finance.invoice_detail', inv_id=inv_id))


# ── MY FEES (parent/student view) ─────────────────────────────────────────────

@finance_bp.route('/my_fees')
@login_required
def my_fees():
    school_id = get_school_id()
    role = session.get('role')
    db = SessionLocal()
    try:
        student_id = None
        if role == 'student':
            st = db.execute(text(
                "SELECT id FROM students WHERE user_id=:uid AND school_id=:sid LIMIT 1"
            ), {'uid': session.get('user_id'), 'sid': school_id}).fetchone()
            student_id = st.id if st else None
        elif role == 'parent':
            # First child
            ch = db.execute(text("""
                SELECT s.id FROM students s
                JOIN student_guardians sg ON sg.student_id=s.id
                JOIN guardians g ON g.id=sg.guardian_id
                WHERE g.user_id=:uid AND s.school_id=:sid LIMIT 1
            """), {'uid': session.get('user_id'), 'sid': school_id}).fetchone()
            student_id = ch.id if ch else None

        invoices = []
        if student_id:
            invoices = db.execute(text("""
                SELECT i.*, t.name AS term_name FROM invoices i
                LEFT JOIN terms t ON t.id=i.term_id
                WHERE i.student_id=:stid ORDER BY i.created_at DESC
            """), {'stid': student_id}).fetchall()

        return render_template('finance/my_fees.html', invoices=invoices, student_id=student_id)
    finally:
        db.close()
