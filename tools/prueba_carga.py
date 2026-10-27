#!/usr/bin/env python
"""Prueba de carga de Hadoop Battle Arena.

Simula N jugadores (el primero también es el anfitrión, como en el juego real)
contra un servidor y comprueba que el torneo siempre termina con un campeón.
Puede simular recargas de página, jugadores que desaparecen y jugadores
conectados que no responden (--afk). El juego avanza solo (reloj de cada
pregunta y resumen entre preguntas): el anfitrión únicamente inicia la partida
y, si un combate de dos inactivos se traba, lo decide con "Gana ...".

Ejemplos (desde la carpeta del proyecto, con el entorno virtual activo):
    python tools/prueba_carga.py --spawn --players 20
    python tools/prueba_carga.py --spawn --players 20 --reload-mid 4 --vanish 3
    python tools/prueba_carga.py --spawn --players 20 --vanish-pair
    python tools/prueba_carga.py --spawn --players 20 --afk 4 --question-seconds 2
    python tools/prueba_carga.py --spawn --players 20 --afk-pair
    python tools/prueba_carga.py --url http://192.168.1.50:5000 --players 20

Con --spawn la prueba arranca su propio servidor (puerto libre, gracia de
reconexión corta y preguntas de pocos segundos) y además revisa que no escriba
errores en su salida, que cada pregunta cierre a tiempo y que el ranking salga
ordenado y sin que nadie pierda puntos.
Requiere: pip install -r requirements-dev.txt
"""
import argparse
import os
import random
import socket
import subprocess
import sys
import threading
import time

import socketio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from app import QUESTIONS  # noqa: E402  (solo para que los bots conozcan las respuestas)

ANSWERS = {q["q"]: q["answer"] for q in QUESTIONS}


class Bot:
    def __init__(self, url, name, accuracy, seed):
        self.url, self.name, self.accuracy = url, name, accuracy
        self.rng = random.Random(seed)
        self.sio = socketio.Client(reconnection=False)
        self.pid = None
        self.token = None
        self.state = None
        self.winner = None
        self.vanished = False
        self.host_ok = threading.Event()
        self.joined = threading.Event()
        self.scheduled_q = None
        self.state_time = 0
        self.reloaded_at = None
        self.afk = False            # conectado pero sin responder nunca
        self.max_points = {}
        self.rank_errors = []
        self.sio.on("joined", self._on_joined)
        self.sio.on("state_update", self._on_state)
        self.sio.on("game_over", self._on_game_over)
        self.sio.on("host_auth", self._on_host_auth)

    def _on_joined(self, data):
        self.pid = data["id"]
        self.token = data.get("token")
        self.joined.set()

    def _on_host_auth(self, data):
        if data.get("ok"):
            self.host_ok.set()

    def _on_game_over(self, data):
        self.winner = data["winner"]

    def _on_state(self, st):
        self.state = st
        self.state_time = time.time()
        if st.get("winner"):
            self.winner = st["winner"]
        self._check_ranking(st)
        self._act(st)

    def _check_ranking(self, st):
        """El top 3 debe venir ordenado por puntos y nadie puede perder puntos."""
        points = [entry["points"] for entry in st.get("ranking", [])]
        if points != sorted(points, reverse=True):
            self.rank_errors.append(f"ranking desordenado: {points}")
        for p in st["players"]:
            if p["points"] < self.max_points.get(p["id"], 0):
                self.rank_errors.append(f"{p['name']} perdió puntos: {self.max_points[p['id']]} -> {p['points']}")
            self.max_points[p["id"]] = max(self.max_points.get(p["id"], 0), p["points"])

    def _act(self, st):
        if self.vanished or self.afk or self.pid is None or st.get("winner"):
            return
        me = next((p for p in st["players"] if p["id"] == self.pid), None)
        if not me or not me["alive"]:
            return
        pair = next((p for p in st["pairs"] if self.pid in p["players"]), None)
        q = st.get("question")
        if not pair or pair.get("winner") or not q:
            return
        n = q["number"]
        if not me["answered"] and self.scheduled_q != n:
            self.scheduled_q = n
            threading.Timer(self.rng.uniform(0.03, 0.25), self._answer, args=(q,)).start()

    def _answer(self, q):
        right = ANSWERS[q["q"]]
        if self.rng.random() < self.accuracy:
            choice = right
        else:
            choice = self.rng.choice([i for i in range(len(q["options"])) if i != right])
        self._emit("submit_answer", {"answer": choice})

    def _emit(self, event, data=None):
        if self.vanished:
            return
        try:
            self.sio.emit(event, data)
        except Exception:
            pass   # justo en medio de una recarga

    def connect(self):
        self.sio.connect(self.url, transports=["websocket"], wait_timeout=15)

    def join(self):
        self.sio.emit("join_game", {"name": self.name})
        return self.joined.wait(15)

    def reload(self, gap):
        """Como pulsar F5: se corta la conexión y vuelve con el token guardado."""
        self.sio.disconnect()
        time.sleep(gap)
        self.scheduled_q = None
        self.sio.connect(self.url, transports=["websocket"], wait_timeout=15)
        if self.token:
            self.sio.emit("rejoin", {"token": self.token})
        self.reloaded_at = time.time()

    def recovered(self):
        """Tras recargar, ¿volvió a recibir el estado de la sala y figura conectado?"""
        if self.reloaded_at is None or self.vanished:
            return True
        if self.state_time <= self.reloaded_at or not self.state:
            return False
        me = next((p for p in self.state["players"] if p["id"] == self.pid), None)
        return bool(me and me["connected"])

    def vanish(self):
        """Cierra la pestaña y no vuelve."""
        self.vanished = True
        self.sio.disconnect()


