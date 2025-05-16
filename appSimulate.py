import os
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request, render_template, redirect, url_for, session, flash, jsonify
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, FileField, IntegerField, SelectField
from wtforms.validators import DataRequired, Email, EqualTo
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import logging
from PyPDF2 import PdfReader
from database import get_db, init_db

# ----- Configuration -----
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, 'Uploads')
LOG_DIR = os.path.join(BASE_DIR, 'logs')
DB_PATH = os.path.join(BASE_DIR, 'print_queue.db')
PRINTER_NAME = 'Simulated_Printer'  # محاكاة الطابعة للاختبار
SESSION_TTL = timedelta(hours=1)
MAX_UPLOAD_SIZE = 16 * 1024 * 1024

# ----- App Setup -----
app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['UPLOAD_FOLDER'] = UPLOAD_DIR
app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_SIZE

# ----- Logging -----
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, 'webapp.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ----- Initialize -----
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

with app.app_context():
    init_db()

# ----- Forms -----


class LoginForm(FlaskForm):
    email = StringField('الإيميل', validators=[DataRequired(), Email()])
    password = PasswordField('كلمة المرور', validators=[DataRequired()])
    submit = SubmitField('تسجيل الدخول')


class RegisterForm(FlaskForm):
    email = StringField('الإيميل', validators=[DataRequired(), Email()])
    password = PasswordField('كلمة المرور', validators=[DataRequired()])
    confirm_password = PasswordField('تأكيد كلمة المرور', validators=[
                                     DataRequired(), EqualTo('password')])
    submit = SubmitField('تسجيل')


class PrintForm(FlaskForm):
    file = FileField('اختر الملف', validators=[DataRequired()])
    copies = IntegerField('عدد النسخ', validators=[DataRequired()], default=1)
    color = SelectField('الألوان', choices=[
                        ('color', 'ألوان'), ('mono', 'أبيض وأسود')], validators=[DataRequired()])
    submit = SubmitField('طباعة')


class ProfileForm(FlaskForm):
    name = StringField('الاسم', validators=[DataRequired()])
    department = StringField('القسم', validators=[DataRequired()])
    year = StringField('السنة الدراسية', validators=[DataRequired()])
    submit = SubmitField('تحديث')


class RechargeForm(FlaskForm):
    amount = IntegerField('المبلغ', validators=[DataRequired()])
    submit = SubmitField('طلب شحن')

# ----- Utility Functions -----


def cleanup_old_files():
    now = datetime.now()
    for folder in (UPLOAD_DIR,):
        for fname in os.listdir(folder):
            path = os.path.join(folder, fname)  # Corrected line
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(path))
                if now - mtime > SESSION_TTL:
                    os.remove(path)
                    logging.info(f"Removed old file: {path}")
            except Exception as e:
                logging.error(f"Error cleaning file {path}: {e}")
    db = get_db()
    db.execute('DELETE FROM sessions WHERE created_at < ?',
               ((now - SESSION_TTL).strftime('%Y-%m-%d %H:%M:%S'),))
    db.commit()


def cleanup_logs():
    while True:
        time.sleep(300)  # 5 دقائق
        now = datetime.now()
        for fname in os.listdir(LOG_DIR):
            if fname.endswith('.log'):
                path = os.path.join(LOG_DIR, fname)
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(path))
                    # الاحتفاظ بالسجلات لمدة 7 أيام
                    if now - mtime > timedelta(days=7):
                        os.remove(path)
                        logging.info(f"Removed old log file: {path}")
                except Exception as e:
                    logging.error(f"Error cleaning log file {path}: {e}")


# بدء خيط تنظيف السجلات
threading.Thread(target=cleanup_logs, daemon=True).start()

# ----- Routes -----


