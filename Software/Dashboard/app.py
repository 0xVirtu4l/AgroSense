import os
from flask import Flask, render_template, url_for, flash, redirect, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    current_user,
    logout_user,
    login_required,
)
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, FloatField, SelectField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError
from datetime import datetime
import requests
import json
from flask_wtf import CSRFProtect
from config import TREFLE_API_KEY

# Initialize Flask app
app = Flask(__name__)
csrf = CSRFProtect(app)

app.config['SECRET_KEY'] = 'SECRET_KEY'  
# Set the base directory
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'agrosense.db')

# Initialize extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


TREFLE_API_KEY = TREFLE_API_KEY  # Will use it in a later section

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False, unique=True)
    password = db.Column(db.String(255), nullable=False)
    devices = db.relationship('Device', backref='owner', lazy=True)

class CommandForm(FlaskForm):
    command = StringField('Command', validators=[DataRequired()])
    submit = SubmitField('Send Command')

class Device(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(50), nullable=False, unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    plant_type = db.Column(db.String(100), nullable=False) 
    location = db.Column(db.String(100), nullable=False)
    sensor_data = db.relationship('SensorData', backref='device', lazy=True)
    commands = db.relationship('DeviceCommand', backref='device', lazy=True)

class SensorData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(50), db.ForeignKey('device.device_id'), nullable=False)
    temperature = db.Column(db.Float, nullable=False)
    humidity = db.Column(db.Float, nullable=False)
    soil_moisture = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)

class DeviceCommand(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(50), db.ForeignKey('device.device_id'), nullable=False)
    command = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    executed = db.Column(db.Boolean, default=False)

# Forms
class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=2, max=150)])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField(
        'Confirm Password', validators=[DataRequired(), EqualTo('password')]
    )
    submit = SubmitField('Sign Up')

    # Custom validator to check if username already exists
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Username already exists.')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=2, max=150)])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class AddDeviceForm(FlaskForm):
    device_id = StringField('Device ID', validators=[DataRequired()])
    plant_type = SelectField('Plant Type', validators=[DataRequired()], choices=[])
    location = StringField('Location', validators=[DataRequired()])
    submit = SubmitField('Add Device')

    def __init__(self, *args, **kwargs):
        super(AddDeviceForm, self).__init__(*args, **kwargs)
        # Load plant types from JSON file
        with open(os.path.join(basedir, 'static/data/normal_plants.json')) as f:
            plants_data = json.load(f)
        self.plant_type.choices = [(plant, plant) for plant in plants_data.keys()]

