from flask import Flask, render_template, request, jsonify, session
import os
import uuid
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Измените на свой секретный ключ
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Максимум 16MB

# Создаем папку для загрузок, если её нет
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Моковые данные для примера
users = {}
barbers = {}

# Главная страница
@app.route('/')
def index():
    # Генерируем случайный ID пользователя, если его нет
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
    
    user_id = session['user_id']
    
    # Если у пользователя нет аватарки, используем дефолтную
    if user_id not in users:
        users[user_id] = {
            'avatar': '/static/default_avatar.png',
            'name': 'Клиент'
        }
    
    return render_template('index.html', 
                         user=users[user_id],
                         barbers=list(barbers.values()))

# Добавление барбера
@app.route('/add_barber', methods=['POST'])
def add_barber():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Пользователь не авторизован'}), 401
    
    barber_name = request.form.get('name')
    
    # Обработка загрузки аватарки
    avatar_url = '/static/default_barber.png'
    if 'avatar' in request.files:
        file = request.files['avatar']
        if file and file.filename:
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4()}_{filename}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(file_path)
            avatar_url = f'/static/uploads/{unique_filename}'
    
    # Создаем барбера
    barber_id = str(uuid.uuid4())
    barbers[barber_id] = {
        'id': barber_id,
        'name': barber_name,
        'avatar': avatar_url,
        'added_by': user_id
    }
    
    return jsonify({'success': True, 'barber': barbers[barber_id]})

# Вход мастера
@app.route('/master_login', methods=['POST'])
def master_login():
    username = request.form.get('username')
    password = request.form.get('password')
    
    # Здесь должна быть реальная проверка логина/пароля
    # Для демо просто проверяем непустые значения
    if username and password:
        session['is_master'] = True
        session['master_name'] = username
        return jsonify({'success': True, 'message': 'Успешный вход'})
    
    return jsonify({'success': False, 'message': 'Неверные данные'})

# Проверка статуса мастера
@app.route('/check_master')
def check_master():
    is_master = session.get('is_master', False)
    return jsonify({'is_master': is_master})

# Получение списка барберов
@app.route('/get_barbers')
def get_barbers():
    return jsonify({'barbers': list(barbers.values())})

if __name__ == '__main__':
    app.run(debug=True, port=5000)