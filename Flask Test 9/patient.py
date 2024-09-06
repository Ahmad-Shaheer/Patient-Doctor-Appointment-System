from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_pymongo import PyMongo
from flask_mail import Mail, Message
from bson.objectid import ObjectId
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# MongoDB connection with Flask-PyMongo
app.config["MONGO_URI"] = "mongodb://localhost:27017/AppointmentTest"  # Use your actual database name
mongo = PyMongo(app)
patients_collection = mongo.db.patients
doctors_collection =mongo.db.doctors
# Flask-Mail configuration
app.config['MAIL_SERVER'] = 'smtp.example.com'  # Replace with your mail server
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your_email@example.com'  # Replace with your email
app.config['MAIL_PASSWORD'] = 'your_password'  # Replace with your email password
app.config['MAIL_DEFAULT_SENDER'] = 'your_email@example.com'
mail = Mail(app)


class User:
    def __init__(self, user_id, name, email):
        self.user_id = user_id
        self.name = name
        self.email = email

    def get_user_info(self):
        return {
            "user_id": self.user_id,
            "name": self.name,
            "email": self.email
        }


class Patient:
    def __init__(self, mongo_db):
        self.mongo_db = mongo_db
        self.collection = mongo_db['patients']
        self.appointments_collection = mongo_db['appointments']
        self.availability_collection = mongo_db['availability']
        
        
    def login(self, username, password):
        user = self.collection.find_one({'email': username})
        if user and user['password'] == password:  # In production, use a hashed password check
            session['username'] = username
            return True
        else:
            return False

    def register(self, username, password, full_name, email, phone):
        if self.collection.find_one({'username': username}):
            return {'success': False, 'message': 'Username already exists!'}
        
        self.collection.insert_one({
            'username': username,
            'password': password,  # Password should be hashed in production
            'full_name': full_name,
            'email': email,
            'phone': phone
        })
        return {'success': True, 'message': 'Registration successful! Please log in.'}

    def book_appointment(self, username, doctor_id, appointment_date, time_slot, reason):
        doctor_id_obj = ObjectId(doctor_id)

        # Fetch time slots for the specific doctor and date
        availability_doc = self.availability_collection.find_one({
            "doctor_id": doctor_id_obj,
            "date": appointment_date
        })

        if not availability_doc:
            return {"error": "Doctor is not available on the selected date."}, 404

        time_slots = availability_doc.get("time_slot", [])
        try:
            time_slot_index = time_slots.index(time_slot)
        except ValueError:
            return {"error": "Invalid time slot."}, 400

        # Fetch patient data
        patient = self.collection.find_one({"email": username})
        if not patient:
            return {"error": "Patient not found."}, 404

        # Create new appointment document
        new_appointment = {
            "patient_id": patient['_id'],
            "doctor_id": doctor_id_obj,
            "date": appointment_date,
            "time": time_slot,
            "status": "Scheduled",
            "reason": reason
        }

        # Insert new appointment into the database
        self.appointments_collection.insert_one(new_appointment)

        # Update availability
        self.availability_collection.update_one(
            {"doctor_id": doctor_id_obj, "date": appointment_date},
            {"$set": {f"is_available.{time_slot_index}": False}}
        )

        return {"success": True, "message": "Appointment booked successfully."}

    def reschedule_appointment(self, appointment_id, doctor_id, new_date, new_time_slot):
        # Find the existing appointment
        appointment = self.appointments_collection.find_one({"_id": ObjectId(appointment_id)})
        if not appointment:
            return {"error": "Appointment not found."}, 404

        old_date = appointment['date']
        old_time_slot = appointment['time']

        # Update the appointment with new date and time
        update_result = self.appointments_collection.update_one(
            {"_id": ObjectId(appointment_id)},
            {"$set": {"date": new_date, "time": new_time_slot}}
        )

        if update_result.matched_count == 0:
            return {"error": "Failed to update the appointment."}, 404

        # Mark the old time slot as available
        self.availability_collection.update_one(
            {"doctor_id": ObjectId(doctor_id), "date": old_date},
            {"$set": {"is_available.$[slot]": True}},
            array_filters=[{"slot": old_time_slot}]
        )

        # Mark the new time slot as unavailable
        self.availability_collection.update_one(
            {"doctor_id": ObjectId(doctor_id), "date": new_date},
            {"$set": {"is_available.$[slot]": False}},
            array_filters=[{"slot": new_time_slot}]
        )

        return {"success": True, "message": "Appointment rescheduled successfully."}

    def cancel_appointment(self, appointment_id):
        # Find and delete the appointment
        appointment = self.appointments_collection.find_one({"_id": ObjectId(appointment_id)})
        if not appointment:
            return {"error": "Appointment not found."}, 404

        doctor_id = appointment['doctor_id']
        old_date_str = appointment['date']
        old_time_slot = appointment['time']

        result = self.appointments_collection.delete_one({"_id": ObjectId(appointment_id)})
        if result.deleted_count == 0:
            return {"error": "Failed to cancel the appointment."}, 404

        # Mark the old time slot as available
        self.availability_collection.update_one(
            {"doctor_id": ObjectId(doctor_id), "date": old_date_str},
            {"$set": {"is_available.$[slot]": True}},
            array_filters=[{"slot": old_time_slot}]
        )

        return {"success": True, "message": "Appointment canceled successfully."}


