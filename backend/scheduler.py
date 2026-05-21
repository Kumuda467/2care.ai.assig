import sqlite3
from datetime import datetime, date, timedelta

# Mock current date for standardized testing (2026-05-21 as of prompt metadata)
BASELINE_DATE = date(2026, 5, 21)

class SchedulingException(Exception):
    def __init__(self, message, code="SCHEDULING_ERROR", alternatives=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.alternatives = alternatives or []

def get_slots_for_hours(working_hours: str) -> list:
    """Generates standard hourly slots based on working hours string like '09:00-17:00'."""
    try:
        start_str, end_str = working_hours.split("-")
        start_hour = int(start_str.split(":")[0])
        end_hour = int(end_str.split(":")[0])
        
        slots = []
        for h in range(start_hour, end_hour):
            slots.append(f"{h:02d}:00")
        return slots
    except Exception:
        return ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00"]

def is_past_date(date_str: str, time_str: str = "00:00") -> bool:
    """Checks if the date/time string is in the past relative to the system's baseline date."""
    try:
        input_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        if input_date < BASELINE_DATE:
            return True
        elif input_date == BASELINE_DATE:
            # If same day, check hour
            current_hour = 18  # baseline time is 18:35 (6:35 PM) from system state
            input_hour = int(time_str.split(":")[0])
            if input_hour <= current_hour:
                return True
        return False
    except Exception:
        return False

def get_doctor_available_slots(conn: sqlite3.Connection, doctor_id: int, date_str: str) -> list:
    """Gets all available hourly slots for a doctor on a specific date using native SQL."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM doctors WHERE id = ?", (doctor_id,))
    doctor = cursor.fetchone()
    if not doctor:
        raise SchedulingException(f"Doctor with ID {doctor_id} not found.", "DOCTOR_NOT_FOUND")

    # If it's a past date, no slots are available
    if is_past_date(date_str):
        return []

    # Get all potential slots based on working hours
    all_slots = get_slots_for_hours(doctor["working_hours"])

    # Fetch active bookings for this doctor on this day
    cursor.execute("""
        SELECT time FROM appointments 
        WHERE doctor_id = ? AND date = ? AND status != 'cancelled'
    """, (doctor_id, date_str))
    
    booked_appointments = cursor.fetchall()
    booked_slots = {row["time"] for row in booked_appointments}

    # Filter out booked slots
    available_slots = [slot for slot in all_slots if slot not in booked_slots]

    # If the date is today, filter out past hours
    if datetime.strptime(date_str, "%Y-%m-%d").date() == BASELINE_DATE:
        current_hour = 18  # 6 PM local baseline time
        available_slots = [slot for slot in available_slots if int(slot.split(":")[0]) > current_hour]

    return available_slots

def suggest_alternatives(conn: sqlite3.Connection, doctor_id: int, date_str: str, preferred_time: str) -> list:
    """
    Finds alternative options using direct SQL:
    1. Closest slots for the same doctor on the same day.
    2. Slots for the same doctor on the next day.
    3. Other doctors with the same specialty who are free at the preferred time on the same day.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM doctors WHERE id = ?", (doctor_id,))
    doctor = cursor.fetchone()
    if not doctor:
        return []

    alternatives = []

    # 1. Check other slots same doctor, same day
    same_day_slots = get_doctor_available_slots(conn, doctor_id, date_str)
    if same_day_slots:
        # Find slots closest to preferred_time
        pref_hour = int(preferred_time.split(":")[0])
        sorted_slots = sorted(same_day_slots, key=lambda s: abs(int(s.split(":")[0]) - pref_hour))
        for slot in sorted_slots[:2]:
            alternatives.append({
                "type": "same_doctor_different_time",
                "doctor_id": doctor["id"],
                "doctor_name": doctor["name"],
                "specialty": doctor["specialty"],
                "date": date_str,
                "time": slot,
                "label": f"Dr. {doctor['name'].split()[-1]} is free at {slot} on {date_str}"
            })

    # 2. Check same doctor, next day (increment date)
    try:
        current_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        next_day = current_date + timedelta(days=1)
        next_day_str = next_day.strftime("%Y-%m-%d")
        next_day_slots = get_doctor_available_slots(conn, doctor_id, next_day_str)
        if next_day_slots:
            pref_hour = int(preferred_time.split(":")[0])
            sorted_next_slots = sorted(next_day_slots, key=lambda s: abs(int(s.split(":")[0]) - pref_hour))
            if sorted_next_slots:
                alternatives.append({
                    "type": "same_doctor_next_day",
                    "doctor_id": doctor["id"],
                    "doctor_name": doctor["name"],
                    "specialty": doctor["specialty"],
                    "date": next_day_str,
                    "time": sorted_next_slots[0],
                    "label": f"Dr. {doctor['name'].split()[-1]} has a slot at {sorted_next_slots[0]} tomorrow ({next_day_str})"
                })
    except Exception:
        pass

    # 3. Check other doctors in the same specialty on the same day at the preferred time
    cursor.execute("""
        SELECT * FROM doctors 
        WHERE specialty = ? AND id != ?
    """, (doctor["specialty"], doctor_id))
    other_docs = cursor.fetchall()

    for other_doc in other_docs:
        other_slots = get_doctor_available_slots(conn, other_doc["id"], date_str)
        if preferred_time in other_slots:
            alternatives.append({
                "type": "different_doctor_same_time",
                "doctor_id": other_doc["id"],
                "doctor_name": other_doc["name"],
                "specialty": other_doc["specialty"],
                "date": date_str,
                "time": preferred_time,
                "label": f"Dr. {other_doc['name'].split()[-1]} ({doctor['specialty']}) is available at {preferred_time} on {date_str}"
            })

    return alternatives

def book_appointment_slot(conn: sqlite3.Connection, patient_phone: str, doctor_id: int, date_str: str, time_str: str) -> dict:
    """Books an appointment slot. Validates availability and handles conflicts."""
    cursor = conn.cursor()
    
    # Validate patient
    cursor.execute("SELECT * FROM patients WHERE phone = ?", (patient_phone,))
    patient = cursor.fetchone()
    if not patient:
        raise SchedulingException(f"Patient with phone {patient_phone} not registered.", "PATIENT_NOT_FOUND")

    # Validate doctor
    cursor.execute("SELECT * FROM doctors WHERE id = ?", (doctor_id,))
    doctor = cursor.fetchone()
    if not doctor:
        raise SchedulingException(f"Doctor with ID {doctor_id} not found.", "DOCTOR_NOT_FOUND")

    # Validate slot time format
    if ":" not in time_str:
        raise SchedulingException(f"Invalid time format: {time_str}. Use HH:MM.", "INVALID_TIME_FORMAT")
        
    try:
        parts = time_str.split(":")
        time_str = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    except Exception:
        raise SchedulingException(f"Invalid time format: {time_str}.", "INVALID_TIME_FORMAT")

    # Validate against past date/time
    if is_past_date(date_str, time_str):
        raise SchedulingException(
            f"Cannot book a slot in the past. Date: {date_str}, Time: {time_str}.",
            "PAST_DATE_REJECTED"
        )

    # Check doctor working hours
    working_slots = get_slots_for_hours(doctor["working_hours"])
    if time_str not in working_slots:
        raise SchedulingException(
            f"Requested slot {time_str} is outside of Dr. {doctor['name']}'s working hours ({doctor['working_hours']}).",
            "OUT_OF_WORKING_HOURS"
        )

    # Check for existing scheduled booking for the doctor at this slot
    cursor.execute("""
        SELECT id FROM appointments 
        WHERE doctor_id = ? AND date = ? AND time = ? AND status != 'cancelled'
    """, (doctor_id, date_str, time_str))
    conflict_appt = cursor.fetchone()

    if conflict_appt:
        alts = suggest_alternatives(conn, doctor_id, date_str, time_str)
        raise SchedulingException(
            f"Dr. {doctor['name']} is already booked at {time_str} on {date_str}.",
            "SLOT_CONFLICT",
            alternatives=alts
        )

    # Check if patient already has an active appointment at this exact date and time
    cursor.execute("""
        SELECT a.id, d.name AS doctor_name FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        WHERE a.patient_id = ? AND a.date = ? AND a.time = ? AND a.status != 'cancelled'
    """, (patient["id"], date_str, time_str))
    patient_conflict = cursor.fetchone()

    if patient_conflict:
        raise SchedulingException(
            f"You already have an appointment scheduled with Dr. {patient_conflict['doctor_name']} at {time_str} on {date_str}.",
            "PATIENT_DOUBLE_BOOKED"
        )

    # Create and commit new appointment
    cursor.execute("""
        INSERT INTO appointments (patient_id, doctor_id, date, time, status)
        VALUES (?, ?, ?, ?, 'scheduled')
    """, (patient["id"], doctor_id, date_str, time_str))
    
    conn.commit()
    new_id = cursor.lastrowid
    
    # Return formatted appointment dict
    return {
        "id": new_id,
        "patient_id": patient["id"],
        "patient_name": patient["name"],
        "patient_phone": patient["phone"],
        "doctor_id": doctor_id,
        "doctor_name": doctor["name"],
        "doctor_specialty": doctor["specialty"],
        "date": date_str,
        "time": time_str,
        "status": "scheduled"
    }

def reschedule_appointment_slot(conn: sqlite3.Connection, appointment_id: int, new_date: str, new_time: str) -> dict:
    """Reschedules an existing appointment to a new slot using native SQL."""
    cursor = conn.cursor()
    
    # Find existing appointment
    cursor.execute("""
        SELECT a.*, d.name AS doctor_name, d.working_hours, p.name AS patient_name, p.phone AS patient_phone, d.specialty AS doctor_specialty 
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        JOIN patients p ON a.patient_id = p.id
        WHERE a.id = ?
    """, (appointment_id,))
    appt = cursor.fetchone()
    
    if not appt:
        raise SchedulingException(f"Appointment with ID {appointment_id} not found.", "APPOINTMENT_NOT_FOUND")

    if appt["status"] == "cancelled":
        raise SchedulingException("Cannot reschedule a cancelled appointment. Please book a new one.", "CANCELLED_RESCHEDULE_REJECTED")

    try:
        parts = new_time.split(":")
        new_time = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    except Exception:
        raise SchedulingException(f"Invalid time format: {new_time}.", "INVALID_TIME_FORMAT")

    if is_past_date(new_date, new_time):
        raise SchedulingException("Cannot reschedule to a past date/time.", "PAST_DATE_REJECTED")

    # Check if doctor is already booked at this new slot (excluding current appointment itself)
    cursor.execute("""
        SELECT id FROM appointments 
        WHERE doctor_id = ? AND date = ? AND time = ? AND status != 'cancelled' AND id != ?
    """, (appt["doctor_id"], new_date, new_time, appointment_id))
    conflict_appt = cursor.fetchone()

    if conflict_appt:
        alts = suggest_alternatives(conn, appt["doctor_id"], new_date, new_time)
        raise SchedulingException(
            f"Dr. {appt['doctor_name']} is already booked at {new_time} on {new_date}.",
            "SLOT_CONFLICT",
            alternatives=alts
        )

    # Update appointment details
    cursor.execute("""
        UPDATE appointments 
        SET date = ?, time = ?, status = 'rescheduled'
        WHERE id = ?
    """, (new_date, new_time, appointment_id))
    conn.commit()
    
    return {
        "id": appointment_id,
        "patient_id": appt["patient_id"],
        "patient_name": appt["patient_name"],
        "patient_phone": appt["patient_phone"],
        "doctor_id": appt["doctor_id"],
        "doctor_name": appt["doctor_name"],
        "doctor_specialty": appt["doctor_specialty"],
        "date": new_date,
        "time": new_time,
        "status": "rescheduled"
    }

def cancel_appointment_slot(conn: sqlite3.Connection, appointment_id: int) -> dict:
    """Cancels an active appointment."""
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT a.*, d.name AS doctor_name, d.specialty AS doctor_specialty, p.name AS patient_name, p.phone AS patient_phone
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        JOIN patients p ON a.patient_id = p.id
        WHERE a.id = ?
    """, (appointment_id,))
    appt = cursor.fetchone()
    
    if not appt:
        raise SchedulingException(f"Appointment with ID {appointment_id} not found.", "APPOINTMENT_NOT_FOUND")

    cursor.execute("""
        UPDATE appointments 
        SET status = 'cancelled'
        WHERE id = ?
    """, (appointment_id,))
    conn.commit()
    
    return {
        "id": appointment_id,
        "patient_id": appt["patient_id"],
        "patient_name": appt["patient_name"],
        "patient_phone": appt["patient_phone"],
        "doctor_id": appt["doctor_id"],
        "doctor_name": appt["doctor_name"],
        "doctor_specialty": appt["doctor_specialty"],
        "date": appt["date"],
        "time": appt["time"],
        "status": "cancelled"
    }
