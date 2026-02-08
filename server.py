# server.py
from flask import Flask, request, jsonify, session, render_template, redirect
import os
import uuid
import psycopg2
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import logging

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-key-change-me')
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

TELEGRAM_TOKEN = '7662525969:AAF33YcsBM8OmeURyarjx-bNxF9ghOVGRNc'
OWNER_ID = 531822805

def get_db():
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        logger.error(f"DB error: {e}")
        return None

def init_db():
    """Создаем таблицы если их нет"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Барберы
            cur.execute('''
                CREATE TABLE IF NOT EXISTS masters (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(20) UNIQUE NOT NULL,
                    full_name VARCHAR(200) NOT NULL,
                    phone VARCHAR(20),
                    password_hash VARCHAR(255),
                    price DECIMAL(10,2) DEFAULT 1000,
                    is_active BOOL DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Записи
            cur.execute('''
                CREATE TABLE IF NOT EXISTS appointments (
                    id SERIAL PRIMARY KEY,
                    master_code VARCHAR(20) REFERENCES masters(code),
                    client_name VARCHAR(200),
                    client_phone VARCHAR(20),
                    service_type VARCHAR(100),
                    price DECIMAL(10,2),
                    appointment_date DATE,
                    appointment_time TIME,
                    status VARCHAR(20) DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Пользователи Telegram
            cur.execute('''
                CREATE TABLE IF NOT EXISTS telegram_users (
                    telegram_id VARCHAR(100) PRIMARY KEY,
                    username VARCHAR(100),
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Избранные барберы
            cur.execute('''
                CREATE TABLE IF NOT EXISTS user_favorites (
                    telegram_id VARCHAR(100),
                    master_code VARCHAR(20),
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (telegram_id, master_code)
                )
            ''')
            
        conn.commit()

# ==================== ГЛАВНЫЕ СТРАНИЦЫ ====================

@app.route('/')
def index():
    session['user_id'] = session.get('user_id', str(uuid.uuid4()))
    return render_template('index.html')

@app.route('/master_login', methods=['GET', 'POST'])
def master_login():
    if request.method == 'POST':
        data = request.get_json() or request.form
        code = data.get('login_code', '').upper()
        password = data.get('password', '')
        
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT full_name, password_hash FROM masters 
                    WHERE code = %s AND is_active = TRUE
                ''', (code,))
                master = cur.fetchone()
                
                if master and check_password_hash(master[1], password):
                    session['master_code'] = code
                    session['master_name'] = master[0]
                    return jsonify({'success': True, 'redirect': '/master_panel'})
                
                return jsonify({'success': False, 'message': 'Неверный код или пароль'})
    
    return render_template('master_login.html')

@app.route('/master_panel')
def master_panel():
    if 'master_code' not in session:
        return redirect('/master_login')
    
    return render_template('master_panel.html', 
                         master_name=session['master_name'],
                         master_code=session['master_code'])

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ==================== API ДЛЯ БАРБЕРОВ ====================

@app.route('/api/masters', methods=['POST'])
def add_master():
    """Добавить нового барбера (только для владельца)"""
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
            # Проверяем уникальность кода
            cur.execute('SELECT id FROM masters WHERE code = %s', (code,))
            if cur.fetchone():
                return jsonify({'error': 'Code already exists'}), 400
            
            # Добавляем барбера
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
    """Получить список барберов"""
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
    """Получить записи барбера"""
    master_code = request.args.get('master_code') or session.get('master_code')
    date_from = request.args.get('from')
    date_to = request.args.get('to')
    
    if not master_code:
        return jsonify({'error': 'Master code required'}), 400
    
    with get_db() as conn:
        with conn.cursor() as cur:
            query = '''
                SELECT id, client_name, client_phone, service_type, price,
                       appointment_date, appointment_time, status
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
                    'status': row[7]
                })
    
    return jsonify({'appointments': appointments})

@app.route('/api/appointments', methods=['POST'])
def create_appointment_api():
    """Создать запись"""
    data = request.json
    
    if 'master_code' in session:  # Создает барбер
        master_code = session['master_code']
    else:  # Создает клиент через бота
        master_code = data.get('master_code', '').upper()
        telegram_id = data.get('telegram_id')
        
        if telegram_id and master_code:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute('''
                        INSERT INTO user_favorites (telegram_id, master_code)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                    ''', (telegram_id, master_code))
                conn.commit()
    
    required = ['client_name', 'client_phone', 'date', 'time']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'Missing {field}'}), 400
    
    # Проверяем доступность времени
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
                 appointment_date, appointment_time, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
                RETURNING id
            ''', (
                master_code,
                data['client_name'],
                data['client_phone'],
                data.get('service_type', 'Стрижка'),
                data.get('price', 1000),
                data['date'],
                data['time']
            ))
            
            appointment_id = cur.fetchone()[0]
        
        conn.commit()
    
    return jsonify({'success': True, 'appointment_id': appointment_id}), 201

@app.route('/api/appointments/<int:app_id>/status', methods=['PUT'])
def update_appointment_status(app_id):
    """Обновить статус записи"""
    if 'master_code' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
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

# ==================== API ДЛЯ TELEGRAM ====================

@app.route('/api/telegram/check_code', methods=['POST'])
def check_barber_code_api():
    """Проверить код барбера для бота"""
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
            
            # Получаем занятые времена
            today = datetime.now().date()
            week_later = today + timedelta(days=7)
            
            cur.execute('''
                SELECT appointment_date, appointment_time
                FROM appointments 
                WHERE master_code = %s 
                AND appointment_date BETWEEN %s AND %s
                AND status != 'cancelled'
            ''', (code, today, week_later))
            
            booked_slots = []
            for row in cur.fetchall():
                booked_slots.append({
                    'date': row[0].isoformat(),
                    'time': str(row[1])
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

@app.route('/api/telegram/user/<telegram_id>/favorites')
def get_user_favorites(telegram_id):
    """Получить избранных барберов пользователя"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                SELECT m.code, m.full_name, m.phone
                FROM user_favorites uf
                JOIN masters m ON uf.master_code = m.code
                WHERE uf.telegram_id = %s AND m.is_active = TRUE
                ORDER BY uf.added_at DESC
            ''', (telegram_id,))
            
            favorites = []
            for row in cur.fetchall():
                favorites.append({
                    'code': row[0],
                    'full_name': row[1],
                    'phone': row[2]
                })
    
    return jsonify({'favorites': favorites})

# ==================== API ДЛЯ СТАТИСТИКИ ====================

@app.route('/api/stats')
def get_stats():
    """Получить статистику барбера"""
    master_code = request.args.get('master_code') or session.get('master_code')
    
    if not master_code:
        return jsonify({'error': 'Master code required'}), 400
    
    with get_db() as conn:
        with conn.cursor() as cur:
            # Общая статистика
            cur.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'completed' THEN price ELSE 0 END) as earnings,
                    COUNT(DISTINCT client_phone) as unique_clients
                FROM appointments 
                WHERE master_code = %s
            ''', (master_code,))
            
            stats = cur.fetchone()
    
    return jsonify({
        'total_appointments': stats[0] or 0,
        'total_earnings': float(stats[1] or 0),
        'unique_clients': stats[2] or 0
    })

# ==================== ЗАПУСК ====================

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
