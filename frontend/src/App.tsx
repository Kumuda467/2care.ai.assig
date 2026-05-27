import { useState, useEffect, useRef } from 'react';
import { 
  Phone, 
  Mic, 
  MicOff, 
  Play, 
  Clock, 
  Calendar, 
  Activity, 
  Check, 
  Languages, 
  Volume2, 
  BrainCircuit,
  FileSpreadsheet
} from 'lucide-react';
import { useWebSpeech } from './hooks/useWebSpeech';

interface Doctor {
  id: number;
  name: string;
  specialty: string;
  languages: string[];
  working_hours: string;
  available_slots_june_1st: string[];
}

interface Patient {
  id: number;
  phone: string;
  name: string;
  language_preference: string;
  past_history: string;
}

interface Appointment {
  id: number;
  patient_id: number;
  patient_name: string;
  patient_phone: string;
  doctor_id: number;
  doctor_name: string;
  doctor_specialty: string;
  date: string;
  time: string;
  status: string;
}

interface LogEntry {
  text: string;
  type: 'tool' | 'llm' | 'system' | 'success';
  timestamp: string;
}

interface TranscriptEntry {
  role: 'user' | 'assistant';
  text: string;
}

interface IncomingCallModal {
  show: boolean;
  phone: string;
  patientName: string;
  campaignName: string;
  doctorId: number;
  doctorName: string;
}

const rawApiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const rawWsUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';

const API_URL = rawApiUrl.replace(/\/$/, '');
const WS_URL = rawWsUrl.replace(/\/$/, '');

