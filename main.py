from fastapi import FastAPI
from pydantic import BaseModel
from pymongo import MongoClient
from bson import ObjectId
from fastapi.middleware.cors import CORSMiddleware
import datetime
import random
import os
from preguntas import preguntas  # tu archivo de preguntas

# ---------------------------
# Configuración de FastAPI
# ---------------------------
app = FastAPI()

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

def obtener_preguntas(bloque: int, tema: str, user_id: str):
    """Devuelve 5 preguntas no respondidas por el usuario."""
    preguntas_respondidas = historial_preguntas_col.find({
        "id_usuario": user_id,
        "bloque": bloque,
        "tema": tema
    }).distinct("pregunta")

    todas = preguntas[bloque][tema]
    disponibles = [p for p in todas if p["pregunta"] not in preguntas_respondidas]

    if not disponibles:
        return random.sample(todas, min(5, len(todas)))

    if len(disponibles) < 5:
        faltan = 5 - len(disponibles)
        extras = [p for p in todas if p["pregunta"] in preguntas_respondidas][:faltan]
        disponibles.extend(extras)

    return random.sample(disponibles, min(5, len(disponibles)))

# ---------------------------
# ENDPOINTS
# ---------------------------

@app.get("/chatbot/inicio/{user_id}")
def iniciar_chatbot(user_id: str):
    usuario_existe = users_col.find_one({"_id": to_objectid(user_id)})

    # Si no existe en users → demo o error
    if not usuario_existe and not user_id.startswith("demo_user_"):
        return {"error": "Usuario no encontrado"}

    if es_usuario_nuevo(user_id):
        nombre_usuario = usuario_existe.get("username", "Usuario") if usuario_existe else "Usuario Demo"
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

    # Usuario ya tiene progreso
    progreso = progreso_chatbot_col.find_one({"id_usuario": user_id})
    nombre = obtener_nombre_usuario(user_id)
    mensaje = (
        f"¡Bienvenido de vuelta {nombre}! "
        f"Estabas practicando {progreso.get('tema', 'un tema pendiente')} "
        f"en el Bloque {progreso.get('bloque', 'N/A')}."
    )
    return {
        "mensaje": mensaje,
        "siguiente": {"endpoint": "/chatbot/seleccionar_bloque"},
        "tema_en_progreso": progreso.get("tema"),
        "bloque_en_progreso": progreso.get("bloque"),
        "usuario_nuevo": False
    }

# ---------------------------
# Selección de bloque
# ---------------------------
@app.post("/chatbot/seleccionar_bloque")
def seleccionar_bloque(data: SeleccionBloque):
    bloques_validos = [1, 2, 3, 4]
    if data.bloque not in bloques_validos:
        return {"mensaje": "Selecciona un bloque válido (1 al 4)"}

    progreso_chatbot_col.update_one(
        {"id_usuario": data.user_id},
        {"$set": {"bloque": data.bloque, "tema": None}},
        upsert=True
    )

    temas = list(preguntas[data.bloque].keys())
    return {
        "mensaje": f"Excelente 🎯. Estás en el Bloque {data.bloque}. Elige un tema:",
        "opciones": temas,
        "siguiente": {"endpoint": "/chatbot/seleccionar_tema"}
    }

# ---------------------------
# Selección de tema
# ---------------------------
@app.post("/chatbot/seleccionar_tema")
def seleccionar_tema(data: SeleccionTema):
    bloque = progreso_chatbot_col.find_one({"id_usuario": data.user_id}).get("bloque")
    if bloque is None:
        return {"mensaje": "Primero selecciona un bloque."}

    temas_disponibles = list(preguntas[bloque].keys())
    tema_lower = data.tema.lower()

    if tema_lower not in [t.lower() for t in temas_disponibles]:
        return {"mensaje": f"Tema no válido. Temas disponibles: {', '.join(temas_disponibles)}"}

    progreso_chatbot_col.update_one(
        {"id_usuario": data.user_id},
        {"$set": {"tema": tema_lower, "indice_pregunta": 0, "correctas": 0}}
    )

    lista_preguntas = obtener_preguntas(bloque, tema_lower, data.user_id)
    progreso_chatbot_col.update_one(
        {"id_usuario": data.user_id},
        {"$set": {"preguntas_actuales": lista_preguntas}}
    )

    primera = lista_preguntas[0]
    return {
        "mensaje": f"Perfecto 💡. Empecemos con el tema {tema_lower}.",
        "pregunta": primera["pregunta"],
        "opciones": primera["opciones"],
        "numero_pregunta": 1,
        "total_preguntas": len(lista_preguntas),
        "siguiente": {"endpoint": "/chatbot/responder"}
    }

# ---------------------------
# Responder preguntas
# ---------------------------
@app.post("/chatbot/responder")
def responder(data: RespuestaUsuario):
    progreso = progreso_chatbot_col.find_one({"id_usuario": data.user_id})
    bloque = progreso.get("bloque")
    tema = progreso.get("tema")
    preguntas_actuales = progreso.get("preguntas_actuales", [])
    indice = progreso.get("indice_pregunta", 0)

    if indice >= len(preguntas_actuales):
        return {"mensaje": "Ya completaste este tema 🎉", "completado": True}

    pregunta_actual = preguntas_actuales[indice]
    respuesta_correcta = pregunta_actual["respuesta"].strip().lower()
    respuesta_usuario = data.respuesta.strip().lower()

    correcto = respuesta_usuario == respuesta_correcta

    historial_preguntas_col.insert_one({
        "id_usuario": data.user_id,
        "bloque": bloque,
        "tema": tema,
        "pregunta": pregunta_actual["pregunta"],
        "respuesta_usuario": respuesta_usuario,
        "correcto": correcto,
        "fecha": datetime.datetime.utcnow()
    })

    progreso_chatbot_col.update_one(
        {"id_usuario": data.user_id},
        {"$inc": {"indice_pregunta": 1, "correctas": 1 if correcto else 0}}
    )

    if indice + 1 >= len(preguntas_actuales):
        return {
            "mensaje": f"{'✅ Correcto' if correcto else '❌ Incorrecto'}.\nCompletaste todas las preguntas de este tema.",
            "completado": True
        }

    siguiente_pregunta = preguntas_actuales[indice + 1]
    return {
        "mensaje": f"{'✅ Correcto' if correcto else '❌ Incorrecto'}.",
        "pregunta": siguiente_pregunta["pregunta"],
        "opciones": siguiente_pregunta["opciones"],
        "numero_pregunta": indice + 2,
        "total_preguntas": len(preguntas_actuales),
        "siguiente": {"endpoint": "/chatbot/responder"},
        "completado": False
    }

# ---------------------------
# Ejecutar servidor
# ---------------------------
if __name__ == "__main__":
    import uvicorn
    PORT = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)