class Server:
    def __init__(self, app_dir, port, grace, question_seconds, review_seconds):
        env = dict(os.environ, PORT=str(port), RECONNECT_GRACE_SECONDS=str(grace),
                   QUESTION_SECONDS=str(question_seconds), REVIEW_SECONDS=str(review_seconds),
                   PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        self.port = port
        self.lines = []
        self.proc = subprocess.Popen(
            [sys.executable, "app.py"], cwd=app_dir, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            self.lines.append(line.rstrip())

    def wait_ready(self, timeout=30):
        end = time.time() + timeout
        while time.time() < end:
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.5).close()
                return True
            except OSError:
                time.sleep(0.2)
        return False

    def problems(self):
        return [l for l in self.lines if "Traceback" in l or "Error" in l or "Exception" in l]

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def pick(bots, k, rng):
    return rng.sample([b for b in bots[1:] if not b.vanished], min(k, len(bots) - 1))


def run_threads(targets):
    threads = [threading.Thread(target=t) for t in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def observe(url, pin):
    """Cliente pasivo, en su propio proceso: anota cuándo llegan new_question y question_end.

    Los bots comparten un solo proceso y, bajo carga, sus hilos se atrasan unas décimas;
    medir los plazos desde aquí evita confundir ese retraso con el del servidor."""
    sio = socketio.Client(reconnection=False)
    sio.on("new_question", lambda q: print(f"q {q['number']} {time.time():.3f}", flush=True))
    sio.on("question_end", lambda r: print(f"end {r['number']} {time.time():.3f}", flush=True))
    sio.connect(url, transports=["websocket"], wait_timeout=15)
    sio.emit("host_login", {"pin": pin})    # solo para entrar en la sala y recibir los eventos
    sio.wait()
    return 0


def read_observer(proc, events):
    for line in proc.stdout:
        parts = line.split()
        if len(parts) == 3 and parts[0] in ("q", "end"):
            events.append((float(parts[2]), parts[0], int(parts[1])))


def check_play(events, host, args, errors):
    """Plazos de cada pregunta, pausa del resumen y ranking (solo con --spawn, que conoce la configuración)."""
    starts, durations, gaps, last_end = {}, [], [], None
    for moment, kind, number in events:
        if kind == "q":
            if last_end is not None:
                gaps.append(moment - last_end)
            starts[number] = moment
        elif number in starts:
            durations.append(moment - starts[number])
            last_end = moment
    if not durations:
        errors.append("no se registró ninguna pregunta cerrada")
        return
    slow = [round(d, 1) for d in durations if d > args.question_seconds + 1.5]
    if slow:
        errors.append(f"preguntas que tardaron más de {args.question_seconds + 1.5:.1f}s en cerrarse: {slow[:6]}")
    quick = [round(g, 1) for g in gaps if g < args.review_seconds - 0.4]
    late = [round(g, 1) for g in gaps if g > args.review_seconds + 1.5]
    if quick or late:
        errors.append(f"pausa entre preguntas fuera de rango (esperada {args.review_seconds}s): {(quick + late)[:6]}")
    if (args.afk or args.afk_pair) and max(durations) < args.question_seconds - 0.4:
        errors.append("con jugadores inactivos ninguna pregunta llegó a cerrarse por tiempo")
    if host.rank_errors:
        errors.append("ranking incorrecto: " + "; ".join(sorted(set(host.rank_errors))[:4]))


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--players", type=int, default=20, help="jugadores simulados, el primero es el anfitrión")
    ap.add_argument("--url", help="servidor ya en marcha (por defecto se usa --spawn)")
    ap.add_argument("--observe", metavar="URL", help=argparse.SUPPRESS)   # uso interno: cliente pasivo de medición
    ap.add_argument("--spawn", action="store_true", help="arranca un servidor propio para la prueba")
    ap.add_argument("--app-dir", default=ROOT, help="carpeta con app.py para --spawn")
    ap.add_argument("--pin", default="1234")
    # El cliente simulado tarda ~3 s en cerrar la conexion al "recargar": la gracia debe superarlo con margen.
    ap.add_argument("--grace", type=float, default=8, help="segundos de gracia del servidor con --spawn")
    ap.add_argument("--reload-lobby", type=int, default=0, help="jugadores que recargan antes de empezar")
    ap.add_argument("--leave-lobby", type=int, default=0, help="jugadores que se van antes de empezar")
    ap.add_argument("--reload-mid", type=int, default=0, help="jugadores que recargan durante el torneo")
    ap.add_argument("--vanish", type=int, default=0, help="jugadores que desaparecen durante el torneo")
    ap.add_argument("--vanish-pair", action="store_true", help="desaparecen los dos de un mismo combate")
    ap.add_argument("--afk", type=int, default=0, help="jugadores conectados que nunca responden")
    ap.add_argument("--afk-pair", action="store_true", help="los dos de un mismo combate están conectados pero inactivos")
    ap.add_argument("--stall-seconds", type=float, default=6, help="espera antes de que el anfitrión decida un combate de dos inactivos")
    ap.add_argument("--question-seconds", type=float, default=3, help="plazo por pregunta del servidor con --spawn")
    ap.add_argument("--review-seconds", type=float, default=0.5, help="duración del resumen entre preguntas con --spawn")
    ap.add_argument("--accuracy", type=float, default=0.85)
    ap.add_argument("--timeout", type=float, default=240)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    if args.observe:
        return observe(args.observe, args.pin)
    rng = random.Random(args.seed)

    server = None
    observer = None
    obs_events = []
    url = args.url
    if args.spawn or not url:
        port = free_port()
        server = Server(args.app_dir, port, args.grace, args.question_seconds, args.review_seconds)
        if not server.wait_ready():
            print("El servidor no arrancó:\n" + "\n".join(server.lines))
            return 2
        url = f"http://127.0.0.1:{port}"
        observer = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--observe", url, "--pin", args.pin],
                                    stdout=subprocess.PIPE, text=True)
        threading.Thread(target=read_observer, args=(observer, obs_events), daemon=True).start()
    t0 = time.time()

    def log(msg):
        print(f"[{time.time() - t0:6.1f}s] {msg}", flush=True)

    bots = [Bot(url, f"Bot{i + 1:02d}", args.accuracy, args.seed * 100 + i) for i in range(args.players)]
    host = bots[0]
    errors = []
    try:
        run_threads([b.connect for b in bots])
        run_threads([b.join for b in bots])
        if not all(b.joined.is_set() for b in bots):
            errors.append("no todos los jugadores lograron entrar")
        host.sio.emit("host_login", {"pin": args.pin})
        if not host.host_ok.wait(10):
            errors.append("el anfitrión no pudo activar el modo anfitrión")
        log(f"{args.players} jugadores dentro del lobby")
        by_id = {b.pid: b for b in bots}

        expected = args.players
        if args.reload_lobby:
            who = pick(bots, args.reload_lobby, rng)
            run_threads([lambda b=b: b.reload(0.3) for b in who])
            log(f"{len(who)} jugadores recargaron en el lobby")
        if args.leave_lobby:
            who = pick(bots, args.leave_lobby, rng)
            for b in who:
                b.vanish()
            expected -= len(who)
            log(f"{len(who)} jugadores se fueron del lobby")
        time.sleep(args.grace + 2.5)   # deja pasar la gracia para que se limpien los que se fueron
        roster = len(host.state["players"]) if host.state else -1
        if roster != expected:
            errors.append(f"el lobby tiene {roster} jugadores y se esperaban {expected}")
        log(f"lobby estable con {roster} jugadores")

        if args.afk:
            who = pick(bots, args.afk, rng)
            for b in who:
                b.afk = True
            log(f"{len(who)} jugadores conectados no responderán: {[b.name for b in who]}")

        host.sio.emit("start_game")
        end = time.time() + 15
        while time.time() < end and not (host.state and host.state["game_started"]):
            time.sleep(0.1)
        if not (host.state and host.state["game_started"]):
            errors.append("la partida no arrancó")
        else:
            log(f"partida iniciada: {len(host.state['pairs'])} combates en la ronda 1")

        time.sleep(0.5)
        if args.reload_mid:
            who = pick(bots, args.reload_mid, rng)
            threading.Thread(target=lambda: run_threads([lambda b=b: b.reload(1.0) for b in who])).start()
            log(f"{len(who)} jugadores recargan durante el torneo")
        if args.vanish:
            who = pick(bots, args.vanish, rng)
            for b in who:
                b.vanish()
            log(f"{len(who)} jugadores desaparecen: {[b.name for b in who]}")
        if args.vanish_pair:
            pair = next((p for p in host.state["pairs"]
                         if len(p["players"]) == 2 and host.pid not in p["players"]), None)
            if pair:
                for pid in pair["players"]:
                    by_id[pid].vanish()
                log(f"desaparece el combate completo: {[by_id[p].name for p in pair['players']]}")
        if args.afk_pair:
            pair = next((p for p in host.state["pairs"]
                         if len(p["players"]) == 2 and host.pid not in p["players"]), None)
            if pair:
                for pid in pair["players"]:
                    by_id[pid].afk = True
                log(f"combate de dos jugadores conectados pero inactivos: {[by_id[p].name for p in pair['players']]}")

        # El juego avanza solo; el anfitrión solo interviene si un combate de dos inactivos se traba.
        deadline = time.time() + args.timeout
        stalled = {}
        while not host.winner and time.time() < deadline:
            time.sleep(0.5)
            now = time.time()
            for p in (host.state or {}).get("pairs", []):
                if p.get("winner") or len(p["players"]) < 2 or not all(by_id[i].afk for i in p["players"]):
                    continue
                key = tuple(p["players"])
                stalled.setdefault(key, now)
                if now - stalled[key] > args.stall_seconds:
                    host.sio.emit("force_winner", {"winner": p["players"][0]})
                    log(f"el anfitrión decide el combate de dos inactivos: {[by_id[i].name for i in p['players']]}")
                    stalled[key] = now + 10 ** 6
        if host.winner:
            st = host.state
            log(f"CAMPEÓN: {host.winner} (ronda {st['tournament_round']}, {st['round']} preguntas)")
            gone = {b.name for b in bots if b.vanished}
            if host.winner in gone:
                errors.append(f"el campeón {host.winner} era un jugador que había desaparecido")
        else:
            st = host.state or {}
            names = {p["id"]: p["name"] for p in st.get("players", [])}
            pending = [[names.get(i, i) for i in p["players"]] for p in st.get("pairs", []) if not p.get("winner")]
            errors.append(f"el torneo se atascó (sin campeón tras {args.timeout:.0f}s); combates sin ganador: {pending}")
        if server:
            check_play(obs_events, host, args, errors)
        time.sleep(1.5)
        lost = [b.name for b in bots if not b.recovered()]
        if lost:
            errors.append(f"{len(lost)} jugadores que recargaron la página no pudieron volver a la partida: {lost}")
    finally:
        for b in bots:
            try:
                b.sio.disconnect()
            except Exception:
                pass
        if observer:
            observer.terminate()
        if server:
            time.sleep(0.5)
            bad = server.problems()
            server.stop()
            if bad:
                errors.append("el servidor escribió errores:\n    " + "\n    ".join(bad[:8]))

    if errors:
        print("\nRESULTADO: FALLO")
        for e in errors:
            print(" -", e)
        return 1
    print("\nRESULTADO: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
