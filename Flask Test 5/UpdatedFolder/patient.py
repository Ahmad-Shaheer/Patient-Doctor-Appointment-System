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
app.config["MONGO_URI"] = "mongodb://localhost:27017/Appointment"  # Use your actual database name
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


''' Scheduler'''


# # Scheduler for sending emails
# scheduler = BackgroundScheduler(timezone='UTC')
# scheduler.start()


# # Utility function to send email
# def send_reminder_email(appointment):
#     doctor = doctors_collection.find_one({"_id": ObjectId(appointment['doctor_id'])})
#     patient = patients_collection.find_one({"_id": ObjectId(appointment['patient_id'])})

#     if not doctor or not patient:
#         print(f"Doctor or patient not found for appointment ID: {appointment['_id']}")
#         return

#     doctor_email = doctor.get('email')
#     patient_email = patient.get('email')

#     if not doctor_email or not patient_email:
#         print(f"Missing email address for doctor or patient for appointment ID: {appointment['_id']}")
#         return

#     subject = "Appointment Reminder"
#     body = f"Dear {doctor['name']} and {patient['full_name']},\n\nThis is a reminder for your upcoming appointment at {appointment['time']} on {appointment['date']}."

#     msg = Message(subject, recipients=[doctor_email, patient_email])
#     msg.body = body

#     try:
#         mail.send(msg)
#         print(f"Reminder email sent successfully for appointment ID: {appointment['_id']}")
#     except Exception as e:
#         print(f"Failed to send reminder email: {e}")

# # Schedule email reminders for all future appointments
# def schedule_email_reminders():
#     now = datetime.now(pytz.UTC)
#     upcoming_appointments = mongo.db.appointments.find({"date": {"$gte": now.strftime('%Y-%m-%d')}})

#     for appointment in upcoming_appointments:
#         try:
#             appointment_datetime = datetime.strptime(f"{appointment['date']} {appointment['time']}", '%Y-%m-%d %H:%M')
#             appointment_datetime = pytz.UTC.localize(appointment_datetime)
#             reminder_time = appointment_datetime - timedelta(hours=1)

#             if reminder_time > now:
#                 scheduler.add_job(send_reminder_email, 'date', run_date=reminder_time, args=[appointment])
#                 print(f"Scheduled email reminder for appointment ID: {appointment['_id']} at {reminder_time}")

#         except ValueError as e:
#             print(f"Error parsing datetime for appointment ID: {appointment['_id']} - {e}")

# # Run scheduler to update reminders whenever the application starts
# schedule_email_reminders()








''' Helping Functions'''
@app.route('/get_doctors', methods=['GET'])
def get_doctors():
    specialization = request.args.get('specialization')
    if not specialization:
        return jsonify([])  # Return an empty list if no specialization is provided

    # Query the database to find doctors with the specified specialization
    doctors = mongo.db.doctors.find({"specialization": specialization})
    doctor_list = []
    for doctor in doctors:
        doctor_list.append({
            "_id": str(doctor["_id"]),
            "name": doctor["name"]
        })

    return jsonify(doctor_list)

@app.route('/get_available_timeslots', methods=['GET'])
def get_available_timeslots():
    doctor_id = request.args.get('doctor_id')
    date = request.args.get('date')
    print(doctor_id)
    print(date)
    if not doctor_id or not date:
        return jsonify([])  # Return an empty list if no doctor_id or date is provided

    # Query the database to find availability for the specified doctor and date
    
    availability = mongo.db.availability.find_one({"doctor_id": ObjectId(doctor_id), "date": date})
    print(availability)

    if not availability:
        return jsonify([])  # Return an empty list if no availability is found
    available_slots = [
        time_slot for time_slot, is_available in zip(availability["time_slots"], availability["is_available"])
        if is_available
    ]

    return jsonify(available_slots)

