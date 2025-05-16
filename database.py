import sqlite3
from werkzeug.security import generate_password_hash


def get_db():
    conn = sqlite3.connect('print_queue.db')
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    db = get_db()
    # إنشاء جدول المستخدمين
    db.execute('''CREATE TABLE IF NOT EXISTS users
                  (id INTEGER PRIMARY KEY, 
                   email TEXT UNIQUE, 
                   password TEXT, 
                   balance REAL, 
                   name TEXT, 
                   department TEXT, 
                   year TEXT, 
                   is_admin BOOLEAN DEFAULT 0)''')
    # إنشاء جدول الجلسات
    db.execute('''CREATE TABLE IF NOT EXISTS sessions
                  (session_id TEXT PRIMARY KEY, 
                   user_id INTEGER, 
                   created_at TIMESTAMP, 
                   active BOOLEAN)''')
    # إنشاء جدول طلبات الشحن
    db.execute('''CREATE TABLE IF NOT EXISTS recharge_requests
                  (id INTEGER PRIMARY KEY, 
                   user_id INTEGER, 
                   amount REAL, 
                   status TEXT, 
                   requested_at TIMESTAMP)''')
    # إنشاء حساب المدير إذا لم يكن موجودًا
    admin_email = 'yosif@gmail.com'
    admin_password = generate_password_hash('11112222')
    db.execute('''INSERT OR IGNORE INTO users 
                  (email, password, balance, name, department, year, is_admin) 
                  VALUES (?, ?, ?, ?, ?, ?, ?)''',
               (admin_email, admin_password, 100.0, 'Yosif Admin', 'إدارة', 'IT', 1))
    db.commit()
