from flask import Blueprint, render_template, redirect, url_for, session, request, flash
from datetime import datetime, date, timedelta
from db import SessionLocal
from sqlalchemy import text

library_bp = Blueprint('library', __name__, template_folder='templates')

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


@library_bp.route('/')
@login_required
def index():
    return redirect(url_for('library.books'))


@library_bp.route('/books')
@login_required
def books():
    school_id = get_school_id()
    search = request.args.get('q', '')
    category = request.args.get('category', '')
    db = SessionLocal()
    try:
        query = "SELECT * FROM books WHERE school_id=:sid"
        params = {'sid': school_id}
        if search:
            query += " AND (title ILIKE :q OR author ILIKE :q OR isbn ILIKE :q)"
            params['q'] = f'%{search}%'
        if category:
            query += " AND category=:cat"
            params['cat'] = category
        query += " ORDER BY title LIMIT 200"
        book_rows = db.execute(text(query), params).fetchall()

        categories = db.execute(text(
            "SELECT DISTINCT category FROM books WHERE school_id=:sid AND category IS NOT NULL ORDER BY category"
        ), {'sid': school_id}).fetchall()

        stats = db.execute(text("""
            SELECT COUNT(*) AS total_books,
                SUM(total_copies) AS total_copies,
                SUM(available_copies) AS available_copies,
                SUM(total_copies - available_copies) AS borrowed_copies
            FROM books WHERE school_id=:sid
        """), {'sid': school_id}).fetchone()

        return render_template('library/books.html',
            books=book_rows, categories=categories, stats=stats,
            search=search, category=category)
    finally:
        db.close()


@library_bp.route('/books/add', methods=['GET', 'POST'])
@login_required
def add_book():
    school_id = get_school_id()
    db = SessionLocal()
    try:
        if request.method == 'POST':
            copies = int(request.form.get('total_copies', 1))
            db.execute(text("""
                INSERT INTO books (school_id, title, author, isbn, category,
                    publisher, year_published, total_copies, available_copies, location, description)
                VALUES (:sid, :title, :author, :isbn, :cat, :pub, :yr, :tc, :tc, :loc, :desc)
            """), {
                'sid': school_id,
                'title': request.form.get('title', '').strip(),
                'author': request.form.get('author', '').strip(),
                'isbn': request.form.get('isbn', '').strip(),
                'cat': request.form.get('category', '').strip(),
                'pub': request.form.get('publisher', '').strip(),
                'yr': request.form.get('year_published', '') or None,
                'tc': copies,
                'loc': request.form.get('location', '').strip(),
                'desc': request.form.get('description', '').strip(),
            })
            db.commit()
            flash('Book added to library.', 'success')
            return redirect(url_for('library.books'))

        return render_template('library/book_form.html', book=None)
    finally:
        db.close()


@library_bp.route('/books/<int:book_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_book(book_id):
    school_id = get_school_id()
    db = SessionLocal()
    try:
        book = db.execute(text(
            "SELECT * FROM books WHERE id=:id AND school_id=:sid"
        ), {'id': book_id, 'sid': school_id}).fetchone()
        if not book:
            flash('Book not found.', 'danger')
            return redirect(url_for('library.books'))

        if request.method == 'POST':
            db.execute(text("""
                UPDATE books SET title=:title, author=:author, isbn=:isbn, category=:cat,
                    publisher=:pub, year_published=:yr, total_copies=:tc, location=:loc, description=:desc
                WHERE id=:id AND school_id=:sid
            """), {
                'title': request.form.get('title', '').strip(),
                'author': request.form.get('author', '').strip(),
                'isbn': request.form.get('isbn', '').strip(),
                'cat': request.form.get('category', '').strip(),
                'pub': request.form.get('publisher', '').strip(),
                'yr': request.form.get('year_published', '') or None,
                'tc': int(request.form.get('total_copies', 1)),
                'loc': request.form.get('location', '').strip(),
                'desc': request.form.get('description', '').strip(),
                'id': book_id, 'sid': school_id,
            })
            db.commit()
            flash('Book updated.', 'success')
            return redirect(url_for('library.books'))

        return render_template('library/book_form.html', book=book)
    finally:
        db.close()


@library_bp.route('/books/<int:book_id>/delete', methods=['POST'])
@login_required
def delete_book(book_id):
    school_id = get_school_id()
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM books WHERE id=:id AND school_id=:sid"),
                   {'id': book_id, 'sid': school_id})
        db.commit()
        flash('Book deleted.', 'success')
    finally:
        db.close()
    return redirect(url_for('library.books'))


