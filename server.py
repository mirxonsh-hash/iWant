# server.py - ПОЛНЫЙ ИСПРАВЛЕННЫЙ КОД
from flask import Flask, request, jsonify, session, render_template, redirect, url_for, send_from_directory
import os
import uuid
import psycopg2
import re
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import logging
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-prod')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# База данных
DB_CONFIG = {
    'host': 'dpg-d63t4ih4tr6s73a46rtg-a.frankfurt-postgres.render.com',
    'database': 'barber_db_33bs',
    'user': 'barber_db_33bs_user',
    'password': 'BL1BlEQaugJijaXJC6VWOfpacuO6pAid',
    'port': '5432'
}

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
OWNER_ID = int(os.environ.get('OWNER_ID', 0))

# Декораторы
def require_user(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            session['user_id'] = str(uuid.uuid4())
        return f(*args, **kwargs)
    return decorated_function

def require_master(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'master_code' not in session:
            return jsonify({'error': 'Требуется вход мастера'}), 401
        return f(*args, **kwargs)
    return decorated_function

# Подключение к БД
def get_db():
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        logger.error(f"DB connection error: {e}")
        return None

# Инициализация БД
def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            # Таблица masters
            cur.execute('''
                CREATE TABLE IF NOT EXISTS masters (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(20) UNIQUE NOT NULL,
                    full_name VARCHAR(200) NOT NULL,
                    phone VARCHAR(20),
                    password_hash VARCHAR(255),
                    price DECIMAL(10,2) DEFAULT 1000,
                    avatar_url VARCHAR(500),
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица appointments
            cur.execute('''
                CREATE TABLE IF NOT EXISTS appointments (
                    id SERIAL PRIMARY KEY,
                    master_code VARCHAR(20) NOT NULL,
                    client_name VARCHAR(200) NOT NULL,
                    client_phone VARCHAR(20) NOT NULL,
                    service_type VARCHAR(100) DEFAULT 'Стрижка',
                    price DECIMAL(10,2) DEFAULT 1000,
                    appointment_date DATE NOT NULL,
                    appointment_time TIME NOT NULL,
                    duration_minutes INTEGER DEFAULT 60,
                    notes TEXT,
                    status VARCHAR(20) DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица clients
            cur.execute('''
                CREATE TABLE IF NOT EXISTS clients (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(100) NOT NULL,
                    master_code VARCHAR(20) NOT NULL,
                    master_name VARCHAR(200) NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, master_code)
                )
            ''')
            
            # Таблица telegram_users
            cur.execute('''
                CREATE TABLE IF NOT EXISTS telegram_users (
                    telegram_id VARCHAR(100) PRIMARY KEY,
                    username VARCHAR(100),
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица user_favorites
            cur.execute('''
                CREATE TABLE IF NOT EXISTS user_favorites (
                    telegram_id VARCHAR(100),
                    master_code VARCHAR(20),
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (telegram_id, master_code)
                )
            ''')
            
        conn.commit()
    logger.info("Database initialized successfully")

def create_test_master():
    """Создать тестового барбера для демонстрации"""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                # Проверяем, не существует ли уже тестовый барбер
                cur.execute("SELECT id FROM masters WHERE code = 'TEST'")
                if not cur.fetchone():
                    cur.execute('''
                        INSERT INTO masters (code, full_name, phone, password_hash, price)
                        VALUES (%s, %s, %s, %s, %s)
                    ''', ('TEST', 'Тестовый Барбер', '+79990001122', 
                          generate_password_hash('123456'), 1500))
                    conn.commit()
                    logger.info("Test master created: TEST / 123456")
    except Exception as e:
        logger.error(f"Error creating test master: {e}")

# ==================== ГЛАВНЫЕ СТРАНИЦЫ ====================

@app.route('/')
@require_user
def index():
    return render_template('index.html')

@app.route('/master_login', methods=['GET', 'POST'])
def master_login():
    if request.method == 'GET':
        return render_template('master_login.html')
    
    login_code = request.form.get('login_code', '').upper()
    password = request.form.get('password', '')
    
    if not login_code or not password:
        return jsonify({'success': False, 'message': 'Введите код и пароль'})
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                SELECT m.full_name, m.password_hash 
                FROM masters m 
                WHERE m.code = %s AND m.is_active = TRUE
            ''', (login_code,))
            
            master = cur.fetchone()
            
            if not master or not check_password_hash(master[1], password):
                return jsonify({'success': False, 'message': 'Неверный код или пароль'})
            
            session['master_code'] = login_code
            session['master_name'] = master[0]
            session.permanent = True
    
    return jsonify({
        'success': True,
        'redirect': '/master_panel'
    })

@app.route('/master_panel')
@require_master
def master_panel():
    today = datetime.now().date()
    start_date = request.args.get('from', today.strftime('%Y-%m-%d'))
    end_date = request.args.get('to', (today + timedelta(days=7)).strftime('%Y-%m-%d'))
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                SELECT id, client_name, client_phone, service_type, price,
                       appointment_date, appointment_time, duration_minutes,
                       notes, status
                FROM appointments 
                WHERE master_code = %s 
                AND appointment_date BETWEEN %s AND %s
                ORDER BY appointment_date, appointment_time
            ''', (session['master_code'], start_date, end_date))
            
            appointments = []
            for row in cur.fetchall():
                appointments.append({
                    'id': row[0],
                    'client_name': row[1],
                    'client_phone': row[2],
                    'service_type': row[3],
                    'price': float(row[4]) if row[4] else None,
                    'appointment_date': row[5].strftime('%Y-%m-%d') if row[5] else None,
                    'appointment_time': str(row[6]) if row[6] else None,
                    'duration_minutes': row[7] or 60,
                    'notes': row[8],
                    'status': row[9]
                })
    
    return render_template('master_panel.html', 
                         master_name=session['master_name'],
                         master_code=session['master_code'],
                         appointments=appointments,
                         start_date=start_date,
                         end_date=end_date)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ==================== API ДЛЯ ВЕБ-ИНТЕРФЕЙСА ====================

@app.route('/get_user_barbers')
@require_user
def get_user_barbers():
    """Получить барберов пользователя (веб)"""
    try:
        user_id = session['user_id']
        
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT m.code, m.full_name as name, 
                           COALESCE(m.avatar_url, '/static/default_barber.png') as avatar,
                           m.price
                    FROM clients c
                    JOIN masters m ON c.master_code = m.code
                    WHERE c.user_id = %s AND m.is_active = TRUE
                    ORDER BY c.added_at DESC
                ''', (user_id,))
                
                barbers = []
                for row in cur.fetchall():
                    barbers.append({
                        'code': row[0],
                        'name': row[1],
                        'avatar': row[2],
                        'price': float(row[3]) if row[3] else 1000
                    })
                
                return jsonify({'success': True, 'barbers': barbers})
        
    except Exception as e:
        logger.error(f"Error getting user barbers: {e}")
        return jsonify({'success': False, 'barbers': []})

@app.route('/add_barber', methods=['POST'])
@require_user
def add_barber():
    """Добавить барбера пользователю"""
    user_id = session['user_id']
    master_code = request.form.get('master_code', '').strip().upper()
    
    if not master_code:
        return jsonify({'success': False, 'message': 'Введите код барбера'})
    
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                # Проверяем, существует ли барбер
                cur.execute('''
                    SELECT code, full_name, avatar_url, price 
                    FROM masters 
                    WHERE code = %s AND is_active = TRUE
                ''', (master_code,))
                
                master = cur.fetchone()
                
                if not master:
                    return jsonify({'success': False, 'message': 'Барбер не найден'})
                
                # Проверяем, не добавлен ли уже этот барбер
                cur.execute('''
                    SELECT 1 FROM clients 
                    WHERE user_id = %s AND master_code = %s
                ''', (user_id, master_code))
                
                if cur.fetchone():
                    return jsonify({'success': False, 'message': 'Этот барбер уже добавлен'})
                
                # Добавляем барбера пользователю
                cur.execute('''
                    INSERT INTO clients (user_id, master_code, master_name)
                    VALUES (%s, %s, %s)
                    RETURNING id
                ''', (user_id, master_code, master[1]))
                
                # Получаем всех барберов пользователя для возврата
                cur.execute('''
                    SELECT m.code, m.full_name as name, 
                           COALESCE(m.avatar_url, '/static/default_barber.png') as avatar,
                           m.price
                    FROM clients c
                    JOIN masters m ON c.master_code = m.code
                    WHERE c.user_id = %s AND m.is_active = TRUE
                    ORDER BY c.added_at DESC
                ''', (user_id,))
                
                user_barbers = []
                for row in cur.fetchall():
                    user_barbers.append({
                        'code': row[0],
                        'name': row[1],
                        'avatar': row[2],
                        'price': float(row[3]) if row[3] else 1000
                    })
                
                conn.commit()
                
        return jsonify({
            'success': True,
            'message': 'Барбер успешно добавлен!',
            'barbers': user_barbers
        })
        
    except Exception as e:
        logger.error(f"Error adding barber: {e}")
        return jsonify({'success': False, 'message': 'Ошибка сервера'})

# ==================== API ДЛЯ БАРБЕРОВ ====================

@app.route('/api/masters', methods=['POST'])
def api_add_master():
    """Добавить барбера (бот)"""
    data = request.json
    owner_id = data.get('owner_id')
    
    if not owner_id or int(owner_id) != OWNER_ID:
        return jsonify({'error': 'Unauthorized'}), 403
    
    code = data.get('code', '').upper()
    full_name = data.get('full_name')
    phone = data.get('phone')
    password = data.get('password')
    
    if not all([code, full_name, phone, password]) or len(password) < 6:
        return jsonify({'error': 'Invalid data'}), 400
    
    with get_db() as conn:
        with conn.cursor() as cur:
            # Проверка уникальности
            cur.execute('SELECT id FROM masters WHERE code = %s', (code,))
            if cur.fetchone():
                return jsonify({'error': 'Code already exists'}), 400
            
            # Создание барбера
            cur.execute('''
                INSERT INTO masters (code, full_name, phone, password_hash)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            ''', (code, full_name, phone, generate_password_hash(password)))
            
            master_id = cur.fetchone()[0]
            
        conn.commit()
    
    return jsonify({'success': True, 'master_id': master_id}), 201

@app.route('/api/masters', methods=['GET'])
def get_masters():
    """Получить всех барберов"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                SELECT code, full_name, phone, is_active 
                FROM masters 
                ORDER BY created_at DESC
            ''')
            
            masters = []
            for row in cur.fetchall():
                masters.append({
                    'code': row[0],
                    'full_name': row[1],
                    'phone': row[2],
                    'is_active': row[3]
                })
    
    return jsonify({'masters': masters})

# ==================== API ДЛЯ ЗАПИСЕЙ ====================

@app.route('/api/appointments', methods=['GET'])
def get_appointments_api():
    """Получить записи"""
    master_code = request.args.get('master_code') or session.get('master_code')
    date_from = request.args.get('from')
    date_to = request.args.get('to')
    
    if not master_code:
        return jsonify({'error': 'Master code required'}), 400
    
    with get_db() as conn:
        with conn.cursor() as cur:
            query = '''
                SELECT id, client_name, client_phone, service_type, price,
                       appointment_date, appointment_time, duration_minutes,
                       notes, status
                FROM appointments 
                WHERE master_code = %s
            '''
            params = [master_code]
            
            if date_from and date_to:
                query += ' AND appointment_date BETWEEN %s AND %s'
                params.extend([date_from, date_to])
            
            query += ' ORDER BY appointment_date, appointment_time'
            cur.execute(query, params)
            
            appointments = []
            for row in cur.fetchall():
                appointments.append({
                    'id': row[0],
                    'client_name': row[1],
                    'client_phone': row[2],
                    'service_type': row[3],
                    'price': float(row[4]) if row[4] else None,
                    'date': row[5].isoformat() if row[5] else None,
                    'time': str(row[6]) if row[6] else None,
                    'duration_minutes': row[7] or 60,
                    'notes': row[8],
                    'status': row[9]
                })
    
    return jsonify({'appointments': appointments})

@app.route('/api/appointments', methods=['POST'])
def create_appointment_api():
    """Создать запись"""
    data = request.json
    
    if 'master_code' in session:
        master_code = session['master_code']
    else:
        master_code = data.get('master_code', '').upper()
    
    required = ['client_name', 'client_phone', 'date', 'time']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'Missing {field}'}), 400
    
    # Проверка времени
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                SELECT id FROM appointments 
                WHERE master_code = %s AND appointment_date = %s 
                AND appointment_time = %s AND status != 'cancelled'
            ''', (master_code, data['date'], data['time']))
            
            if cur.fetchone():
                return jsonify({'error': 'Time slot taken'}), 409
            
            # Создаем запись
            cur.execute('''
                INSERT INTO appointments 
                (master_code, client_name, client_phone, service_type, price,
                 appointment_date, appointment_time, duration_minutes, notes, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
                RETURNING id
            ''', (
                master_code,
                data['client_name'],
                data['client_phone'],
                data.get('service_type', 'Стрижка'),
                data.get('price', 1000),
                data['date'],
                data['time'],
                data.get('duration_minutes', 60),
                data.get('notes', ''),
            ))
            
            appointment_id = cur.fetchone()[0]
        
        conn.commit()
    
    return jsonify({'success': True, 'appointment_id': appointment_id}), 201

@app.route('/api/appointments/<int:app_id>/status', methods=['PUT'])
@require_master
def update_appointment_status(app_id):
    """Обновить статус записи"""
    data = request.json
    status = data.get('status')
    
    if status not in ['pending', 'confirmed', 'completed', 'cancelled']:
        return jsonify({'error': 'Invalid status'}), 400
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                UPDATE appointments 
                SET status = %s 
                WHERE id = %s AND master_code = %s
            ''', (status, app_id, session['master_code']))
            
            if cur.rowcount == 0:
                return jsonify({'error': 'Appointment not found'}), 404
            
        conn.commit()
    
    return jsonify({'success': True})

# ==================== API ДЛЯ ПРОВЕРКИ БАРБЕРОВ ====================

@app.route('/api/barbers/check', methods=['POST'])
def check_barber_exists():
    """Проверить существование барбера по коду"""
    data = request.json
    code = data.get('code', '').upper()
    
    if not code:
        return jsonify({'exists': False, 'message': 'Код не указан'})
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                SELECT code, full_name, phone, price, avatar_url
                FROM masters 
                WHERE code = %s AND is_active = TRUE
            ''', (code,))
            
            master = cur.fetchone()
            
            if not master:
                return jsonify({'exists': False, 'message': 'Барбер не найден'})
            
            return jsonify({
                'exists': True,
                'master': {
                    'code': master[0],
                    'full_name': master[1],
                    'phone': master[2],
                    'price': float(master[3]) if master[3] else 1000,
                    'avatar': master[4] or '/static/default_barber.png'
                }
            })

@app.route('/api/bookings/slots', methods=['GET'])
def get_available_slots():
    """Получить доступные слоты для записи"""
    master_code = request.args.get('master_code', '').upper()
    date = request.args.get('date')
    
    if not master_code or not date:
        return jsonify({'error': 'Master code and date required'}), 400
    
    # Рабочие часы: 10:00 - 21:00 с интервалом в 30 минут
    working_hours = [
        '10:00', '10:30', '11:00', '11:30', '12:00', '12:30',
        '13:00', '13:30', '14:00', '14:30', '15:00', '15:30',
        '16:00', '16:30', '17:00', '17:30', '18:00', '18:30',
        '19:00', '19:30', '20:00', '20:30'
    ]
    
    with get_db() as conn:
        with conn.cursor() as cur:
            # Получаем занятые слоты на выбранную дату
            cur.execute('''
                SELECT appointment_time::text
                FROM appointments 
                WHERE master_code = %s 
                AND appointment_date = %s
                AND status != 'cancelled'
                ORDER BY appointment_time
            ''', (master_code, date))
            
            booked_times = []
            rows = cur.fetchall()
            for row in rows:
                if row[0]:
                    time_str = str(row[0])
                    booked_times.append(time_str[:5])  # Берем только часы:минуты
            
            # Формируем список доступных слотов
            available_slots = []
            for time in working_hours:
                if time not in booked_times:
                    available_slots.append(time)
    
    return jsonify({
        'master_code': master_code,
        'date': date,
        'available_slots': available_slots,
        'booked_slots': booked_times
    })

# ==================== API ДЛЯ TELEGRAM БОТА ====================

@app.route('/api/bot/register_master', methods=['POST'])
def bot_register_master():
    """Регистрация барбера через бота"""
    try:
        data = request.json
        
        # Проверка владельца
        owner_id = data.get('owner_id')
        if OWNER_ID and owner_id and int(owner_id) != OWNER_ID:
            return jsonify({'success': False, 'message': 'Неавторизованный запрос'}), 403
        
        code = data.get('code', '').upper()
        full_name = data.get('full_name')
        phone = data.get('phone')
        password = data.get('password')
        
        # Валидация данных
        if not all([code, full_name, phone, password]):
            return jsonify({'success': False, 'message': 'Все поля обязательны'}), 400
        
        if len(password) < 6:
            return jsonify({'success': False, 'message': 'Пароль должен быть минимум 6 символов'}), 400
        
        if not re.match(r'^[A-Z0-9]{3,10}$', code):
            return jsonify({'success': False, 'message': 'Код должен содержать только латинские буквы и цифры, 3-10 символов'}), 400
        
        with get_db() as conn:
            with conn.cursor() as cur:
                # Проверка уникальности кода
                cur.execute('SELECT id FROM masters WHERE code = %s', (code,))
                if cur.fetchone():
                    return jsonify({'success': False, 'message': 'Код уже используется'}), 400
                
                # Создание барбера
                cur.execute('''
                    INSERT INTO masters (code, full_name, phone, password_hash, price)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                ''', (code, full_name, phone, generate_password_hash(password), 1000))
                
                master_id = cur.fetchone()[0]
                
            conn.commit()
        
        logger.info(f"New master registered via bot: {code} - {full_name}")
        
        return jsonify({
            'success': True, 
            'message': 'Барбер успешно зарегистрирован',
            'master_id': master_id,
            'code': code
        })
        
    except Exception as e:
        logger.error(f"Error in bot_register_master: {e}")
        return jsonify({'success': False, 'message': 'Внутренняя ошибка сервера'}), 500

@app.route('/api/telegram/check_code', methods=['POST'])
def check_barber_code_api():
    """Проверить код барбера"""
    data = request.json
    code = data.get('code', '').upper()
    
    if not code:
        return jsonify({'error': 'Code required'}), 400
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                SELECT code, full_name, phone, price 
                FROM masters 
                WHERE code = %s AND is_active = TRUE
            ''', (code,))
            
            master = cur.fetchone()
            
            if not master:
                return jsonify({'exists': False}), 200
            
            # Занятые слоты
            today = datetime.now().date()
            week_later = today + timedelta(days=7)
            
            cur.execute('''
                SELECT appointment_date, appointment_time::text
                FROM appointments 
                WHERE master_code = %s 
                AND appointment_date BETWEEN %s AND %s
                AND status != 'cancelled'
            ''', (code, today, week_later))
            
            booked_slots = []
            rows = cur.fetchall()
            for row in rows:
                if row[0] and row[1]:
                    booked_slots.append({
                        'date': row[0].isoformat() if hasattr(row[0], 'isoformat') else str(row[0]),
                        'time': row[1][:5] if row[1] else ''
                    })
    
    return jsonify({
        'exists': True,
        'master': {
            'code': master[0],
            'full_name': master[1],
            'phone': master[2],
            'price': float(master[3]) if master[3] else 1000
        },
        'booked_slots': booked_slots
    })

# ==================== СТАТИЧЕСКИЕ ФАЙЛЫ ====================

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

# ==================== ОШИБКИ ====================

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def server_error(e):
    logger.error(f"Server error: {e}")
    return jsonify({'error': 'Internal server error'}), 500

# ==================== ЗАПУСК ====================

if __name__ == '__main__':
    init_db()
    create_test_master()  # Создаем тестового барбера
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
