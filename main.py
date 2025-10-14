from fastapi import FastAPI
from pydantic import BaseModel
from pymongo import MongoClient
from bson import ObjectId
import datetime
import random
import os
from fastapi.middleware.cors import CORSMiddleware
from preguntas import preguntas  

# ---------------------------
# Configuración FastAPI
# ---------------------------
app = FastAPI()

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------
# Conexión a MongoDB
# ---------------------------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client["RetoMates"]

progreso_chatbot_col = db["progreso_chatbot"]
respuestas_col = db["respuestas"]
historial_preguntas_col = db["historial_preguntas"]
users_col = db["users"]

# ---------------------------
# Modelos
# ---------------------------
class Saludo(BaseModel):
    user_id: str
    texto: str

class SeleccionBloque(BaseModel):
    user_id: str
    bloque: int

class SeleccionTema(BaseModel):
    user_id: str
    tema: str

class RespuestaUsuario(BaseModel):
    user_id: str
    respuesta: str

# ---------------------------
# Funciones auxiliares
# ---------------------------
def to_objectid(id_str: str):
    try:
        return ObjectId(id_str)
    except:
        return id_str

def obtener_preguntas_alternativas(bloque: int, tema: str, user_id: str):
    preguntas_respondidas = historial_preguntas_col.find({
        "id_usuario": user_id,
        "bloque": bloque,
        "tema": tema
    }).distinct("pregunta")

    todas_preguntas = preguntas[bloque][tema]
    preguntas_disponibles = [p for p in todas_preguntas if p["pregunta"] not in preguntas_respondidas]

    if len(preguntas_disponibles) < 5 and len(todas_preguntas) >= 5:
        preguntas_respondidas_disponibles = [p for p in todas_preguntas if p["pregunta"] in preguntas_respondidas]
        random.shuffle(preguntas_respondidas_disponibles)
        preguntas_disponibles.extend(preguntas_respondidas_disponibles[:5 - len(preguntas_disponibles)])

    if not preguntas_disponibles:
        return random.sample(todas_preguntas, min(5, len(todas_preguntas)))

    return random.sample(preguntas_disponibles, min(5, len(preguntas_disponibles)))

def es_usuario_nuevo(user_id: str) -> bool:
    return progreso_chatbot_col.find_one({"id_usuario": user_id}) is None

def obtener_nombre_usuario(user_id: str) -> str:
    usuario = users_col.find_one({"_id": to_objectid(user_id)})
    if usuario:
        return usuario.get("username", "Usuario")
    progreso = progreso_chatbot_col.find_one({"id_usuario": user_id})
    if progreso and "nombre" in progreso:
        return progreso["nombre"]
    return "Usuario"

# ---------------------------
# Endpoints de chatbot
# ---------------------------
@app.get("/chatbot/inicio/{user_id}")
def iniciar_chatbot(user_id: str):
    # Demo
    if user_id.startswith("demo_user_"):
        if es_usuario_nuevo(user_id):
            progreso_chatbot_col.update_one(
                {"id_usuario": user_id},
                {"$set": {
                    "nombre": "Usuario Demo",
                    "fecha_primer_acceso": datetime.datetime.utcnow(),
                    "fecha_ultima_interaccion": datetime.datetime.utcnow(),
                    "bloque": None,
                    "tema": None,
                    "indice_pregunta": 0,
                    "correctas": 0,
                    "preguntas_actuales": []
                }},
                upsert=True
            )
            return {
                "mensaje": "¡Hola! Bienvenido a RetoMate 🎉. ¿Qué bloque quieres practicar hoy?",
                "siguiente": {"endpoint": "/chatbot/seleccionar_bloque"},
                "tema_en_progreso": None,
                "bloque_en_progreso": None,
                "usuario_nuevo": True
            }
        progreso = progreso_chatbot_col.find_one({"id_usuario": user_id})
        mensaje = (f"¡Bienvenido de vuelta! Veo que estabas practicando {progreso.get('tema')} "
                   f"en el Bloque {progreso.get('bloque')}. ¿Quieres continuar o elegir otro tema?")
        return {
            "mensaje": mensaje,
            "siguiente": {"endpoint": "/chatbot/seleccionar_bloque"},
            "tema_en_progreso": progreso.get("tema"),
            "bloque_en_progreso": progreso.get("bloque"),
            "usuario_nuevo": False
        }

    # Usuario real
    usuario_existe = users_col.find_one({"_id": to_objectid(user_id)})
    if not usuario_existe:
        return {"error": "Usuario no encontrado"}

    if es_usuario_nuevo(user_id):
        nombre_usuario = usuario_existe.get("username", "Usuario")
        progreso_chatbot_col.update_one(
            {"id_usuario": user_id},
            {"$set": {
                "nombre": nombre_usuario,
                "fecha_primer_acceso": datetime.datetime.utcnow(),
                "fecha_ultima_interaccion": datetime.datetime.utcnow(),
                "bloque": None,
                "tema": None,
                "indice_pregunta": 0,
                "correctas": 0,
                "preguntas_actuales": []
            }},
            upsert=True
        )
        return {
            "mensaje": f"¡Hola {nombre_usuario}! Bienvenido a RetoMate 🎉. ¿Qué bloque quieres practicar hoy?",
            "siguiente": {"endpoint": "/chatbot/seleccionar_bloque"},
            "tema_en_progreso": None,
            "bloque_en_progreso": None,
            "usuario_nuevo": True
        }

    # Usuario existente
    progreso = progreso_chatbot_col.find_one({"id_usuario": user_id})
    nombre_usuario = obtener_nombre_usuario(user_id)
    if progreso.get("tema"):
        mensaje = f"¡Bienvenido de vuelta {nombre_usuario}! Estabas practicando {progreso['tema']} en el Bloque {progreso['bloque']}."
    else:
        mensaje = f"¡Bienvenido de vuelta {nombre_usuario}! ¿Qué quieres practicar hoy?"
    return {
        "mensaje": mensaje,
        "siguiente": {"endpoint": "/chatbot/seleccionar_bloque"},
        "tema_en_progreso": progreso.get("tema"),
        "bloque_en_progreso": progreso.get("bloque"),
        "usuario_nuevo": False
    }

# Aquí seguirían tus endpoints: saludo, seleccionar_bloque, seleccionar_tema, responder
# Puedes copiarlos tal como los tienes, porque funcionan igual

# ---------------------------
# Ejecutar servidor
# ---------------------------
if __name__ == "__main__":
    import uvicorn
    PORT = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)
