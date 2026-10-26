import json, time, asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import paho.mqtt.client as mqtt
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker  # Corrección SQLAlchemy
from sklearn.ensemble import RandomForestClassifier
import numpy as np

DATABASE_URL = "sqlite:///./calidad_aire.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class CalidadAireLectura(Base):
    __tablename__ = "lecturas_aire"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    gas = Column(Float)
    temperatura = Column(Float)
    humedad = Column(Float)
    estado_riesgo = Column(String)
    latencia = Column(Float)
    fecha_registro = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

rf_model = RandomForestClassifier(n_estimators=15, random_state=42)
X_train = np.array([
    [1000, 22.0, 45.0], [1200, 24.0, 50.0],
    [2100, 27.0, 55.0], [2300, 28.5, 60.0],
    [2800, 31.0, 70.0], [3200, 35.0, 75.0]
])
y_train = np.array(["Aire Limpio/Seguro", "Aire Limpio/Seguro", 
                    "Requiere Ventilación", "Requiere Ventilación", 
                    "Riesgo Respiratorio", "Riesgo Respiratorio"])
rf_model.fit(X_train, y_train)

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

MQTT_BROKER = "localhost"
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

def on_message(client, userdata, msg):
    global time_offset
    t_recepcion = time.time() * 1000.0
    payload = json.loads(msg.payload.decode('utf-8'))
    
    t_envio = float(payload.get("timestamp_ms", 0))
    if time_offset is None: time_offset = t_recepcion - t_envio
    latencia = round(abs(t_recepcion - (t_envio + time_offset)), 2)
    
    gas = float(payload.get("gas_filtered", 0))
    temp = float(payload.get("temperature", 0))
    hum = float(payload.get("humidity", 0))

    features = np.array([[gas, temp, hum]])
    prediccion = rf_model.predict(features)[0]
    
    payload["ml_risk_state"] = prediccion
    payload["latencia_ms"] = latencia

    db = SessionLocal()
    nueva_lectura = CalidadAireLectura(
        gas=gas, temperatura=temp, humedad=hum, 
        estado_riesgo=prediccion, latencia=latencia
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