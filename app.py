import os
import random
import secrets
import socket
import threading
import time
from functools import wraps

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room


def load_env_file(path):
    """Lee un archivo .env sencillo (CLAVE=valor) sin pisar variables ya definidas."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    except OSError:
        pass


load_env_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "cambia-esta-clave")
socketio = SocketIO(
    app, cors_allowed_origins="*", async_mode="threading",
    ping_interval=10, ping_timeout=30,
)

HOST_PIN = os.environ.get("HOST_PIN", "1234")
ROOM = "hadoop-battle"
MAX_PLAYERS = 80
DAMAGE = 20
# Puntos del ranking: cada acierto golpea (+10) y ganar un combate suma +50 (el descanso no suma).
POINTS_HIT = 10
POINTS_WIN = 50
RANKING_TOP = 3
# Segundos que se espera a que un jugador desconectado vuelva antes de sacarlo
# del lobby o de darle el combate por perdido.
GRACE_SECONDS = float(os.environ.get("RECONNECT_GRACE_SECONDS", "45"))
# Tiempo para responder cada pregunta y duración del resumen del ranking entre preguntas.
QUESTION_SECONDS = float(os.environ.get("QUESTION_SECONDS", "20"))
REVIEW_SECONDS = float(os.environ.get("REVIEW_SECONDS", "6"))

# Los handlers de Socket.IO corren en hilos distintos y comparten `state`:
# un solo candado reentrante serializa cualquier lectura o escritura.
LOCK = threading.RLock()


def locked(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        with LOCK:
            return fn(*args, **kwargs)
    return wrapper

QUESTIONS = [
    {
        "q": "¿Cuál es la función principal de Apache Hadoop?",
        "options": [
            "Editar imágenes y documentos",
            "Almacenar y procesar datos distribuidos en clústeres",
            "Crear páginas web",
            "Administrar únicamente bases de datos relacionales"
        ],
        "answer": 1,
        "explain": "Hadoop es un marco de software para almacenar y procesar datos distribuidos en clústeres."
    },
    {
        "q": "¿Por qué surge la necesidad de distribuir los datos entre varias máquinas?",
        "options": [
            "Para evitar utilizar almacenamiento",
            "Porque una sola computadora puede convertirse en un límite de capacidad o rendimiento",
            "Para eliminar todos los archivos duplicados",
            "Porque las computadoras no pueden procesar datos individualmente"
        ],
        "answer": 1,
        "explain": "La presentación explica que un solo equipo puede convertirse en un límite de capacidad o rendimiento."
    },
    {
        "q": "¿Cuáles son los tres componentes principales de Hadoop que se presentan?",
        "options": [
            "HDFS, YARN y MapReduce",
            "NameNode, Reduce y Hortonworks",
            "HDFS, DataNode y Cloudera",
            "Map, Shuffle y Sort"
        ],
        "answer": 0,
        "explain": "HDFS se encarga del almacenamiento distribuido, YARN de la gestión de recursos y MapReduce del procesamiento."
    },
    {
        "q": "¿Cuál es la función principal de HDFS?",
        "options": [
            "Administrar las aplicaciones del clúster",
            "Almacenar archivos en bloques distribuidos entre diferentes nodos",
            "Combinar los resultados de Reduce",
            "Coordinar exclusivamente los recursos de memoria"
        ],
        "answer": 1,
        "explain": "HDFS divide los archivos en bloques que se distribuyen entre los DataNodes."
    },
    {
        "q": "¿Qué función tiene el NameNode en HDFS?",
        "options": [
            "Almacenar exclusivamente todos los bloques de datos",
            "Administrar el espacio de nombres y los metadatos",
            "Ejecutar la fase Reduce",
            "Asignar recursos a todas las aplicaciones"
        ],
        "answer": 1,
        "explain": "El NameNode administra el espacio de nombres y los metadatos de HDFS."
    },
    {
        "q": "¿Qué función cumplen los DataNodes?",
        "options": [
            "Gestionar los metadatos del espacio de nombres",
            "Almacenar los bloques de archivos distribuidos",
            "Coordinar la fusión de empresas",
            "Administrar exclusivamente las aplicaciones"
        ],
        "answer": 1,
        "explain": "Los DataNodes almacenan los bloques de datos distribuidos en HDFS."
    },
    {
        "q": "¿Para qué sirve la replicación de bloques en HDFS?",
        "options": [
            "Para convertir los archivos en pares clave-valor",
            "Para ayudar a recuperarse ante fallos de nodos",
            "Para sustituir al NameNode",
            "Para ordenar los valores de MapReduce"
        ],
        "answer": 1,
        "explain": "La presentación señala que la replicación ayuda a recuperarse ante fallos de nodos."
    },
    {
        "q": "¿Qué ocurre cuando un cliente quiere leer un archivo almacenado en HDFS?",
        "options": [
            "El cliente consulta al NameNode para localizar los bloques y después los obtiene de los DataNodes",
            "El cliente solicita todos los datos directamente a YARN",
            "Reduce localiza los bloques y los almacena en el NameNode",
            "Hortonworks convierte el archivo en una aplicación"
        ],
        "answer": 0,
        "explain": "El cliente consulta al NameNode para localizar los bloques y obtiene los datos desde los DataNodes."
    },
    {
        "q": "¿Cuál es la función de YARN?",
        "options": [
            "Almacenar archivos en bloques",
            "Gestionar recursos y aplicaciones del clúster",
            "Clasificar los bloques por nombre",
            "Sustituir el almacenamiento distribuido"
        ],
        "answer": 1,
        "explain": "YARN administra los recursos y las aplicaciones que se ejecutan en el clúster."
    },
    {
        "q": "¿Qué componente de YARN arbitra los recursos del clúster?",
        "options": [
            "DataNode",
            "ResourceManager",
            "NameNode",
            "Reducer"
        ],
        "answer": 1,
        "explain": "El ResourceManager arbitra los recursos disponibles del clúster."
    },
    {
        "q": "¿Qué función tiene el NodeManager según la presentación?",
        "options": [
            "Gestionar recursos y contenedores en su máquina",
            "Administrar el espacio de nombres de HDFS",
            "Agrupar todas las claves de Reduce",
            "Almacenar las referencias históricas de Hortonworks"
        ],
        "answer": 0,
        "explain": "Cada NodeManager gestiona recursos y contenedores en su máquina."
    },
    {
        "q": "¿Qué función tiene el ApplicationMaster?",
        "options": [
            "Administrar los metadatos de todos los archivos",
            "Coordinar la ejecución de cada aplicación",
            "Almacenar las réplicas de HDFS",
            "Combinar obligatoriamente todos los archivos del clúster"
        ],
        "answer": 1,
        "explain": "El ApplicationMaster coordina la ejecución de cada aplicación."
    },
    {
        "q": "¿Cuáles son las fases principales del procesamiento MapReduce que aparecen en la presentación?",
        "options": [
            "Read, Write y Delete",
            "Map, Shuffle and Sort y Reduce",
            "HDFS, YARN y DataNode",
            "NameNode, ResourceManager y ApplicationMaster"
        ],
        "answer": 1,
        "explain": "Map transforma registros, Shuffle and Sort agrupa valores por clave y Reduce combina los valores."
    },
    {
        "q": "¿Qué produce la fase Map?",
        "options": [
            "Pares clave-valor intermedios",
            "Únicamente archivos de configuración",
            "Metadatos del NameNode",
            "Una lista de recursos del clúster"
        ],
        "answer": 0,
        "explain": "Map transforma los registros de entrada en pares clave-valor intermedios."
    },
    {
        "q": "¿Qué sucede durante Shuffle and Sort?",
        "options": [
            "Se eliminan todos los valores repetidos",
            "Se agrupan y ordenan los valores por clave",
            "Se distribuyen los archivos únicamente entre los usuarios",
            "Se detienen las aplicaciones del clúster"
        ],
        "answer": 1,
        "explain": "Shuffle and Sort agrupa y organiza los valores intermedios de acuerdo con su clave."
    },
    {
        "q": "¿Cuál es la función de Reduce?",
        "options": [
            "Localizar los bloques de HDFS",
            "Administrar los recursos de cada máquina",
            "Combinar los valores asociados a cada clave para producir resultados",
            "Dividir los archivos originales en bloques"
        ],
        "answer": 2,
        "explain": "Reduce combina los valores asociados a una misma clave para obtener los resultados."
    },
    {
        "q": "En el ejemplo de conteo de palabras, ¿cuál sería el resultado para la entrada 'sol luna sol'?",
        "options": [
            "sol: 1, luna: 2",
            "sol: 2, luna: 1",
            "sol: 3, luna: 3",
            "sol: 1, luna: 1"
        ],
        "answer": 1,
        "explain": "La palabra sol aparece dos veces y luna aparece una vez."
    },
    {
        "q": "En el ejemplo de las pizzas, ¿qué representa el par (Pepperoni, 1)?",
        "options": [
            "Un bloque almacenado en HDFS",
            "Una aparición de la pizza Pepperoni en los datos de entrada",
            "Un recurso asignado por YARN",
            "El resultado final de todas las ventas"
        ],
        "answer": 1,
        "explain": "Map emite un par por cada aparición de una pizza, utilizando su nombre como clave y 1 como valor."
    },
    {
        "q": "¿Cuál de las siguientes opciones aparece como una aplicación de Hadoop en la presentación?",
        "options": [
            "Indexación web en motores de búsqueda",
            "Diseño exclusivo de interfaces gráficas",
            "Edición manual de fotografías",
            "Creación de animaciones sin procesamiento de datos"
        ],
        "answer": 0,
        "explain": "La presentación menciona la indexación web, el análisis de registros, las redes sociales y el comercio electrónico."
    },
    {
        "q": "¿Qué significa la localidad de datos?",
        "options": [
            "Procesar los datos donde están almacenados para evitar tráfico pesado en la red",
            "Guardar todos los datos en una sola computadora",
            "Eliminar las aplicaciones que utilizan el clúster",
            "Transferir obligatoriamente todos los datos a una máquina central"
        ],
        "answer": 0,
        "explain": "La localidad de datos busca procesar la información donde está almacenada, reduciendo el tráfico de red."
    },
    {
        "q": "¿Cuál de las siguientes opciones es una ventaja de Hadoop mencionada en la presentación?",
        "options": [
            "Respuestas instantáneas garantizadas para cualquier aplicación",
            "Escalabilidad económica al añadir servidores estándar",
            "Ausencia total de mantenimiento",
            "Eliminación de todos los errores de entrada"
        ],
        "answer": 1,
        "explain": "La presentación destaca que la capacidad puede crecer añadiendo servidores estándar."
    },
    {
        "q": "¿Cuál es una limitación de MapReduce señalada en la presentación?",
        "options": [
            "No puede distribuir el trabajo",
            "Es lento para aplicaciones que requieren respuestas en tiempo real",
            "No puede generar resultados",
            "Solo permite almacenar archivos de imágenes"
        ],
        "answer": 1,
        "explain": "La presentación indica que MapReduce puede ser ineficiente cuando se necesitan respuestas inmediatas."
    },
    {
        "q": "¿Qué problema puede generar el uso constante de disco durante el procesamiento?",
        "options": [
            "Cuellos de botella en el rendimiento",
            "La eliminación automática de todos los DataNodes",
            "La desaparición del NameNode",
            "La conversión de YARN en una base de datos"
        ],
        "answer": 0,
        "explain": "La lectura y escritura constante en HDFS puede generar cuellos de botella."
    },
    {
        "q": "¿Qué fue Hortonworks?",
        "options": [
            "Una empresa centrada en tecnologías del ecosistema Hadoop",
            "Una fase de MapReduce",
            "Un componente encargado de almacenar bloques",
            "Un tipo de archivo distribuido"
        ],
        "answer": 0,
        "explain": "La presentación describe a Hortonworks como una empresa centrada en tecnologías del ecosistema Hadoop."
    },
    {
        "q": "¿Qué era Hortonworks Data Platform (HDP)?",
        "options": [
            "Una distribución empresarial basada en Apache Hadoop",
            "Un componente de hardware del NameNode",
            "Una fase de procesamiento de MapReduce",
            "Un lenguaje de programación para imágenes"
        ],
        "answer": 0,
        "explain": "HDP integraba Hadoop y otros proyectos Apache como una distribución empresarial."
    },
    {
        "q": "¿En qué año se fundó Hortonworks, según la línea de tiempo?",
        "options": [
            "2004",
            "2011",
            "2018",
            "2021"
        ],
        "answer": 1,
        "explain": "La presentación indica que Hortonworks se fundó en 2011."
    },
    {
        "q": "¿En qué año se lanzó Hortonworks Data Platform (HDP)?",
        "options": [
            "2011",
            "2012",
            "2018",
            "2019"
        ],
        "answer": 1,
        "explain": "La línea de tiempo de la presentación indica que HDP se lanzó en 2012."
    },
    {
        "q": "¿Cuándo anunciaron Hortonworks y Cloudera su fusión?",
        "options": [
            "3 de enero de 2019",
            "8 de octubre de 2021",
            "3 de octubre de 2018",
            "Diciembre de 2021"
        ],
        "answer": 2,
        "explain": "La presentación sitúa el anuncio de la fusión el 3 de octubre de 2018."
    },
    {
        "q": "¿Cuándo se completó la fusión de Hortonworks y Cloudera?",
        "options": [
            "3 de enero de 2019",
            "3 de octubre de 2018",
            "En 2011",
            "En diciembre de 2021"
        ],
        "answer": 0,
        "explain": "Según la presentación, la fusión se completó el 3 de enero de 2019 bajo el nombre Cloudera."
    },
    {
        "q": "¿Qué indica la presentación sobre el soporte ordinario de HDP 3.1?",
        "options": [
            "Terminó en diciembre de 2021",
            "Terminó en octubre de 2018",
            "Continúa indefinidamente sin cambios",
            "Terminó cuando se fundó Hortonworks"
        ],
        "answer": 0,
        "explain": "La diapositiva sobre productos históricos indica que el soporte ordinario de HDP 3.1 terminó en diciembre de 2021."
    },
    {
        "q": "¿Qué criterio debe considerarse al elegir entre Hadoop y otros enfoques de procesamiento?",
        "options": [
            "Únicamente el nombre de la empresa",
            "La latencia, el volumen de datos, la operación, los costes y los requisitos técnicos",
            "Solamente el número de archivos",
            "El diseño visual de la interfaz"
        ],
        "answer": 1,
        "explain": "La presentación señala que la elección depende de la latencia, el volumen, la operación, los costes y los requisitos técnicos."
    },
    {
        "q": "¿Qué función cumple HDFS en el caso ilustrativo de procesamiento por categorías?",
        "options": [
            "Almacena los registros distribuidos en bloques",
            "Asigna los recursos a la aplicación",
            "Combina por sí solo los resultados finales",
            "Coordina la ejecución de cada aplicación"
        ],
        "answer": 0,
        "explain": "En el ejemplo, HDFS almacena los registros distribuidos en bloques."
    },
    {
        "q": "En el mismo caso ilustrativo, ¿qué función cumple YARN?",
        "options": [
            "Almacena los bloques de registros",
            "Asigna recursos a la aplicación de procesamiento",
            "Cuenta directamente todas las categorías",
            "Replica exclusivamente los resultados finales"
        ],
        "answer": 1,
        "explain": "La presentación indica que YARN asigna recursos a la aplicación de procesamiento."
    },
    {
        "q": "¿Cuál de los siguientes retos de implementación de Hadoop se menciona en la presentación?",
        "options": [
            "La imposibilidad de distribuir el almacenamiento",
            "La operación del clúster, la planificación de recursos, la seguridad y el mantenimiento",
            "La ausencia de procesamiento paralelo",
            "La imposibilidad de recuperar datos ante fallos"
        ],
        "answer": 1,
        "explain": "La presentación identifica la operación del clúster, la planificación de recursos, la seguridad y el mantenimiento como retos."
    },
    {
        "q": "¿Cuál es la idea principal que resume la relación entre HDFS, YARN y MapReduce?",
        "options": [
            "Los tres cumplen exactamente la misma función",
            "HDFS almacena datos, YARN gestiona recursos y MapReduce procesa pares clave-valor",
            "MapReduce almacena los archivos y HDFS coordina las aplicaciones",
            "YARN sustituye por completo a HDFS y MapReduce"
        ],
        "answer": 1,
        "explain": "La conclusión de la presentación distingue las funciones de almacenamiento, gestión de recursos y procesamiento."
    }
]

hosts = set()          # conexiones (sid) con permisos de anfitrión
host_tokens = set()    # tokens que permiten recuperar el rol de anfitrión tras recargar
token_to_pid = {}      # token secreto del jugador -> id público
sid_to_pid = {}        # conexión actual -> id público
CHARACTERS = ["goro1.png","goroa.png","gorob.png","goroc.png","hana2.png","hanaa.png","hanna.png","hannab.png","kai1.png","kai2.png","kai4.png","kaia.png","rei1.png","rei3.png","rei4.png","reia.png","yuki1.png","yuki2.png","yukia.png","yukib.png"]

# `players` se indexa por id público (pid), no por la conexión: así un jugador
# que recarga o pierde la red conserva su lugar en el torneo.
state = {
    "players": {},
    "question_index": -1,
    "question": None,
    "round": 0,
    "game_started": False,
    "used_questions": [],
    "winner": None,
    "pairs": [],
    "tournament_round": 0,
    # Ciclo de preguntas: lobby -> question (con plazo) -> review (resumen) -> question ... -> over
    "phase": "lobby",
    "deadline": 0.0,
    "review_until": 0.0,
    "review": None,
    "question_events": [],
    "rank_base": {}
}


def as_dict(data):
    return data if isinstance(data, dict) else {}


def is_host():
    return request.sid in hosts


def current_pid():
    return sid_to_pid.get(request.sid)


def find_pair(pid):
    return next((pair for pair in state["pairs"] if pid in pair["players"]), None)


def abandoned(p, now):
    """Desconectado por más tiempo del permitido."""
    return (not p.get("connected", True)) and now - p.get("disconnected_at", now) >= GRACE_SECONDS


def attach_sid(pid, sid):
    p = state["players"][pid]
    old = p.get("sid")
    if old and old != sid:
        sid_to_pid.pop(old, None)
    p["sid"] = sid
    p["connected"] = True
    p.pop("disconnected_at", None)
    sid_to_pid[sid] = pid


def drop_player(pid):
    p = state["players"].pop(pid, None)
    if p:
        token_to_pid.pop(p.get("token"), None)
        sid_to_pid.pop(p.get("sid"), None)


def ranking():
    """Ids ordenados por puntos, victorias, aciertos y nombre (los eliminados también cuentan)."""
    return sorted(state["players"], key=lambda pid: (
        -state["players"][pid]["points"], -state["players"][pid]["wins"],
        -state["players"][pid]["hits"], state["players"][pid]["name"].lower()))


def ranking_view(limit=RANKING_TOP):
    """Los primeros puestos; `delta` es cuántos lugares subió (+) o bajó (-) desde que empezó la pregunta."""
    base = state["rank_base"]
    view = []
    for rank, pid in enumerate(ranking()[:limit], start=1):
        p = state["players"][pid]
        view.append({
            "rank": rank, "id": pid, "name": p["name"], "points": p["points"], "wins": p["wins"],
            "alive": p["hp"] > 0, "delta": base[pid] - rank if pid in base else 0
        })
    return view


def seconds_left(now):
    if state["phase"] == "question":
        return round(max(0.0, state["deadline"] - now), 2)
    if state["phase"] == "review":
        return round(max(0.0, state["review_until"] - now), 2)
    return 0.0


def public_state():
    with LOCK:
        now = time.time()
        ranks = {pid: rank for rank, pid in enumerate(ranking(), start=1)}
        players = []
        for pid, p in state["players"].items():
            players.append({
                "id": pid, "name": p["name"], "hp": p["hp"], "avatar": p["avatar"],
                "alive": p["hp"] > 0, "connected": p.get("connected", True),
                "answered": p.get("answered", False),
                "correct": p.get("correct", False),
                "points": p["points"], "wins": p["wins"], "rank": ranks[pid]
            })
        players.sort(key=lambda x: (-x["alive"], -x["hp"], x["name"].lower()))
        pair_for = {}
        for pair in state["pairs"]:
            for pid in pair["players"]:
                pair_for[pid] = pair
        for player in players:
            pair = pair_for.get(player["id"], {})
            other = next((pid for pid in pair.get("players", []) if pid != player["id"]), None)
            player["opponent_id"] = other
            player["opponent_name"] = state["players"][other]["name"] if other in state["players"] else None
        pairs = [{
            "players": list(pair["players"]),
            "names": [state["players"][pid]["name"] for pid in pair["players"] if pid in state["players"]],
            "winner": pair.get("winner")
        } for pair in state["pairs"]]
        pending = sum(1 for pair in state["pairs"] if len(pair["players"]) == 2 and not pair.get("winner"))
        return {
            "players": players,
            "pairs": pairs,
            "pending_matches": pending,
            "tournament_round": state["tournament_round"],
            "question": state["question"],
            "round": state["round"],
            "game_started": state["game_started"],
            "winner": state["winner"],
            "alive_count": sum(1 for p in state["players"].values() if p["hp"] > 0),
            "phase": state["phase"],
            "seconds_left": seconds_left(now),
            "question_seconds": QUESTION_SECONDS,
            "review_seconds": REVIEW_SECONDS,
            "ranking": ranking_view(),
            "review": state["review"] if state["phase"] == "review" else None
        }


def broadcast_state():
    socketio.emit("state_update", public_state(), to=ROOM)


def make_pairs(ids):
    """Empareja al azar. Con un número impar, el descanso (bye) va a quien menos ha descansado."""
    ids = list(ids)
    random.shuffle(ids)
    bye = None
    if len(ids) % 2 == 1:
        fewest = min(state["players"][pid]["byes"] for pid in ids)
        bye = random.choice([pid for pid in ids if state["players"][pid]["byes"] == fewest])
        ids.remove(bye)
    pairs = [{"players": [ids[i], ids[i + 1]], "winner": None} for i in range(0, len(ids), 2)]
    if bye:
        state["players"][bye]["byes"] += 1
        pairs.append({"players": [bye], "winner": bye})
    return pairs


def declare_champion(pid):
    state["winner"] = state["players"][pid]["name"]
    state["question"] = None
    state["phase"] = "over"
    socketio.emit("game_over", {"winner": state["winner"], "ranking": ranking_view()}, to=ROOM)


EVENT_TEXT = {
    "ko": "{w} dejó KO a {l}",
    "abandono": "{w} avanza: {l} se desconectó",
    "anfitrion": "{w} avanza por decisión del anfitrión",
}


def finish_match(pair, winner_pid, how="ko"):
    pair["winner"] = winner_pid
    winner = state["players"][winner_pid]
    winner["points"] += POINTS_WIN
    winner["wins"] += 1
    loser = next(state["players"][i] for i in pair["players"] if i != winner_pid)
    state["question_events"].append(EVENT_TEXT[how].format(w=winner["name"], l=loser["name"]))
    # Si solo queda un combate, es la final: el campeón se anuncia solo.
    if len(state["pairs"]) == 1 and not state["winner"]:
        declare_champion(winner_pid)


def form_next_round():
    winners = [pair["winner"] for pair in state["pairs"]]
    state["tournament_round"] += 1
    state["pairs"] = make_pairs(winners)
    for pair in state["pairs"]:
        for pid in pair["players"]:
            state["players"][pid]["hp"] = 100


def eligible_unanswered():
    """Quienes aún pueden responder: vivos, conectados, en un combate sin ganador y sin responder."""
    waiting = []
    for pair in state["pairs"]:
        if pair.get("winner") or len(pair["players"]) < 2:
            continue
        for pid in pair["players"]:
            p = state["players"][pid]
            if p["hp"] > 0 and p.get("connected", True) and not p["answered"]:
                waiting.append(pid)
    return waiting


def begin_question():
    """Forma la siguiente ronda si hace falta y lanza una pregunta nueva con su plazo."""
    if state["winner"]:
        return
    # Cuando todos los combates de la ronda tienen ganador, formar la siguiente ronda.
    if state["pairs"] and all(pair.get("winner") for pair in state["pairs"]):
        if len(state["pairs"]) == 1:
            declare_champion(state["pairs"][0]["winner"])
            return
        form_next_round()
    if len(state["used_questions"]) == len(QUESTIONS):
        state["used_questions"] = []
    available = [i for i in range(len(QUESTIONS)) if i not in state["used_questions"]]
    idx = random.choice(available)
    state["used_questions"].append(idx)
    state["question_index"] = idx
    state["round"] += 1
    q = QUESTIONS[idx]
    state["question"] = {"q": q["q"], "options": q["options"], "number": state["round"]}
    for p in state["players"].values():
        p.update({"answered": False, "correct": False})
    state["phase"] = "question"
    state["deadline"] = time.time() + QUESTION_SECONDS
    state["review"] = None
    state["question_events"] = []
    # Las flechas del ranking comparan contra las posiciones al empezar esta pregunta.
    state["rank_base"] = {pid: rank for rank, pid in enumerate(ranking(), start=1)}
    socketio.emit("new_question", dict(state["question"], seconds=QUESTION_SECONDS), to=ROOM)


def end_question():
    """Cierra la pregunta y abre el resumen con la respuesta correcta y el ranking."""
    if state["phase"] != "question":
        return
    q = QUESTIONS[state["question_index"]]
    state["phase"] = "review"
    state["review_until"] = time.time() + REVIEW_SECONDS
    state["review"] = {
        "number": state["round"],
        "correct": q["answer"],
        "explain": q["explain"],
        "events": state["question_events"][:6],
        "round_over": bool(state["pairs"]) and all(pair.get("winner") for pair in state["pairs"]),
        "tournament_round": state["tournament_round"],
        "ranking": ranking_view(),
    }
    socketio.emit("question_end", state["review"], to=ROOM)
    broadcast_state()


def maybe_close_question(now=None):
    """Cierra la pregunta al vencer el plazo o cuando ya respondieron todos los que podían."""
    if state["phase"] != "question":
        return
    now = time.time() if now is None else now
    if now >= state["deadline"] or not eligible_unanswered():
        end_question()


def tick_game():
    """Reloj del juego: cierra preguntas por tiempo y pasa solo de un resumen a la pregunta siguiente."""
    with LOCK:
        if not state["game_started"] or state["winner"]:
            return
        now = time.time()
        if state["phase"] == "question":
            maybe_close_question(now)
        elif state["phase"] == "review" and now >= state["review_until"]:
            begin_question()
            broadcast_state()


def resume_player(pid):
    """Devuelve a un jugador existente su lugar usando la conexión actual."""
    p = state["players"][pid]
    was_away = not p.get("connected", True)
    attach_sid(pid, request.sid)
    join_room(ROOM)
    emit("joined", {"id": pid, "name": p["name"], "token": p["token"]})
    broadcast_state()
    if was_away:
        socketio.emit("notice", {"type": "success", "message": f'{p["name"]} volvió a la arena.'}, to=ROOM)


@app.route("/")
def index():
    return render_template("index.html")


@socketio.on("join_game")
@locked
def join_game(data):
    sid = request.sid
    name = str(as_dict(data).get("name", "")).strip()[:18]
    if not name:
        emit("notice", {"type": "error", "message": "Escribe un apodo para entrar."})
        return
    pid = sid_to_pid.get(sid)
    if pid:
        # Esta conexión ya está dentro (doble clic): se confirma sin crear otro jugador.
        p = state["players"][pid]
        emit("joined", {"id": pid, "name": p["name"], "token": p["token"]})
        emit("state_update", public_state())
        return
    same_name = next((i for i, p in state["players"].items() if p["name"].casefold() == name.casefold()), None)
    if same_name:
        if state["players"][same_name].get("connected", True):
            emit("notice", {"type": "error", "message": "Ese apodo ya está ocupado. Prueba otro (si eres tú y acabas de recargar, espera unos segundos e inténtalo de nuevo)."})
        else:
            resume_player(same_name)   # quien se cayó vuelve con su mismo apodo
        return
    if state["game_started"]:
        emit("notice", {"type": "error", "message": "La partida ya comenzó. Pide al anfitrión que reinicie la sala."})
        return
    if len(state["players"]) >= MAX_PLAYERS:
        emit("notice", {"type": "error", "message": f"La sala está llena (máximo {MAX_PLAYERS} jugadores)."})
        return
    pid = secrets.token_hex(4)
    token = secrets.token_urlsafe(16)
    state["players"][pid] = {
        "name": name, "hp": 100, "avatar": random.choice(CHARACTERS), "connected": True,
        "answered": False, "correct": False, "byes": 0, "points": 0, "hits": 0, "wins": 0,
        "token": token
    }
    token_to_pid[token] = pid
    attach_sid(pid, sid)
    join_room(ROOM)
    emit("joined", {"id": pid, "name": name, "token": token})
    broadcast_state()
    socketio.emit("notice", {"type": "success", "message": f"{name} se unió a la arena."}, to=ROOM)


@socketio.on("rejoin")
@locked
def rejoin(data):
    pid = token_to_pid.get(str(as_dict(data).get("token", "")))
    if pid not in state["players"]:
        emit("rejoin_failed")
        return
    resume_player(pid)


@socketio.on("host_login")
@locked
def host_login(data):
    pin = str(as_dict(data).get("pin", ""))
    if pin != HOST_PIN:
        emit("host_auth", {"ok": False, "message": "PIN incorrecto."})
        return
    token = secrets.token_urlsafe(16)
    host_tokens.add(token)
    join_room(ROOM)
    hosts.add(request.sid)
    emit("host_auth", {"ok": True, "message": "Modo anfitrión activado.", "token": token})
    emit("state_update", public_state())


@socketio.on("host_resume")
@locked
def host_resume(data):
    token = str(as_dict(data).get("token", ""))
    if token not in host_tokens:
        emit("host_auth", {"ok": False, "silent": True, "message": ""})
        return
    join_room(ROOM)
    hosts.add(request.sid)
    emit("host_auth", {"ok": True, "silent": True, "message": "Modo anfitrión restaurado.", "token": token})
    emit("state_update", public_state())


@socketio.on("start_game")
@locked
def start_game(*_):
    if not is_host():
        emit("notice", {"type": "error", "message": "Solo el anfitrión puede iniciar la partida."})
        return
    if state["game_started"]:
        emit("notice", {"type": "error", "message": "La partida ya está en curso."})
        return
    connected = [p for p in state["players"].values() if p.get("connected", True)]
    if len(connected) < 2:
        emit("notice", {"type": "error", "message": "Necesitas al menos 2 jugadores conectados para comenzar."})
        return
    state.update({
        "game_started": True, "winner": None, "tournament_round": 1, "round": 0,
        "question_index": -1, "used_questions": [], "phase": "lobby", "review": None,
        "question_events": [], "rank_base": {}
    })
    for p in state["players"].values():
        p.update({"hp": 100, "answered": False, "correct": False, "byes": 0, "points": 0, "hits": 0, "wins": 0})
    state["pairs"] = make_pairs(state["players"].keys())
    begin_question()    # a partir de aquí el juego avanza solo (ver tick_game)
    broadcast_state()


@socketio.on("force_winner")
@locked
def force_winner(data):
    """El anfitrión decide un combate trabado (p. ej. un jugador que no vuelve)."""
    if not is_host():
        emit("notice", {"type": "error", "message": "Solo el anfitrión puede decidir un combate."})
        return
    pid = str(as_dict(data).get("winner", ""))
    pair = find_pair(pid)
    if not state["game_started"] or state["winner"] or not pair or pair.get("winner") or len(pair["players"]) < 2:
        emit("notice", {"type": "error", "message": "Ese combate no está pendiente."})
        return
    for other in pair["players"]:
        if other != pid:
            state["players"][other]["hp"] = 0
    finish_match(pair, pid, "anfitrion")
    socketio.emit("notice", {"type": "success", "message": f'El anfitrión dio el combate a {state["players"][pid]["name"]}.'}, to=ROOM)
    broadcast_state()


@socketio.on("submit_answer")
@locked
def submit_answer(data):
    pid = current_pid()
    p = state["players"].get(pid)
    if not p or p["hp"] <= 0:
        emit("notice", {"type": "error", "message": "No puedes responder porque estás eliminado o no estás en la sala."})
        return
    if not state["game_started"] or not state["question"]:
        emit("notice", {"type": "error", "message": "Todavía no hay una pregunta activa."})
        return
    if state["phase"] != "question" or time.time() >= state["deadline"]:
        emit("notice", {"type": "error", "message": "Se acabó el tiempo de esta pregunta."})
        return
    pair = find_pair(pid)
    if not pair or pair.get("winner"):
        emit("notice", {"type": "error", "message": "Tu combate ya terminó. Espera a que terminen los demás."})
        return
    if p["answered"]:
        emit("notice", {"type": "error", "message": "Ya respondiste esta ronda."})
        return
    try:
        answer = int(as_dict(data).get("answer"))
    except (TypeError, ValueError):
        return
    p["answered"] = True
    p["correct"] = answer == QUESTIONS[state["question_index"]]["answer"]
    # Mientras el combate no tiene ganador, el rival es el otro jugador de la pareja.
    rival_id = next(i for i in pair["players"] if i != pid)
    emit("answer_result", {
        "correct": p["correct"],
        "message": f'¡Correcto! Golpeaste a {state["players"][rival_id]["name"]}.' if p["correct"] else "Respuesta incorrecta. ¡Prepárate para la siguiente ronda!",
        "explanation": QUESTIONS[state["question_index"]]["explain"]
    })
    if p["correct"]:
        hit(pid, rival_id, pair)
    maybe_close_question()    # si ya respondieron todos (o acabó el último combate), no hay que esperar al reloj
    broadcast_state()


def hit(attacker_pid, target_id, pair):
    """Un acierto golpea de inmediato al rival del combate; no hay botón de ataque."""
    attacker = state["players"][attacker_pid]
    target = state["players"][target_id]
    attacker["points"] += POINTS_HIT
    attacker["hits"] += 1
    target["hp"] = max(0, target["hp"] - DAMAGE)
    ko = target["hp"] <= 0
    if ko:
        finish_match(pair, attacker_pid)
    payload = {
        "attacker": attacker["name"], "target": target["name"],
        "damage": DAMAGE, "attacker_id": attacker_pid, "target_id": target_id,
        "target_hp": target["hp"], "ko": ko
    }
    # Solo los dos peleadores reciben la animación; el resto ve el resultado en el estado.
    for fighter in pair["players"]:
        sid = state["players"][fighter].get("sid")
        if sid:
            socketio.emit("attack_animation", payload, to=sid)


@socketio.on("reset_game")
@locked
def reset_game(*_):
    if not is_host():
        emit("notice", {"type": "error", "message": "Solo el anfitrión puede reiniciar la sala."})
        return
    state["players"] = {}
    token_to_pid.clear()
    sid_to_pid.clear()
    state.update({
        "question_index": -1, "question": None, "round": 0,
        "game_started": False, "used_questions": [], "winner": None,
        "pairs": [], "tournament_round": 0, "phase": "lobby", "deadline": 0.0,
        "review_until": 0.0, "review": None, "question_events": [], "rank_base": {}
    })
    socketio.emit("reset_notice", {"message": "La sala se reinició. Vuelvan a entrar con su apodo."}, to=ROOM)
    broadcast_state()


@socketio.on("disconnect")
@locked
def disconnect(*_):
    sid = request.sid
    hosts.discard(sid)
    pid = sid_to_pid.pop(sid, None)
    p = state["players"].get(pid)
    # Si el jugador ya se reconectó con otra conexión, esta baja no cuenta.
    if p and p.get("sid") == sid:
        p["connected"] = False
        p["disconnected_at"] = time.time()
        broadcast_state()


def reap_disconnected():
    """Saca del lobby, o da por perdido el combate, a quien no volvió a tiempo."""
    with LOCK:
        now = time.time()
        changed = False
        if not state["game_started"]:
            for pid, p in list(state["players"].items()):
                if abandoned(p, now):
                    drop_player(pid)
                    changed = True
        elif not state["winner"]:
            for pair in state["pairs"]:
                if pair.get("winner") or len(pair["players"]) < 2 or state["winner"]:
                    continue
                a, b = pair["players"]
                pa, pb = state["players"][a], state["players"][b]
                gone_a, gone_b = abandoned(pa, now), abandoned(pb, now)
                if not (gone_a or gone_b):
                    continue
                if gone_a and gone_b:
                    # Se cayeron los dos: avanza quien tenga más vida (o al azar).
                    winner = max(pair["players"], key=lambda i: (state["players"][i]["hp"], random.random()))
                else:
                    winner = b if gone_a else a
                loser = a if winner == b else b
                state["players"][loser]["hp"] = 0
                finish_match(pair, winner, "abandono")
                socketio.emit("notice", {
                    "type": "error",
                    "message": f'{state["players"][loser]["name"]} se desconectó: {state["players"][winner]["name"]} avanza por abandono.'
                }, to=ROOM)
                changed = True
        if changed:
            broadcast_state()


def game_loop():
    """Reloj de fondo: cada 0.25 s hace avanzar el juego y, cada segundo, revisa a los desconectados."""
    last_reap = 0.0
    while True:
        socketio.sleep(0.25)
        try:
            tick_game()
            if time.time() - last_reap >= 1:
                last_reap = time.time()
                reap_disconnected()
        except Exception:
            app.logger.exception("Error en el ciclo del juego")


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))   # no envía nada: solo averigua la interfaz de red activa
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  Hadoop Battle Arena\n  En este equipo : http://127.0.0.1:{port}\n  En la red local: http://{lan_ip()}:{port}\n")
    socketio.start_background_task(game_loop)
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)
