"""
Medicare - AI Powered Smart Healthcare Platform
Main Flask application entry point.
"""

from flask import Flask, render_template, redirect, url_for, flash, request, session, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from functools import wraps
import os
import re

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx'}

app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-this-secret-key-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///medicare.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

# ---------------------------------------------------------------
# DATABASE MODELS
# ---------------------------------------------------------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='patient')  # 'patient' or 'doctor'
    phone = db.Column(db.String(15))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Doctor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    specialization = db.Column(db.String(100), nullable=False)
    qualification = db.Column(db.String(150))
    experience_years = db.Column(db.Integer, default=0)
    consultation_fee = db.Column(db.Float, default=0.0)
    available_days = db.Column(db.String(100))

    user = db.relationship('User', backref='doctor_profile')


class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False)
    appointment_date = db.Column(db.String(20), nullable=False)
    appointment_time = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(20), default='pending')
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    patient = db.relationship('User', foreign_keys=[patient_id])
    doctor = db.relationship('Doctor', foreign_keys=[doctor_id])


class Prescription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointment.id'))
    patient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False)
    medicines = db.Column(db.Text, nullable=False)
    instructions = db.Column(db.Text)
    issued_date = db.Column(db.DateTime, default=datetime.utcnow)

    patient = db.relationship('User', foreign_keys=[patient_id])
    doctor = db.relationship('Doctor', foreign_keys=[doctor_id])


class MedicalRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)
    record_type = db.Column(db.String(50))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)


class Reminder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    medicine_name = db.Column(db.String(150), nullable=False)
    dosage = db.Column(db.String(100))
    reminder_time = db.Column(db.String(10), nullable=False)
    frequency = db.Column(db.String(50))
    active = db.Column(db.Boolean, default=True)


# ---------------------------------------------------------------
# HELPERS / DECORATORS
# ---------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


