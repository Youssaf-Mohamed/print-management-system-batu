from wtforms.validators import Email, Length, EqualTo
from wtforms import StringField, PasswordField, FloatField
from flask import Flask, request, render_template, redirect, url_for, flash, session, jsonify
from flask_wtf import FlaskForm
from wtforms import FileField, IntegerField, RadioField, SubmitField
from wtforms.validators import DataRequired, NumberRange
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import sqlite3
import os
import logging
from logging.handlers import RotatingFileHandler
from PyPDF2 import PdfReader
from flask_socketio import SocketIO, emit
import win32print
import uuid

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24).hex())
app.config['UPLOAD_DIR'] = 'Uploads'
app.config['MAX_UPLOAD_SIZE'] = 16 * 1024 * 1024  # 16MB
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Initialize SocketIO
socketio = SocketIO(app)

# Configure logging
log_file = 'logs/webapp.log'
os.makedirs('logs', exist_ok=True)
handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
handler.setFormatter(logging.Formatter(
    '%(asctime)s:%(levelname)s:%(message)s'))
logging.getLogger().setLevel(logging.INFO)
logging.getLogger().addHandler(handler)

# Database setup
DB_PATH = 'database.db'
PRINTER_NAME = 'HP_LaserJet_Pro'

# Database functions


