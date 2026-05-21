import sqlite3
import json
import scheduler
from database import get_db_conn, init_and_seed_db

def run_diagnostic():
    print("=" * 70)
    print("           2CARE.AI - CLINICAL SCHEDULER DIAGNOSTIC LOGS            ")
    print("=" * 70)
    
    # 1. Initialize and Seed database if it's empty
    init_and_seed_db()
    
    conn = get_db_conn()
    cursor = conn.cursor()
    
    print("\n[Step 1/3] Seeded Doctors & Active Slots Grid:")
    cursor.execute("SELECT * FROM doctors")
    doctors = cursor.fetchall()
    for doc in doctors:
        # Check available slots on demo date 2026-06-01
        slots = scheduler.get_doctor_available_slots(conn, doc["id"], "2026-06-01")
        print(f" - {doc['name']} ({doc['specialty']}):")
        print(f"   * Working Hours: {doc['working_hours']}")
        print(f"   * Available Slots (June 1st): {', '.join(slots[:5])}...")
        
    print("\n[Step 2/3] Triggering Booking Conflict Resolution Check:")
    # We attempt to book Amit Patel (phone 9876543210) with Dr. Rajesh Kumar (ID 1)
    # on 2026-06-01 at 10:00 AM (which is pre-booked by seed database)
    patient_phone = "9876543210"
    target_doctor_id = 1
    target_date = "2026-06-01"
    target_time = "10:00"
    
    print(f" -> Attempting to book Dr. Rajesh Kumar at {target_time} on {target_date}...")
    try:
        scheduler.book_appointment_slot(conn, patient_phone, target_doctor_id, target_date, target_time)
        print(" [SUCCESS] Appointment booked successfully (No conflicts).")
    except scheduler.SchedulingException as e:
        print(f" [CONFLICT CAUGHT] Code: {e.code}")
        print(f"   * Error Message: \"{e.message}\"")
        print("   * Alternative Suggestions Computed by Engine:")
        for idx, alt in enumerate(e.alternatives, 1):
            print(f"     {idx}. [{alt['type'].upper()}] {alt['label']}")
            
    print("\n[Step 3/3] Printing All Active Scheduled Appointments:")
    cursor.execute("""
        SELECT a.id, p.name AS patient_name, d.name AS doctor_name, a.date, a.time, a.status 
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        JOIN doctors d ON a.doctor_id = d.id
        WHERE a.status != 'cancelled'
        ORDER BY a.date, a.time
    """)
    appointments = cursor.fetchall()
    for appt in appointments:
        print(f" - Appt #{appt['id']}: Patient '{appt['patient_name']}' with '{appt['doctor_name']}' on {appt['date']} @ {appt['time']} [{appt['status'].upper()}]")
        
    conn.close()
    print("\n" + "=" * 70)

if __name__ == "__main__":
    run_diagnostic()
