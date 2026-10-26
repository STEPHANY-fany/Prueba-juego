import os
import random
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "cambia-esta-clave")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

HOST_PIN = os.environ.get("HOST_PIN", "1234")
ROOM = "hadoop-battle"

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

hosts = set()
CHARACTERS = ["goro1.png","goroa.png","gorob.png","goroc.png","hana2.png","hanaa.png","hanna.png","hannab.png","kai1.png","kai2.png","kai4.png","kaia.png","rei1.png","rei3.png","rei4.png","reia.png","yuki1.png","yuki2.png","yukia.png","yukib.png"]

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

def public_state():
    players = []
    for sid, p in state["players"].items():
        players.append({
            "id": sid, "name": p["name"], "hp": p["hp"], "avatar": p["avatar"],
            "alive": p["hp"] > 0, "connected": p.get("connected", True),
            "attacked": p.get("attacked", False),
            "answered": p.get("answered", False),
            "correct": p.get("correct", False)
        })
    players.sort(key=lambda x: (-x["alive"], -x["hp"], x["name"].lower()))
    pair_for = {}
    for pair in state["pairs"]:
        for pid in pair.get("players", []):
            pair_for[pid] = pair
    for player in players:
        pair = pair_for.get(player["id"], {})
        other = next((pid for pid in pair.get("players", []) if pid != player["id"]), None)
        player["opponent_id"] = other
        player["opponent_name"] = state["players"].get(other, {}).get("name") if other else None
    return {
        "players": players,
        "pairs": state["pairs"],
        "tournament_round": state["tournament_round"],
        "question": state["question"],
        "round": state["round"],
        "game_started": state["game_started"],
        "winner": state["winner"],
        "alive_count": sum(1 for p in state["players"].values() if p["hp"] > 0)
    }

def broadcast_state():
    socketio.emit("state_update", public_state(), to=ROOM)

@app.route("/")
def index():
    return render_template("index.html")

@socketio.on("join_game")
def join_game(data):
    name = str((data or {}).get("name", "")).strip()[:18]
    if not name:
        emit("notice", {"type": "error", "message": "Escribe un apodo para entrar."})
        return
    if state["game_started"]:
        emit("notice", {"type": "error", "message": "La partida ya comenzó. Pide al anfitrión que reinicie la sala."})
        return
    if len(state["players"]) >= 80:
        emit("notice", {"type": "error", "message": "La sala está llena (máximo 80 jugadores)."})
        return
    existing_names = [p["name"].casefold() for p in state["players"].values()]
    if name.casefold() in existing_names:
        emit("notice", {"type": "error", "message": "Ese apodo ya está ocupado. Prueba otro."})
        return
    join_room(ROOM)
    state["players"][request.sid] = {
        "name": name, "hp": 100, "avatar": random.choice(CHARACTERS), "connected": True,
        "answered": False, "correct": False, "attacked": False
    }
    emit("joined", {"id": request.sid, "name": name})
    broadcast_state()
    socketio.emit("notice", {"type": "success", "message": f"{name} se unió a la arena."}, to=ROOM)

@socketio.on("host_login")
def host_login(data):
    pin = str((data or {}).get("pin", ""))
    if pin != HOST_PIN:
        emit("host_auth", {"ok": False, "message": "PIN incorrecto."})
        return
    join_room(ROOM)
    hosts.add(request.sid)
    emit("host_auth", {"ok": True, "message": "Modo anfitrión activado."})
    emit("state_update", public_state())

@socketio.on("start_game")
def start_game():
    if request.sid not in hosts:
        emit("notice", {"type": "error", "message": "Solo el anfitrión puede iniciar la partida."})
        return
    if len(state["players"]) < 2:
        emit("notice", {"type": "error", "message": "Necesitas al menos 2 jugadores para comenzar."})
        return
    state["game_started"] = True
    state["winner"] = None
    state["tournament_round"] = 1
    ids = list(state["players"].keys())
    random.shuffle(ids)
    state["pairs"] = []
    while ids:
        a = ids.pop()
        if ids:
            b = ids.pop()
            state["pairs"].append({"players": [a, b], "winner": None})
        else:
            state["pairs"].append({"players": [a], "winner": a})
    state["round"] = 0
    state["question_index"] = -1
    state["used_questions"] = []
    for p in state["players"].values():
        p.update({"hp": 100, "answered": False, "correct": False, "attacked": False})
    next_question_internal()
    broadcast_state()

