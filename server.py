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
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')
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
TELEGRAM_API = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}'

# Настройка логирования
logging.basicConfig(level=logging.INFO)
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
        return
    
    try:
        cur = conn.cursor()
        
        # Таблица мастеров (барберов)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS masters (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE,
                username VARCHAR(100),
                login_code VARCHAR(50) UNIQUE,
                password_hash VARCHAR(255),
                full_name VARCHAR(200),
                phone VARCHAR(20),
                avatar_url VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
        ''')
        
        # Таблица записей
        cur.execute('''
            CREATE TABLE IF NOT EXISTS appointments (
                id SERIAL PRIMARY KEY,
                master_id INTEGER REFERENCES masters(id),
                client_name VARCHAR(200),
                client_phone VARCHAR(20),
                service_type VARCHAR(100),
                appointment_date DATE,
                appointment_time TIME,
                duration_minutes INTEGER DEFAULT 60,
                status VARCHAR(50) DEFAULT 'pending',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица клиентов
        cur.execute('''
            CREATE TABLE IF NOT EXISTS clients (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE,
                username VARCHAR(100),
                full_name VARCHAR(200),
                phone VARCHAR(20),
                master_code VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица админов
        cur.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE,
                password_hash VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

def generate_login_code():
    """Генерация уникального кода для входа"""
    return str(uuid.uuid4())[:8].upper()

# ==================== ВЕБ-РОУТЫ ====================

@app.route('/')
def index():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
    
    user_id = session['user_id']
    return render_template('index.html')

@app.route('/master_login', methods=['POST'])
def master_login():
    login_code = request.form.get('login_code', '').strip()
    password = request.form.get('password', '').strip()
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Ошибка базы данных'})
    
    try:
        cur = conn.cursor()
        cur.execute(
            'SELECT id, username, full_name FROM masters WHERE login_code = %s AND password_hash = %s AND is_active = TRUE',
            (login_code, generate_password_hash(password))
        )
        master = cur.fetchone()
        
        if master:
            session['master_id'] = master[0]
            session['master_username'] = master[1]
            session['master_name'] = master[2]
            session['is_master'] = True
            return jsonify({
                'success': True, 
                'message': 'Успешный вход',
                'redirect': '/master_panel'
            })
        else:
            return jsonify({'success': False, 'message': 'Неверный код или пароль'})
            
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
    
    # Получаем даты для календаря
    today = datetime.now().date()
    start_date = today - timedelta(days=30)  # Месяц назад
    end_date = today + timedelta(days=30)    # Месяц вперед
    
    conn = get_db_connection()
    appointments = []
    
    if conn:
        try:
            cur = conn.cursor()
            cur.execute('''
                SELECT id, client_name, client_phone, service_type, 
                       appointment_date, appointment_time, duration_minutes, status, notes
                FROM appointments 
                WHERE master_id = %s AND appointment_date BETWEEN %s AND %s
                ORDER BY appointment_date, appointment_time
            ''', (master_id, start_date, end_date))
            
            columns = [desc[0] for desc in cur.description]
            appointments = [dict(zip(columns, row)) for row in cur.fetchall()]
            
            # Получаем информацию о мастере
            cur.execute('SELECT full_name, login_code FROM masters WHERE id = %s', (master_id,))
            master_info = cur.fetchone()
            master_name = master_info[0] if master_info else ''
            master_code = master_info[1] if master_info else ''
            
        except Exception as e:
            logger.error(f"Error fetching appointments: {e}")
        finally:
            cur.close()
            conn.close()
    
    return render_template('master_panel.html', 
                         appointments=appointments,
                         master_name=session.get('master_name', ''),
                         master_code=master_code,
                         start_date=start_date.strftime('%Y-%m-%d'),
                         end_date=end_date.strftime('%Y-%m-%d'))

@app.route('/api/appointments')
def get_appointments():
    if not session.get('is_master'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    master_id = session.get('master_id')
    date_from = request.args.get('from')
    date_to = request.args.get('to')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database error'}), 500
    
    try:
        cur = conn.cursor()
        query = '''
            SELECT id, client_name, client_phone, service_type, 
                   appointment_date, appointment_time, duration_minutes, status, notes
            FROM appointments 
            WHERE master_id = %s
        '''
        params = [master_id]
        
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
    master_id = session.get('master_id')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database error'}), 500
    
    try:
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO appointments 
            (master_id, client_name, client_phone, service_type, appointment_date, appointment_time, duration_minutes, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            master_id,
            data.get('client_name'),
            data.get('client_phone'),
            data.get('service_type', 'Стрижка'),
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
            WHERE id = %s AND master_id = %s
        ''', (status, appointment_id, session.get('master_id')))
        
        conn.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error updating appointment: {e}")
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ==================== TELEGRAM BOT ФУНКЦИИ ====================

def create_master_via_bot(telegram_id, username, full_name, phone):
    """Создание нового мастера через бота"""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        cur = conn.cursor()
        
        # Генерируем логин и пароль
        login_code = generate_login_code()
        password = str(uuid.uuid4())[:6]  # Простой пароль из 6 символов
        
        cur.execute('''
            INSERT INTO masters (telegram_id, username, full_name, phone, login_code, password_hash)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, login_code
        ''', (telegram_id, username, full_name, phone, login_code, generate_password_hash(password)))
        
        master_id, login_code = cur.fetchone()
        conn.commit()
        
        return {
            'master_id': master_id,
            'login_code': login_code,
            'password': password
        }
        
    except Exception as e:
        logger.error(f"Error creating master: {e}")
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()

def send_telegram_message(chat_id, text):
    """Отправка сообщения в Telegram"""
    try:
        url = f'{TELEGRAM_API}/sendMessage'
        payload = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, json=payload)
        return response.json()
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")
        return None

# ==================== ЗАПУСК СЕРВЕРА ====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
