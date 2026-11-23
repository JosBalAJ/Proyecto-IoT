import json, time, asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import paho.mqtt.client as mqtt
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from sklearn.ensemble import RandomForestClassifier
import numpy as np
import joblib
import os
from dotenv import load_dotenv
import httpx

load_dotenv()

MODEL_PATH = 'modelo_rf_aire.pkl'
if os.path.exists(MODEL_PATH):
    rf_model = joblib.load(MODEL_PATH)
    print(f"[IA] Modelo Random Forest '{MODEL_PATH}' cargado correctamente.")
else:
    print(f"[ERROR] No se encontró '{MODEL_PATH}'. Ejecuta 'entrenamiento_rf.py' primero.")
    rf_model = None

DATABASE_URL = "sqlite:///./calidad_aire.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class CalidadAireLectura(Base):
    __tablename__ = "lecturas_aire"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    sequence_id = Column(Integer)
    gas = Column(Float)
    temperatura = Column(Float)
    humedad = Column(Float)
    estado_riesgo = Column(String)
    latencia = Column(Float)
    fecha_registro = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections: self.active_connections.remove(websocket)
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try: await connection.send_text(message)
            except: pass

manager = ConnectionManager()
loop = None
time_offset = None

COOLDOWN_SECONDS = 30
last_alert_time = 0

async def enviar_alerta_telegram(payload, prediccion):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[Alerta] Faltan credenciales en el archivo .env")
        return

    mensaje = (
        f" *ALERTA CRÍTICA DE AIRE* \n\n"
        f" *Diagnóstico IA:* {prediccion}\n"
        f" *Secuencia (Seq):* {payload.get('sequence_id')}\n"
        f" *Gas MQ-135:* {payload.get('gas_filtered')} ADC\n"
        f" *Temperatura:* {payload.get('temperature')} °C\n"
        f" *Humedad:* {payload.get('humidity')} %\n"
        f" *Latencia de Red:* {payload.get('latencia_ms')} ms\n"
        f" *Hora:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}"
    )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json={"chat_id": chat_id, "text": mensaje, "parse_mode": "Markdown"})
            print(f"[Telegram] Alerta disparada para secuencia {payload.get('sequence_id')} a las {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
        except Exception as e:
            print(f"[ERROR Telegram] {e}")

MQTT_BROKER = "localhost"
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

def on_message(client, userdata, msg):
    global time_offset, last_alert_time
    t_recepcion = time.time() * 1000.0
    payload = json.loads(msg.payload.decode('utf-8'))
    
    t_envio = float(payload.get("timestamp_ms", 0))
    if time_offset is None: 
        time_offset = t_recepcion - t_envio
    latencia = round(abs(t_recepcion - (t_envio + time_offset)), 2)
    
    gas = float(payload.get("gas_filtered", 0))
    temp = float(payload.get("temperature", 0))
    hum = float(payload.get("humidity", 0))
    seq = int(payload.get("sequence_id", 0))

    if rf_model is not None:
        features = np.array([[gas, temp, hum, latencia]])
        prediccion = rf_model.predict(features)[0]
    else:
        prediccion = "Error de Modelo"
    
    payload["ml_risk_state"] = prediccion
    payload["latencia_ms"] = latencia

    if prediccion == "Riesgo Respiratorio":
        current_time = time.time()
        if (current_time - last_alert_time) > COOLDOWN_SECONDS:
            last_alert_time = current_time
            if loop is not None:
                asyncio.run_coroutine_threadsafe(enviar_alerta_telegram(payload, prediccion), loop)

    db = SessionLocal()
    nueva_lectura = CalidadAireLectura(
        sequence_id=seq,
        gas=gas,
        temperatura=temp,
        humedad=hum,
        estado_riesgo=prediccion,
        latencia=latencia
    )
    db.add(nueva_lectura)
    db.commit()
    db.close()

    if loop is not None:
        asyncio.run_coroutine_threadsafe(manager.broadcast(json.dumps(payload)), loop)

mqtt_client.on_message = on_message

@asynccontextmanager
async def lifespan(app: FastAPI):
    global loop
    loop = asyncio.get_running_loop()
    mqtt_client.connect(MQTT_BROKER, 1883, 60)
    mqtt_client.subscribe("sensores/aire/telemetria")
    mqtt_client.loop_start()
    print("[FastAPI] Conectado a MQTT y escuchando...")
    yield
    mqtt_client.loop_stop()
    mqtt_client.disconnect()

app = FastAPI(title="Middleware Calidad del Aire", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.websocket("/ws/telemetria")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            cmd = json.loads(data).get("action", "")
            if cmd in ["VENT_ON", "VENT_OFF"]:
                mqtt_client.publish("dispositivos/esp32/control", cmd)
    except WebSocketDisconnect:
        manager.disconnect(websocket)