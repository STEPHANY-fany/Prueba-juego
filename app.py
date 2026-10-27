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
# Segundos que se espera a que un jugador desconectado vuelva antes de sacarlo
# del lobby o de darle el combate por perdido.
GRACE_SECONDS = float(os.environ.get("RECONNECT_GRACE_SECONDS", "45"))

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
    {"q": "¿Cuál es la función principal de Hadoop?", "options": [
        "Editar imágenes", "Almacenar y procesar grandes volúmenes de datos de forma distribuida",
        "Crear páginas web", "Diseñar bases de datos únicamente"
    ], "answer": 1, "explain": "Hadoop permite distribuir almacenamiento y procesamiento entre varias computadoras."},
    {"q": "¿Qué componente almacena archivos en bloques distribuidos?", "options": [
        "YARN", "Hadoop Common", "HDFS", "MapReduce"
    ], "answer": 2, "explain": "HDFS es el sistema de archivos distribuido de Hadoop."},
    {"q": "¿Qué administra los metadatos de HDFS?", "options": [
        "NameNode", "DataNode", "Reducer", "NodeManager"
    ], "answer": 0, "explain": "El NameNode mantiene metadatos como nombres de archivos y ubicación de bloques."},
    {"q": "¿Qué almacena los bloques reales de los archivos en HDFS?", "options": [
        "ResourceManager", "DataNode", "NameNode", "Hive"
    ], "answer": 1, "explain": "Los DataNodes almacenan los bloques y atienden operaciones de lectura y escritura."},
    {"q": "¿Para qué sirve YARN?", "options": [
        "Para dibujar gráficos", "Para comprimir todas las imágenes",
        "Para administrar recursos y coordinar aplicaciones", "Para sustituir HDFS"
    ], "answer": 2, "explain": "YARN gestiona recursos del clúster, como memoria y capacidad de procesamiento."},
    {"q": "¿Qué componente de YARN administra recursos del clúster?", "options": [
        "ResourceManager", "NameNode", "DataNode", "Mapper"
    ], "answer": 0, "explain": "El ResourceManager administra los recursos disponibles del clúster."},
    {"q": "¿Qué hace un NodeManager?", "options": [
        "Administra cada nodo trabajador", "Guarda todos los metadatos de HDFS",
        "Es una distribución comercial", "Agrupa resultados de MapReduce"
    ], "answer": 0, "explain": "El NodeManager gestiona recursos y tareas en un nodo."},
    {"q": "¿Cuáles son las dos fases principales del modelo MapReduce?", "options": [
        "Read y Write", "Map y Reduce", "Start y Stop", "Store y Search"
    ], "answer": 1, "explain": "Map genera resultados intermedios y Reduce los combina."},
    {"q": "En MapReduce, ¿qué ocurre durante Shuffle y Sort?", "options": [
        "Se apaga el clúster", "Se eliminan los datos originales",
        "Se agrupan los valores por clave", "Se crean usuarios"
    ], "answer": 2, "explain": "Shuffle y Sort transfieren y agrupan resultados intermedios por clave."},
    {"q": "¿Qué incluye Hadoop Common?", "options": [
        "Bibliotecas y utilidades compartidas", "Solo una interfaz gráfica",
        "Únicamente datos de ventas", "Un sistema operativo"
    ], "answer": 0, "explain": "Hadoop Common contiene utilidades y bibliotecas comunes a los módulos de Hadoop."},
    {"q": "¿Qué herramienta del ecosistema permite consultar datos con un lenguaje similar a SQL?", "options": [
        "HBase", "Hive", "NameNode", "Ambari"
    ], "answer": 1, "explain": "Hive permite realizar consultas sobre grandes conjuntos de datos mediante HiveQL."},
    {"q": "¿Qué tipo de base de datos es HBase?", "options": [
        "Relacional tradicional", "NoSQL distribuida orientada a columnas", "Un lenguaje de programación", "Un navegador web"
    ], "answer": 1, "explain": "HBase es una base de datos NoSQL distribuida basada en familias de columnas."},
    {"q": "¿Qué describe mejor la computación distribuida?", "options": [
        "Una sola computadora hace todo", "Varias computadoras colaboran en una tarea",
        "Los datos no se guardan", "Solo se trabaja sin internet"
    ], "answer": 1, "explain": "La computación distribuida reparte almacenamiento o procesamiento entre varias máquinas."},
    {"q": "¿Para qué sirve la replicación de bloques en HDFS?", "options": [
        "Para decorar la interfaz", "Para aumentar la resolución de imágenes",
        "Para reducir el riesgo de pérdida de datos ante fallos", "Para borrar archivos duplicados siempre"
    ], "answer": 2, "explain": "Las réplicas ayudan a mantener disponibilidad si falla un nodo."},
    {"q": "¿Qué era Hortonworks Data Platform (HDP)?", "options": [
        "Una distribución del ecosistema Hadoop", "Un componente físico de una computadora",
        "Un algoritmo de cifrado", "Un tipo de archivo de imagen"
    ], "answer": 0, "explain": "Hortonworks ofrecía una plataforma integrada basada en proyectos de código abierto del ecosistema Hadoop."},
    {"q": "¿Qué fue MapR?", "options": [
        "Una distribución/plataforma empresarial compatible con el ecosistema Hadoop",
        "Una fase de MapReduce", "El nombre del NameNode", "Un lenguaje SQL"
    ], "answer": 0, "explain": "MapR fue una plataforma comercial con tecnologías propias para datos distribuidos."},
    {"q": "¿Cuál afirmación sobre Hadoop es correcta?", "options": [
        "Predice automáticamente sin modelos", "Solo funciona con imágenes",
        "Distribuye almacenamiento y procesamiento, pero el análisis depende de las herramientas usadas",
        "No puede trabajar con varios equipos"
    ], "answer": 2, "explain": "Hadoop es infraestructura; las predicciones requieren desarrollar o integrar modelos y herramientas."},
    {"q": "Una óptica quiere contar cuántos lentes de cada tipo vendió. ¿Qué enfoque encaja con MapReduce?", "options": [
        "Map crea conteos parciales y Reduce los suma", "NameNode diseña lentes",
        "YARN responde por los clientes", "HDFS calcula la predicción por sí solo"
    ], "answer": 0, "explain": "Map puede generar pares tipo (producto, 1) y Reduce sumar por producto."},
    {"q": "¿Cuál es una limitación del MapReduce tradicional?", "options": [
        "No puede procesar datos", "Está orientado al procesamiento por lotes y puede ser poco adecuado para baja latencia",
        "Solo funciona con una máquina", "No utiliza datos"
    ], "answer": 1, "explain": "MapReduce tradicional está pensado principalmente para trabajos por lotes."},
    {"q": "¿Qué herramienta se asocia con la administración de clústeres en Hortonworks HDP?", "options": [
        "Apache Ambari", "Photoshop", "PowerPoint", "Notepad"
    ], "answer": 0, "explain": "Apache Ambari ofrece herramientas de aprovisionamiento, administración y supervisión de clústeres."}
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
    "tournament_round": 0
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