export default function App() {
  // App State
  const [patients, setPatients] = useState<Patient[]>([]);
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  
  const [activePatientPhone, setActivePatientPhone] = useState('9876543210');
  const [agentState, setAgentState] = useState<'idle' | 'listening' | 'thinking' | 'speaking'>('idle');
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [activeConsoleTab, setActiveConsoleTab] = useState<'reasoning' | 'transcript'>('reasoning');
  
  // Call modal state
  const [incomingCall, setIncomingCall] = useState<IncomingCallModal>({
    show: false,
    phone: '',
    patientName: '',
    campaignName: '',
    doctorId: 0,
    doctorName: ''
  });
  const [isCallActive, setIsCallActive] = useState(false);

  // Telemetry metric state (sub-450ms target)
  const [telemetry, setTelemetry] = useState({
    stt: 65,
    db: 2,
    agent: 4,
    tts: 110,
    network: 20,
    total: 201
  });

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const animationFrameRef = useRef<number | null>(null);

  // Hook Callback handlers
  const handleTranscriptUpdate = (role: 'user' | 'assistant', text: string) => {
    setTranscript(prev => [...prev, { role, text }]);
  };

  const handleReasoningTrace = (traces: string[]) => {
    const timeStr = new Date().toLocaleTimeString();
    setLogs(prev => [
      ...prev,
      ...traces.map(t => {
        let type: 'tool' | 'llm' | 'system' | 'success' = 'llm';
        if (t.includes('[Tool Call]')) type = 'tool';
        else if (t.includes('[System') || t.includes('[Language')) type = 'system';
        else if (t.includes('[Tool Output] Success') || t.includes('[Conflict Handling]')) type = 'success';
        return { text: t, type, timestamp: timeStr };
      })
    ]);
  };

  const handleTelemetryUpdate = (newTel: Record<string, number>) => {
    setTelemetry(newTel as any);
  };

  const handleAgentStateChange = (state: 'idle' | 'listening' | 'thinking' | 'speaking') => {
    setAgentState(state);
  };

  const handleLanguageChanged = (lang: string) => {
    // Sync language selection
    console.log("Language updated by agent:", lang);
  };

  const [manualText, setManualText] = useState('');

  // Instantiate Voice AI hook
  const {
    isRecording,
    language,
    toggleRecording,
    triggerOutboundGreeting,
    changeLanguage,
    sendTextMessage
  } = useWebSpeech({
    patientPhone: activePatientPhone,
    onTranscriptUpdate: handleTranscriptUpdate,
    onReasoningTrace: handleReasoningTrace,
    onTelemetryUpdate: handleTelemetryUpdate,
    onAgentStateChange: handleAgentStateChange,
    onLanguageChanged: handleLanguageChanged
  });

  const handleManualSubmit = (e: any) => {
    e.preventDefault();
    if (!manualText.trim()) return;
    sendTextMessage(manualText);
    setManualText('');
  };

  // Fetch DB records
  const fetchDbData = async () => {
    try {
      const docsRes = await fetch(`${API_URL}/api/doctors`);
      const docs = await docsRes.json();
      setDoctors(docs);

      const apptsRes = await fetch(`${API_URL}/api/appointments`);
      const appts = await apptsRes.json();
      setAppointments(appts);

      const patsRes = await fetch(`${API_URL}/api/patients`);
      const pats = await patsRes.json();
      setPatients(pats);
    } catch (e) {
      console.error("Error fetching dashboard data:", e);
    }
  };

  useEffect(() => {
    fetchDbData();

    // Listen to real-time broadcasts on standard websocket channel
    const socket = new WebSocket(`${WS_URL}/ws/chat`);
    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      // Real-time slot and appointment updates
      if (data.event === 'database_update') {
        fetchDbData();
        const timeStr = new Date().toLocaleTimeString();
        setLogs(prev => [...prev, {
          text: "[System Sync] Clinic database updated successfully. Re-fetching slots...",
          type: 'system',
          timestamp: timeStr
        }]);
      }
      
      // Outbound campaign call ringing
      if (data.event === 'incoming_call') {
        setIncomingCall({
          show: true,
          phone: data.phone,
          patientName: data.patient_name,
          campaignName: data.campaign_name,
          doctorId: data.doctor_id,
          doctorName: data.doctor_name
        });
      }
    };

    return () => {
      socket.close();
    };
  }, []);

  // Sync patient language preference in selectors
  useEffect(() => {
    const patient = patients.find(p => p.phone === activePatientPhone);
    if (patient && patient.language_preference !== language) {
      changeLanguage(patient.language_preference);
    }
    setTranscript([]);
    setLogs(prev => [...prev, {
      text: `[Context Switch] Loaded patient session for ${patient?.name || activePatientPhone}. Past Medical History: "${patient?.past_history || 'None'}"`,
      type: 'system',
      timestamp: new Date().toLocaleTimeString()
    }]);
  }, [activePatientPhone, patients]);

  // Audio wave canvas animation
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let phase = 0;
    
    const drawWave = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      
      // Adjust amplitudes based on agent state
      let amp = 0;
      let freq = 0.05;
      let speed = 0.08;

      if (agentState === 'listening') {
        amp = 12;
        freq = 0.07;
        speed = 0.15;
      } else if (agentState === 'speaking') {
        amp = 18;
        freq = 0.04;
        speed = 0.12;
      } else if (agentState === 'thinking') {
        amp = 4;
        freq = 0.1;
        speed = 0.2;
      }

      ctx.lineWidth = 2;
      
      if (amp > 0) {
        // Draw 3 layers of overlapping sine waves for premium glass wave feel
        for (let i = 0; i < 3; i++) {
          ctx.beginPath();
          const offset = i * Math.PI / 3;
          ctx.strokeStyle = i === 0 ? 'rgba(6, 182, 212, 0.6)' : i === 1 ? 'rgba(99, 102, 241, 0.4)' : 'rgba(16, 185, 129, 0.3)';
          
          for (let x = 0; x < canvas.width; x++) {
            const y = canvas.height / 2 + Math.sin(x * freq + phase + offset) * (amp - i * 3) * Math.sin(x * Math.PI / canvas.width);
            if (x === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          }
          ctx.stroke();
        }
        phase += speed;
      } else {
        // Draw a flat baseline
        ctx.beginPath();
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
        ctx.moveTo(0, canvas.height / 2);
        ctx.lineTo(canvas.width, canvas.height / 2);
        ctx.stroke();
      }

      animationFrameRef.current = requestAnimationFrame(drawWave);
    };

    drawWave();

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [agentState]);

  // Outbound Trigger Click Handler
  const handleTriggerCampaign = async (phone: string, campaignName: string, doctorId: number) => {
    try {
      const res = await fetch(`${API_URL}/api/campaigns/trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          patient_phone: phone,
          campaign_name: campaignName,
          doctor_id: doctorId
        })
      });
      await res.json();
    } catch (e) {
      console.error("Error triggering campaign:", e);
    }
  };

  const handleDeclineCall = () => {
    setIncomingCall(prev => ({ ...prev, show: false }));
    setIsCallActive(false);
  };

  const handleAcceptCall = () => {
    setIncomingCall(prev => ({ ...prev, show: false }));
    setActivePatientPhone(incomingCall.phone);
    setIsCallActive(true);
    
    // Auto-launch the recording and send outbound prompt
    triggerOutboundGreeting(incomingCall.campaignName, incomingCall.doctorId);
    
    setLogs(prev => [...prev, {
      text: `[Outbound Call Accepted] Connecting to patient ${incomingCall.patientName} (${incomingCall.phone}). Context: ${incomingCall.campaignName}`,
      type: 'system',
      timestamp: new Date().toLocaleTimeString()
    }]);
  };

  // Generate specific label names
  const getLanguageLabel = (code: string) => {
    if (code === 'hi') return 'हिन्दी (Hindi)';
    if (code === 'ta') return 'தமிழ் (Tamil)';
    return 'English';
  };

  const activePatient = patients.find(p => p.phone === activePatientPhone);

  return (
    <div className="app-container">
      {/* SVG linear gradients for Lucide icons */}
      <svg width="0" height="0" style={{ position: 'absolute' }}>
        <defs>
          <linearGradient id="logo-grad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#06b6d4" />
            <stop offset="100%" stopColor="#6366f1" />
          </linearGradient>
        </defs>
      </svg>

      <header>
        <div className="logo">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4.8 16.2A8 8 0 1 0 16.2 4.8" />
            <path d="M2 2v10h10" />
            <path d="m2 2 10 10" />
          </svg>
          2care.ai
        </div>
        
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          {isCallActive && (
            <div className="header-status" style={{ background: 'rgba(16, 185, 129, 0.08)', borderColor: 'rgba(16, 185, 129, 0.2)', color: '#10b981' }}>
              <Phone size={14} style={{ verticalAlign: 'middle', marginRight: '0.2rem' }} />
              <span>Campaign Call: <strong style={{ color: '#fff' }}>ACTIVE</strong></span>
            </div>
          )}

          <div className="header-status">
            <div className={`status-dot ${agentState !== 'idle' ? 'active' : ''}`}></div>
            <span>Voice Agent Engine: <strong style={{ color: '#fff' }}>ONLINE</strong></span>
          </div>
          
          <div className="header-status" style={{ background: 'rgba(99, 102, 241, 0.08)', borderColor: 'rgba(99, 102, 241, 0.2)' }}>
            <Languages size={14} style={{ color: '#6366f1' }} />
            <span>Target: <strong style={{ color: '#fff' }}>EN · हिन्दी · தமிழ்</strong></span>
          </div>
        </div>
      </header>

      <main className="dashboard-grid">
        {/* LEFT COLUMN */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          
          {/* Card 1: Voice Cockpit */}
          <section className="card voice-agent-card">
            <div className="card-header w-full">
              <h2 className="card-title">
                <Activity size={18} className="text-cyan" />
                AI Dialog Cockpit
              </h2>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Selected Patient:</span>
                <select 
                  className="patient-select" 
                  style={{ width: 'auto', padding: '0.25rem 0.5rem', margin: 0 }}
                  value={activePatientPhone}
                  onChange={(e) => setActivePatientPhone(e.target.value)}
                >
                  {patients.map(p => (
                    <option key={p.id} value={p.phone}>{p.name} ({p.phone})</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Mic control */}
            <div className="mic-button-container">
              <div className={`mic-pulse-ring ${isRecording ? 'active' : ''}`}></div>
              <button 
                className={`mic-button ${isRecording ? 'active' : ''}`}
                onClick={toggleRecording}
                title={isRecording ? 'Click to Mute Agent' : 'Click to Speak to Agent'}
              >
                {isRecording ? <MicOff size={32} /> : <Mic size={32} />}
              </button>
            </div>

            {/* Status indicator */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.5rem' }}>
              <span className={`agent-state-badge state-${agentState}`}>
                {agentState}
              </span>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', maxWidth: '380px' }}>
                {agentState === 'listening' && "Listening to you... Speak in English, Hindi, or Tamil."}
                {agentState === 'thinking' && "Reasoning & executing tools..."}
                {agentState === 'speaking' && "AI Agent is responding via voice..."}
                {agentState === 'idle' && (isRecording ? "Listening for your voice... Start speaking!" : "Microphone disabled. Click to start voice consultation.")}
              </p>
            </div>

            {/* Simulated sine-wave oscillator */}
            <canvas ref={canvasRef} className="audio-waveform-canvas" width="400" height="60"></canvas>

            {/* Manual Simulation Input Box */}
            <form onSubmit={handleManualSubmit} style={{ width: '100%', display: 'flex', gap: '0.5rem', margin: '0.2rem 0 0.8rem 0' }}>
              <input 
                type="text" 
                value={manualText} 
                onChange={(e) => setManualText(e.target.value)}
                placeholder="Type query or command (e.g. 'hello', 'who are you', 'how are you')..." 
                style={{
                  flex: 1,
                  background: 'rgba(255, 255, 255, 0.03)',
                  border: '1px solid var(--border-glass)',
                  borderRadius: '6px',
                  color: '#fff',
                  padding: '0.45rem 0.75rem',
                  fontSize: '0.8rem',
                  outline: 'none',
                  transition: 'border-color 0.2s'
                }}
                onFocus={(e) => e.target.style.borderColor = 'rgba(6, 182, 212, 0.5)'}
                onBlur={(e) => e.target.style.borderColor = 'var(--border-glass)'}
              />
              <button 
                type="submit"
                style={{
                  background: 'linear-gradient(135deg, var(--accent-cyan), var(--accent-indigo))',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '6px',
                  padding: '0.45rem 1rem',
                  fontSize: '0.8rem',
                  fontWeight: '600',
                  cursor: 'pointer',
                  boxShadow: '0 2px 8px rgba(6, 182, 212, 0.2)',
                  transition: 'transform 0.1s, opacity 0.2s'
                }}
                onMouseDown={(e) => e.currentTarget.style.transform = 'scale(0.96)'}
                onMouseUp={(e) => e.currentTarget.style.transform = 'scale(1)'}
              >
                Send
              </button>
            </form>

            {/* Context memo preview */}
            {activePatient && (
              <div style={{ 
                width: '100%', 
                background: 'rgba(255, 255, 255, 0.02)', 
                border: '1px solid var(--border-glass)',
                borderRadius: '10px',
                padding: '0.75rem',
                fontSize: '0.75rem',
                textAlign: 'left'
              }}>
                <div style={{ fontWeight: 600, color: 'var(--accent-indigo)', marginBottom: '0.25rem' }}>
                  Cross-Session Patient Context Memory:
                </div>
                <div><strong>Patient Name:</strong> {activePatient.name} | <strong>Lang Pref:</strong> {getLanguageLabel(language)}</div>
                <div style={{ color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                  <strong>Prior History:</strong> {activePatient.past_history}
                </div>
              </div>
            )}
          </section>

          {/* Card 2: Precision Latency Dashboard */}
          <section className="card">
            <div className="card-header">
              <h2 className="card-title">
                <Clock size={18} className="text-amber" />
                Real-Time Telemetry & Latency Benchmark
              </h2>
              <span style={{ fontSize: '0.75rem', color: 'var(--accent-emerald)', fontWeight: 600 }}>
                Budget Target: &lt;450ms
              </span>
            </div>

            <div className="telemetry-container">
              <div className="telemetry-card">
                <div className="telemetry-label">Speech-To-Text</div>
                <div className="telemetry-value text-cyan">{telemetry.stt.toFixed(0)} ms</div>
              </div>
              <div className="telemetry-card">
                <div className="telemetry-label">Agent Planner</div>
                <div className="telemetry-value text-indigo">{telemetry.agent.toFixed(0)} ms</div>
              </div>
              <div className="telemetry-card">
                <div className="telemetry-label">Database Tool</div>
                <div className="telemetry-value text-amber">{telemetry.db.toFixed(0)} ms</div>
              </div>
              <div className="telemetry-card">
                <div className="telemetry-label">Text-To-Speech</div>
                <div className="telemetry-value text-emerald">{telemetry.tts.toFixed(0)} ms</div>
              </div>
            </div>

            {/* Custom bar chart */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', marginTop: '0.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem' }}>
                <span>Total End-to-End Processing Delay:</span>
                <strong className={telemetry.total < 450 ? "text-emerald" : "text-rose"} style={{ fontSize: '0.95rem' }}>
                  {telemetry.total.toFixed(0)} ms
                </strong>
              </div>
              
              <div className="latency-meter-wrapper">
                {/* Visualizing stack layers in single line bar */}
                <div style={{ width: `${(telemetry.stt / 500) * 100}%`, background: 'var(--accent-cyan)' }} className="latency-meter-fill" title="STT"></div>
                <div style={{ width: `${(telemetry.agent / 500) * 100}%`, background: 'var(--accent-indigo)' }} className="latency-meter-fill" title="Agent Reasoning"></div>
                <div style={{ width: `${(telemetry.db / 500) * 100}%`, background: 'var(--accent-amber)' }} className="latency-meter-fill" title="Database/Tool"></div>
                <div style={{ width: `${(telemetry.tts / 500) * 100}%`, background: 'var(--accent-emerald)' }} className="latency-meter-fill" title="TTS"></div>
                <div style={{ width: `${(telemetry.network / 500) * 100}%`, background: 'var(--text-muted)' }} className="latency-meter-fill" title="Network Round Trip"></div>
                
                {/* 450ms budget marker */}
                <div style={{ left: '90%' }} className="latency-meter-budget-marker" title="450ms SLA Budget limit"></div>
              </div>

              <div className="latency-legend">
                <span>0 ms</span>
                <span>150 ms</span>
                <span>300 ms</span>
                <span className="text-rose" style={{ fontWeight: 600 }}>450ms SLA Budget</span>
                <span>500 ms</span>
              </div>
            </div>
          </section>

          {/* Card 3: Outbound Reminder Campaign Manager */}
          <section className="card campaign-card">
            <div className="card-header">
              <h2 className="card-title">
                <Phone size={18} className="text-emerald" />
                Proactive Outbound Campaigns
              </h2>
            </div>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div className="campaign-row">
                <div className="campaign-info">
                  <div className="campaign-name">Pediatric Immunization Recall</div>
                  <div className="campaign-recipient">Recipient: Simran Kaur (Pediatric patient)</div>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <span className="campaign-badge badge-en">EN</span>
                  <button 
                    className="call-btn"
                    onClick={() => handleTriggerCampaign("9999999999", "Pediatric Immunization Recall", 1)}
                  >
                    <Play size={12} fill="currentColor" /> Call
                  </button>
                </div>
              </div>

              <div className="campaign-row">
                <div className="campaign-info">
                  <div className="campaign-name">Hypertension Clinic Booking</div>
                  <div className="campaign-recipient">Recipient: Suresh Kumar (Chronic pain follow-up)</div>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <span className="campaign-badge badge-hi">HI</span>
                  <button 
                    className="call-btn"
                    onClick={() => handleTriggerCampaign("9123456789", "Hypertension Follow-Up Campaign", 2)}
                  >
                    <Play size={12} fill="currentColor" /> Call
                  </button>
                </div>
              </div>

              <div className="campaign-row">
                <div className="campaign-info">
                  <div className="campaign-name">Type 2 Diabetes Lab Review</div>
                  <div className="campaign-recipient">Recipient: Priya Sundaram (Hba1c Recall)</div>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <span className="campaign-badge badge-ta">TA</span>
                  <button 
                    className="call-btn"
                    onClick={() => handleTriggerCampaign("8765432109", "Type-2 Diabetes lab review Campaign", 3)}
                  >
                    <Play size={12} fill="currentColor" /> Call
                  </button>
                </div>
              </div>
            </div>
          </section>
        </div>

        {/* RIGHT COLUMN */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          
          {/* Card 4: Console */}
          <section className="card console-card" style={{ flex: 1 }}>
            <div className="tabs">
              <button 
                className={`tab-btn ${activeConsoleTab === 'reasoning' ? 'active' : ''}`}
                onClick={() => setActiveConsoleTab('reasoning')}
              >
                <BrainCircuit size={14} style={{ marginRight: '0.25rem', verticalAlign: 'middle' }} />
                Real-Time AI Reasoning traces
              </button>
              <button 
                className={`tab-btn ${activeConsoleTab === 'transcript' ? 'active' : ''}`}
                onClick={() => setActiveConsoleTab('transcript')}
              >
                <Volume2 size={14} style={{ marginRight: '0.25rem', verticalAlign: 'middle' }} />
                Dialogue Transcript ({transcript.length})
              </button>
            </div>

            {activeConsoleTab === 'reasoning' ? (
              <div className="log-terminal">
                {logs.length === 0 ? (
                  <div className="empty-logs">
                    System logs are ready. Speak into the microphone to trigger agent reasoning traces...
                  </div>
                ) : (
                  logs.map((log, idx) => (
                    <div key={idx} className={`log-entry ${log.type}`}>
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.7rem', marginRight: '0.5rem' }}>
                        [{log.timestamp}]
                      </span>
                      {log.text}
                    </div>
                  ))
                )}
              </div>
            ) : (
              <div className="log-terminal" style={{ background: '#0a0d16' }}>
                {transcript.length === 0 ? (
                  <div className="empty-logs">
                    No speech dialogue recorded yet.
                  </div>
                ) : (
                  <div className="chat-transcript-view">
                    {transcript.map((bubble, idx) => (
                      <div key={idx} className={`chat-bubble ${bubble.role}`}>
                        <div style={{ fontWeight: 700, fontSize: '0.7rem', marginBottom: '0.2rem', opacity: 0.7 }}>
                          {bubble.role === 'user' ? 'PATIENT' : '2CARE AI AGENT'}
                        </div>
                        {bubble.text}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </section>

          {/* Quick instructions / Help */}
          <section className="card" style={{ padding: '1rem', background: 'rgba(99, 102, 241, 0.04)', borderColor: 'rgba(99, 102, 241, 0.15)' }}>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-start' }}>
              <BrainCircuit className="text-indigo" size={16} style={{ marginTop: '0.1rem', flexShrink: 0 }} />
              <div style={{ fontSize: '0.75rem', lineHeight: '1.4', textAlign: 'left' }}>
                <strong style={{ color: '#fff', display: 'block', marginBottom: '0.25rem' }}>Clinical Simulation Guide:</strong>
                <ul style={{ paddingLeft: '1.1rem', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '0.15rem' }}>
                  <li><strong>Language switches:</strong> Talk in English, Hindi, or Tamil; the AI auto-detects and transitions instantly.</li>
                  <li><strong>Booking:</strong> "Book an appointment for General Medicine tomorrow at 10 AM."</li>
                  <li><strong>Conflict Test:</strong> Try booking Dr. Rajesh Kumar at 10:00 AM on June 1st. He is pre-booked, triggering alternative suggestions!</li>
                  <li><strong>Reschedule:</strong> "Reschedule my doctor meeting to June 2nd at 11 AM."</li>
                  <li><strong>Barge-in:</strong> Talk while the agent is speaking. It instantly stops and listens!</li>
                </ul>
              </div>
            </div>
          </section>
        </div>

        {/* BOTTOM FULL-WIDTH GRID */}
        <div className="management-grid">
          
          {/* Card 5: Doctors database */}
          <section className="card">
            <div className="card-header">
              <h2 className="card-title">
                <FileSpreadsheet size={18} className="text-cyan" />
                Clinic Staff & Hourly Schedules
              </h2>
            </div>
            
            <div className="clinical-list">
              {doctors.length === 0 ? (
                <div className="empty-text">Loading clinical staff...</div>
              ) : (
                doctors.map(doc => (
                  <div key={doc.id} className="doctor-item">
                    <div className="doctor-avatar-info">
                      <div className="doctor-avatar">
                        {doc.name.split(' ').pop()?.charAt(0)}
                      </div>
                      <div style={{ textAlign: 'left' }}>
                        <div className="doc-name">{doc.name}</div>
                        <div className="doc-specialty">{doc.specialty} | {doc.languages.join(', ')}</div>
                      </div>
                    </div>
                    
                    <div style={{ textAlign: 'right' }}>
                      <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Demo Date slots (June 1st):</span>
                      <div className="slots-grid">
                        {/* We list standard slots, marking taken ones */}
                        {["09:00", "10:00", "11:00", "12:00", "14:00", "15:00", "16:00"].map(slot => {
                          const isAvailable = doc.available_slots_june_1st?.includes(slot);
                          return (
                            <span 
                              key={slot} 
                              className={`slot-pill ${isAvailable ? 'available' : ''}`}
                              style={{ 
                                textDecoration: isAvailable ? 'none' : 'line-through',
                                opacity: isAvailable ? 1 : 0.4
                              }}
                            >
                              {slot}
                            </span>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>

          {/* Card 6: Bookings list */}
          <section className="card">
            <div className="card-header">
              <h2 className="card-title">
                <Calendar size={18} className="text-emerald" />
                Active Patient Appointments ({appointments.length})
              </h2>
            </div>

            <div className="clinical-list">
              {appointments.length === 0 ? (
                <div className="empty-text">No active appointments scheduled. Book one using the voice agent!</div>
              ) : (
                appointments.map(appt => (
                  <div key={appt.id} className="appointment-item">
                    <div className="doctor-avatar-info">
                      <div className="doctor-avatar" style={{ background: 'var(--accent-emerald-opaque)', color: 'var(--accent-emerald)' }}>
                        <Check size={18} />
                      </div>
                      <div style={{ textAlign: 'left' }}>
                        <div className="appt-patient">{appt.patient_name} <span style={{ fontWeight: 400, color: 'var(--text-muted)', fontSize: '0.75rem' }}>({appt.patient_phone})</span></div>
                        <div className="appt-doctor">Staff: {appt.doctor_name} ({appt.doctor_specialty})</div>
                      </div>
                    </div>
                    
                    <div className="appt-time-badge">
                      <div className="appt-time">{appt.date} @ {appt.time}</div>
                      <span className={`appt-status status-${appt.status}`}>
                        {appt.status}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        </div>
      </main>

      {/* OVERLAY RINGING MODAL SIMULATION */}
      {incomingCall.show && (
        <div className="modal-overlay">
          <div className="call-modal">
            <div className="call-avatar">
              <Phone size={36} fill="currentColor" />
            </div>
            
            <div>
              <div className="call-subtitle">Incoming Clinical Call</div>
              <div className="call-title">2Care.ai Agent</div>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                Connecting: <strong>{incomingCall.patientName}</strong>
              </div>
              <div style={{ 
                marginTop: '0.5rem', 
                fontSize: '0.75rem', 
                color: 'var(--accent-cyan)',
                background: 'var(--accent-cyan-opaque)',
                padding: '0.25rem 0.5rem',
                borderRadius: '4px'
              }}>
                Topic: {incomingCall.campaignName}
              </div>
            </div>

            <div className="call-actions">
              <button className="call-action-btn btn-decline" onClick={handleDeclineCall}>
                Decline
              </button>
              <button className="call-action-btn btn-accept" onClick={handleAcceptCall}>
                Answer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
