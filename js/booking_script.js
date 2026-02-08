// booking_script.js
let currentStep = 1;
let bookingData = {
    master_code: '',
    master_name: '',
    master_avatar: '',
    selected_date: '',
    selected_time: '',
    selected_service: 'Стрижка',
    client_name: '',
    client_phone: '',
    notes: '',
    price: 1000
};

let currentMonth = new Date().getMonth();
let currentYear = new Date().getFullYear();

function openBookingModal(masterCode, masterName, masterAvatar) {
    bookingData.master_code = masterCode;
    bookingData.master_name = masterName;
    bookingData.master_avatar = masterAvatar || '/static/default_barber.png';
    
    document.getElementById('bookingBarberName').textContent = masterName;
    document.getElementById('bookingBarberCode').textContent = masterCode;
    document.getElementById('bookingBarberAvatar').src = masterAvatar || '/static/default_barber.png';
    
    document.getElementById('bookingModal').style.display = 'flex';
    resetBookingForm();
    generateCalendar();
    updateNavigation();
}

function closeBookingModal() {
    document.getElementById('bookingModal').style.display = 'none';
    resetBookingForm();
}

function resetBookingForm() {
    currentStep = 1;
    currentMonth = new Date().getMonth();
    currentYear = new Date().getFullYear();
    
    bookingData = {
        master_code: bookingData.master_code,
        master_name: bookingData.master_name,
        master_avatar: bookingData.master_avatar,
        selected_date: '',
        selected_time: '',
        selected_service: 'Стрижка',
        client_name: '',
        client_phone: '',
        notes: '',
        price: 1000
    };
    
    // Скрыть все шаги кроме первого
    document.querySelectorAll('.step').forEach(step => {
        step.classList.remove('active');
    });
    document.getElementById('stepDate').classList.add('active');
    
    // Сбросить поля
    document.getElementById('clientNameInput').value = '';
    document.getElementById('clientPhoneInput').value = '';
    document.getElementById('clientNotes').value = '';
    document.getElementById('serviceSelect').value = 'Стрижка';
    
    updateNavigation();
}

function updateNavigation() {
    const prevBtn = document.getElementById('prevBtn');
    const nextBtn = document.getElementById('nextBtn');
    
    // Обновить текст кнопки "Далее"
    if (currentStep === 5) {
        nextBtn.textContent = 'Записаться';
    } else if (currentStep === 6) {
        nextBtn.style.display = 'none';
        prevBtn.style.display = 'none';
        return;
    } else {
        nextBtn.textContent = 'Далее';
    }
    
    // Показать/скрыть кнопку "Назад"
    if (currentStep > 1 && currentStep < 6) {
        prevBtn.style.display = 'block';
    } else {
        prevBtn.style.display = 'none';
    }
    
    // Активировать/деактивировать кнопку "Далее"
    if (currentStep === 1 && !bookingData.selected_date) {
        nextBtn.disabled = true;
    } else if (currentStep === 2 && !bookingData.selected_time) {
        nextBtn.disabled = true;
    } else if (currentStep === 4 && (!bookingData.client_name || !bookingData.client_phone)) {
        nextBtn.disabled = true;
    } else {
        nextBtn.disabled = false;
    }
}

function nextStep() {
    if (currentStep === 5) {
        createBooking();
        return;
    }
    
    // Валидация на текущем шаге
    if (currentStep === 4) {
        const name = document.getElementById('clientNameInput').value.trim();
        const phone = document.getElementById('clientPhoneInput').value.trim();
        
        if (!name || !phone) {
            alert('Пожалуйста, заполните все обязательные поля');
            return;
        }
        
        bookingData.client_name = name;
        bookingData.client_phone = phone;
        bookingData.notes = document.getElementById('clientNotes').value.trim();
    }
    
    // Перейти к следующему шагу
    document.getElementById(`step${getStepName(currentStep)}`).classList.remove('active');
    currentStep++;
    
    if (currentStep === 3) {
        loadTimeSlots();
        document.getElementById('servicePrice').textContent = `${bookingData.price} ₽`;
    } else if (currentStep === 5) {
        updateConfirmation();
    }
    
    document.getElementById(`step${getStepName(currentStep)}`).classList.add('active');
    updateNavigation();
}

function prevStep() {
    if (currentStep > 1) {
        document.getElementById(`step${getStepName(currentStep)}`).classList.remove('active');
        currentStep--;
        document.getElementById(`step${getStepName(currentStep)}`).classList.add('active');
        updateNavigation();
    }
}

function getStepName(step) {
    const stepNames = ['', 'Date', 'Time', 'Service', 'Details', 'Confirm', 'Success'];
    return stepNames[step];
}

