import sqlite3
from pathlib import Path
import hashlib
import sys


BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / 'data_second'
DB_PATH = DATA_DIR / 'empower_second.db'


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def ensure_db_dir():
    DATA_DIR.mkdir(exist_ok=True)


def ensure_users_table(conn):
    conn.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        role TEXT,
        password_hash TEXT,
        subjects_taught TEXT,
        class_teacher_for TEXT,
        gender TEXT,
        phone_number TEXT
    )
    ''')
    conn.commit()


def create_admin(email='admin', password='admin123', name='Administrator'):
    ensure_db_dir()
    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_users_table(conn)

        cur = conn.cursor()
        # check existing
        cur.execute('SELECT id, email FROM users WHERE email = ?', (email,))
        row = cur.fetchone()
        pwd_hash = sha256(password)
        if row:
            print(f"Admin already exists (id={row[0]}, email={row[1]}). Updating password and role.")
            cur.execute('UPDATE users SET password_hash = ?, role = ? WHERE id = ?', (pwd_hash, 'admin', row[0]))
        else:
            cur.execute('INSERT INTO users (name, email, role, password_hash) VALUES (?, ?, ?, ?)', (name, email, 'admin', pwd_hash))
            print(f"Admin created with email='{email}'.")
        conn.commit()
    finally:
        conn.close()


def main():
    email = 'admin'
    password = 'admin123'
    if len(sys.argv) >= 2:
        email = sys.argv[1]
    if len(sys.argv) >= 3:
        password = sys.argv[2]

    create_admin(email=email, password=password)


if __name__ == '__main__':
    main()