class Appointment:
    def __init__(self, mongo_db):
        self.mongo_db = mongo_db

    def postpone_appointment(self, appointment_id):
        if not appointment_id:
            return {'success': False, 'message': 'Invalid appointment ID format'}

        # Convert appointment ID to ObjectId
        appointment_id = ObjectId(appointment_id)

        # Find the appointment by ID
        appointment = self.mongo_db.appointments.find_one({"_id": appointment_id})
        if not appointment:
            return {'success': False, 'message': 'Appointment not found in the database'}

        doctor_id = appointment['doctor_id']
        current_date = appointment['date']
        # Find the next available date with an available time slot
        next_available_date = self.mongo_db.availability.find_one({
            "doctor_id": ObjectId(doctor_id),
            "date": {"$gt": current_date},
            "is_available": True
        }, sort=[("date", 1)])

        if next_available_date:
            available_time_slots = [
                time for index, time in enumerate(next_available_date['time_slot'])
                if next_available_date['is_available'][index]
            ]

            if available_time_slots:
                next_time_slot = available_time_slots[0]

                # Update the appointment to the new date and time slot
                self.mongo_db.appointments.update_one(
                    {"_id": appointment_id},
                    {"$set": {"date": next_available_date['date'], "time": next_time_slot}}
                )

                # Mark the new time slot as unavailable
                time_slot_index = next_available_date['time_slot'].index(next_time_slot)
                self.mongo_db.availability.update_one(
                    {"_id": next_available_date['_id']},
                    {"$set": {f"is_available.{time_slot_index}": False}}
                )

                return {'success': True}
        
        return {'success': False, 'message': 'No available slots found.'}


