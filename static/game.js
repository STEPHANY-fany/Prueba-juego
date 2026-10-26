const $ = (id) => document.getElementById(id);

// Los avatares los asigna el servidor y se sincronizan en todos los navegadores.
function setCharacter(imgId, filename) {
  if (filename) $(imgId).src = "/static/characters/" + filename;
}

const socket = io();
let myId = null;
let myName = "";
let isHost = false;
let currentState = null;
let answeredThisRound = false;
let canAttack = false;
let hasAttacked = false;
let currentQuestion = null;

const joinScreen = $("join-screen");
const gameScreen = $("game-screen");

$("join-btn").addEventListener("click", () => {
  const name = $("nickname").value.trim();
  if (!name) { $("join-message").textContent = "Escribe tu apodo primero."; return; }
  socket.emit("join_game", {name});
});
$("nickname").addEventListener("keydown", e => { if (e.key === "Enter") $("join-btn").click(); });

socket.on("joined", data => {
  myId = data.id; myName = data.name;
  $("my-name").textContent = myName;
  joinScreen.classList.add("hidden");
  gameScreen.classList.remove("hidden");
  showToast("¡Entraste a la arena, " + myName + "!", "success");
});
socket.on("notice", data => {
  showToast(data.message, data.type || "");
  if (data.type === "error" && joinScreen.classList.contains("hidden") && !myId) {
    $("join-message").textContent = data.message;
  }
});
socket.on("host_auth", data => {
  if (!data.ok) { showToast(data.message, "error"); return; }
  isHost = true;
  $("host-panel").classList.remove("hidden");
  showToast("Modo anfitrión activado.", "success");
});
socket.on("state_update", renderState);
socket.on("new_question", q => {
  currentQuestion = q;
  answeredThisRound = false; canAttack = false; hasAttacked = false;
  $("answer-feedback").textContent = "";
  $("answer-status").textContent = "¡Responde!";
  $("attack-area").classList.add("hidden");
  renderQuestion(q);
});
socket.on("answer_result", result => {
  $("answer-feedback").textContent = result.message + " " + result.explanation;
  $("answer-status").textContent = result.correct ? "¡CORRECTO!" : "INCORRECTO";
  $("answer-status").style.color = result.correct ? "var(--green)" : "var(--pink)";
  canAttack = result.correct;
  if (result.correct) populateTargets();
});
socket.on("attack_animation", data => {
  showToast(`🥊 ${data.attacker} golpeó a ${data.target} (-${data.damage} vida)`, "success");
  // Cada participante anima su personaje si fue quien atacó o recibió el golpe.
  if (data.attacker_id === myId) animateFighter("my-stage", "attacking");
  if (data.target_id === myId) animateFighter("my-stage", "hit");
  // El rival mostrado es el primer oponente vivo de la lista.
  const opponent = currentState && currentState.players.find(p => p.alive && p.id !== myId);
  if (opponent && opponent.id === data.attacker_id) animateFighter("opponent-stage", "attacking");
  if (opponent && opponent.id === data.target_id) animateFighter("opponent-stage", "hit");
  if (data.target_id === myId || (opponent && opponent.id === data.target_id)) {
    const health = data.target_id === myId ? $("my-health") : $("opponent-health");
    health.classList.remove("damage-flash"); void health.offsetWidth; health.classList.add("damage-flash");
  }
  if (data.target_hp <= 0) {
    if (data.target_id === myId) $("my-stage").classList.add("ko");
    if (opponent && opponent.id === data.target_id) $("opponent-stage").classList.add("ko");
    showToast(`💀 ¡KO! ${data.target} quedó fuera de combate.`, "error");
  }
});
socket.on("game_over", data => {
  $("winner-name").textContent = data.winner;
  $("winner-modal").classList.remove("hidden");
});
$("close-modal").addEventListener("click", () => $("winner-modal").classList.add("hidden"));


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
      if (answeredThisRound) return;
      answeredThisRound = true;
      document.querySelectorAll(".option").forEach(b => b.disabled = true);
      btn.classList.add("selected");
      socket.emit("submit_answer", {answer:i});
    });
    $("options").appendChild(btn);
  });
}

function renderState(state) {
  currentState = state;
  $("alive-count").textContent = `${state.alive_count} vivos · Torneo ${state.tournament_round || 0}`;
  const finalBanner = $("final-banner");
  if (state.game_started && state.alive_count === 2) {
    finalBanner.classList.remove("hidden");
  } else {
    finalBanner.classList.add("hidden");
  }
  if (state.question && (!currentQuestion || state.question.number !== currentQuestion.number)) {
    currentQuestion = state.question;
    renderQuestion(state.question);
  }
  const me = state.players.find(p => p.id === myId);
  if (me) {
    setCharacter("my-character", me.avatar);
    $("my-name").textContent = me.name;
    $("my-hp").textContent = `${me.hp}/100`;
    $("my-health").style.width = `${me.hp}%`;
    if (!me.alive) {
      $("answer-status").textContent = "ELIMINADO";
      $("answer-feedback").textContent = "Te quedaste sin vida. Observa la final.";
      $("options").querySelectorAll("button").forEach(b => b.disabled = true);
      $("attack-area").classList.add("hidden");
    }
  }
  renderRoster(state.players);
  populateTargets();
  if (isHost) $("start-btn").disabled = state.game_started;
}

function renderRoster(players) {
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
    const hp = document.createElement("small"); hp.textContent = p.alive ? `❤️ ${p.hp}/100 vida` : "Eliminado";
    details.append(name, hp); card.append(avatar, details); roster.append(card);
  });
  const me = players.find(p => p.id === myId);
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
}

function populateTargets() {
  if (!currentState || !myId) return;
  const me = currentState.players.find(p => p.id === myId);
  const targets = currentState.players.filter(p => p.alive && p.id === me?.opponent_id);
  const select = $("target-select");
  const old = select.value;
  select.innerHTML = "";
  targets.forEach(p => {
    const opt = document.createElement("option");
    opt.value = p.id; opt.textContent = `${p.name} — ${p.hp} vida`;
    select.appendChild(opt);
  });
  if (targets.some(p => p.id === old)) select.value = old;
  if (canAttack && !hasAttacked && me && me.alive && targets.length) {
    $("attack-area").classList.remove("hidden");
    $("attack-btn").disabled = false;
  } else {
    $("attack-area").classList.add("hidden");
  }
}
$("attack-btn").addEventListener("click", () => {
  const target = $("target-select").value;
  if (!target) return;
  socket.emit("attack", {target});
  hasAttacked = true;
  canAttack = false;
  $("attack-btn").disabled = true;
  $("attack-area").classList.add("hidden");
});

$("start-btn").addEventListener("click", () => socket.emit("start_game"));
$("next-btn").addEventListener("click", () => socket.emit("next_question"));
$("reset-btn").addEventListener("click", () => {
  if (confirm("¿Seguro que quieres reiniciar la sala? Todos tendrán que volver a entrar.")) socket.emit("reset_game");
});
$("host-panel").addEventListener("dblclick", () => {});
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