# @app.route('/get_availability_data')
# def get_availability_data():
#     doctor_id = request.args.get('doctor_id')
#     available_dates = mongo.db.availability.find_one({"doctor_id": ObjectId(doctor_id)})['available_dates']
#     return jsonify(available_dates=available_dates)
@app.route('/get_available_dates')
def get_available_dates():
    doctor_id = request.args.get('doctor_id')

    # Fetch available dates from your database
    available_dates_cursor = mongo.db.availability.find({"doctor_id": ObjectId(doctor_id)})
    available_dates = list(available_dates_cursor)  # Convert cursor to list

    # Create a list of available dates in YYYY-MM-DD format
    dates = [availability['date'] for availability in available_dates]

    # Print the raw data to the terminal for debugging
    print("Raw available dates:", dates)

    # Remove duplicates by converting to a set, then back to a list
    unique_dates = list(set(dates))

    # Sort dates in increasing order and limit to the first 14 dates
    sorted_dates = sorted(unique_dates)[:14]

    # Print the sorted dates to the terminal for debugging
    print("Sorted available dates (first 14):", sorted_dates)

    # Send response
    return jsonify({"available_dates": sorted_dates})

''' Complete Login and Register Functionality'''



@app.route('/')
def home():
    return redirect(url_for('index'))
@app.route('/index', methods=['GET', 'POST'])
def index():
    return render_template('index.html')

@app.route('/doctor-login', methods=['GET', 'POST'])
def doctor_login():
    if request.method == 'POST':
        # Get form data
        username = request.form['username']
        password = request.form['password']

        # Fetch doctor from the 'doctors' collection
        user = mongo.db.doctors.find_one({'email': username})

        if user:
            # Compare plain text password
            if password == user['password']:
                session['username'] = username
                return redirect(url_for('doctor_dashboard'))
            else:
                flash('Invalid username or password', 'error')
        else:
            flash('Doctor not found', 'error')

    return render_template('doctor-login.html')

@app.route('/patient-login', methods=['GET', 'POST'])
def patient_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']  # Password should be hashed in production

        # Validate user credentials
        user = mongo.db.patients.find_one({"email": username})

        if user and user['password'] == password:  # In production, use a hashed password check
            session['username'] = username
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

        # Check if any form field is missing
        if not all([username, password, full_name, email, phone]):
            flash('All fields are required!', 'danger')
            return redirect(url_for('register_patient_form'))

        # Check if the username already exists
        if patients_collection.find_one({'username': username}):
            flash('Username already exists!', 'danger')
            return redirect(url_for('register_patient_form'))

        # Insert new patient
        patients_collection.insert_one({
            'username': username,
            'password': password,  # Password is stored in plain text
            'full_name': full_name,
            'email': email,
            'phone': phone
        })

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('patient_login'))

    return render_template('patient-register.html')

@app.route('/register-doctor', methods=['GET', 'POST'])
def register_doctor():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        phone = request.form.get('phone')

        # Check if any form field is missing
        if not all([username, password, full_name, email, phone]):
            flash('All fields are required!', 'danger')
            return redirect(url_for('register_doctor'))

        # Check if the username already exists
        if doctors_collection.find_one({'username': username}):
            flash('Username already exists!', 'danger')
            return redirect(url_for('register_doctor'))

        # Insert new doctor
        doctors_collection.insert_one({
            'username': username,
            'password': password,  # Password is stored in plain text
            'full_name': full_name,
            'email': email,
            'phone': phone
        })

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('doctor_login'))

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
    doctor_id_obj = ObjectId(doctor_id)
    # Fetch time slots for the specific doctor and date
    availability_doc = mongo.db.availability.find_one({
    "doctor_id": ObjectId(doctor_id),
    "date": appointment_date
    })
    
    time_slots = availability_doc.get("time_slots", [])  # Adjust the field name if different
    time_slot_index = time_slots.index(time_slot)

    # Fetch patient data
    patient = patients_collection.find_one({"email": username})
    if not patient:
        return "Patient not found", 404
    
    # Create new appointment document
    new_appointment = {
        "patient_id": patient['_id'],
        "doctor_id": doctor_id_obj,
        "date": appointment_date,  # Extract date part
        "time": time_slot,  # Extract time part
        "status": "Scheduled",
        "reason": reason  # You can set this to any default value or retrieve from form
    }

    # Insert new appointment into the database
    mongo.db.appointments.insert_one(new_appointment)
    
    mongo.db.availability.update_one(
    {"doctor_id": ObjectId(doctor_id), "date": appointment_date},
    {"$set": {f"is_available.{time_slot_index}": False}}
    )
    # Redirect to patient dashboard
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

    if not appointment_id or not doctor_id or not new_date or not new_time_slot:
        return jsonify({"error": "Missing required fields."}), 400

    # Find the existing appointment
    appointment = mongo.db.appointments.find_one({"_id": ObjectId(appointment_id)})
    if not appointment:
        return jsonify({"error": "Appointment not found."}), 404

    old_date = appointment['date']
    old_time_slot = appointment['time']

    # Update the appointment with new date and time
    update_result = mongo.db.appointments.update_one(
        {"_id": ObjectId(appointment_id)},
        {"$set": {"date": new_date, "time": new_time_slot}}
    )

    if update_result.matched_count == 0:
        return jsonify({"error": "Failed to update the appointment."}), 404

    # Mark the old time slot as available
    mongo.db.availability.update_one(
        {"doctor_id": ObjectId(doctor_id), "date": old_date},
        {"$set": {"is_available.$[slot]": True}},
        array_filters=[{"slot": old_time_slot}]
    )

    # Mark the new time slot as unavailable
    mongo.db.availability.update_one(
        {"doctor_id": ObjectId(doctor_id), "date": new_date},
        {"$set": {"is_available.$[slot]": False}},
        array_filters=[{"slot": new_time_slot}]
    )

    return redirect(url_for('manage_appointments'))