class Doctor:
    def __init__(self, mongo_db):
        self.mongo_db = mongo_db
        self.collection = mongo_db['doctors']
    
    def get_doctors(self, specialization):
        if not specialization:
            return []

        doctors = self.mongo_db.doctors.find({"specialization": specialization})
        doctor_list = [{"_id": str(doctor["_id"]), "name": doctor["name"]} for doctor in doctors]

        return doctor_list
    def login(self, username, password):
        user = self.collection.find_one({'email': username})
        if user and user['password'] == password:  # In production, use a hashed password check
            session['username'] = username
            return True
        else:
            return False

    def register(self, username, password, full_name, email, phone):
        if self.collection.find_one({'username': username}):
            return {'success': False, 'message': 'Username already exists!'}
        
        self.collection.insert_one({
            'username': username,
            'password': password,  # Password should be hashed in production
            'full_name': full_name,
            'email': email,
            'phone': phone
        })
        return {'success': True, 'message': 'Registration successful! Please log in.'}
    def set_working_hours(self, username, days, start_time_str, end_time_str):
        # Fetch doctor ID using the username
        doctor = self.mongo_db.doctors.find_one({"email": username})
        if not doctor:
            return {"error": "Doctor not found"}, 404

        doctor_id = str(doctor['_id'])

        if not doctor_id or not days or not start_time_str or not end_time_str:
            return {"error": "Missing data"}, 400

        # Parse time strings
        start_time = datetime.strptime(start_time_str, '%H:%M').time()
        end_time = datetime.strptime(end_time_str, '%H:%M').time()

        # Calculate start date (2 weeks from now) and end date (4 weeks from now)
        tz = pytz.timezone('UTC')  # Adjust timezone as needed
        now = datetime.now(tz)
        start_date = now + timedelta(weeks=2)
        end_date = start_date + timedelta(weeks=2)

        # Generate list of dates for 2 weeks
        date_range = [start_date + timedelta(days=x) for x in range((end_date - start_date).days)]

        # Convert days to numbers for easier comparison (Monday=0, ..., Sunday=6)
        day_map = {'Monday': 0, 'Tuesday': 1, 'Wednesday': 2, 'Thursday': 3, 'Friday': 4, 'Saturday': 5, 'Sunday': 6}

        for date in date_range:
            if date.weekday() in [day_map[day] for day in days]:
                # Generate one-hour time slots from start to end time
                time_slots = []
                is_available = []

                current_time = datetime.combine(date, start_time)
                end_datetime = datetime.combine(date, end_time)

                while current_time < end_datetime:
                    next_time = current_time + timedelta(minutes=30)  # Adjust duration as needed
                    time_slot = f"{current_time.strftime('%H:%M')}-{next_time.strftime('%H:%M')}"
                    time_slots.append(time_slot)
                    is_available.append(True)  # Assuming all new slots are available
                    current_time = next_time

                # Update or create availability document for the day
                result = self.mongo_db.availability.update_one(
                    {"doctor_id": ObjectId(doctor_id), "date": date.strftime('%Y-%m-%d')},
                    {"$set": {
                        "time_slot": time_slots,
                        "is_available": is_available
                    }},
                    upsert=True
                )
                if result.matched_count > 0:
                    print(f"Updated availability for {date.strftime('%Y-%m-%d')}")
                else:
                    print(f"Inserted new availability for {date.strftime('%Y-%m-%d')}")

        print(f'Successfully updated availability for dates: {date_range}')
        return {"success": "Successfully updated availability"}, 200
    
    
class Availability:
    def __init__(self, mongo_db):
        self.mongo_db = mongo_db

    def get_available_timeslots(self, doctor_id, date):
        if not doctor_id or not date:
            return []

        availability = self.mongo_db.availability.find_one({"doctor_id": ObjectId(doctor_id), "date": date})
        if not availability:
            return []

        available_slots = [
            time_slot for time_slot, is_available in zip(availability["time_slot"], availability["is_available"])
            if is_available
        ]

        return available_slots

    def get_available_dates(self, doctor_id):
        if not doctor_id:
            return []

        available_dates_cursor = self.mongo_db.availability.find({"doctor_id": ObjectId(doctor_id)})
        available_dates = list(available_dates_cursor)

        dates = [availability['date'] for availability in available_dates]
        unique_dates = list(set(dates))
        sorted_dates = sorted(unique_dates)[:14]

        return sorted_dates


class Scheduler:
    def __init__(self, mongo_db, mail):
        self.appointments = []
        self.mongo_db = mongo_db
        self.mail = mail
        self.scheduler = BackgroundScheduler(timezone='UTC')
        self.scheduler.start()
        self.schedule_email_reminders()

    def book_appointment(self, patient, doctor, date, time_slot):
        availability = Availability(doctor)
        if availability.check_availability(date):
            appointment_id = len(self.appointments) + 1
            appointment = Appointment(appointment_id, patient, doctor, date, time_slot)
            self.appointments.append(appointment)
            self.schedule_email_reminders()
            return appointment
        else:
            print("Selected doctor is not available on the chosen date.")
            return None

    def cancel_appointment(self, appointment_id):
        self.appointments = [appt for appt in self.appointments if appt.appointment_id != appointment_id]

    def get_all_appointments(self):
        return [appt.get_appointment_info() for appt in self.appointments]