def public_state():
    with LOCK:
        players = []
        for pid, p in state["players"].items():
            players.append({
                "id": pid, "name": p["name"], "hp": p["hp"], "avatar": p["avatar"],
                "alive": p["hp"] > 0, "connected": p.get("connected", True),
                "answered": p.get("answered", False),
                "correct": p.get("correct", False)
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
            "alive_count": sum(1 for p in state["players"].values() if p["hp"] > 0)
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
    socketio.emit("game_over", {"winner": state["winner"]}, to=ROOM)


def finish_match(pair, winner_pid):
    pair["winner"] = winner_pid
    # Si solo queda un combate, es la final: el campeón se anuncia sin esperar al anfitrión.
    if len(state["pairs"]) == 1 and not state["winner"]:
        declare_champion(winner_pid)


def form_next_round():
    winners = [pair["winner"] for pair in state["pairs"]]
    state["tournament_round"] += 1
    state["pairs"] = make_pairs(winners)
    for pair in state["pairs"]:
        for pid in pair["players"]:
            state["players"][pid]["hp"] = 100


def next_question_internal():
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
    socketio.emit("new_question", state["question"], to=ROOM)


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
        "answered": False, "correct": False, "byes": 0, "token": token
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
        "question_index": -1, "used_questions": []
    })
    for p in state["players"].values():
        p.update({"hp": 100, "answered": False, "correct": False, "byes": 0})
    state["pairs"] = make_pairs(state["players"].keys())
    next_question_internal()
    broadcast_state()


@socketio.on("next_question")
@locked
def next_question(*_):
    if not is_host():
        emit("notice", {"type": "error", "message": "Solo el anfitrión puede avanzar las preguntas."})
        return
    if not state["game_started"]:
        emit("notice", {"type": "error", "message": "Primero inicia la partida."})
        return
    next_question_internal()
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
    finish_match(pair, pid)
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
    broadcast_state()


def hit(attacker_pid, target_id, pair):
    """Un acierto golpea de inmediato al rival del combate; no hay botón de ataque."""
    attacker = state["players"][attacker_pid]
    target = state["players"][target_id]
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
        "pairs": [], "tournament_round": 0
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
                finish_match(pair, winner)
                socketio.emit("notice", {
                    "type": "error",
                    "message": f'{state["players"][loser]["name"]} se desconectó: {state["players"][winner]["name"]} avanza por abandono.'
                }, to=ROOM)
                changed = True
        if changed:
            broadcast_state()


def reaper_loop():
    while True:
        socketio.sleep(1)
        try:
            reap_disconnected()
        except Exception:
            app.logger.exception("Error al revisar jugadores desconectados")


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
    socketio.start_background_task(reaper_loop)
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)