def next_question_internal():
    if state["winner"]:
        return
    # Cuando todos los combates de la ronda tienen ganador, formar la siguiente ronda.
    if state["pairs"] and all(pair.get("winner") for pair in state["pairs"]):
        winners = [pair["winner"] for pair in state["pairs"]]
        if len(winners) == 1:
            state["winner"] = state["players"][winners[0]]["name"]
            state["question"] = None
            socketio.emit("game_over", {"winner": state["winner"]}, to=ROOM)
            return
        random.shuffle(winners)
        state["tournament_round"] += 1
        new_pairs = []
        while winners:
            a = winners.pop()
            if winners:
                b = winners.pop()
                new_pairs.append({"players": [a, b], "winner": None})
            else:
                new_pairs.append({"players": [a], "winner": a})
        state["pairs"] = new_pairs
        for pid in winners:
            state["players"][pid]["hp"] = 100
        for pair in state["pairs"]:
            for pid in pair["players"]:
                state["players"][pid]["hp"] = 100
    alive = [p for p in state["players"].values() if p["hp"] > 0]
    if len(alive) <= 1 and not state["pairs"]:
        state["winner"] = alive[0]["name"] if alive else "Sin ganador"
        state["question"] = None
        socketio.emit("game_over", {"winner": state["winner"]}, to=ROOM)
        return
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
        p.update({"answered": False, "correct": False, "attacked": False})
    socketio.emit("new_question", state["question"], to=ROOM)

@socketio.on("next_question")
def next_question():
    if request.sid not in hosts:
        emit("notice", {"type": "error", "message": "Solo el anfitrión puede avanzar las preguntas."})
        return
    if not state["game_started"]:
        emit("notice", {"type": "error", "message": "Primero inicia la partida."})
        return
    next_question_internal()
    broadcast_state()

@socketio.on("submit_answer")
def submit_answer(data):
    sid = request.sid
    p = state["players"].get(sid)
    if not p or p["hp"] <= 0:
        emit("notice", {"type": "error", "message": "No puedes responder porque estás eliminado o no estás en la sala."})
        return
    if not state["game_started"] or not state["question"]:
        emit("notice", {"type": "error", "message": "Todavía no hay una pregunta activa."})
        return
    if p["answered"]:
        emit("notice", {"type": "error", "message": "Ya respondiste esta ronda."})
        return
    try:
        answer = int((data or {}).get("answer"))
    except (TypeError, ValueError):
        return
    p["answered"] = True
    p["correct"] = answer == QUESTIONS[state["question_index"]]["answer"]
    emit("answer_result", {
        "correct": p["correct"],
        "message": "¡Correcto! Ya puedes atacar." if p["correct"] else "Respuesta incorrecta. ¡Prepárate para la siguiente ronda!",
        "explanation": QUESTIONS[state["question_index"]]["explain"]
    })
    broadcast_state()

@socketio.on("attack")
def attack(data):
    sid = request.sid
    attacker = state["players"].get(sid)
    target_id = str((data or {}).get("target", ""))
    target = state["players"].get(target_id)
    pair = next((pair for pair in state["pairs"] if sid in pair.get("players", [])), None)
    if not attacker or not target:
        emit("notice", {"type": "error", "message": "No se encontró al jugador seleccionado."})
        return
    if not state["game_started"] or not attacker["correct"]:
        emit("notice", {"type": "error", "message": "Necesitas responder correctamente para atacar."})
        return
    if attacker["attacked"]:
        emit("notice", {"type": "error", "message": "Ya atacaste en esta ronda."})
        return
    if attacker["hp"] <= 0 or target["hp"] <= 0 or sid == target_id:
        emit("notice", {"type": "error", "message": "Elige a un rival que siga en la partida."})
        return
    if not pair or pair.get("winner") or target_id not in pair.get("players", []):
        emit("notice", {"type": "error", "message": "Solo puedes atacar al rival asignado en tu combate."})
        return
    attacker["attacked"] = True
    damage = 20
    target["hp"] = max(0, target["hp"] - damage)
    if target["hp"] <= 0:
        pair["winner"] = sid
        socketio.emit("notice", {"type": "success", "message": f'¡KO! {attacker["name"]} gana su combate y avanza.'}, to=ROOM)
    socketio.emit("attack_animation", {
        "attacker": attacker["name"], "target": target["name"],
        "damage": damage, "attacker_id": sid, "target_id": target_id,
        "target_hp": target["hp"]
    }, to=ROOM)
    socketio.emit("notice", {
        "type": "success", "message": f'{attacker["name"]} golpeó a {target["name"]}: -{damage} de vida.'
    }, to=ROOM)
    broadcast_state()

@socketio.on("reset_game")
def reset_game():
    if request.sid not in hosts:
        emit("notice", {"type": "error", "message": "Solo el anfitrión puede reiniciar la sala."})
        return
    state["players"] = {}
    state.update({
        "question_index": -1, "question": None, "round": 0,
        "game_started": False, "used_questions": [], "winner": None,
        "pairs": [], "tournament_round": 0
    })
    socketio.emit("reset_notice", {"message": "La sala se reinició. Vuelvan a entrar con su apodo."}, to=ROOM)
    broadcast_state()

@socketio.on("disconnect")
def disconnect():
    hosts.discard(request.sid)
    p = state["players"].get(request.sid)
    if p:
        p["connected"] = False
        broadcast_state()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)