# Utility function to send reminder emails
    def send_reminder_email(self, appointment):
        doctor = self.mongo_db.doctors.find_one({"_id": ObjectId(appointment['doctor_id'])})
        patient = self.mongo_db.patients.find_one({"_id": ObjectId(appointment['patient_id'])})

        if not doctor or not patient:
            print(f"Doctor or patient not found for appointment ID: {appointment['_id']}")
            return

        doctor_email = doctor.get('email')
        patient_email = patient.get('email')

        if not doctor_email or not patient_email:
            print(f"Missing email address for doctor or patient for appointment ID: {appointment['_id']}")
            return

        subject = "Appointment Reminder"
        body = f"Dear {doctor['name']} and {patient['full_name']},\n\nThis is a reminder for your upcoming appointment at {appointment['time']} on {appointment['date']}."

        msg = Message(subject, recipients=[doctor_email, patient_email])
        msg.body = body

        try:
            self.mail.send(msg)
            print(f"Reminder email sent successfully for appointment ID: {appointment['_id']}")
        except Exception as e:
            print(f"Failed to send reminder email: {e}")

    # Schedule email reminders for all future appointments
    def schedule_email_reminders(self):
        now = datetime.now(pytz.UTC)
        upcoming_appointments = self.mongo_db.appointments.find({"date": {"$gte": now.strftime('%Y-%m-%d')}})

        for appointment in upcoming_appointments:
            try:
                appointment_datetime = datetime.strptime(f"{appointment['date']} {appointment['time']}", '%Y-%m-%d %H:%M')
                appointment_datetime = pytz.UTC.localize(appointment_datetime)
                reminder_time = appointment_datetime - timedelta(hours=1)

                if reminder_time > now:
                    self.scheduler.add_job(self.send_reminder_email, 'date', run_date=reminder_time, args=[appointment])
                    print(f"Scheduled email reminder for appointment ID: {appointment['_id']} at {reminder_time}")

            except ValueError as e:
                print(f"Error parsing datetime for appointment ID: {appointment['_id']} - {e}")


appointment_manager = Appointment(mongo.db)
doctor_manager = Doctor(mongo.db)
availability_manager = Availability(mongo.db)
patient_manager = Patient(mongo.db)

''' Helping Functions'''

@app.route('/postpone_appointment', methods=['POST'])
def postpone_appointment():
    appointment_id = request.args.get('appointment_id')
    result = appointment_manager.postpone_appointment(appointment_id)
    return jsonify(result)


@app.route('/get_doctors', methods=['GET'])
def get_doctors():
    specialization = request.args.get('specialization')
    result = doctor_manager.get_doctors(specialization)
    return jsonify(result)

@app.route('/get_available_timeslots', methods=['GET'])
def get_available_timeslots():
    doctor_id = request.args.get('doctor_id')
    date = request.args.get('date')
    result = availability_manager.get_available_timeslots(doctor_id, date)
    return jsonify(result)


@app.route('/get_available_dates')
def get_available_dates():
    doctor_id = request.args.get('doctor_id')
    result = availability_manager.get_available_dates(doctor_id)
    return jsonify({"available_dates": result})





@app.route('/')
def home():
    return redirect(url_for('index'))
@app.route('/index', methods=['GET', 'POST'])
def index():
    return render_template('index.html')




@app.route('/doctor-login', methods=['GET', 'POST'])
def doctor_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        success = doctor_manager.login(username, password)
        if success:
            return redirect(url_for('doctor_dashboard'))
        else:
            flash('Invalid username or password', 'error')

    return render_template('doctor-login.html')

@app.route('/patient-login', methods=['GET', 'POST'])
def patient_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        success = patient_manager.login(username, password)
        if success:
            return redirect(url_for('patient_dashboard'))
        else:
            flash('Invalid username or password', 'error')

    return render_template('patient-login.html')

