from flask import Flask
from flask_pymongo import PyMongo
from bson.objectid import ObjectId  # Required for creating ObjectIds
import random
from datetime import datetime, timedelta
import bcrypt

app = Flask(__name__)

# MongoDB connection with Flask-PyMongo
app.config["MONGO_URI"] = "mongodb://localhost:27017/Appointment"  # Replace 'your_database' with the actual name of your database
mongo = PyMongo(app)

# Helper function to generate a random date
def generate_random_date(start_date, end_date):
    delta = end_date - start_date
    random_days = random.randint(0, delta.days)
    return start_date + timedelta(days=random_days)

with app.app_context():
    # 1. Insert 20 dummy doctors
    doctors = []
    for i in range(1, 21):
        doctor = {
            "name": f"Doctor {i}",
            "specialization": random.choice(["Cardiology", "Dermatology", "Pediatrics", "Orthopedics"]),
            "email": f"doctor{i}@example.com",
            "phone": f"123-456-78{i:02d}",
            "appointments": [],
            "password": bcrypt.hashpw(f"password{i}".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        }
        doctors.append(doctor)

    mongo.db.doctors.insert_many(doctors)

    # 2. Insert 20 dummy patients
    patients = []
    for i in range(1, 21):
        patient = {
            "name": f"Patient {i}",
            "email": f"patient{i}@example.com",
            "phone": f"987-654-32{i:02d}",
            "appointments": [],
            "password": bcrypt.hashpw(f"password{i}".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        }
        patients.append(patient)

    mongo.db.patients.insert_many(patients)

    # 3. Insert 20 dummy appointments
    appointments = []
    doctor_ids = [doctor["_id"] for doctor in mongo.db.doctors.find()]
    patient_ids = [patient["_id"] for patient in mongo.db.patients.find()]

    for i in range(1, 21):
        appointment = {
            "patient_id": random.choice(patient_ids),
            "doctor_id": random.choice(doctor_ids),
            "date": generate_random_date(datetime(2024, 9, 1), datetime(2024, 12, 31)).strftime('%Y-%m-%d'),
            "time": f"{random.randint(9, 17)}:00",  # Random time between 09:00 and 17:00
            "status": random.choice(["scheduled", "rescheduled", "canceled"]),
            "reason": random.choice(["Check-up", "Consultation", "Follow-up", "Urgent care"])
        }
        appointments.append(appointment)

    mongo.db.appointments.insert_many(appointments)

    # 4. Insert 20 dummy availabilities
    availabilities = []
    for doctor_id in doctor_ids:
        for i in range(1, 6):  # Create availability for 5 days for each doctor
            availability = {
                "doctor_id": doctor_id,
                "date": generate_random_date(datetime(2024, 9, 1), datetime(2024, 12, 31)).strftime('%Y-%m-%d'),
                "time_slots": ["09:00-09:30", "10:00-10:30", "11:00-11:30", "14:00-14:30", "15:00-15:30"],
                "is_available": [True, True, False, True, False]  # Randomize availability slots
            }
            availabilities.append(availability)

    mongo.db.availability.insert_many(availabilities)

print("Dummy data inserted successfully!")