function generateCalendar() {
    const datePicker = document.getElementById('datePicker');
    const monthNames = [
        'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
        'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
    ];
    
    document.getElementById('currentBookingMonth').textContent = 
        `${monthNames[currentMonth]} ${currentYear}`;
    
    const firstDay = new Date(currentYear, currentMonth, 1);
    const lastDay = new Date(currentYear, currentMonth + 1, 0);
    const today = new Date();
    
    let html = '';
    
    // Пустые ячейки для дней предыдущего месяца
    for (let i = 0; i < firstDay.getDay(); i++) {
        html += '<div class="date-item"></div>';
    }
    
    // Дни текущего месяца
    for (let day = 1; day <= lastDay.getDate(); day++) {
        const date = new Date(currentYear, currentMonth, day);
        const dayOfWeek = date.getDay();
        const isPast = date < today;
        const isToday = date.toDateString() === today.toDateString();
        const isSelected = bookingData.selected_date === date.toISOString().split('T')[0];
        
        let className = 'date-item';
        if (isPast) className += ' booked';
        if (isToday) className += ' today';
        if (isSelected) className += ' selected';
        
        const dayNames = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];
        
        html += `
            <div class="${className}" 
                 onclick="${isPast ? '' : `selectDate('${date.toISOString().split('T')[0]}')`}">
                <div class="date-day">${dayNames[dayOfWeek]}</div>
                <div class="date-number">${day}</div>
            </div>
        `;
    }
    
    datePicker.innerHTML = html;
}

function changeMonth(delta) {
    currentMonth += delta;
    if (currentMonth < 0) {
        currentMonth = 11;
        currentYear--;
    } else if (currentMonth > 11) {
        currentMonth = 0;
        currentYear++;
    }
    generateCalendar();
}

function selectDate(dateStr) {
    bookingData.selected_date = dateStr;
    generateCalendar(); // Перерисовываем календарь с выбранной датой
    updateNavigation();
}

async function loadTimeSlots() {
    if (!bookingData.selected_date) return;
    
    try {
        const response = await fetch(
            `/api/bookings/slots?master_code=${bookingData.master_code}&date=${bookingData.selected_date}`
        );
        const data = await response.json();
        
        if (data.error) {
            alert('Ошибка при загрузке временных слотов');
            return;
        }
        
    const timePicker = document.getElementById('timePicker');
    const allSlots = [
        '10:00', '10:30', '11:00', '11:30', '12:00', '12:30',
        '13:00', '13:30', '14:00', '14:30', '15:00', '15:30',
        '16:00', '16:30', '17:00', '17:30', '18:00', '18:30',
        '19:00', '19:30', '20:00', '20:30'
    ];
    
    let html = '';
    
    allSlots.forEach(time => {
        const isBooked = data.booked_slots.includes(time);
        const isSelected = bookingData.selected_time === time;
        
        let className = 'time-slot';
        if (isBooked) className += ' booked';
        if (isSelected) className += ' selected';
        
        html += `
            <div class="${className}" 
                 onclick="${isBooked ? '' : `selectTime('${time}')`}">
                ${time}
            </div>
        `;
    });
    
    timePicker.innerHTML = html;
} catch (error) {
    console.error('Error loading time slots:', error);
}
}

function selectTime(time) {
    bookingData.selected_time = time;
    
    // Обновить отображение выбранного времени
    document.querySelectorAll('.time-slot').forEach(slot => {
        slot.classList.remove('selected');
    });
    event.target.classList.add('selected');
    
    updateNavigation();
}

// Обработчик изменения услуги
document.getElementById('serviceSelect').addEventListener('change', function(e) {
    bookingData.selected_service = e.target.value;
    
    // Обновить цену в зависимости от услуги
    const prices = {
        'Стрижка': 1000,
        'Бритье': 800,
        'Стрижка + Бритье': 1500,
        'Окрашивание': 2000,
        'Уход': 500
    };
    
    bookingData.price = prices[bookingData.selected_service] || 1000;
    document.getElementById('servicePrice').textContent = `${bookingData.price} ₽`;
});

function updateConfirmation() {
    document.getElementById('confirmBarberName').textContent = bookingData.master_name;
    document.getElementById('confirmDate').textContent = formatDate(bookingData.selected_date);
    document.getElementById('confirmTime').textContent = bookingData.selected_time;
    document.getElementById('confirmService').textContent = bookingData.selected_service;
    document.getElementById('confirmClientName').textContent = bookingData.client_name;
    document.getElementById('confirmPhone').textContent = bookingData.client_phone;
    document.getElementById('confirmPrice').textContent = `${bookingData.price} ₽`;
}

function formatDate(dateStr) {
    const date = new Date(dateStr);
    const options = { day: 'numeric', month: 'long', year: 'numeric' };
    return date.toLocaleDateString('ru-RU', options);
}

async function createBooking() {
    try {
        const response = await fetch('/api/appointments', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                master_code: bookingData.master_code,
                client_name: bookingData.client_name,
                client_phone: bookingData.client_phone,
                service_type: bookingData.selected_service,
                price: bookingData.price,
                date: bookingData.selected_date,
                time: bookingData.selected_time,
                notes: bookingData.notes
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            // Показать шаг успеха
            document.getElementById('stepConfirm').classList.remove('active');
            currentStep = 6;
            document.getElementById('stepSuccess').classList.add('active');
            
            document.getElementById('successBarberName').textContent = bookingData.master_name;
            document.getElementById('successDateTime').textContent = 
                `${formatDate(bookingData.selected_date)} в ${bookingData.selected_time}`;
            
            updateNavigation();
        } else {
            alert('Ошибка при создании записи: ' + (result.error || 'Неизвестная ошибка'));
        }
    } catch (error) {
        console.error('Error creating booking:', error);
        alert('Ошибка подключения к серверу');
    }
}

// Закрытие модального окна при клике вне его
document.getElementById('bookingModal').addEventListener('click', function(e) {
    if (e.target === this) {
        closeBookingModal();
    }
});

// Закрытие по Escape
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeBookingModal();
    }
});
