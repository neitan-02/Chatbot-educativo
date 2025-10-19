# RetoMate Chatbot
Un chatbot educativo usado por el proyecto [RetoMate](https://github.com/luisillo2048/RetoMate) para practicar ejercicios de matemáticas de forma interactiva.

> Nota: Este servicio se ejecuta en paralelo al proyecto principal y expone endpoints HTTP que el frontend o backend pueden consumir.

## Descripción
Servidor FastAPI que:

- Gestiona progreso y estado por usuario (almacenado en MongoDB).
- Sirve preguntas por bloque y tema desde `preguntas.py`.
- Permite seleccionar bloque/tema, responder preguntas y persistir historial.

## Requisitos
- Python 3.10+ (recomendado)
- MongoDB disponible (local o remoto)
- `requirements.txt` en este directorio

## Instalación rápida
1. Crear y activar un entorno virtual:

```bash
python -m venv venv
source venv/bin/activate
```

2. Instalar dependencias:

```bash
pip install -r requirements.txt
```

3. Configurar variables de entorno (ejemplo `.env`):

```
MONGO_URI=mongodb://localhost:27017
PORT=8000
```

Puedes usar `python-dotenv` para cargar `.env` o exportarlas en tu shell:

```bash
export MONGO_URI="mongodb://localhost:27017"
export PORT=8000
```

## Endpoints principales (ejemplos)

- Iniciar chatbot / estado del usuario
	- GET /chatbot/inicio/{user_id}
	- Ejemplo:
		```bash
		curl http://localhost:8000/chatbot/inicio/demo_user_123
		```

- Otros endpoints esperados (revisar `main.py`):
	- POST /chatbot/saludo
	- POST /chatbot/seleccionar_bloque
	- POST /chatbot/seleccionar_tema
	- POST /chatbot/responder

Cada endpoint suele usar JSON con modelos Pydantic definidos en `main.py` (por ejemplo `Saludo`, `SeleccionBloque`, `SeleccionTema`, `RespuestaUsuario`).

## Estructura del repositorio
```
.
├── main.py                     # Servidor FastAPI principal
├── preguntas.py                # Banco de preguntas (dict por bloque/tema)
├── requirements.txt            # Dependencias del proyecto
└── README.md
```

## Integración con el proyecto principal
- El frontend/backend principal puede consumir los endpoints HTTP de este servicio.
- Compartir la misma base de datos Mongo (mismo `MONGO_URI`) permite sincronizar usuarios y progreso.
- Ajustar CORS en producción para restringir orígenes.

## Próximos pasos sugeridos
- Documentar todos los endpoints (métodos, payloads, respuestas) con ejemplos.
- Añadir tests mínimos para los endpoints principales.
- Añadir integración Docker y/o configuración para despliegue.

## Tecnologías
- FastAPI
- Uvicorn
- Pydantic
- PyMongo
- python-dotenv