@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data
        password = generate_password_hash(form.password.data)
        try:
            db = get_db()
            db.execute(
                'INSERT INTO users (email, password, balance, name, department, year, is_admin) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (email, password, 10.0, 'اسم افتراضي',
                 'قسم افتراضي', 'سنة افتراضية', 0)
            )
            db.commit()
            logging.info(f"New user registered: {email}")
            flash('تم التسجيل بنجاح! يرجى تسجيل الدخول.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('الإيميل مستخدم بالفعل.', 'error')
    return render_template('register.html', form=form, now=datetime.now())


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    sess_id = request.args.get('session')
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        db = get_db()
        user = db.execute(
            'SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            if sess_id:
                db.execute(
                    'UPDATE sessions SET user_id=?, active=?, created_at=? WHERE session_id=?',
                    (user['id'], True, datetime.now().strftime(
                        '%Y-%m-%d %H:%M:%S'), sess_id)
                )
                db.commit()
                logging.info(f"User {email} logged in for session {sess_id}")
            if user['is_admin']:
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('print_settings', session=sess_id))
        flash('بيانات تسجيل الدخول غير صحيحة.', 'error')
    return render_template('login.html', form=form, now=datetime.now())


@app.route('/logout', methods=['GET'])
def logout():
    session.pop('user_id', None)
    flash('تم تسجيل الخروج بنجاح.', 'success')
    return redirect(url_for('login'))


@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً.', 'error')
        return redirect(url_for('login'))
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?',
                      (session['user_id'],)).fetchone()
    form = ProfileForm(
        data={'name': user['name'], 'department': user['department'], 'year': user['year']})
    if form.validate_on_submit():
        db.execute('UPDATE users SET name=?, department=?, year=? WHERE id=?',
                   (form.name.data, form.department.data, form.year.data, session['user_id']))
        db.commit()
        flash('تم تحديث البيانات بنجاح.', 'success')
        return redirect(url_for('profile'))
    return render_template('profile.html', form=form, user=user, now=datetime.now())


@app.route('/recharge', methods=['GET', 'POST'])
def recharge():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً.', 'error')
        return redirect(url_for('login'))
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?',
                      (session['user_id'],)).fetchone()
    form = RechargeForm()
    if form.validate_on_submit():
        db.execute('INSERT INTO recharge_requests (user_id, amount, status, requested_at) VALUES (?, ?, ?, ?)',
                   (session['user_id'], form.amount.data, 'pending', datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        db.commit()
        flash('تم إرسال طلب الشحن بنجاح.', 'success')
        return redirect(url_for('profile'))
    return render_template('recharge.html', form=form, user=user, now=datetime.now())


@app.route('/admin/dashboard', methods=['GET'])
def admin_dashboard():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً.', 'error')
        return redirect(url_for('login'))
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?',
                      (session['user_id'],)).fetchone()
    if not user or not user['is_admin']:
        flash('غير مصرح لك بالوصول إلى هذه الصفحة.', 'error')
        return redirect(url_for('profile'))
    total_users = db.execute(
        'SELECT COUNT(*) as count FROM users').fetchone()['count']
    pending_recharges = db.execute(
        'SELECT COUNT(*) as count FROM recharge_requests WHERE status="pending"').fetchone()['count']
    requests = db.execute('''SELECT r.id, u.email, r.amount, r.status, r.requested_at
                             FROM recharge_requests r JOIN users u ON r.user_id = u.id
                             WHERE r.status = 'pending' LIMIT 5''').fetchall()
    return render_template('admin_dashboard.html', total_users=total_users, pending_recharges=pending_recharges, requests=requests, user=user, now=datetime.now())


@app.route('/admin/recharge_requests', methods=['GET'])
def admin_recharge_requests():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً.', 'error')
        return redirect(url_for('login'))
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?',
                      (session['user_id'],)).fetchone()
    if not user or not user['is_admin']:
        flash('غير مصرح لك بالوصول إلى هذه الصفحة.', 'error')
        return redirect(url_for('profile'))
    requests = db.execute('''SELECT r.id, u.email, r.amount, r.status, r.requested_at
                             FROM recharge_requests r JOIN users u ON r.user_id = u.id
                             WHERE r.status = 'pending' ''').fetchall()
    return render_template('admin_recharge_requests.html', requests=requests, user=user, now=datetime.now())


@app.route('/admin/approve_recharge/<int:req_id>', methods=['POST'])
def admin_approve_recharge(req_id):
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً.', 'error')
        return redirect(url_for('login'))
    db = get_db()
    user = db.execute('SELECT is_admin FROM users WHERE id=?',
                      (session['user_id'],)).fetchone()
    if not user or not user['is_admin']:
        flash('غير مصرح لك بالوصول إلى هذه الصفحة.', 'error')
        return redirect(url_for('profile'))
    req = db.execute(
        'SELECT * FROM recharge_requests WHERE id=? AND status="pending"', (req_id,)).fetchone()
    if req:
        db.execute('UPDATE users SET balance = balance + ? WHERE id=?',
                   (req['amount'], req['user_id']))
        db.execute(
            'UPDATE recharge_requests SET status="approved" WHERE id=?', (req_id,))
        db.commit()
        flash('تم قبول طلب الشحن.', 'success')
    else:
        flash('طلب الشحن غير موجود أو تم معالجته بالفعل.', 'error')
    return redirect(url_for('admin_recharge_requests'))


