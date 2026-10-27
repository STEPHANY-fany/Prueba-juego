const $ = (id) => document.getElementById(id);

// Los avatares los asigna el servidor y se sincronizan en todos los navegadores.
function setCharacter(imgId, filename) {
  if (filename) $(imgId).src = "/static/characters/" + filename;
}

// sessionStorage sobrevive a recargas (F5) de la pestaña y no se comparte entre pestañas.
const store = {
  get(key) { try { return sessionStorage.getItem(key); } catch (e) { return null; } },
  set(key, value) { try { sessionStorage.setItem(key, value); } catch (e) { /* sin almacenamiento */ } },
  del(key) { try { sessionStorage.removeItem(key); } catch (e) { /* sin almacenamiento */ } }
};
const PLAYER_KEY = "hba_player_token";
const HOST_KEY = "hba_host_token";

const socket = io();
let myId = null;
let myName = "";
let isHost = false;
let currentState = null;
let answeredThisRound = false;
let currentQuestion = null;
let winnerShown = false;
let myPick = null;            // opción que elegí en la pregunta actual
let phase = "lobby";          // lobby | question | review | over (lo marca el servidor)
let timerEndsAt = 0;          // momento (performance.now) en que vence la pregunta
let timerTotal = 20;
let reviewEndsAt = 0;         // momento en que empieza la pregunta siguiente
let reviewShownFor = null;    // número de la pregunta cuyo resumen ya se mostró
const TROPHIES = ["🏆", "🥈", "🥉"];
const PLACES = ["first", "second", "third"];

const joinScreen = $("join-screen");
const gameScreen = $("game-screen");

$("join-btn").addEventListener("click", () => {
  const name = $("nickname").value.trim();
  if (!name) { $("join-message").textContent = "Escribe tu apodo primero."; return; }
  socket.emit("join_game", {name});
});
$("nickname").addEventListener("keydown", e => { if (e.key === "Enter") $("join-btn").click(); });

// Cada vez que la conexión se (re)establece se recupera el lugar de jugador y el rol de anfitrión.
socket.on("connect", () => {
  const playerToken = store.get(PLAYER_KEY);
  if (playerToken) socket.emit("rejoin", {token: playerToken});
  const hostToken = store.get(HOST_KEY);
  if (hostToken) socket.emit("host_resume", {token: hostToken});
});
socket.on("disconnect", () => showToast("Conexión perdida. Reintentando…", "error"));

