import os
import time
import json
import uuid
import sqlite3
from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from database import init_and_seed_db, get_db_conn
from agent import run_agent_turn

load_dotenv()

app = FastAPI(title="2care.ai Voice AI Agent API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active WebSockets connection manager (for real-time dashboard updates)
class ConnectionManager:
    def __init__(self):
        self.active_connections = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass

manager = ConnectionManager()

# Seed database on startup
@app.on_event("startup")
def startup_event():
    init_and_seed_db()

# --- REST ENDPOINTS ---

@app.get("/api/doctors")
def get_doctors():
    conn = get_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM doctors")
        doctors = cursor.fetchall()
        
        result = []
        demo_date = "2026-06-01"
        for doc in doctors:
            d_dict = dict(doc)
            d_dict["languages"] = [lang.strip() for lang in doc["languages"].split(",") if lang.strip()]
            try:
                from scheduler import get_doctor_available_slots
                d_dict["available_slots_june_1st"] = get_doctor_available_slots(conn, doc["id"], demo_date)
            except Exception:
                d_dict["available_slots_june_1st"] = []
            result.append(d_dict)
        return result
    finally:
        conn.close()

@app.get("/api/patients")
def get_patients():
    conn = get_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM patients")
        patients = cursor.fetchall()
        return [dict(pat) for pat in patients]
    finally:
        conn.close()

@app.get("/api/appointments")
def get_appointments():
    conn = get_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT a.*, p.name AS patient_name, p.phone AS patient_phone, d.name AS doctor_name, d.specialty AS doctor_specialty 
            FROM appointments a
            JOIN patients p ON a.patient_id = p.id
            JOIN doctors d ON a.doctor_id = d.id
            WHERE a.status != 'cancelled'
            ORDER BY a.date, a.time
        """)
        appointments = cursor.fetchall()
        return [dict(appt) for appt in appointments]
    finally:
        conn.close()

# Models for campaigns
class OutboundTrigger(BaseModel):
    patient_phone: str
    campaign_name: str
    doctor_id: int

@app.post("/api/campaigns/trigger")
async def trigger_campaign(trigger: OutboundTrigger):
    """Triggers an outbound call event that will be pushed to the browser frontend."""
    conn = get_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM patients WHERE phone = ?", (trigger.patient_phone,))
        patient = cursor.fetchone()
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")
        
        cursor.execute("SELECT * FROM doctors WHERE id = ?", (trigger.doctor_id,))
        doctor = cursor.fetchone()
        if not doctor:
            raise HTTPException(status_code=404, detail="Doctor not found")
            
        call_id = str(uuid.uuid4())
        
        # Broadcast an incoming call event to all connected dashboard pages
        event = {
            "event": "incoming_call",
            "call_id": call_id,
            "phone": patient["phone"],
            "patient_name": patient["name"],
            "campaign_name": trigger.campaign_name,
            "doctor_id": doctor["id"],
            "doctor_name": doctor["name"],
            "language_preference": patient["language_preference"] or "en"
        }
        
        await manager.broadcast(json.dumps(event))
        return {"status": "triggered", "call_id": call_id, "event": event}
    finally:
        conn.close()

# --- REAL-TIME WEBSOCKET AGENT PROTOCOL ---

@app.websocket("/ws/chat")
async def websocket_chat_endpoint(websocket: WebSocket):
    """
    Handles real-time speech dialogue. 
    Accepts text representing speech recognition end-pointings, 
    executes Agent Tool calling pipelines, and sends back speech responses and latencies.
    """
    await websocket.accept()
    session_id = str(uuid.uuid4())
    print(f"WS Client connected. Session ID: {session_id}")
    
    conn = get_db_conn()
    cursor = conn.cursor()
    
    try:
        while True:
            # Receive speech transcription text or outbound call commands
            data_str = await websocket.receive_text()
            data = json.loads(data_str)
            
            # Start strict latency timing (End-to-End Budget < 450ms)
            start_time = time.perf_counter()
            
            # Extract inputs
            user_text = data.get("text", "")
            patient_phone = data.get("phone", "9876543210")
            is_outbound_init = data.get("is_outbound_init", False)
            campaign_context = data.get("campaign_name", "")
            doctor_id = data.get("doctor_id", None)
            
            # 1. Handle Outbound Call Init (Proactive Agent Prompting)
            if is_outbound_init:
                cursor.execute("SELECT * FROM patients WHERE phone = ?", (patient_phone,))
                patient = cursor.fetchone()
                patient_name = patient["name"] if patient else "Patient"
                pref_lang = patient["language_preference"] if patient else "en"
                
                # Preset session intent in DB
                cursor.execute("SELECT * FROM session_memory WHERE session_id = ?", (session_id,))
                session = cursor.fetchone()
                
                init_intent = "book" if "book" in campaign_context.lower() or "schedule" in campaign_context.lower() else "none"
                init_temp = {"doctor_id": doctor_id} if doctor_id else {}
                
                if not session:
                    cursor.execute("""
                        INSERT INTO session_memory (session_id, patient_phone, chat_history, active_intent, temp_data)
                        VALUES (?, ?, '[]', ?, ?)
                    """, (session_id, patient_phone, init_intent, json.dumps(init_temp)))
                else:
                    cursor.execute("""
                        UPDATE session_memory 
                        SET patient_phone = ?, active_intent = ?, temp_data = ?, chat_history = '[]'
                        WHERE session_id = ?
                    """, (patient_phone, init_intent, json.dumps(init_temp), session_id))
                conn.commit()
                
                # Proactive Greeting Formulation based on Campaign and Language
                if pref_lang == "hi":
                    speech_out = f"नमस्ते {patient_name}, मैं 2Care AI से बोल रही हूँ। डॉक्टर राजेश कुमार क्लिनिक से। मैं आपके आगामी बाल रोग चेक-अप की याद दिलाने के लिए कॉल कर रही हूँ। क्या हम 1 जून सुबह 10:00 बजे का स्लॉट बुक करें?"
                elif pref_lang == "ta":
                    speech_out = f"வணக்கம் {patient_name}, நான் 2Care AI இல் இருந்து பேசுகிறேன். டாக்டர் சுப்பிரமணியன் கார்டியாலஜி கிளினிக்கில் இருந்து. உங்களது இதய பரிசோதனை அப்பாயிண்ட்மெண்ட்டை உங்களுக்கு நினைவூட்ட நான் அழைக்கிறேன். ஜூன் 1 காலை 10 மணிக்கு பதிவு செய்யலாமா?"
                else:
                    cursor.execute("SELECT * FROM doctors WHERE id = ?", (doctor_id,))
                    doc = cursor.fetchone() if doctor_id else None
                    doc_last = doc["name"].split()[-1] if doc else "Rajesh"
                    speech_out = f"Hello {patient_name}, I am calling from 2Care AI on behalf of Dr. {doc_last}'s clinic regarding your pending follow-up. Would you like to schedule an appointment for June 1st at 10:00 AM?"

                # Set session greeting
                cursor.execute("""
                    UPDATE session_memory 
                    SET chat_history = ?
                    WHERE session_id = ?
                """, (json.dumps([{"role": "assistant", "content": speech_out}]), session_id))
                conn.commit()
                
                # Package latency
                agent_duration = (time.perf_counter() - start_time) * 1000
                stt_latency = 0.0
                db_latency = 2.0
                tts_latency = 120.0
                network_latency = 15.0
                total_latency = agent_duration + stt_latency + db_latency + tts_latency + network_latency
                
                resp = {
                    "speech_text": speech_out,
                    "reasoning_trace": [
                        "[Outbound Triggered] Proactive calling initiated for " + campaign_context,
                        "[Contextual Memory] Pulled patient preference language: " + pref_lang,
                        "[Agent Logic] Formulating warm proactive follow-up dialogue."
                    ],
                    "active_intent": init_intent,
                    "temp_data": init_temp,
                    "detected_language": pref_lang,
                    "telemetry": {
                        "stt": stt_latency,
                        "agent": agent_duration,
                        "db": db_latency,
                        "tts": tts_latency,
                        "network": network_latency,
                        "total": total_latency
                    }
                }
                
                await websocket.send_text(json.dumps(resp))
                continue
            
            # 2. Inbound Voice Turn Processing
            db_start = time.perf_counter()
            cursor.execute("SELECT * FROM patients WHERE phone = ?", (patient_phone,))
            patient = cursor.fetchone()
            db_duration = (time.perf_counter() - db_start) * 1000
            
            # Execute Agent reasoning turn
            agent_start = time.perf_counter()
            agent_res = run_agent_turn(conn, session_id, user_text, patient_phone)
            agent_duration = (time.perf_counter() - agent_start) * 1000
            
            # Broadcast update events to refresh other dashboards on voice updates
            if agent_res["active_intent"] == "none" and ("booked" in agent_res["speech_text"].lower() or "rescheduled" in agent_res["speech_text"].lower() or "cancelled" in agent_res["speech_text"].lower() or "सफलतापूर्वक" in agent_res["speech_text"] or "வெற்றிகரமாக" in agent_res["speech_text"] or "ரத்து" in agent_res["speech_text"]):
                await manager.broadcast(json.dumps({"event": "database_update"}))
            
            # Latency Telemetry Breakdown
            stt_latency = data.get("stt_latency", 65.0)
            tts_latency = 110.0
            network_latency = data.get("network_latency", 25.0)
            total_latency = stt_latency + db_duration + agent_duration + tts_latency + network_latency
            
            telemetry = {
                "stt": stt_latency,
                "agent": agent_duration,
                "db": db_duration,
                "tts": tts_latency,
                "network": network_latency,
                "total": total_latency
            }
            
            agent_res["telemetry"] = telemetry
            
            # Dispatch back
            await websocket.send_text(json.dumps(agent_res))
            
    except WebSocketDisconnect:
        print(f"WS Client disconnected: {session_id}")
    except Exception as e:
        print(f"WebSocket Error: {e}")
        try:
            await websocket.send_text(json.dumps({
                "speech_text": "I'm sorry, I encountered a temporary connection issue. Let's try again.",
                "reasoning_trace": [f"[System Error] Exception: {str(e)}", "[Graceful Recovery] Prompting patient again."],
                "active_intent": "none",
                "temp_data": {},
                "detected_language": "en",
                "telemetry": {"stt": 0, "agent": 0, "db": 0, "tts": 0, "network": 0, "total": 0}
            }))
        except Exception:
            pass
    finally:
        conn.close()