@app.route('/register-patient', methods=['GET', 'POST'])
def register_patient():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        phone = request.form.get('phone')

        if not all([username, password, full_name, email, phone]):
            flash('All fields are required!', 'danger')
            return redirect(url_for('register_patient'))

        result = patient_manager.register(username, password, full_name, email, phone)
        if result['success']:
            flash(result['message'], 'success')
            return redirect(url_for('patient_login'))
        else:
            flash(result['message'], 'danger')

    return render_template('patient-register.html')

@app.route('/register-doctor', methods=['GET', 'POST'])
def register_doctor():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        phone = request.form.get('phone')

        if not all([username, password, full_name, email, phone]):
            flash('All fields are required!', 'danger')
            return redirect(url_for('register_doctor'))

        result = doctor_manager.register(username, password, full_name, email, phone)
        if result['success']:
            flash(result['message'], 'success')
            return redirect(url_for('doctor_login'))
        else:
            flash(result['message'], 'danger')

    return render_template('doctor-register.html')



''' Patient Dashboard Functionality'''


@app.route('/patient_dashboard')
def patient_dashboard():
    if 'username' not in session:
        return redirect(url_for('patient_login'))  # Redirect to login if not authenticated

    username = session['username']

    # Fetch patient data
    patient = patients_collection.find_one({"email": username})
    if not patient:
        return "Patient not found", 404

    # # Fetch upcoming appointments
    # appointments = mongo.db.appointments.find({"patient_id": patient['_id']}).sort("date")
    # doctors = doctors_collection.find()
    specializations = doctors_collection.distinct("specialization")
    appointments = list(mongo.db.appointments.find({"patient_id": patient['_id']}).sort("date"))
    
    # Create a dictionary for doctor IDs to names
    doctor_ids = {appointment['doctor_id'] for appointment in appointments}
    doctor_ids = [ObjectId(doc_id) for doc_id in doctor_ids]

    doctors = mongo.db.doctors.find({"_id": {"$in": list(doctor_ids)}})
    doctor_names = {str(doctor['_id']): doctor['name'] for doctor in doctors}  # Convert ObjectId to string

    # Update appointments with doctor's names
    for appointment in appointments:
        appointment['doctor_name'] = doctor_names.get(str(appointment['doctor_id']), 'Unknown')
        appointment['_id_str'] = str(appointment['_id'])[:6]
    return render_template('patient-dashboard.html', patient=patient, appointments=appointments, doctors=doctors, specializations=specializations)

@app.route('/booked_appointment', methods=['POST'])
def book_appointment():
    if 'username' not in session:
        return redirect(url_for('patient_login'))  # Redirect to login if not authenticated

    username = session['username']
    doctor_id = request.form.get('doctor_id')
    appointment_date = request.form.get('appointment_date')
    time_slot = request.form.get('time_slot')
    reason = request.form.get('reason')

    result = patient_manager.book_appointment(username, doctor_id, appointment_date, time_slot, reason)
    if "error" in result:
        flash(result["error"], "danger")
        return redirect(url_for('patient_dashboard'))
    else:
        flash(result["message"], "success")
        return redirect(url_for('patient_dashboard'))
    
    
@app.route('/booked_appointments')
def manage_appointments():
    if 'username' not in session:
        return redirect(url_for('patient_login'))  # Redirect to login if not authenticated

    username = session['username']

    # Fetch patient data
    patient = patients_collection.find_one({"email": username})
    if not patient:
        return "Patient not found", 404

    # Fetch all appointments for the patient
    appointments = mongo.db.appointments.find({"patient_id": patient['_id']}).sort("date")
    appointments = list(mongo.db.appointments.find({"patient_id": patient['_id']}).sort("date"))
    
    # Create a dictionary for doctor IDs to names
    doctor_ids = {appointment['doctor_id'] for appointment in appointments}
    doctor_ids = [ObjectId(doc_id) for doc_id in doctor_ids]

    doctors = mongo.db.doctors.find({"_id": {"$in": list(doctor_ids)}})
    doctor_names = {str(doctor['_id']): doctor['name'] for doctor in doctors}  # Convert ObjectId to string

    # Update appointments with doctor's names
    for appointment in appointments:
        appointment['doctor_name'] = doctor_names.get(str(appointment['doctor_id']), 'Unknown')
        appointment['_id_str'] = str(appointment['_id'])[:6]
    return render_template('booked_appointments.html', appointments=appointments)

