from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
from functools import wraps
import secrets
import re

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(32)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///hotel.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==================== МОДЕЛИ ====================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    bookings = db.relationship('Booking', backref='user', lazy=True, cascade='all, delete-orphan')

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event_name = db.Column(db.String(200), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.String(50), nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    attendees = db.Column(db.Integer, nullable=False)
    coffee_break = db.Column(db.Boolean, default=False)
    business_lunch = db.Column(db.Boolean, default=False)
    total_price = db.Column(db.Float, nullable=False)
    comments = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ==================== ДЕКОРАТОРЫ ====================
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or not session.get('is_admin'):
            flash('Доступ запрещён', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def is_time_slot_available(booking_date, booking_time, duration, exclude_booking_id=None):
    """Проверка, свободно ли время"""
    try:
        start_hour = int(booking_time.split(':')[0])
        start_minute = int(booking_time.split(':')[1])
        booking_start = start_hour + start_minute / 60
        booking_end = booking_start + duration
        
        query = Booking.query.filter_by(date=booking_date, status='confirmed')
        if exclude_booking_id:
            query = query.filter(Booking.id != exclude_booking_id)
        
        existing_bookings = query.all()
        
        for booking in existing_bookings:
            exist_start_hour = int(booking.time.split(':')[0])
            exist_start_minute = int(booking.time.split(':')[1])
            exist_start = exist_start_hour + exist_start_minute / 60
            exist_end = exist_start + booking.duration
            
            if not (booking_end <= exist_start or booking_start >= exist_end):
                return False, f"Время {booking.time} уже занято"
        
        return True, "Время свободно"
    except Exception as e:
        return False, f"Ошибка проверки: {str(e)}"

# ==================== СОЗДАНИЕ БД ====================
with app.app_context():
    db.create_all()
    
    if not User.query.filter_by(email='admin@altai-hotel.ru').first():
        admin = User(
            name='Администратор',
            email='admin@altai-hotel.ru',
            phone='+7 (800) 700-36-50',
            password=generate_password_hash('admin123'),
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()
        print('✅ Админ создан: admin@altai-hotel.ru / admin123')

# ==================== МАРШРУТЫ ====================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contacts')
def contacts():
    return render_template('contacts.html')

@app.route('/booking', methods=['GET', 'POST'])
@login_required
def booking():
    if request.method == 'POST':
        try:
            event_name = request.form.get('event_name', 'Мероприятие')
            booking_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
            booking_time = request.form.get('time', '12:00')
            duration = int(request.form.get('duration', 1))
            attendees = int(request.form.get('attendees', 1))
            coffee = 'coffee_break' in request.form
            lunch = 'business_lunch' in request.form
            comments = request.form.get('message', '')
            
            if booking_date < date.today():
                flash('❌ Нельзя выбрать прошедшую дату', 'danger')
                return redirect(url_for('booking'))
            
            is_available, message = is_time_slot_available(booking_date, booking_time, duration)
            if not is_available:
                flash(f'❌ {message}', 'danger')
                return redirect(url_for('booking'))
            
            total = 1400 * duration
            if coffee:
                total += 500 * attendees
            if lunch:
                total += 450 * attendees
            
            booking = Booking(
                user_id=session['user_id'],
                event_name=event_name,
                date=booking_date,
                time=booking_time,
                duration=duration,
                attendees=attendees,
                coffee_break=coffee,
                business_lunch=lunch,
                total_price=total,
                comments=comments
            )
            db.session.add(booking)
            db.session.commit()
            flash('✅ Бронирование успешно создано!', 'success')
            return redirect(url_for('personal'))
        except Exception as e:
            flash(f'❌ Ошибка: {str(e)}', 'danger')
            return redirect(url_for('booking'))
    
    return render_template('booking.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('personal'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['is_admin'] = user.is_admin
            flash(f'Добро пожаловать, {user.name}!', 'success')
            
            if user.is_admin:
                return redirect(url_for('admin'))
            return redirect(url_for('personal'))
        else:
            flash('❌ Неверный email или пароль', 'danger')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('personal'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        email_pattern = r'^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$'
        if not re.match(email_pattern, email, re.IGNORECASE):
            flash('❌ Неверный формат email', 'danger')
            return render_template('register.html')
        
        phone_clean = re.sub(r'[\s\(\)-]', '', phone)
        if not (phone_clean.startswith('+7') or phone_clean.startswith('8')):
            flash('❌ Неверный формат телефона. Используйте +7 или 8', 'danger')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('❌ Этот email уже зарегистрирован', 'danger')
            return render_template('register.html')
        
        if len(password) < 6:
            flash('❌ Пароль должен содержать минимум 6 символов', 'danger')
            return render_template('register.html')
        
        if password != confirm_password:
            flash('❌ Пароли не совпадают', 'danger')
            return render_template('register.html')
        
        new_user = User(
            name=name,
            email=email,
            phone=phone,
            password=generate_password_hash(password)
        )
        db.session.add(new_user)
        db.session.commit()
        
        flash('✅ Регистрация успешна! Теперь вы можете войти.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))

@app.route('/personal')
@login_required
def personal():
    user = User.query.get(session['user_id'])
    return render_template('personal.html', user=user)

# ==================== API ДЛЯ ЛИЧНОГО КАБИНЕТА ====================
@app.route('/api/user/bookings')
@login_required
def api_user_bookings():
    bookings = Booking.query.filter_by(user_id=session['user_id']).order_by(Booking.date.desc()).all()
    result = []
    for b in bookings:
        result.append({
            'id': b.id,
            'event_name': b.event_name,
            'date': b.date.strftime('%Y-%m-%d'),
            'time': b.time,
            'duration': b.duration,
            'attendees': b.attendees,
            'total_price': b.total_price,
            'status': b.status,
            'comments': b.comments,
            'coffee_break': b.coffee_break,
            'business_lunch': b.business_lunch
        })
    return jsonify(result)

@app.route('/api/user/profile')
@login_required
def api_user_profile():
    user = User.query.get(session['user_id'])
    return jsonify({
        'id': user.id,
        'name': user.name,
        'email': user.email,
        'phone': user.phone,
        'is_admin': user.is_admin
    })

# ==================== API ДЛЯ АДМИНКИ ====================
@app.route('/api/admin/bookings')
@admin_required
def api_get_bookings():
    status = request.args.get('status')
    date_filter = request.args.get('date')
    
    query = Booking.query
    if status and status != 'all':
        query = query.filter_by(status=status)
    if date_filter:
        try:
            query = query.filter_by(date=datetime.strptime(date_filter, '%Y-%m-%d').date())
        except:
            pass
    
    bookings = query.order_by(Booking.date.desc()).all()
    result = []
    for b in bookings:
        result.append({
            'id': b.id,
            'user_id': b.user_id,
            'user_name': b.user.name if b.user else 'Гость',
            'event_name': b.event_name,
            'date': b.date.strftime('%Y-%m-%d'),
            'time': b.time,
            'duration': b.duration,
            'attendees': b.attendees,
            'total_price': b.total_price,
            'status': b.status,
            'comments': b.comments
        })
    return jsonify(result)

@app.route('/api/admin/users')
@admin_required
def api_get_users():
    search = request.args.get('search', '')
    query = User.query.filter_by(is_admin=False)
    if search:
        query = query.filter(
            db.or_(
                User.name.contains(search),
                User.email.contains(search)
            )
        )
    
    users = query.all()
    result = []
    for u in users:
        bookings_count = Booking.query.filter_by(user_id=u.id).count()
        result.append({
            'id': u.id,
            'name': u.name,
            'email': u.email,
            'phone': u.phone,
            'bookings_count': bookings_count
        })
    return jsonify(result)

@app.route('/api/admin/stats')
@admin_required
def api_get_stats():
    total_bookings = Booking.query.count()
    pending_bookings = Booking.query.filter_by(status='pending').count()
    total_users = User.query.filter_by(is_admin=False).count()
    confirmed_revenue = db.session.query(db.func.sum(Booking.total_price)).filter_by(status='confirmed').scalar() or 0
    
    return jsonify({
        'total_bookings': total_bookings,
        'pending_bookings': pending_bookings,
        'total_users': total_users,
        'total_revenue': confirmed_revenue
    })

@app.route('/admin/update_status/<int:booking_id>', methods=['POST'])
@admin_required
def update_status(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    new_status = request.form.get('status')
    if new_status in ['pending', 'confirmed', 'cancelled']:
        booking.status = new_status
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False}), 400

@app.route('/admin/delete_booking/<int:booking_id>', methods=['POST'])
@admin_required
def admin_delete_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    db.session.delete(booking)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/delete_booking/<int:booking_id>', methods=['POST'])
@login_required
def delete_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    
    if booking.user_id != session['user_id'] and not session.get('is_admin'):
        flash('❌ Нельзя удалить чужое бронирование', 'danger')
        return redirect(url_for('personal'))
    
    db.session.delete(booking)
    db.session.commit()
    flash('✅ Бронирование удалено', 'success')
    
    if session.get('is_admin'):
        return redirect(url_for('admin'))
    return redirect(url_for('personal'))

@app.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    user = User.query.get(session['user_id'])
    user.name = request.form.get('name')
    user.phone = request.form.get('phone')
    
    new_password = request.form.get('new_password')
    if new_password:
        if len(new_password) >= 6:
            user.password = generate_password_hash(new_password)
            flash('✅ Пароль обновлён', 'success')
        else:
            flash('❌ Пароль должен быть минимум 6 символов', 'danger')
            return redirect(url_for('personal'))
    
    db.session.commit()
    session['user_name'] = user.name
    flash('✅ Профиль обновлён!', 'success')
    return redirect(url_for('personal'))

@app.route('/admin')
@admin_required
def admin():
    return render_template('admin.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)