def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    with get_db() as db:
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                balance REAL DEFAULT 10.0,
                is_admin INTEGER DEFAULT 0,
                name TEXT,
                department TEXT,
                year TEXT
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id INTEGER,
                active INTEGER DEFAULT 1,
                created_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS recharge_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS print_jobs (
                job_id TEXT PRIMARY KEY,
                user_id INTEGER,
                filename TEXT,
                status TEXT,
                created_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        db.commit()


def get_user_by_email(email):
    with get_db() as db:
        return db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()


def get_user_by_id(user_id):
    with get_db() as db:
        return db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()


def create_user(email, password):
    with get_db() as db:
        try:
            db.execute('BEGIN TRANSACTION')
            db.execute(
                'INSERT INTO users (email, password) VALUES (?, ?)',
                (email, password)
            )
            db.commit()
            return True
        except sqlite3.IntegrityError:
            db.rollback()
            return False


def update_session(session_id, user_id, active=True):
    with get_db() as db:
        db.execute(
            'UPDATE sessions SET user_id=?, active=?, created_at=? WHERE session_id=?',
            (user_id, active, datetime.now().strftime(
                '%Y-%m-%d %H:%M:%S'), session_id)
        )
        db.commit()


def create_recharge_request(user_id, amount):
    with get_db() as db:
        db.execute(
            'INSERT INTO recharge_requests (user_id, amount, created_at) VALUES (?, ?, ?)',
            (user_id, amount, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        db.commit()


def update_user_profile(user_id, name, department, year):
    with get_db() as db:
        db.execute(
            'UPDATE users SET name=?, department=?, year=? WHERE id=?',
            (name, department, year, user_id)
        )
        db.commit()


def get_admin_dashboard_stats():
    with get_db() as db:
        total_users = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        pending_requests = db.execute(
            'SELECT COUNT(*) FROM recharge_requests WHERE status = "pending"'
        ).fetchone()[0]
        recent_requests = db.execute(
            'SELECT r.id, u.email, r.amount, r.created_at FROM recharge_requests r JOIN users u ON r.user_id = u.id WHERE r.status = "pending" ORDER BY r.created_at DESC LIMIT 5'
        ).fetchall()
        return total_users, pending_requests, recent_requests


def get_recharge_requests():
    with get_db() as db:
        return db.execute(
            'SELECT r.id, u.email, r.amount, r.status, r.created_at FROM recharge_requests r JOIN users u ON r.user_id = u.id ORDER BY r.created_at DESC'
        ).fetchall()


def process_recharge_request(request_id, action):
    with get_db() as db:
        try:
            db.execute('BEGIN TRANSACTION')
            req = db.execute(
                'SELECT * FROM recharge_requests WHERE id = ?', (request_id,)
            ).fetchone()
            if req:
                if action == 'accept':
                    db.execute(
                        'UPDATE users SET balance = balance + ? WHERE id = ?',
                        (req['amount'], req['user_id'])
                    )
                    db.execute(
                        'UPDATE recharge_requests SET status = "accepted" WHERE id = ?',
                        (request_id,)
                    )
                elif action == 'reject':
                    db.execute(
                        'UPDATE recharge_requests SET status = "rejected" WHERE id = ?',
                        (request_id,)
                    )
                db.commit()
                return True
            db.rollback()
            return False
        except Exception as e:
            db.rollback()
            logging.error(
                f"Error processing recharge request {request_id}: {e}")
            return False


def create_print_job(job_id, user_id, filename):
    with get_db() as db:
        db.execute(
            'INSERT INTO print_jobs (job_id, user_id, filename, status, created_at) VALUES (?, ?, ?, ?, ?)',
            (job_id, user_id, filename, 'uploaded',
             datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        db.commit()


def update_print_job_status(job_id, status):
    with get_db() as db:
        db.execute(
            'UPDATE print_jobs SET status=? WHERE job_id=?',
            (status, job_id)
        )
        db.commit()


def update_user_balance(user_id, new_balance):
    with get_db() as db:
        db.execute('UPDATE users SET balance=? WHERE id=?',
                   (new_balance, user_id))
        db.commit()


def delete_pending_print_jobs(user_id):
    with get_db() as db:
        db.execute(
            'DELETE FROM print_jobs WHERE user_id = ? AND status = "uploaded"', (
                user_id,)
        )
        db.commit()


def get_session_status(session_id):
    with get_db() as db:
        row = db.execute(
            'SELECT active FROM sessions WHERE session_id=?', (session_id,)).fetchone()
        return bool(row and row['active']) if row else False


def setup_admin_user():
    with get_db() as db:
        admin_email = 'yosif@gmail.com'
        admin_password = generate_password_hash('11112222')
        db.execute('''
            INSERT OR IGNORE INTO users 
            (email, password, balance, name, department, year, is_admin) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (admin_email, admin_password, 100.0, 'Yosif Admin', 'إدارة', 'IT', 1))
        db.commit()
        logging.info("Admin user setup completed for email: %s", admin_email)

# Clean up old files


def cleanup_old_files():
    now = datetime.now()
    threshold = now - timedelta(hours=1)
    for fname in os.listdir(app.config['UPLOAD_DIR']):
        fpath = os.path.join(app.config['UPLOAD_DIR'], fname)
        mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
        if mtime < threshold:
            try:
                os.remove(fpath)
                logging.info(f"Deleted old file: {fpath}")
            except Exception as e:
                logging.error(f"Error deleting file {fpath}: {e}")

# WTForms classes


class PrintForm(FlaskForm):
    files = FileField('الملفات', validators=[
                      DataRequired()], render_kw={'multiple': True})
    copies = IntegerField('عدد النسخ', validators=[
                          DataRequired(), NumberRange(min=1, max=10)], default=1)
    color = RadioField('الألوان', choices=[
                       ('color', 'ألوان'), ('bw', 'أبيض وأسود')], default='bw')
    submit = SubmitField('طباعة')


class RegisterForm(FlaskForm):
    email = StringField('البريد الإلكتروني', validators=[
                        DataRequired(), Email()])
    password = PasswordField('كلمة المرور', validators=[
                             DataRequired(), Length(min=8)])
    confirm_password = PasswordField('تأكيد كلمة المرور', validators=[
                                     DataRequired(), EqualTo('password')])
    submit = SubmitField('تسجيل')


class LoginForm(FlaskForm):
    email = StringField('البريد الإلكتروني', validators=[
                        DataRequired(), Email()])
    password = PasswordField('كلمة المرور', validators=[DataRequired()])
    submit = SubmitField('تسجيل الدخول')


class ProfileForm(FlaskForm):
    name = StringField('الاسم', validators=[DataRequired()])
    department = StringField('القسم', validators=[DataRequired()])
    year = StringField('السنة الدراسية', validators=[DataRequired()])
    submit = SubmitField('تحديث')


class RechargeForm(FlaskForm):
    amount = FloatField('المبلغ', validators=[
                        DataRequired(), NumberRange(min=10)])
    submit = SubmitField('طلب شحن')

# Application setup


def setup():
    os.makedirs(app.config['UPLOAD_DIR'], exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    init_db()
    setup_admin_user()
    cleanup_old_files()


setup()

# Application routes


@app.route('/')
def index():
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data
        password = generate_password_hash(form.password.data)
        if create_user(email, password):
            flash('تم التسجيل بنجاح! يرجى تسجيل الدخول.', 'success')
            return redirect(url_for('login'))
        flash('البريد الإلكتروني مستخدم بالفعل.', 'error')
    return render_template('register.html', form=form, now=datetime.now())


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    sess_id = request.args.get('session')
    if form.validate_on_submit():
        user = get_user_by_email(form.email.data)
        if user and check_password_hash(user['password'], form.password.data):
            session['user_id'] = user['id']
            if sess_id:
                update_session(sess_id, user['id'])
            if user['is_admin']:
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('print_settings', session=sess_id))
        flash('البريد الإلكتروني أو كلمة المرور غير صحيحة.', 'error')
    return render_template('login.html', form=form, now=datetime.now())


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('تم تسجيل الخروج بنجاح.', 'success')
    return redirect(url_for('login'))


@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً.', 'error')
        return redirect(url_for('login'))
    user = get_user_by_id(session['user_id'])
    form = ProfileForm()
    if form.validate_on_submit():
        update_user_profile(
            session['user_id'], form.name.data, form.department.data, form.year.data)
        flash('تم تحديث الملف الشخصي بنجاح.', 'success')
        return redirect(url_for('profile'))
    form.name.data = user['name']
    form.department.data = user['department']
    form.year.data = user['year']
    return render_template('profile.html', form=form, user=user, now=datetime.now())


@app.route('/recharge', methods=['GET', 'POST'])
def recharge():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً.', 'error')
        return redirect(url_for('login'))
    user = get_user_by_id(session['user_id'])
    form = RechargeForm()
    if form.validate_on_submit():
        create_recharge_request(session['user_id'], form.amount.data)
        flash('تم إرسال طلب شحن الرصيد بنجاح.', 'success')
        return redirect(url_for('profile'))
    return render_template('recharge.html', form=form, user=user, now=datetime.now())


@app.route('/admin/dashboard')
def admin_dashboard():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً.', 'error')
        return redirect(url_for('login'))
    user = get_user_by_id(session['user_id'])
    if not user['is_admin']:
        flash('غير مصرح لك بالوصول إلى لوحة التحكم.', 'error')
        return redirect(url_for('print_settings'))
    total_users, pending_requests, recent_requests = get_admin_dashboard_stats()
    return render_template('admin_dashboard.html', total_users=total_users, pending_requests=pending_requests, recent_requests=recent_requests, now=datetime.now())


@app.route('/admin/recharge_requests', methods=['GET', 'POST'])
def admin_recharge_requests():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً.', 'error')
        return redirect(url_for('login'))
    user = get_user_by_id(session['user_id'])
    if not user['is_admin']:
        flash('غير مصرح لك بالوصول إلى هذه الصفحة.', 'error')
        return redirect(url_for('print_settings'))
    requests = get_recharge_requests()
    if request.method == 'POST':
        req_id = request.form.get('request_id')
        action = request.form.get('action')
        if process_recharge_request(req_id, action):
            flash('تم معالجة طلب الشحن بنجاح.', 'success')
        else:
            flash('خطأ في معالجة طلب الشحن.', 'error')
        return redirect(url_for('admin_recharge_requests'))
    return render_template('admin_recharge_requests.html', requests=requests, now=datetime.now())


@app.route('/print_settings', methods=['GET', 'POST'])
def print_settings():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً.', 'error')
        return redirect(url_for('login', session=request.args.get('session')))
    form = PrintForm()
    sess_id = request.args.get('session')
    if form.validate_on_submit():
        files = request.files.getlist('files')
        if not files:
            flash('يرجى رفع ملف واحد على الأقل.', 'error')
            return redirect(url_for('print_settings', session=sess_id))

        user = get_user_by_id(session['user_id'])
        total_cost = 0
        job_ids = []
        successful_jobs = []

        for f in files:
            if not f.filename.lower().endswith('.pdf'):
                flash(f'الملف {f.filename} ليس PDF.', 'error')
                socketio.emit('print_status', {
                    'job_id': str(uuid.uuid4()),
                    'filename': f.filename,
                    'status': 'error',
                    'message': 'الملف ليس PDF'
                })
                continue

            job_id = str(uuid.uuid4())
            fname = f"{job_id}_{f.filename}"
            fpath = os.path.join(app.config['UPLOAD_DIR'], fname)
            try:
                f.save(fpath)
                logging.info(f"File saved: {fpath}")
                socketio.emit('print_status', {
                    'job_id': job_id,
                    'filename': f.filename,
                    'status': 'uploaded',
                    'message': 'تم رفع الملف'
                })
            except Exception as e:
                logging.error(f"Error saving file {f.filename}: {e}")
                flash(f'خطأ في حفظ الملف {f.filename}.', 'error')
                socketio.emit('print_status', {
                    'job_id': job_id,
                    'filename': f.filename,
                    'status': 'error',
                    'message': f'خطأ في حفظ الملف: {e}'
                })
                continue

            try:
                pdf = PdfReader(fpath)
                num_pages = len(pdf.pages)
            except Exception as e:
                logging.error(f"PDF read error for {f.filename}: {e}")
                flash(f'خطأ في قراءة الملف {f.filename}.', 'error')
                socketio.emit('print_status', {
                    'job_id': job_id,
                    'filename': f.filename,
                    'status': 'error',
                    'message': f'خطأ في قراءة الملف: {e}'
                })
                if os.path.exists(fpath):
                    os.remove(fpath)
                continue

            cost_per_page = 0.5 if form.color.data == 'color' else 0.1
            file_cost = form.copies.data * num_pages * cost_per_page
            total_cost += file_cost

            create_print_job(job_id, user['id'], f.filename)
            job_ids.append((job_id, fpath, fname, num_pages, file_cost))

        if total_cost == 0:
            flash('لم يتم معالجة أي ملفات بنجاح.', 'error')
            return redirect(url_for('print_settings', session=sess_id))

        if user['balance'] < total_cost:
            flash('الرصيد غير كافٍ.', 'error')
            for _, fpath, _, _, _ in job_ids:
                if os.path.exists(fpath):
                    os.remove(fpath)
            delete_pending_print_jobs(user['id'])
            return redirect(url_for('print_settings', session=sess_id))

        actual_cost = 0
        for job_id, fpath, fname, num_pages, file_cost in job_ids:
            try:
                socketio.emit('print_status', {
                    'job_id': job_id,
                    'filename': fname,
                    'status': 'printing',
                    'message': 'قيد الطباعة'
                })
                hprinter = win32print.OpenPrinter(PRINTER_NAME)
                try:
                    printer_info = win32print.GetPrinter(hprinter, 2)
                    if printer_info['Status'] != 0:
                        raise Exception("الطابعة غير جاهزة")
                    job_info = {
                        "pDocName": f"Print Job {fname}",
                        "pDataType": "RAW"
                    }
                    hjob = win32print.StartDocPrinter(
                        hprinter, 1, (job_info["pDocName"], None, job_info["pDataType"]))
                    with open(fpath, 'rb') as f:
                        while chunk := f.read(8192):
                            win32print.WritePrinter(hprinter, chunk)
                    win32print.EndDocPrinter(hprinter)
                    logging.info(
                        f"Printed {fname} on {PRINTER_NAME}, pages={num_pages}, copies={form.copies.data}")
                    update_print_job_status(job_id, 'completed')
                    socketio.emit('print_status', {
                        'job_id': job_id,
                        'filename': fname,
                        'status': 'completed',
                        'message': 'تمت الطباعة بنجاح'
                    })
                    successful_jobs.append(file_cost)
                    actual_cost += file_cost
                finally:
                    win32print.ClosePrinter(hprinter)
            except Exception as e:
                logging.error(f"Print error for {fname}: {e}")
                flash(f'خطأ في طباعة الملف {fname}: {e}', 'error')
                update_print_job_status(job_id, 'error')
                socketio.emit('print_status', {
                    'job_id': job_id,
                    'filename': fname,
                    'status': 'error',
                    'message': f'خطأ في الطباعة: {e}'
                })
            finally:
                if os.path.exists(fpath):
                    os.remove(fpath)

        if successful_jobs:
            new_bal = user['balance'] - actual_cost
            update_user_balance(user['id'], new_bal)
            flash(
                f'تمت طباعة الملفات بنجاح بتكلفة {actual_cost} جنيه.', 'success')
        else:
            flash('لم يتم طباعة أي ملفات بنجاح.', 'error')

        if sess_id:
            update_session(sess_id, user['id'], active=False)
        return redirect(url_for('print_settings', session=sess_id))

    return render_template('print_settings.html', form=form, now=datetime.now())


@app.route('/session_status/<sess_id>')
def session_status():
    return jsonify({'active': get_session_status(sess_id)})


@socketio.on('connect')
def handle_connect():
    logging.info('Client connected to WebSocket')


if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