socket.on("joined", data => {
  const reconnecting = myId === data.id;
  myId = data.id; myName = data.name;
  store.set(PLAYER_KEY, data.token);
  $("my-name").textContent = myName;
  joinScreen.classList.add("hidden");
  gameScreen.classList.remove("hidden");
  showToast(reconnecting ? "Reconectado a la arena." : "¡Entraste a la arena, " + myName + "!", "success");
});
socket.on("rejoin_failed", () => {
  store.del(PLAYER_KEY);
  if (myId) {
    myId = null;
    gameScreen.classList.add("hidden");
    joinScreen.classList.remove("hidden");
    $("join-message").textContent = "Saliste de la sala. Vuelve a entrar con tu apodo.";
  }
});
socket.on("notice", data => {
  showToast(data.message, data.type || "");
  if (data.type === "error" && !myId) $("join-message").textContent = data.message;
});
socket.on("host_auth", data => {
  if (!data.ok) {
    if (data.silent) store.del(HOST_KEY);
    else showToast(data.message, "error");
    return;
  }
  isHost = true;
  store.set(HOST_KEY, data.token);
  $("host-panel").classList.remove("hidden");
  if (!data.silent) showToast(data.message, "success");
  if (currentState) renderHostMatches(currentState);
});
socket.on("state_update", renderState);
socket.on("new_question", q => {
  currentQuestion = q;
  answeredThisRound = false;
  myPick = null;
  phase = "question";
  timerTotal = q.seconds || timerTotal;
  timerEndsAt = performance.now() + timerTotal * 1000;
  hideReview();
  $("answer-feedback").textContent = "";
  setStatus("¡Responde!", "");
  renderQuestion(q);
  tickClock();
});
// Fin de la pregunta: se revela la respuesta correcta y se enseña el ranking unos segundos.
socket.on("question_end", review => {
  phase = "review";
  reviewEndsAt = performance.now() + ((currentState && currentState.review_seconds) || 6) * 1000;
  markCorrect(review.correct);
  showReview(review);
  tickClock();
});
socket.on("answer_result", result => {
  $("answer-feedback").textContent = result.message + " " + result.explanation;
  setStatus(result.correct ? "¡CORRECTO!" : "INCORRECTO", result.correct ? "var(--green)" : "var(--pink)");
});
// Solo los dos peleadores reciben este evento, así que "yo" siempre es uno de ellos.
socket.on("attack_animation", data => {
  const iAttacked = data.attacker_id === myId;
  const iWasHit = data.target_id === myId;
  showToast(`🥊 ${data.attacker} golpeó a ${data.target} (-${data.damage} vida)`, "success");
  if (iAttacked) {
    animateFighter("my-stage", "attacking");
    animateFighter("opponent-stage", "hit");
    flashHealth("opponent-health");
  }
  if (iWasHit) {
    animateFighter("opponent-stage", "attacking");
    animateFighter("my-stage", "hit");
    flashHealth("my-health");
  }
  if (data.ko) {
    if (iWasHit) $("my-stage").classList.add("ko");
    if (iAttacked) $("opponent-stage").classList.add("ko");
    showToast(iAttacked ? "🏆 ¡KO! Ganaste tu combate y avanzas." : `💀 ¡KO! ${data.target} quedó fuera de combate.`, iAttacked ? "success" : "error");
  }
});
socket.on("game_over", data => showWinner(data.winner, data.ranking));
$("close-modal").addEventListener("click", () => $("winner-modal").classList.add("hidden"));

function showWinner(name, ranking) {
  if (winnerShown) return;
  winnerShown = true;
  $("winner-name").textContent = name;
  const podium = $("winner-podium");
  podium.innerHTML = "";
  (ranking || []).forEach(entry => podium.append(rankRow(entry, entry.id === myId)));
  $("winner-modal").classList.remove("hidden");
}

function setStatus(text, color) {
  const status = $("answer-status");
  status.textContent = text;
  status.style.color = color;
}

function flashHealth(id) {
  const health = $(id);
  health.classList.remove("damage-flash"); void health.offsetWidth; health.classList.add("damage-flash");
}

function animateFighter(id, animation) {
  const fighter = $(id);
  if (!fighter) return;
  fighter.classList.remove("attacking", "hit");
  void fighter.offsetWidth;
  fighter.classList.add(animation);
  window.setTimeout(() => fighter.classList.remove(animation), animation === "attacking" ? 460 : 520);
}

function renderQuestion(q) {
  if (!q) {
    $("question-text").textContent = "Esperando a que el anfitrión inicie la partida…";
    $("options").innerHTML = "";
    return;
  }
  $("round-number").textContent = q.number || 0;
  $("question-text").textContent = q.q;
  $("options").innerHTML = "";
  q.options.forEach((option, i) => {
    const btn = document.createElement("button");
    btn.className = "option";
    btn.innerHTML = `<span class="letter">${String.fromCharCode(65+i)}</span><span></span>`;
    btn.querySelector("span:last-child").textContent = option;
    btn.addEventListener("click", () => {
      if (answeredThisRound || phase !== "question") return;
      answeredThisRound = true;
      myPick = i;
      document.querySelectorAll(".option").forEach(b => b.disabled = true);
      btn.classList.add("selected");
      socket.emit("submit_answer", {answer:i});
    });
    $("options").appendChild(btn);
  });
}

