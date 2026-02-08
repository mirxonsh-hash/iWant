from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import os
import uuid
import json
import psycopg2
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import threading
import requests
import logging

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-me-in-production')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Настройки базы данных
DB_CONFIG = {
    'host': 'dpg-d63t4ih4tr6s73a46rtg-a.frankfurt-postgres.render.com',
    'database': 'barber_db_33bs',
    'user': 'barber_db_33bs_user',
    'password': 'BL1BlEQaugJijaXJC6VWOfpacuO6pAid',
    'port': '5432'
}

# Telegram Bot
TELEGRAM_TOKEN = '7662525969:AAF33YcsBM8OmeURyarjx-bNxF9ghOVGRNc'
OWNER_ID = 531822805  # ID владельца

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_db_connection():
    """Создание подключения к базе данных"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return None

def init_database():
    """Инициализация таблиц в базе данных"""
    conn = get_db_connection()
    if not conn:
        logger.error("Cannot initialize database - no connection")
        return
    
    try:
        cur = conn.cursor()
        
        # Таблица мастеров (барберов)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS masters (
                id SERIAL PRIMARY KEY,
                code VARCHAR(20) UNIQUE NOT NULL,
                full_name VARCHAR(200) NOT NULL,
                phone VARCHAR(20),
                price_per_hour DECIMAL(10, 2) DEFAULT 1000.00,
                avatar_url VARCHAR(500),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER DEFAULT 0,
                telegram_username VARCHAR(100)
            )
        ''')
        
        # Таблица записей
        cur.execute('''
            CREATE TABLE IF NOT EXISTS appointments (
                id SERIAL PRIMARY KEY,
                master_id INTEGER REFERENCES masters(id),
                master_code VARCHAR(20),
                client_name VARCHAR(200),
                client_phone VARCHAR(20),
                service_type VARCHAR(100),
                price DECIMAL(10, 2),
                appointment_date DATE,
                appointment_time TIME,
                duration_minutes INTEGER DEFAULT 60,
                status VARCHAR(50) DEFAULT 'pending',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица клиентов (которые добавили барберов)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS clients (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(100),
                master_code VARCHAR(20),
                master_name VARCHAR(200),
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица авторизации мастеров
        cur.execute('''
            CREATE TABLE IF NOT EXISTS masters_auth (
                id SERIAL PRIMARY KEY,
                master_code VARCHAR(20) UNIQUE,
                password_hash VARCHAR(255),
                last_login TIMESTAMP
            )
        ''')
        
        conn.commit()
        logger.info("Database tables created/verified")
        
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

# Инициализируем базу при запуске
init_database()

# ==================== ВЕБ-РОУТЫ ====================

@app.route('/')
def index():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
    
    user_id = session['user_id']
    
    # Получаем список барберов для отображения
    conn = get_db_connection()
    barbers = []
    if conn:
        try:
            cur = conn.cursor()
            cur.execute('SELECT code, full_name, avatar_url FROM masters WHERE is_active = TRUE')
            barbers = [{'code': row[0], 'name': row[1], 'avatar': row[2] or '/static/default_barber.png'} 
                      for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Error fetching barbers: {e}")
        finally:
            cur.close()
            conn.close()
    
    return render_template('index.html', barbers=barbers)

@app.route('/add_barber', methods=['POST'])
def add_barber():
    user_id = session.get('user_id')
    master_code = request.form.get('master_code', '').strip().upper()
    
    if not master_code:
        return jsonify({'success': False, 'message': 'Введите код барбера'})
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Ошибка базы данных'})
    
    try:
        cur = conn.cursor()
        
        # Проверяем существование барбера
        cur.execute('SELECT id, full_name FROM masters WHERE code = %s AND is_active = TRUE', (master_code,))
        master = cur.fetchone()
        
        if not master:
            return jsonify({'success': False, 'message': 'Барбер с таким кодом не найден'})
        
        master_id, master_name = master
        
        # Проверяем, не добавил ли уже этот пользователь этого барбера
        cur.execute('SELECT id FROM clients WHERE user_id = %s AND master_code = %s', (user_id, master_code))
        if cur.fetchone():
            return jsonify({'success': False, 'message': 'Вы уже добавили этого барбера'})
        
        # Добавляем запись о клиенте
        cur.execute('''
            INSERT INTO clients (user_id, master_code, master_name)
            VALUES (%s, %s, %s)
        ''', (user_id, master_code, master_name))
        
        conn.commit()
        
        # Получаем обновленный список барберов пользователя
        cur.execute('''
            SELECT c.master_code, m.full_name, m.avatar_url 
            FROM clients c
            JOIN masters m ON c.master_code = m.code
            WHERE c.user_id = %s AND m.is_active = TRUE
        ''', (user_id,))
        
        user_barbers = [{'code': row[0], 'name': row[1], 'avatar': row[2] or '/static/default_barber.png'} 
                       for row in cur.fetchall()]
        
        return jsonify({
            'success': True, 
            'message': f'Барбер {master_name} успешно добавлен!',
            'barbers': user_barbers
        })
        
    except Exception as e:
        logger.error(f"Error adding barber: {e}")
        conn.rollback()
        return jsonify({'success': False, 'message': 'Ошибка при добавлении барбера'})
    finally:
        cur.close()
        conn.close()

@app.route('/master_login', methods=['POST'])
def master_login():
    master_code = request.form.get('login_code', '').strip().upper()
    password = request.form.get('password', '').strip()
    
    if not master_code or not password:
        return jsonify({'success': False, 'message': 'Введите код и пароль'})
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Ошибка базы данных'})
    
    try:
        cur = conn.cursor()
        
        # Получаем хеш пароля из базы
        cur.execute('''
            SELECT password_hash FROM masters_auth 
            WHERE master_code = %s
        ''', (master_code,))
        
        auth_data = cur.fetchone()
        
        if not auth_data:
            return jsonify({'success': False, 'message': 'Неверный код или пароль'})
        
        password_hash = auth_data[0]
        
        # Проверяем пароль
        if not check_password_hash(password_hash, password):
            return jsonify({'success': False, 'message': 'Неверный код или пароль'})
        
        # Получаем информацию о мастере
        cur.execute('SELECT id, full_name FROM masters WHERE code = %s AND is_active = TRUE', (master_code,))
        master = cur.fetchone()
        
        if not master:
            return jsonify({'success': False, 'message': 'Мастер не найден или неактивен'})
        
        master_id, full_name = master
        
        # Устанавливаем сессию
        session['master_id'] = master_id
        session['master_code'] = master_code
        session['master_name'] = full_name
        session['is_master'] = True
        
        # Обновляем время последнего входа
        cur.execute('''
            UPDATE masters_auth 
            SET last_login = CURRENT_TIMESTAMP 
            WHERE master_code = %s
        ''', (master_code,))
        
        conn.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Успешный вход',
            'redirect': '/master_panel'
        })
            
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({'success': False, 'message': 'Ошибка при входе'})
    finally:
        cur.close()
        conn.close()

@app.route('/master_panel')
def master_panel():
    if not session.get('is_master'):
        return redirect('/')
    
    master_id = session.get('master_id')
    master_code = session.get('master_code')
    
    # Получаем даты для календаря
    today = datetime.now().date()
    start_date = today - timedelta(days=30)  # Месяц назад
    end_date = today + timedelta(days=30)    # Месяц вперед
    
    conn = get_db_connection()
    appointments = []
    stats = {}
    
    if conn:
        try:
            cur = conn.cursor()
            
            # Получаем записи мастера
            cur.execute('''
                SELECT id, client_name, client_phone, service_type, price,
                       appointment_date, appointment_time, duration_minutes, status, notes
                FROM appointments 
                WHERE master_code = %s AND appointment_date BETWEEN %s AND %s
                ORDER BY appointment_date, appointment_time
            ''', (master_code, start_date, end_date))
            
            columns = [desc[0] for desc in cur.description]
            appointments = [dict(zip(columns, row)) for row in cur.fetchall()]
            
            # Получаем статистику мастера
            cur.execute('''
                SELECT 
                    COUNT(*) as total_appointments,
                    SUM(CASE WHEN status = 'completed' THEN price ELSE 0 END) as total_earnings,
                    COUNT(DISTINCT client_phone) as unique_clients
                FROM appointments 
                WHERE master_code = %s
            ''', (master_code,))
            
            stats_row = cur.fetchone()
            if stats_row:
                stats = {
                    'total_appointments': stats_row[0] or 0,
                    'total_earnings': float(stats_row[1] or 0),
                    'unique_clients': stats_row[2] or 0
                }
            
        except Exception as e:
            logger.error(f"Error fetching appointments: {e}")
        finally:
            cur.close()
            conn.close()
    
    return render_template('master_panel.html', 
                         appointments=appointments,
                         master_name=session.get('master_name', ''),
                         master_code=master_code,
                         stats=stats,
                         start_date=start_date.strftime('%Y-%m-%d'),
                         end_date=end_date.strftime('%Y-%m-%d'))

@app.route('/api/appointments')
def get_appointments():
    if not session.get('is_master'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    master_code = session.get('master_code')
    date_from = request.args.get('from')
    date_to = request.args.get('to')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database error'}), 500
    
    try:
        cur = conn.cursor()
        query = '''
            SELECT id, client_name, client_phone, service_type, price,
                   appointment_date, appointment_time, duration_minutes, status, notes
            FROM appointments 
            WHERE master_code = %s
        '''
        params = [master_code]
        
        if date_from and date_to:
            query += ' AND appointment_date BETWEEN %s AND %s'
            params.extend([date_from, date_to])
        
        query += ' ORDER BY appointment_date, appointment_time'
        cur.execute(query, params)
        
        columns = [desc[0] for desc in cur.description]
        appointments = [dict(zip(columns, row)) for row in cur.fetchall()]
        
        return jsonify({'appointments': appointments})
        
    except Exception as e:
        logger.error(f"Error fetching appointments API: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/api/add_appointment', methods=['POST'])
def add_appointment():
    if not session.get('is_master'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    master_code = session.get('master_code')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database error'}), 500
    
    try:
        cur = conn.cursor()
        
        # Получаем ID мастера
        cur.execute('SELECT id, price_per_hour FROM masters WHERE code = %s', (master_code,))
        master = cur.fetchone()
        if not master:
            return jsonify({'error': 'Master not found'}), 404
        
        master_id, price_per_hour = master
        price = float(data.get('price', price_per_hour))
        
        cur.execute('''
            INSERT INTO appointments 
            (master_id, master_code, client_name, client_phone, service_type, price, 
             appointment_date, appointment_time, duration_minutes, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            master_id,
            master_code,
            data.get('client_name'),
            data.get('client_phone'),
            data.get('service_type', 'Стрижка'),
            price,
            data.get('appointment_date'),
            data.get('appointment_time'),
            data.get('duration_minutes', 60),
            data.get('notes', '')
        ))
        
        appointment_id = cur.fetchone()[0]
        conn.commit()
        
        return jsonify({'success': True, 'appointment_id': appointment_id})
        
    except Exception as e:
        logger.error(f"Error adding appointment: {e}")
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/api/update_appointment_status', methods=['POST'])
def update_appointment_status():
    if not session.get('is_master'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    appointment_id = data.get('appointment_id')
    status = data.get('status')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database error'}), 500
    
    try:
        cur = conn.cursor()
        cur.execute('''
            UPDATE appointments 
            SET status = %s 
            WHERE id = %s AND master_code = %s
        ''', (status, appointment_id, session.get('master_code')))
        
        conn.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error updating appointment: {e}")
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/api/master_stats')
def get_master_stats():
    if not session.get('is_master'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    master_code = session.get('master_code')
    period = request.args.get('period', 'month')  # day, week, month, year
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database error'}), 500
    
    try:
        cur = conn.cursor()
        
        # Определяем период
        today = datetime.now().date()
        if period == 'day':
            date_condition = "appointment_date = %s"
            date_param = today
        elif period == 'week':
            date_condition = "appointment_date >= %s"
            date_param = today - timedelta(days=7)
        elif period == 'month':
            date_condition = "appointment_date >= %s"
            date_param = today - timedelta(days=30)
        else:  # year
            date_condition = "appointment_date >= %s"
            date_param = today - timedelta(days=365)
        
        cur.execute(f'''
            SELECT 
                COUNT(*) as appointments,
                SUM(CASE WHEN status = 'completed' THEN price ELSE 0 END) as earnings,
                COUNT(DISTINCT client_phone) as clients
            FROM appointments 
            WHERE master_code = %s AND {date_condition}
        ''', (master_code, date_param))
        
        stats = cur.fetchone()
        
        return jsonify({
            'period': period,
            'appointments': stats[0] or 0,
            'earnings': float(stats[1] or 0),
            'clients': stats[2] or 0
        })
        
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ==================== TELEGRAM BOT API ====================

@app.route('/api/telegram/add_master', methods=['POST'])
def api_add_master():
    """API для добавления мастера через бота (только для владельца)"""
    try:
        data = request.json
        logger.info(f"Received add_master request: {data}")
        
        # Получаем owner_id из данных
        owner_id = data.get('owner_id')
        if not owner_id:
            return jsonify({'success': False, 'message': 'Не указан ID владельца'}), 400
        
        # Проверяем ID владельца
        if int(owner
