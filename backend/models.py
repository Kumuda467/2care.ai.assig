# 2care.ai - SQLite Database Schemas Reference
# Native SQL is managed transactionally in database.py and scheduler.py.

"""
DOCTORS SCHEMA
==============
CREATE TABLE doctors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    specialty TEXT NOT NULL,
    languages TEXT NOT NULL,
    working_hours TEXT DEFAULT '09:00-17:00',
    max_appointments_per_day INTEGER DEFAULT 8
);

PATIENTS SCHEMA
===============
CREATE TABLE patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    language_preference TEXT DEFAULT 'en',
    past_history TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

APPOINTMENTS SCHEMA
===================
CREATE TABLE appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    doctor_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    time TEXT NOT NULL,
    status TEXT DEFAULT 'scheduled',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id),
    FOREIGN KEY (doctor_id) REFERENCES doctors(id)
);

SESSION MEMORY SCHEMA
=====================
CREATE TABLE session_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    patient_phone TEXT,
    chat_history TEXT DEFAULT '[]',
    active_intent TEXT DEFAULT 'none',
    temp_data TEXT DEFAULT '{}',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""