function renderState(state) {
  currentState = state;
  syncClock(state);
  $("alive-count").textContent = `${state.alive_count} vivos · Torneo ${state.tournament_round || 0}`;
  // La final es el único combate que queda en el cuadro, con dos jugadores.
  const isFinal = state.game_started && !state.winner && state.pairs.length === 1 && state.pairs[0].players.length === 2;
  $("final-banner").classList.toggle("hidden", !isFinal);
  if (state.question && (!currentQuestion || state.question.number !== currentQuestion.number)) {
    currentQuestion = state.question;
    renderQuestion(state.question);
  }
  const me = state.players.find(p => p.id === myId);
  const myPair = state.pairs.find(p => p.players.includes(myId));
  const matchDecided = !!(myPair && myPair.winner);
  if (me) {
    setCharacter("my-character", me.avatar);
    $("my-name").textContent = me.name;
    $("my-hp").textContent = `${me.hp}/100`;
    $("my-health").style.width = `${me.hp}%`;
    if (me.answered) {
      answeredThisRound = true;   // también al volver tras una recarga
      setStatus(me.correct ? "¡CORRECTO!" : "INCORRECTO", me.correct ? "var(--green)" : "var(--pink)");
    }
    if (state.phase === "question" && me.alive && !me.answered && !matchDecided) {
      setStatus("¡Responde!", "");   // también al volver tras una recarga en plena pregunta
    }
    if (state.phase === "review" && me.alive && !me.answered && !matchDecided) {
      setStatus("¡TIEMPO!", "var(--pink)");   // el plazo venció sin respuesta
    }
    if (matchDecided && me.alive) {
      setStatus(myPair.players.length === 1 ? "DESCANSO" : "¡GANASTE!", "var(--green)");
    }
    if (!me.alive || me.answered || matchDecided || state.phase !== "question" || !state.question) {
      $("options").querySelectorAll("button").forEach(b => b.disabled = true);
    }
    if (!me.alive) {
      setStatus("ELIMINADO", "var(--pink)");
      $("answer-feedback").textContent = "Te quedaste sin vida. Observa la final.";
    }
  }
  if (state.phase === "review" && state.review) {
    markCorrect(state.review.correct);
    showReview(state.review);
  } else {
    hideReview();
  }
  renderRanking(state, me);
  renderWaitBanner(state, me, myPair);
  renderRoster(state.players, me);
  renderHostMatches(state);
  if (isHost) $("start-btn").disabled = state.game_started;
  if (state.winner) showWinner(state.winner, state.ranking);
}

// Quien ya ganó su combate (o descansa) espera a que terminen los demás.
function renderWaitBanner(state, me, myPair) {
  const banner = $("wait-banner");
  banner.classList.add("hidden");
  if (!state.game_started || state.winner || !me || !me.alive || !myPair || !myPair.winner) return;
  const left = state.pending_matches;
  const intro = myPair.players.length === 1
    ? "😴 Descanso esta ronda: pasas directo a la siguiente."
    : "🏆 ¡Ganaste tu combate!";
  const outro = left > 0
    ? `Esperando a que terminen los demás (${left} combate${left === 1 ? "" : "s"} pendiente${left === 1 ? "" : "s"}).`
    : "Todos los combates terminaron: la siguiente ronda empieza en un momento.";
  banner.textContent = `${intro} ${outro}`;
  banner.classList.remove("hidden");
}

function renderRoster(players, me) {
  const roster = $("roster");
  roster.innerHTML = "";
  players.forEach(p => {
    const card = document.createElement("div");
    card.className = "player-card" + (p.alive ? "" : " dead");
    const avatar = document.createElement("div");
    avatar.className = "player-avatar";
    avatar.textContent = p.alive ? "⚔️" : "💀";
    const details = document.createElement("div");
    details.className = "player-details";
    const name = document.createElement("b"); name.textContent = p.name + (p.id === myId ? " (tú)" : "");
    const hp = document.createElement("small");
    hp.textContent = (p.alive ? `❤️ ${p.hp}/100 vida` : "Eliminado") + (p.connected ? "" : " · 📴 sin conexión");
    details.append(name, hp); card.append(avatar, details); roster.append(card);
  });
  const chosen = me && me.opponent_id ? players.find(p => p.id === me.opponent_id) : null;
  if (chosen) {
    setCharacter("opponent-character", chosen.avatar);
    $("opponent-name").textContent = chosen.name;
    $("opponent-hp").textContent = `${chosen.hp}/100`;
    $("opponent-health").style.width = `${chosen.hp}%`;
  } else {
    $("opponent-name").textContent = "SIN RIVAL";
    $("opponent-hp").textContent = "—";
    $("opponent-health").style.width = "0%";
  }
  // El estado KO sigue a la vida real, así no se arrastra de una ronda a la siguiente.
  $("my-stage").classList.toggle("ko", !!me && !me.alive);
  $("opponent-stage").classList.toggle("ko", !!chosen && !chosen.alive);
}

