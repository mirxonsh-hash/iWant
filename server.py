from flask import Flask, render_template, request, jsonify, session
import os
import uuid
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-123')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

users = {}
barbers = {}

@app.route('/')
def index():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
    
    user_id = session['user_id']
    
    if user_id not in users:
        users[user_id] = {
            'avatar': '/static/default_avatar.png',
            'name': 'Клиент'
        }
    
    return render_template('index.html', 
                         user=users[user_id],
                         barbers=list(barbers.values()))

@app.route('/add_barber', methods=['POST'])
def add_barber():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Пользователь не авторизован'}), 401
    
    barber_name = request.form.get('name')
    
    avatar_url = '/static/default_barber.png'
    if 'avatar' in request.files:
        file = request.files['avatar']
        if file and file.filename:
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4()}_{filename}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(file_path)
            avatar_url = f'/static/uploads/{unique_filename}'
    
    barber_id = str(uuid.uuid4())
    barbers[barber_id] = {
        'id': barber_id,
        'name': barber_name,
        'avatar': avatar_url,
        'added_by': user_id
    }
    
    return jsonify({'success': True, 'barber': barbers[barber_id]})

@app.route('/master_login', methods=['POST'])
def master_login():
    username = request.form.get('username')
    password = request.form.get('password')
    
    if username and password:
        session['is_master'] = True
        session['master_name'] = username
        return jsonify({'success': True, 'message': 'Успешный вход'})
    
    return jsonify({'success': False, 'message': 'Неверные данные'})

@app.route('/check_master')
def check_master():
    is_master = session.get('is_master', False)
    return jsonify({'is_master': is_master})

@app.route('/get_barbers')
def get_barbers():
    return jsonify({'barbers': list(barbers.values())})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