def doctor_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'doctor':
            flash('This page is only for doctors.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return wrapper


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None


# ---------------------------------------------------------------
# SIMPLE AI HEALTH CHATBOT (rule/keyword based demo engine)
# ---------------------------------------------------------------

GREETING_PATTERNS = r'\b(hi|hello|hey|namaste)\b'
AFFIRMATIVE_PATTERNS = r'^\s*(yes|yeah|yep|sure|ok|okay|haan|ha)\s*[.!]?\s*$'

CHATBOT_RULES = [
    (r'\b(fever|temperature)\b',
     "For fever: rest, stay hydrated, and monitor temperature. If it stays above 102F for more than 2 days, or is accompanied by severe symptoms, please consult a doctor.",
     ('Find a Doctor', '/doctors')),
    (r'\b(headache|migraine)\b',
     "For headaches: rest in a quiet dark room, stay hydrated, and avoid screen time. Frequent or severe headaches should be evaluated by a doctor.",
     ('Find a Doctor', '/doctors')),
    (r'\b(cold|cough|flu)\b',
     "For cold/cough: warm fluids, rest, and steam inhalation can help. See a doctor if symptoms last more than a week or breathing becomes difficult.",
     ('Find a Doctor', '/doctors')),
    (r'\b(stomach|nausea|vomit|diarrhea)\b',
     "For stomach issues: stay hydrated with ORS, eat light food (BRAT diet), and avoid oily food. Consult a doctor if symptoms persist beyond 2 days or you notice blood.",
     ('Find a Doctor', '/doctors')),
    (r'\b(appointment|book)\b',
     "You can book an appointment with a doctor right here:",
     ('Find a Doctor', '/doctors')),
    (r'\bdoctor\b',
     "Here's where you can search and book doctors:",
     ('Find a Doctor', '/doctors')),
    (r'\b(prescription|medicine|medication)\b',
     "Here are your digital prescriptions:",
     ('View Prescriptions', '/prescriptions')),
    (r'\b(reminder|dose|schedule)\b',
     "You can set up medicine reminders here so you never miss a dose:",
     ('Manage Reminders', '/reminders')),
    (r'\b(record|report|upload)\b',
     "You can upload and manage your medical records here:",
     ('Medical Records', '/records')),
    (r'\b(emergency|chest pain|breathless|unconscious)\b',
     "This sounds like it could be a medical emergency. Please call your local emergency number or go to the nearest hospital immediately.",
     None),
]

DEFAULT_REPLY = ("I can offer general wellness guidance, but I'm not a substitute for professional medical advice. "
                  "Tell me your symptom (e.g. fever, headache, cough), or use the buttons below to jump straight to a page.")
DEFAULT_ACTIONS = [
    ('Find a Doctor', '/doctors'),
    ('Prescriptions', '/prescriptions'),
    ('Reminders', '/reminders'),
]

GREETING_REPLY = "Hello! I'm the Medicare AI Assistant. I can give general health guidance and help you navigate the platform. What's bothering you today?"

AFFIRMATIVE_REPLY = "Great — here are some quick links:"
AFFIRMATIVE_ACTIONS = [
    ('Find a Doctor', '/doctors'),
    ('Prescriptions', '/prescriptions'),
    ('Reminders', '/reminders'),
    ('Medical Records', '/records'),
]


def get_bot_response(message):
    msg = message.lower().strip()

    if re.search(AFFIRMATIVE_PATTERNS, msg):
        return {'reply': AFFIRMATIVE_REPLY, 'actions': [{'label': l, 'url': u} for l, u in AFFIRMATIVE_ACTIONS]}

    if re.search(GREETING_PATTERNS, msg):
        return {'reply': GREETING_REPLY, 'actions': []}

    for pattern, reply, action in CHATBOT_RULES:
        if re.search(pattern, msg):
            actions = [{'label': action[0], 'url': action[1]}] if action else []
            return {'reply': reply, 'actions': actions}

    return {'reply': DEFAULT_REPLY, 'actions': [{'label': l, 'url': u} for l, u in DEFAULT_ACTIONS]}

def get_bot_reply(message):
    msg = message.lower()
    for pattern, reply in CHATBOT_RULES:
        if re.search(pattern, msg):
            return reply
    return DEFAULT_REPLY


# ---------------------------------------------------------------
# PAGE ROUTES
# ---------------------------------------------------------------

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role', 'patient')

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return redirect(url_for('register'))

        new_user = User(name=name, email=email, role=role)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        if role == 'doctor':
            db.session.add(Doctor(user_id=new_user.id, specialization='General Physician'))
            db.session.commit()

        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            session['user_id'] = user.id
            session['role'] = user.role
            flash('Login successful.', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('home'))


@app.route('/dashboard')
@login_required
def dashboard():
    user = current_user()
    return render_template('dashboard.html', user=user)


@app.route('/doctors')
def doctor_list():
    doctors = Doctor.query.all()
    return render_template('doctors.html', doctors=doctors)


@app.route('/book/<int:doctor_id>', methods=['GET', 'POST'])
@login_required
def book_appointment(doctor_id):
    doctor = Doctor.query.get_or_404(doctor_id)

    if request.method == 'POST':
        appt = Appointment(
            patient_id=session['user_id'],
            doctor_id=doctor_id,
            appointment_date=request.form.get('date'),
            appointment_time=request.form.get('time'),
            notes=request.form.get('notes')
        )
        db.session.add(appt)
        db.session.commit()
        flash('Appointment booked successfully.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('book_appointment.html', doctor=doctor)


@app.route('/appointments')
@login_required
def my_appointments():
    if session.get('role') == 'doctor':
        doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
        appts = Appointment.query.filter_by(doctor_id=doctor.id).all() if doctor else []
    else:
        appts = Appointment.query.filter_by(patient_id=session['user_id']).all()
    return render_template('appointments.html', appointments=appts)


@app.route('/appointments/<int:appt_id>/status', methods=['POST'])
@login_required
@doctor_required
def update_appointment_status(appt_id):
    appt = Appointment.query.get_or_404(appt_id)
    appt.status = request.form.get('status', appt.status)
    db.session.commit()
    flash('Appointment status updated.', 'success')
    return redirect(url_for('my_appointments'))


# ---- Prescriptions ----

@app.route('/prescriptions')
@login_required
def prescriptions():
    if session.get('role') == 'doctor':
        doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
        items = Prescription.query.filter_by(doctor_id=doctor.id).all() if doctor else []
    else:
        items = Prescription.query.filter_by(patient_id=session['user_id']).all()
    return render_template('prescriptions.html', prescriptions=items)


@app.route('/prescriptions/new', methods=['GET', 'POST'])
@login_required
@doctor_required
def new_prescription():
    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    appts = Appointment.query.filter_by(doctor_id=doctor.id).all() if doctor else []

    if request.method == 'POST':
        appointment_id = request.form.get('appointment_id') or None
        patient_id = request.form.get('patient_id')
        presc = Prescription(
            appointment_id=appointment_id,
            patient_id=patient_id,
            doctor_id=doctor.id,
            medicines=request.form.get('medicines'),
            instructions=request.form.get('instructions')
        )
        db.session.add(presc)
        db.session.commit()
        flash('Prescription issued successfully.', 'success')
        return redirect(url_for('prescriptions'))

    return render_template('new_prescription.html', appointments=appts)


# ---- Medical Records ----

@app.route('/records')
@login_required
def records():
    items = MedicalRecord.query.filter_by(patient_id=session['user_id']).all()
    return render_template('records.html', records=items)


@app.route('/records/upload', methods=['POST'])
@login_required
def upload_record():
    file = request.files.get('file')
    record_type = request.form.get('record_type', 'report')

    if not file or file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('records'))

    if not allowed_file(file.filename):
        flash('File type not allowed. Use PDF, image, or Word document.', 'error')
        return redirect(url_for('records'))

    original_name = secure_filename(file.filename)
    stored_name = f"{session['user_id']}_{datetime.utcnow().timestamp()}_{original_name}"
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], stored_name))

    record = MedicalRecord(
        patient_id=session['user_id'],
        file_name=original_name,
        stored_name=stored_name,
        record_type=record_type
    )
    db.session.add(record)
    db.session.commit()
    flash('Medical record uploaded successfully.', 'success')
    return redirect(url_for('records'))