# Routes
@app.route('/')
def home():
    return redirect(url_for('dashboard'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_pw = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(username=form.username.data, password=hashed_pw)
        db.session.add(user)
        db.session.commit()
        flash('Your account has been created! You can now log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Login unsuccessful. Please check username and password.', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    devices = current_user.devices

    # Handle Add Device form submission
    form = AddDeviceForm()
    if form.validate_on_submit():
        device_id = form.device_id.data
        plant_type = form.plant_type.data
        location = form.location.data

        existing_device = Device.query.filter_by(device_id=device_id).first()
        if existing_device:
            flash('Device already registered.', 'danger')
        else:
            new_device = Device(
                device_id=device_id,
                owner=current_user,
                plant_type=plant_type,
                location=location
            )
            db.session.add(new_device)
            db.session.commit()
            flash('Device added successfully!', 'success')
            return redirect(url_for('dashboard'))

    return render_template('dashboard.html', devices=devices, form=form)


@app.route('/api/device_data/<device_id>', methods=['GET'])
@login_required
def api_device_data(device_id):
    device = Device.query.filter_by(device_id=device_id, owner=current_user).first()
    if device:
        data = SensorData.query.filter_by(device_id=device_id).order_by(SensorData.timestamp.desc()).limit(50).all()
        data_list = [{
            'temperature': d.temperature,
            'humidity': d.humidity,
            'soil_moisture': d.soil_moisture,
            'latitude': d.latitude,
            'longitude': d.longitude,
            'timestamp': d.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        } for d in data]
        return jsonify({
            'device': {
                'device_id': device.device_id,
                'plant_type': device.plant_type,  
                'location': device.location
            },
            'sensor_data': data_list
        }), 200
    else:
        return jsonify({'message': 'Device not found'}), 404




@app.route('/add_device', methods=['GET', 'POST'])
@login_required
def add_device():
    form = AddDeviceForm()
    if form.validate_on_submit():
        device_id = form.device_id.data
        plant_name = form.plant_name.data
        location = form.location.data

        existing_device = Device.query.filter_by(device_id=device_id).first()
        if existing_device:
            flash('Device already registered.', 'danger')
        else:
            new_device = Device(
                device_id=device_id,
                owner=current_user,
                plant_name=plant_name,
                plant_data=None,
                location=location
            )
            db.session.add(new_device)
            db.session.commit()
            flash('Device added successfully!', 'success')
            return redirect(url_for('dashboard'))
    return render_template('add_device.html', form=form)

@app.route('/device/<device_id>')
@login_required
def device_data(device_id):
    device = Device.query.filter_by(device_id=device_id, owner=current_user).first()
    if device:
        form = CommandForm()  # Create an instance of the form
        plant_data = device.plant_data or {}
        # Default values if data is missing
        normal_temp_min = plant_data.get('temperature_min', None)
        normal_temp_max = plant_data.get('temperature_max', None)
        normal_humidity_min = 50
        normal_humidity_max = 80
        normal_soil_moisture_min = 50
        normal_soil_moisture_max = 80

        return render_template(
            'device_data.html',
            device=device,
            form=form, 
            normal_temp_min=normal_temp_min,
            normal_temp_max=normal_temp_max,
            normal_humidity_min=normal_humidity_min,
            normal_humidity_max=normal_humidity_max,
            normal_soil_moisture_min=normal_soil_moisture_min,
            normal_soil_moisture_max=normal_soil_moisture_max
        )
    else:
        flash('Device not found or you do not have access to it.', 'danger')
        return redirect(url_for('dashboard'))

@csrf.exempt
@app.route('/api/sensordata', methods=['POST'])
def receive_data():
    data = request.get_json()
    device_id = data.get('device_id')
    temperature = data.get('temperature')
    humidity = data.get('humidity')
    soil_moisture = data.get('soil_moisture')
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    print(f"Received data: {data}")
    device = Device.query.filter_by(device_id=device_id).first()
    if device:
        sensor_data = SensorData(
            device_id=device_id,
            temperature=temperature,
            humidity=humidity,
            soil_moisture=soil_moisture,
            latitude=latitude,
            longitude=longitude
        )
        db.session.add(sensor_data)
        db.session.commit()

        pending_command = DeviceCommand.query.filter_by(
            device_id=device_id, executed=False
        ).order_by(DeviceCommand.timestamp.asc()).first()

        response = {'message': 'Data received successfully'}
        if pending_command:
            response['command'] = pending_command.command
            pending_command.executed = True
            db.session.commit()
        else:
            response['command'] = None

        return jsonify(response), 200
    else:
        return jsonify({'message': 'Device not registered'}), 400

@app.route('/api/get_sensor_data/<device_id>', methods=['GET'])
@login_required
def get_sensor_data(device_id):
    device = Device.query.filter_by(device_id=device_id, owner=current_user).first()
    if device:
        data = SensorData.query.filter_by(device_id=device_id).order_by(SensorData.timestamp.desc()).limit(50).all()
        data_list = [{
            'temperature': d.temperature,
            'humidity': d.humidity,
            'soil_moisture': d.soil_moisture,
            'timestamp': d.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        } for d in data]
        return jsonify(data_list), 200
    else:
        return jsonify({'message': 'Device not found'}), 404

@csrf.exempt
@app.route('/delete_device/<device_id>', methods=['POST'])
@login_required
def delete_device(device_id):
    device = Device.query.filter_by(device_id=device_id, owner=current_user).first()
    if device:
        SensorData.query.filter_by(device_id=device_id).delete()
        DeviceCommand.query.filter_by(device_id=device_id).delete()
        db.session.delete(device)
        db.session.commit()
        return jsonify({'success': True}), 200
    else:
        return jsonify({'success': False, 'message': 'Device not found'}), 404


@app.route('/add_command/<device_id>', methods=['POST'])
@login_required
def add_command(device_id):
    form = CommandForm()
    if form.validate_on_submit():
        device = Device.query.filter_by(device_id=device_id, owner=current_user).first()
        if device:
            command = form.command.data
            new_command = DeviceCommand(
                device_id=device_id,
                command=command,
                executed=False
            )
            db.session.add(new_command)
            db.session.commit()
            flash('Command added successfully.', 'success')
            return redirect(url_for('device_data', device_id=device_id))
        else:
            flash('Device not found.', 'danger')
            return redirect(url_for('dashboard'))
    else:
        flash('Invalid form submission.', 'danger')
        return redirect(url_for('device_data', device_id=device_id))


# Create the database tables
with app.app_context():
        db.create_all()

if __name__ == '__main__':

    app.run(host="0.0.0.0", port=80)