@app.route('/reschedule_appointment', methods=['POST'])

def reschedule_appointment():
    appointment_id = request.form.get('appointment_id')
    doctor_id = request.form.get('doctor_id')
    new_date = request.form.get('new_date')
    new_time_slot = request.form.get('new_time_slot')

    result = patient_manager.reschedule_appointment(appointment_id, doctor_id, new_date, new_time_slot)
    if "error" in result:
        flash(result["error"], "danger")
    else:
        flash(result["message"], "success")

    return redirect(url_for('manage_appointments'))

@app.route('/cancel_appointment', methods=['POST'])
def cancel_appointment():
    appointment_id = request.form.get('appointment_id')

    result = patient_manager.cancel_appointment(appointment_id)
    if "error" in result:
        flash(result["error"], "danger")
    else:
        flash(result["message"], "success")

    return redirect(url_for('manage_appointments'))



''' Doctor DashBoard Functionality'''



@app.route('/doctor-dashboard')
def doctor_dashboard():
    if 'username' not in session:
        return redirect(url_for('doctor_login'))  # Redirect to login if not authenticated

    username = session['username']

    # Fetch doctor data
    doctor = doctors_collection.find_one({"email": username})
    if not doctor:
        return "Doctor not found", 404

    # Fetch upcoming appointments for the doctor
    appointments = mongo.db.appointments.find({"doctor_id": doctor['_id']}).sort("date")
    appointments = list(mongo.db.appointments.find({"doctor_id": doctor['_id']}).sort("date"))
    doctor_name = doctor.get('name', 'Doctor')
    # Extract patient_ids from appointments
    patient_ids = {appointment['patient_id'] for appointment in appointments}
    
    # Ensure patient_ids are in ObjectId format
    patient_ids = [ObjectId(pat_id) for pat_id in patient_ids]
    
    # Fetch patients
    patients = mongo.db.patients.find({"_id": {"$in": patient_ids}})
    
    # Create a dictionary for patient IDs to names
    patient_names = {str(patient['_id']): patient['name'] for patient in patients}  # Convert ObjectId to string
    print("Appointments:", appointments)
    print("Patient IDs:", patient_ids)
    print("Patient Names:", patient_names)

    # Update appointments with patient's names and simplified appointment IDs
    for appointment in appointments:
        # Convert ObjectId to string and slice
        appointment['appointment_id'] = ObjectId(appointment['_id'])  # Full ObjectId as a string
        appointment['patient_name'] = patient_names.get(str(appointment['patient_id']), 'Unknown')
        appointment['appointment_id_str'] = str(appointment['_id'])[:6] 
        print('HERE IS APPOINTMENT ID: ',appointment['appointment_id'])
        print(type(appointment['appointment_id']))
    return render_template('doctor-dashboard.html', doctor=doctor, doctor_name= doctor_name, appointments=appointments)

@app.route('/set_working_hours', methods=['POST'])
def set_working_hours():
    if 'username' not in session:
        return redirect(url_for('doctor_login'))  # Redirect if not authenticated

    username = session['username']
    days = request.form.getlist('days')
    start_time_str = request.form.get('start_time')
    end_time_str = request.form.get('end_time')

    # Call the method from the Doctor class
    result, status_code = doctor_manager.set_working_hours(username, days, start_time_str, end_time_str)

    if status_code == 200:
        flash(result["success"], 'success')
    else:
        flash(result["error"], 'danger')

    return redirect(url_for('doctor_dashboard'))

@app.route('/logout', methods=['POST', 'GET'])
def logout():
    # Clear all session data
    session.clear()
    # Redirect to the login page
    return redirect(url_for('patient_login'))

@app.route('/doctor_logout', methods=['GET'])
def doctor_logout():
    # Clear the session
    session.clear()
    # Redirect to the doctor login page
    return redirect(url_for('doctor_login'))  # Replace 'doctor_login' with your actual login route for doctors

if __name__ == '__main__':
    app.run(debug=True)