// Combates sin ganador: el anfitrión puede decidirlos si alguien no vuelve.
function renderHostMatches(state) {
  const box = $("pending-matches");
  const title = $("pending-title");
  box.innerHTML = "";
  title.textContent = "";
  if (!isHost || !state.game_started || state.winner) return;
  const pending = state.pairs.filter(pair => pair.players.length === 2 && !pair.winner);
  title.textContent = `Combates pendientes: ${pending.length}`;
  pending.forEach(pair => {
    const fighters = pair.players.map(id => state.players.find(p => p.id === id)).filter(Boolean);
    const row = document.createElement("div");
    row.className = "pending-row";
    const label = document.createElement("span");
    label.textContent = fighters.map(p => p.name + (p.connected ? "" : " 📴")).join("  vs  ");
    row.append(label);
    fighters.forEach(p => {
      const btn = document.createElement("button");
      btn.className = "secondary small";
      btn.textContent = `Gana ${p.name}`;
      btn.addEventListener("click", () => {
        if (confirm(`¿Dar el combate a ${p.name}?`)) socket.emit("force_winner", {winner: p.id});
      });
      row.append(btn);
    });
    box.append(row);
  });
}

// ----- Reloj: el servidor manda los segundos que faltan y aquí solo se cuenta hacia atrás -----
function syncClock(state) {
  phase = state.phase;
  timerTotal = state.question_seconds || timerTotal;
  if (state.phase === "question") timerEndsAt = performance.now() + state.seconds_left * 1000;
  if (state.phase === "review") reviewEndsAt = performance.now() + state.seconds_left * 1000;
  tickClock();
}

function tickClock() {
  const timer = $("timer");
  if (phase === "question") {
    const left = Math.max(0, (timerEndsAt - performance.now()) / 1000);
    timer.classList.remove("hidden");
    timer.classList.toggle("urgent", left <= 5);
    $("timer-fill").style.width = `${Math.min(100, left / timerTotal * 100)}%`;
    $("timer-seconds").textContent = Math.ceil(left);
  } else {
    timer.classList.add("hidden");
  }
  if (phase === "review") {
    const left = Math.max(0, Math.ceil((reviewEndsAt - performance.now()) / 1000));
    $("review-countdown").textContent = `Siguiente pregunta en ${left} s`;
  }
}
setInterval(tickClock, 250);

// ----- Ranking: un puesto con trofeo, estado (vivo/eliminado), puntos y cambio de posición -----
function rankRow(entry, isMe) {
  const li = document.createElement("li");
  li.className = "rank-row " + (PLACES[entry.rank - 1] || "") + (entry.alive ? "" : " dead") + (isMe ? " me" : "");
  const trophy = document.createElement("span");
  trophy.className = "rank-trophy";
  trophy.textContent = TROPHIES[entry.rank - 1] || entry.rank;
  const info = document.createElement("span");
  const name = document.createElement("b");
  name.className = "rank-name";
  name.textContent = entry.name + (isMe ? " (tú)" : "");
  const meta = document.createElement("small");
  meta.className = "rank-meta";
  const state = document.createElement("span");
  state.textContent = entry.alive ? "❤️ Vivo" : "💀 Eliminado";
  const wins = document.createElement("span");
  wins.className = "rank-wins";    // en pantallas pequeñas se oculta para que el panel quepa en una fila
  wins.textContent = ` · ${entry.wins} victoria${entry.wins === 1 ? "" : "s"}`;
  meta.append(state, wins);
  info.append(name, meta);
  const points = document.createElement("span");
  points.className = "rank-points";
  points.textContent = entry.points;
  if (entry.delta) {
    const delta = document.createElement("span");
    delta.className = "rank-delta " + (entry.delta > 0 ? "up" : "down");
    delta.textContent = (entry.delta > 0 ? "▲" : "▼") + Math.abs(entry.delta);
    points.append(delta);
  }
  li.append(trophy, info, points);
  return li;
}