@library_bp.route('/borrowings')
@login_required
def borrowings():
    school_id = get_school_id()
    status_filter = request.args.get('status', 'borrowed')
    search = request.args.get('q', '')
    db = SessionLocal()
    try:
        query = """
            SELECT bb.*, b.title AS book_title, b.author,
                u.first_name || ' ' || u.last_name AS borrower_name,
                s.student_number, s.class_name
            FROM book_borrowings bb
            JOIN books b ON b.id=bb.book_id
            LEFT JOIN students s ON s.id=bb.student_id
            LEFT JOIN users u ON u.id=bb.borrower_user_id
            WHERE bb.school_id=:sid
        """
        params = {'sid': school_id}
        if status_filter:
            query += " AND bb.status=:st"
            params['st'] = status_filter
        if search:
            query += " AND (b.title ILIKE :q OR s.first_name ILIKE :q OR s.last_name ILIKE :q)"
            params['q'] = f'%{search}%'
        query += " ORDER BY bb.borrowed_date DESC LIMIT 200"

        rows = db.execute(text(query), params).fetchall()

        # Overdue count
        overdue_count = db.execute(text(
            "SELECT COUNT(*) FROM book_borrowings WHERE school_id=:sid AND status='borrowed' AND due_date < NOW()"
        ), {'sid': school_id}).scalar()

        from datetime import date as _date
        today = _date.today().isoformat()
        return render_template('library/borrowings.html',
            borrowings=rows, status_filter=status_filter,
            search=search, overdue_count=overdue_count, today=today)
    finally:
        db.close()


@library_bp.route('/borrow', methods=['POST'])
@login_required
def borrow_book():
    school_id = get_school_id()
    db = SessionLocal()
    try:
        book_id = int(request.form.get('book_id', 0))
        book = db.execute(text(
            "SELECT * FROM books WHERE id=:id AND school_id=:sid"
        ), {'id': book_id, 'sid': school_id}).fetchone()

        if not book or book.available_copies < 1:
            flash('Book not available.', 'danger')
            return redirect(url_for('library.books'))

        student_id = request.form.get('student_id', '') or None
        borrower_user_id = request.form.get('borrower_user_id', '') or None
        due_days = int(request.form.get('due_days', 14))
        due_date = date.today() + timedelta(days=due_days)

        db.execute(text("""
            INSERT INTO book_borrowings (school_id, book_id, student_id, borrower_user_id,
                borrowed_date, due_date, status, issued_by)
            VALUES (:sid, :bid, :stid, :buid, NOW(), :dd, 'borrowed', :ib)
        """), {
            'sid': school_id, 'bid': book_id,
            'stid': student_id, 'buid': borrower_user_id,
            'dd': due_date, 'ib': session.get('user_id'),
        })
        db.execute(text(
            "UPDATE books SET available_copies=available_copies-1 WHERE id=:id"
        ), {'id': book_id})
        db.commit()
        flash(f'Book borrowed. Due: {due_date.strftime("%d %b %Y")}', 'success')
    finally:
        db.close()
    return redirect(url_for('library.borrowings'))


@library_bp.route('/return/<int:borrow_id>', methods=['POST'])
@login_required
def return_book(borrow_id):
    school_id = get_school_id()
    db = SessionLocal()
    try:
        borrow = db.execute(text(
            "SELECT * FROM book_borrowings WHERE id=:id AND school_id=:sid"
        ), {'id': borrow_id, 'sid': school_id}).fetchone()

        if not borrow:
            flash('Borrowing record not found.', 'danger')
            return redirect(url_for('library.borrowings'))

        condition = request.form.get('condition', 'good')
        fine = float(request.form.get('fine', 0) or 0)

        db.execute(text("""
            UPDATE book_borrowings SET returned_date=NOW(), status='returned',
                book_condition_returned=:cond, fine_amount=:fine WHERE id=:id
        """), {'cond': condition, 'fine': fine, 'id': borrow_id})

        db.execute(text(
            "UPDATE books SET available_copies=available_copies+1 WHERE id=:bid"
        ), {'bid': borrow.book_id})
        db.commit()
        flash('Book returned successfully.', 'success')
    finally:
        db.close()
    return redirect(url_for('library.borrowings'))
