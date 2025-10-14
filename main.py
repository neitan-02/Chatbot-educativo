from fastapi import FastAPI
from pydantic import BaseModel
from pymongo import MongoClient
from bson import ObjectId
import datetime
import random
import os
from fastapi.middleware.cors import CORSMiddleware
from preguntas import preguntas  

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
@app.get("/")
def read_root():
    return {"message": "Chatbot API funcionando correctamente"}

@app.get("/chatbot/inicio/{user_id}")
def iniciar_chatbot(user_id: str):
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

@app.post("/chatbot/saludo")
def saludo_usuario(saludo: Saludo):
    usuario_existe = users_col.find_one({"_id": to_objectid(saludo.user_id)})
    if not usuario_existe:
        return {"error": "Usuario no encontrado"}
    
    progreso_chatbot_col.update_one(
        {"id_usuario": saludo.user_id},
        {"$set": {
            "nombre": saludo.texto,
            "fecha_ultima_interaccion": datetime.datetime.utcnow()
        }},
        upsert=True
    )

    return {
        "mensaje": f"¡Hola {saludo.texto}! ¿Qué bloque quieres practicar hoy?",
        "opciones": ["1", "2", "3", "4"],
        "siguiente": {"endpoint": "/chatbot/seleccionar_bloque"}
    }

@app.post("/chatbot/seleccionar_bloque")
def seleccionar_bloque(seleccion: SeleccionBloque):
    if seleccion.bloque not in preguntas:
        return {"error": "Bloque no válido. Por favor selecciona un bloque entre 1 y 4"}

    progreso_chatbot_col.update_one(
        {"id_usuario": seleccion.user_id},
        {"$set": {
            "bloque": seleccion.bloque,
            "fecha_ultima_interaccion": datetime.datetime.utcnow()
        }}
    )

    temas_disponibles = list(preguntas[seleccion.bloque].keys())

    return {
        "mensaje": f"Has seleccionado el Bloque {seleccion.bloque}. ¿Qué tema quieres practicar?",
        "opciones": temas_disponibles,
        "siguiente": {"endpoint": "/chatbot/seleccionar_tema"}
    }

@app.post("/chatbot/seleccionar_tema")
def seleccionar_tema(seleccion: SeleccionTema):
    progreso = progreso_chatbot_col.find_one({"id_usuario": seleccion.user_id})
    if not progreso or progreso.get("bloque") is None:
        return {"error": "Primero debes seleccionar un bloque"}

    bloque = progreso["bloque"]
    tema = seleccion.tema.lower()

    if tema not in preguntas[bloque]:
        return {"error": f"Tema no válido para el Bloque {bloque}"}

    preguntas_tema = obtener_preguntas_alternativas(bloque, tema, seleccion.user_id)

    progreso_chatbot_col.update_one(
        {"id_usuario": seleccion.user_id},
        {"$set": {
            "tema": tema,
            "indice_pregunta": 0,
            "correctas": 0,
            "preguntas_actuales": [p["pregunta"] for p in preguntas_tema],
            "fecha_ultima_interaccion": datetime.datetime.utcnow()
        }}
    )

    primera_pregunta = preguntas_tema[0]

    return {
        "mensaje": f"¡Empecemos con {tema}! Primera pregunta:",
        "pregunta": primera_pregunta["pregunta"],
        "numero_pregunta": 1,
        "total_preguntas": len(preguntas_tema),
        "siguiente": {"endpoint": "/chatbot/responder"}
    }

@app.post("/chatbot/responder")
def responder_chatbot(respuesta: RespuestaUsuario):
    progreso = progreso_chatbot_col.find_one({"id_usuario": respuesta.user_id})
    if not progreso or progreso.get("tema") is None:
        return {"error": "Primero debes seleccionar un bloque y un tema"}

    bloque = progreso["bloque"]
    tema = progreso["tema"]
    indice = progreso.get("indice_pregunta", 0)
    correctas = progreso.get("correctas", 0)

    preguntas_tema = []
    for pregunta_text in progreso.get("preguntas_actuales", []):
        for p in preguntas[bloque][tema]:
            if p["pregunta"] == pregunta_text:
                preguntas_tema.append(p)
                break

    if indice >= len(preguntas_tema):
        progreso_chatbot_col.update_one(
            {"id_usuario": respuesta.user_id},
            {"$set": {
                "tema": None,
                "fecha_ultima_interaccion": datetime.datetime.utcnow()
            }}
        )
        return {
            "mensaje": f"¡Felicidades! Has completado todas las preguntas de {tema} en el Bloque {bloque}.",
            "correctas": correctas,
            "total_preguntas": len(preguntas_tema),
            "opciones": ["Continuar", "Salir"],
            "siguiente": {"endpoint": "/chatbot/seleccionar_bloque"},
            "completado": True
        }

    pregunta_actual = preguntas_tema[indice]
    respuesta_correcta = pregunta_actual["respuesta"]

    if respuesta.respuesta.strip().lower() in ["listo", "ya", "listo!"]:
        return {
            "mensaje": "Continuemos con la pregunta:",
            "pregunta": pregunta_actual["pregunta"],
            "numero_pregunta": indice + 1,
            "total_preguntas": len(preguntas_tema)
        }

    es_correcta = respuesta.respuesta.strip() == respuesta_correcta

    respuestas_col.insert_one({
        "id_usuario": respuesta.user_id,
        "bloque": bloque,
        "tema": tema,
        "pregunta": pregunta_actual["pregunta"],
        "respuesta_usuario": respuesta.respuesta,
        "respuesta_correcta": respuesta_correcta,
        "correcto": es_correcta,
        "fecha": datetime.datetime.utcnow()
    })

    historial_preguntas_col.update_one(
        {"id_usuario": respuesta.user_id,
         "bloque": bloque,
         "tema": tema,
         "pregunta": pregunta_actual["pregunta"]},
        {"$set": {"ultima_vez": datetime.datetime.utcnow()}},
        upsert=True
    )

    if es_correcta:
        nuevo_indice = indice + 1
        nuevas_correctas = correctas + 1

        progreso_chatbot_col.update_one(
            {"id_usuario": respuesta.user_id},
            {"$set": {
                "indice_pregunta": nuevo_indice,
                "correctas": nuevas_correctas,
                "fecha_ultima_interaccion": datetime.datetime.utcnow()
            }}
        )

        if nuevo_indice >= len(preguntas_tema):
            progreso_chatbot_col.update_one(
                {"id_usuario": respuesta.user_id},
                {"$set": {
                    "tema": None,
                    "fecha_ultima_interaccion": datetime.datetime.utcnow()
                }}
            )
            return {
                "correcto": True,
                "mensaje": f"¡Felicidades! Has completado todas las preguntas de {tema} en el Bloque {bloque}.",
                "correctas": nuevas_correctas,
                "total_preguntas": len(preguntas_tema),
                "completado": True,
                "siguiente": {"endpoint": "/chatbot/seleccionar_bloque"}
            }

        siguiente_pregunta = preguntas_tema[nuevo_indice]
        return {
            "correcto": True,
            "mensaje": "¡Respuesta correcta! 🎉",
            "siguiente_pregunta": siguiente_pregunta["pregunta"],
            "numero_pregunta": nuevo_indice + 1,
            "total_preguntas": len(preguntas_tema)
        }
    else:
        return {
            "correcto": False,
            "mensaje": "¡No te preocupes! Todos nos equivocamos, es parte del aprendizaje. 💪",
            "pregunta": pregunta_actual["pregunta"],
            "numero_pregunta": indice + 1,
            "total_preguntas": len(preguntas_tema)
        }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)