@app.route('/records/<int:record_id>/download')
@login_required
def download_record(record_id):
    record = MedicalRecord.query.get_or_404(record_id)
    if record.patient_id != session['user_id']:
        flash('Not authorized to access this record.', 'error')
        return redirect(url_for('records'))
    return send_from_directory(app.config['UPLOAD_FOLDER'], record.stored_name,
                                as_attachment=True, download_name=record.file_name)


@app.route('/records/<int:record_id>/delete', methods=['POST'])
@login_required
def delete_record(record_id):
    record = MedicalRecord.query.get_or_404(record_id)
    if record.patient_id != session['user_id']:
        flash('Not authorized.', 'error')
        return redirect(url_for('records'))
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], record.stored_name)
    if os.path.exists(file_path):
        os.remove(file_path)
    db.session.delete(record)
    db.session.commit()
    flash('Record deleted.', 'success')
    return redirect(url_for('records'))


# ---- Medicine Reminders ----

@app.route('/reminders')
@login_required
def reminders():
    items = Reminder.query.filter_by(patient_id=session['user_id']).all()
    return render_template('reminders.html', reminders=items)


@app.route('/reminders/new', methods=['POST'])
@login_required
def new_reminder():
    reminder = Reminder(
        patient_id=session['user_id'],
        medicine_name=request.form.get('medicine_name'),
        dosage=request.form.get('dosage'),
        reminder_time=request.form.get('reminder_time'),
        frequency=request.form.get('frequency')
    )
    db.session.add(reminder)
    db.session.commit()
    flash('Reminder added.', 'success')
    return redirect(url_for('reminders'))