// Tu posición cuando no estás entre los primeros.
function myRankText(state, me) {
  if (!me || state.ranking.some(entry => entry.id === myId)) return "";
  return `Tu posición: #${me.rank} · ${me.points} pts · ${me.alive ? "vivo" : "eliminado"}`;
}

function renderRanking(state, me) {
  const list = $("ranking-list");
  const mine = $("my-rank");
  list.innerHTML = "";
  if (!state.game_started) {
    $("ranking-note").textContent = "Sin puntos";
    const empty = document.createElement("li");
    empty.className = "ranking-empty";
    empty.textContent = "Cuando empiece la partida verás aquí a los 3 primeros.";
    list.append(empty);
    mine.classList.add("hidden");
    return;
  }
  $("ranking-note").textContent = "Top 3";
  state.ranking.forEach(entry => list.append(rankRow(entry, entry.id === myId)));
  const text = myRankText(state, me);
  mine.textContent = text;
  mine.classList.toggle("hidden", !text);
}

// ----- Resumen al final de cada pregunta -----
function markCorrect(correct) {
  document.querySelectorAll("#options .option").forEach((button, i) => {
    button.classList.toggle("correct-answer", i === correct);
    button.classList.toggle("wrong-pick", i !== correct && i === myPick);
    button.disabled = true;
  });
}

function showReview(review) {
  if (reviewShownFor === review.number) return;
  reviewShownFor = review.number;
  const options = currentQuestion && currentQuestion.options;
  const answer = $("review-answer");
  answer.textContent = "";
  const label = document.createElement("b");
  label.textContent = "✅ Respuesta correcta: ";
  answer.append(label, (options && options[review.correct]) || "");
  const explain = document.createElement("small");
  explain.textContent = review.explain;
  answer.append(document.createElement("br"), explain);
  const round = $("review-round");
  round.textContent = `🏁 Ronda ${review.tournament_round} terminada. La siguiente empieza ahora.`;
  round.classList.toggle("hidden", !review.round_over);
  const ranking = $("review-ranking");
  ranking.innerHTML = "";
  review.ranking.forEach(entry => ranking.append(rankRow(entry, entry.id === myId)));
  const me = currentState && currentState.players.find(p => p.id === myId);
  const mineText = currentState ? myRankText({ranking: review.ranking}, me) : "";
  $("review-me").textContent = mineText;
  $("review-me").classList.toggle("hidden", !mineText);
  const events = $("review-events");
  events.innerHTML = "";
  review.events.forEach(text => {
    const item = document.createElement("li");
    item.textContent = text;
    events.append(item);
  });
  $("review-card").classList.remove("hidden");
}

function hideReview() {
  $("review-card").classList.add("hidden");
}
$("review-card").addEventListener("click", hideReview);

$("start-btn").addEventListener("click", () => socket.emit("start_game"));
$("reset-btn").addEventListener("click", () => {
  if (confirm("¿Seguro que quieres reiniciar la sala? Todos tendrán que volver a entrar.")) socket.emit("reset_game");
});
function solicitarAccesoAnfitrion() {
  const pin = prompt("PIN del anfitrión:");
  if (pin !== null) socket.emit("host_login", {pin});
}
$("host-access-btn").addEventListener("click", solicitarAccesoAnfitrion);
document.addEventListener("keydown", e => {
  if (e.altKey && e.shiftKey && e.key.toLowerCase() === "h") {
    e.preventDefault();
    solicitarAccesoAnfitrion();
  }
});

socket.on("reset_notice", data => {
  store.del(PLAYER_KEY);
  showToast(data.message, "error");
  setTimeout(() => location.reload(), 1800);
});

function showToast(message, type="") {
  const toast = $("toast");
  toast.textContent = message;
  toast.className = "toast show " + type;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("show"), 3500);
}
renderQuestion(null);