@app.route('/admin/reject_recharge/<int:req_id>', methods=['POST'])
def admin_reject_recharge(req_id):
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً.', 'error')
        return redirect(url_for('login'))
    db = get_db()
    user = db.execute('SELECT is_admin FROM users WHERE id=?',
                      (session['user_id'],)).fetchone()
    if not user or not user['is_admin']:
        flash('غير مصرح لك بالوصول إلى هذه الصفحة.', 'error')
        return redirect(url_for('profile'))
    req = db.execute(
        'SELECT * FROM recharge_requests WHERE id=? AND status="pending"', (req_id,)).fetchone()
    if req:
        db.execute(
            'UPDATE recharge_requests SET status="rejected" WHERE id=?', (req_id,))
        db.commit()
        flash('تم رفض طلب الشحن.', 'success')
    else:
        flash('طلب الشحن غير موجود أو تم معالجته بالفعل.', 'error')
    return redirect(url_for('admin_recharge_requests'))


@app.route('/print_settings', methods=['GET', 'POST'])
def print_settings():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً.', 'error')
        return redirect(url_for('login', session=request.args.get('session')))
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?',
                      (session['user_id'],)).fetchone()
    form = PrintForm()
    sess_id = request.args.get('session')
    if form.validate_on_submit():
        f = form.file.data
        if not f.filename.lower().endswith('.pdf'):
            flash('يرجى رفع ملف PDF فقط.', 'error')
            return redirect(url_for('print_settings', session=sess_id))
        fname = f"{datetime.now().timestamp()}_{f.filename}"
        fpath = os.path.join(UPLOAD_DIR, fname)
        f.save(fpath)
        try:
            pdf = PdfReader(fpath)
            num_pages = len(pdf.pages)
        except Exception as e:
            logging.error(f"PDF read error {f.filename}: {e}")
            flash(f'خطأ في قراءة الملف: {e}', 'error')
            os.remove(fpath)
            return redirect(url_for('print_settings', session=sess_id))
        cost_per_page = 1.0 if form.color.data == 'color' else 0.5
        total_cost = form.copies.data * num_pages * cost_per_page
        db = get_db()
        user = db.execute('SELECT balance FROM users WHERE id=?',
                          (session['user_id'],)).fetchone()
        if user['balance'] < total_cost:
            flash('الرصيد غير كافٍ.', 'error')
            os.remove(fpath)
            return redirect(url_for('print_settings', session=sess_id))
        try:
            logging.info(
                f"Simulated printing {fname}, pages={num_pages}, copies={form.copies.data}, color={form.color.data}, cost={total_cost}")
            new_bal = user['balance'] - total_cost
            db.execute('UPDATE users SET balance=? WHERE id=?',
                       (new_bal, session['user_id']))
            db.execute(
                'UPDATE sessions SET active=? WHERE session_id=?', (False, sess_id))
            db.commit()
            os.remove(fpath)
            flash('تمت محاكاة الطباعة بنجاح!', 'success')
            return redirect(url_for('success'))
        except Exception as e:
            logging.error(f"Simulated print error: {e}")
            flash(f'خطأ في محاكاة الطباعة: {e}', 'error')
            os.remove(fpath)
            return redirect(url_for('print_settings', session=sess_id))
    return render_template('print_settings.html', form=form, user=user, now=datetime.now())


@app.route('/success')
def success():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً.', 'error')
        return redirect(url_for('login'))
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?',
                      (session['user_id'],)).fetchone()
    return render_template('success.html', user=user, now=datetime.now())


@app.route('/session_status')
def session_status():
    sess_id = request.args.get('session')
    db = get_db()
    row = db.execute(
        'SELECT active FROM sessions WHERE session_id=?', (sess_id,)).fetchone()
    return jsonify({'active': bool(row and row['active'])})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