@app.route('/reminders/<int:reminder_id>/toggle', methods=['POST'])
@login_required
def toggle_reminder(reminder_id):
    reminder = Reminder.query.get_or_404(reminder_id)
    if reminder.patient_id != session['user_id']:
        flash('Not authorized.', 'error')
        return redirect(url_for('reminders'))
    reminder.active = not reminder.active
    db.session.commit()
    return redirect(url_for('reminders'))


@app.route('/reminders/<int:reminder_id>/delete', methods=['POST'])
@login_required
def delete_reminder(reminder_id):
    reminder = Reminder.query.get_or_404(reminder_id)
    if reminder.patient_id != session['user_id']:
        flash('Not authorized.', 'error')
        return redirect(url_for('reminders'))
    db.session.delete(reminder)
    db.session.commit()
    flash('Reminder removed.', 'success')
    return redirect(url_for('reminders'))


# ---- AI Chatbot ----

@app.route('/chatbot')
@login_required
def chatbot_page():
    return render_template('chatbot.html')


@app.route('/api/chatbot', methods=['POST'])
@login_required
def chatbot_api():
    data = request.get_json(silent=True) or {}
    message = data.get('message', '').strip()
    if not message:
        return jsonify({'error': 'Message is required'}), 400
    result = get_bot_response(message)
    return jsonify(result)


# ---------------------------------------------------------------
# REST API (JSON) - for external / mobile clients
# ---------------------------------------------------------------

@app.route('/api/doctors', methods=['GET'])
def api_doctors():
    doctors = Doctor.query.all()
    return jsonify([{
        'id': d.id,
        'name': d.user.name,
        'specialization': d.specialization,
        'qualification': d.qualification,
        'experience_years': d.experience_years,
        'consultation_fee': d.consultation_fee
    } for d in doctors])


@app.route('/api/appointments', methods=['GET', 'POST'])
@login_required
def api_appointments():
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        appt = Appointment(
            patient_id=session['user_id'],
            doctor_id=data.get('doctor_id'),
            appointment_date=data.get('date'),
            appointment_time=data.get('time'),
            notes=data.get('notes')
        )
        db.session.add(appt)
        db.session.commit()
        return jsonify({'message': 'Appointment created', 'id': appt.id}), 201

    appts = Appointment.query.filter_by(patient_id=session['user_id']).all()
    return jsonify([{
        'id': a.id,
        'doctor': a.doctor.user.name if a.doctor else None,
        'date': a.appointment_date,
        'time': a.appointment_time,
        'status': a.status
    } for a in appts])


@app.route('/api/prescriptions', methods=['GET'])
@login_required
def api_prescriptions():
    items = Prescription.query.filter_by(patient_id=session['user_id']).all()
    return jsonify([{
        'id': p.id,
        'doctor': p.doctor.user.name if p.doctor else None,
        'medicines': p.medicines,
        'instructions': p.instructions,
        'issued_date': p.issued_date.isoformat()
    } for p in items])


@app.route('/api/reminders', methods=['GET', 'POST'])
@login_required
def api_reminders():
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        reminder = Reminder(
            patient_id=session['user_id'],
            medicine_name=data.get('medicine_name'),
            dosage=data.get('dosage'),
            reminder_time=data.get('reminder_time'),
            frequency=data.get('frequency')
        )
        db.session.add(reminder)
        db.session.commit()
        return jsonify({'message': 'Reminder created', 'id': reminder.id}), 201

    items = Reminder.query.filter_by(patient_id=session['user_id']).all()
    return jsonify([{
        'id': r.id,
        'medicine_name': r.medicine_name,
        'dosage': r.dosage,
        'reminder_time': r.reminder_time,
        'frequency': r.frequency,
        'active': r.active
    } for r in items])


# ---------------------------------------------------------------
# APP INITIALIZATION
# ---------------------------------------------------------------

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