@app.route('/cancel_appointment', methods=['POST'])
def cancel_appointment():
    appointment_id = request.form.get('appointment_id')
    print(' appointment id:', appointment_id)
    print('Appointment ID')
    if not appointment_id:
        return jsonify({"error": "Invalid appointment ID."}), 400

    # Find and delete the appointment
    appointment = mongo.db.appointments.find_one({"_id": ObjectId(appointment_id)})
    if not appointment:
        return jsonify({"error": "Appointment not found."}), 404

    doctor_id = appointment['doctor_id']
    old_date_str = appointment['date']
    old_time_slot = appointment['time']

    result = mongo.db.appointments.delete_one({"_id": ObjectId(appointment_id)})
    if result.deleted_count == 0:
        return jsonify({"error": "Failed to cancel the appointment."}), 404

    # Mark the old time slot as available
    mongo.db.availability.update_one(
        {"doctor_id": ObjectId(doctor_id), "date": old_date_str},
        {"$set": {"is_available.$[slot]": True}},
        array_filters=[{"slot": old_time_slot}]
    )

    # Return success response
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
        appointment['patient_name'] = patient_names.get(str(appointment['patient_id']), 'Unknown')
        appointment['appointment_id_str'] = str(appointment['_id'])[:6] 
        
    return render_template('doctor-dashboard.html', doctor=doctor, doctor_name= doctor_name, appointments=appointments)

# @app.route('/set_working_hours', methods=['POST'])
# def set_working_hours():
#     if 'username' not in session:
#         return redirect(url_for('doctor_login'))  # Redirect to login if not authenticated

#     username = session['username']
#     doctor = doctors_collection.find_one({"email": username})

#     if not doctor:
#         return "Doctor not found", 404

#     working_days = request.form['working_days']
#     working_hours = request.form['working_hours']

#     # Update doctor's working hours
#     doctors_collection.update_one(
#         {"_id": doctor['_id']},
#         {"$set": {"working_days": working_days, "working_hours": working_hours}}
#     )

#     flash('Working hours updated successfully!', 'success')
#     return redirect(url_for('doctor_dashboard'))


@app.route('/set_working_hours', methods=['POST'])
def set_working_hours():
    def set_working_hours():
        if 'username' not in session:
            return redirect(url_for('doctor_login'))  # Redirect if not authenticated

    username = session['username']

    # Fetch doctor ID using the username
    doctor = mongo.db.doctors.find_one({"email": username})
    if not doctor:
        return "Doctor not found", 404

    doctor_id = str(doctor['_id'])

    days = request.form.getlist('days')
    start_time_str = request.form.get('start_time')
    end_time_str = request.form.get('end_time')

    if not doctor_id or not days or not start_time_str or not end_time_str:
        return "Missing data", 400

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
            result = mongo.db.availability.update_one(
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
