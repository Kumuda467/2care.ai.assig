import sqlite3
import os
import json

DB_FILE = "healthcare.db"

def get_db_conn():
    """Returns a sqlite3 connection with dictionary-like row access."""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_and_seed_db():
    """Initializes tables and seeds clinical data using native SQLite3."""
    print("Initializing native SQLite database...")
    
    conn = get_db_conn()
    cursor = conn.cursor()
    
    # 1. Create Tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS doctors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        specialty TEXT NOT NULL,
        languages TEXT NOT NULL,
        working_hours TEXT DEFAULT '09:00-17:00',
        max_appointments_per_day INTEGER DEFAULT 8
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        language_preference TEXT DEFAULT 'en',
        past_history TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        doctor_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        time TEXT NOT NULL,
        status TEXT DEFAULT 'scheduled',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (patient_id) REFERENCES patients(id),
        FOREIGN KEY (doctor_id) REFERENCES doctors(id)
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS session_memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT UNIQUE NOT NULL,
        patient_phone TEXT,
        chat_history TEXT DEFAULT '[]',
        active_intent TEXT DEFAULT 'none',
        temp_data TEXT DEFAULT '{}',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    
    # Check if doctors are already seeded
    cursor.execute("SELECT COUNT(*) FROM doctors")
    if cursor.fetchone()[0] > 0:
        print("Database already seeded.")
        conn.close()
        return

    print("Seeding clinical data...")
    
    # 2. Seed Doctors
    doctors_data = [
        ("Dr. Rajesh Kumar", "Pediatrics", "English, Hindi", "09:00-17:00", 8),
        ("Dr. Ananya Iyer", "General Medicine", "English, Hindi, Tamil", "09:00-17:00", 8),
        ("Dr. K. Subramanian", "Cardiology", "English, Tamil", "10:00-16:00", 6),
        ("Dr. Meera Sen", "Dermatology", "English, Hindi", "09:00-17:00", 8)
    ]
    cursor.executemany("""
    INSERT INTO doctors (name, specialty, languages, working_hours, max_appointments_per_day)
    VALUES (?, ?, ?, ?, ?)
    """, doctors_data)
    
    # 3. Seed Patients
    patients_data = [
        ("Amit Patel", "9876543210", "en", "Hypertension, takes Metformin 500mg daily. Last follow-up: March 2026. Prefers morning slots."),
        ("Suresh Kumar", "9123456789", "hi", "Chronic lower back pain. Takes Ibuprofen. Needs physiotherapy recommendations."),
        ("Priya Sundaram", "8765432109", "ta", "Type 2 Diabetes. HbA1c checked at 7.2. Last checked 1 month ago. Prefers Tamil speaking doctors."),
        ("Simran Kaur", "9999999999", "en", "No known chronic illnesses. Routine checkups. Prefers pediatrician for her infant.")
    ]
    cursor.executemany("""
    INSERT INTO patients (name, phone, language_preference, past_history)
    VALUES (?, ?, ?, ?)
    """, patients_data)
    
    conn.commit()
    
    # 4. Add initial conflicts (Dr. Rajesh booked on June 1st, Dr. Ananya booked on June 1st)
    cursor.execute("SELECT id FROM doctors WHERE name = 'Dr. Rajesh Kumar'")
    dr_rajesh_id = cursor.fetchone()[0]
    
    cursor.execute("SELECT id FROM doctors WHERE name = 'Dr. Ananya Iyer'")
    dr_ananya_id = cursor.fetchone()[0]
    
    cursor.execute("SELECT id FROM patients WHERE phone = '9876543210'")
    pat_amit_id = cursor.fetchone()[0]
    
    cursor.execute("SELECT id FROM patients WHERE phone = '9123456789'")
    pat_suresh_id = cursor.fetchone()[0]
    
    # Dr. Rajesh is booked at 10:00 AM on 2026-06-01
    cursor.execute("""
    INSERT INTO appointments (patient_id, doctor_id, date, time, status)
    VALUES (?, ?, '2026-06-01', '10:00', 'scheduled')
    """, (pat_amit_id, dr_rajesh_id))
    
    # Dr. Ananya is booked at 11:00 AM on 2026-06-01
    cursor.execute("""
    INSERT INTO appointments (patient_id, doctor_id, date, time, status)
    VALUES (?, ?, '2026-06-01', '11:00', 'scheduled')
    """, (pat_suresh_id, dr_ananya_id))
    
    # Dr. Ananya is booked at 10:00 AM on 2026-06-01 (Amit double booked)
    cursor.execute("""
    INSERT INTO appointments (patient_id, doctor_id, date, time, status)
    VALUES (?, ?, '2026-06-01', '10:00', 'scheduled')
    """, (pat_amit_id, dr_ananya_id))
    
    conn.commit()
    conn.close()
    print("Database seeding completed.")
