const $ = (id) => document.getElementById(id);
const ui = { hit: $("hitbtn"), stand: $("standbtn"), actions: $("actionbuttons"), turn: $("turnindicator"), msg: $("message"), dealerHand: $("dealerhand"), dealerScore: $("dealerscore") };
const slots = [1, 2].map((n) => ({ panel: $(`player${n}panel`), title: $(`player${n}title`), hand: $(`player${n}hand`), score: $(`player${n}score`) }));
const CARD_BACK = "Assets/PNG-cards-1.3/card back red.png";
const RANK = { A: "ace", J: "jack", Q: "queen", K: "king" };
const SUIT = { S: "spades", H: "hearts", D: "diamonds", C: "clubs" };
const makeSummary = () => ({ winners: [], pushes: [], losers: [] });
const ACTION_BY_KEY = { h: "hit", s: "stand" };
const SEAT_LABELS = ["Player 1", "Player 2"];
let youId = null;
let state = null;
let poll = null;
let autoRound = null;
let wasOver = false;
let local = false;
const engine = {
  g: null,
  deck() {
    const suits = ["S", "H", "D", "C"];
    const ranks = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"];
    const d = suits.flatMap((s) => ranks.map((r) => r + s));
    for (let i = d.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      [d[i], d[j]] = [d[j], d[i]];
    }
    return d;
  },
  draw() {
    if (!this.g.deck.length) this.g.deck = this.deck();
    return this.g.deck.pop();
  },
  score(hand) {
    let total = 0;
    let aces = 0;
    for (const c of hand) {
      const r = c.slice(0, -1);
      if (r === "A") {
        total += 11;
        aces += 1;
      } else if (r === "K" || r === "Q" || r === "J") total += 10;
      else total += Number(r);
    }
    while (total > 21 && aces > 0) {
      total -= 10;
      aces -= 1;
    }
    return total;
  },
  compare(p, d) {
    if (p > 21) return "Lose (bust)";
    if (d > 21) return "Win (dealer bust)";
    if (p > d) return "Win";
    return p === d ? "Push" : "Lose";
  },
  init() {
    this.g = {
      deck: this.deck(),
      dealer: [],
      players: [{ id: 1, nickname: "Player 1", hand: [] }, { id: 2, nickname: "Player 2", hand: [] }],
      turnIndex: 0,
      started: true,
      over: false,
      message: "",
      dealerResolving: false,
      roundSummary: makeSummary()
    };
    this.newRound();
  },
  newRound() {
    const g = this.g;
    g.deck = this.deck();
    g.dealer = [this.draw(), this.draw()];
    g.turnIndex = 0;
    g.started = true;
    g.over = false;
    g.dealerResolving = false;
    g.roundSummary = makeSummary();
    for (const p of g.players) p.hand = [this.draw(), this.draw()];
    g.message = `${g.players[0].nickname}'s turn`;
  },
  finish() {
    const g = this.g;
    const dScore = this.score(g.dealer);
    const results = [];
    const s = makeSummary();
    for (const p of g.players) {
      const out = this.compare(this.score(p.hand), dScore);
      results.push(`${p.nickname}: ${out}`);
      if (out.startsWith("Win")) s.winners.push(p.nickname);
      else if (out === "Push") s.pushes.push(p.nickname);
      else s.losers.push(p.nickname);
    }
    g.over = true;
    g.turnIndex = -1;
    g.dealerResolving = false;
    g.message = results.join(" | ");
    g.roundSummary = s;
  },
  dealer() {
    const g = this.g;
    g.dealerResolving = true;
    g.turnIndex = -1;
    g.message = "Dealer turn";
    while (this.score(g.dealer) <= 16) g.dealer.push(this.draw());
    this.finish();
  },
  action(type) {
    const g = this.g;
    if (type === "newRound") return this.newRound();
    if (!g.started || g.over || g.turnIndex < 0) return;
    const p = g.players[g.turnIndex];
    if (!p) return;
    if (type === "hit") {
      p.hand.push(this.draw());
      if (this.score(p.hand) > 21) g.turnIndex += 1;
    } else if (type === "stand") g.turnIndex += 1;
    if (g.turnIndex >= g.players.length) this.dealer();
    else g.message = `${g.players[g.turnIndex].nickname}'s turn`;
  },
  snapshot() {
    const g = this.g;
    return {
      youId,
      started: g.started,
      over: g.over,
      turnIndex: g.turnIndex,
      message: g.message,
      deckCount: g.deck.length,
      dealerHand: g.dealer,
      dealerScore: this.score(g.dealer),
      players: g.players.map((p) => ({ ...p, score: this.score(p.hand) })),
      roundSummary: g.roundSummary,
      dealerResolving: g.dealerResolving
    };
  }
};
const setActions = (on) => {
  ui.hit.disabled = !on;
  ui.stand.disabled = !on;
  ui.actions.style.display = on ? "flex" : "none";
};
async function joinGame() {
  try {
    const res = await fetch("/api/join", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    const data = await res.json();
    if (!data.ok) {
      ui.turn.textContent = "Game full";
      ui.msg.textContent = data.reason || "Unable to join.";
      return setActions(false);
    }
    youId = data.clientId;
    window.alert(`You are ${data.playerName || "a player"}.`);
    fetchState();
    poll = window.setInterval(fetchState, 600);
  } catch {
    local = true;
    youId = 1;
    engine.init();
    state = engine.snapshot();
    render();
    window.alert("Backend unavailable. Running in Local Mode for GitHub Pages/demo use.");
  }
}
function leaveGame() {
  if (!youId || local) return;
  const body = JSON.stringify({ clientId: youId });
  navigator.sendBeacon("/api/leave", new Blob([body], { type: "application/json" }));
}
async function fetchState() {
  if (local) {
    state = engine.snapshot();
    return render();
  }
  if (!youId) return;
  try {
    const res = await fetch(`/api/state?clientId=${encodeURIComponent(String(youId))}`);
    state = await res.json();
    render();
  } catch {
    ui.turn.textContent = "Disconnected";
    ui.msg.textContent = "Server not reachable.";
    setActions(false);
    if (poll) {
      clearInterval(poll);
      poll = null;
    }
  }
}
function sendAction(action) {
  if (local) {
    engine.action(action);
    return fetchState();
  }
  if (!youId) return;
  fetch("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ clientId: youId, action })
  }).then(fetchState);
}
function drawHand(el, hand, hideFirst) {
  el.innerHTML = "";
  for (let i = 0; i < hand.length; i += 1) {
    const code = hand[i];
    const card = document.createElement("div");
    card.className = "card";
    const img = document.createElement("img");
    img.className = "cardimg";
    img.alt = hideFirst && i === 0 ? "Hidden card" : code;
    if (hideFirst && i === 0) img.src = CARD_BACK;
    else {
      const suit = code.slice(-1);
      const rank = code.slice(0, -1);
      img.src = `Assets/PNG-cards-1.3/${RANK[rank] || rank}_of_${SUIT[suit] || "clubs"}.png`;
    }
    img.onerror = () => {
      card.textContent = code;
    };
    card.appendChild(img);
    el.appendChild(card);
  }
}
function showRoundPrompt() {
  const s = state.roundSummary || makeSummary();
  const winners = s.winners.length ? s.winners.join(", ") : "None";
  let msg = `Round Over\nWinners: ${winners}`;
  if (s.pushes.length) msg += `\nPushes: ${s.pushes.join(", ")}`;
  window.alert(msg);
}
function render() {
  if (!state) return;
  if (state.over && !wasOver) showRoundPrompt();
  wasOver = state.over;
  const players = state.players;
  const seat1 = players.find((p) => p.nickname === SEAT_LABELS[0]) || null;
  const seat2 = players.find((p) => p.nickname === SEAT_LABELS[1]) || null;
  const seated = [seat1, seat2];
  slots.forEach((slot, i) => {
    const p = seated[i];
    slot.title.textContent = p ? p.nickname : "Waiting...";
    slot.score.textContent = p ? `Count: ${p.score}` : "Count: -";
    drawHand(slot.hand, p ? p.hand : [], false);
  });
  drawHand(ui.dealerHand, state.dealerHand, !state.over && !state.dealerResolving);
  ui.dealerScore.textContent = state.over || state.dealerResolving ? `Count: ${state.dealerScore}` : "Count: ?";
  const me = players.find((p) => p.id === youId);
  const active = players[state.turnIndex];
  const turn = state.over
    ? "Turn: round over"
    : state.dealerResolving
      ? "Turn: dealer"
      : state.started && active
        ? `Turn: ${active.nickname}`
        : "Turn: waiting";
  ui.turn.textContent = `${me ? me.nickname : "waiting"} | ${turn}`;
  ui.msg.textContent = state.over ? state.message || "" : "";

  const activeTurnPlayer = players[state.turnIndex];
  const gameInProgress = state.started && !state.over && !state.dealerResolving;
  const yourTurn = local
    ? gameInProgress
    : gameInProgress &&
      state.turnIndex >= 0 &&
      state.turnIndex < players.length &&
      activeTurnPlayer &&
      activeTurnPlayer.id === youId;

  if (!state.over || players.length < 2) {
    if (autoRound) {
      clearTimeout(autoRound);
      autoRound = null;
    }
  } else if (seat1 && seat1.id === youId && !autoRound) {
    autoRound = window.setTimeout(() => {
      sendAction("newRound");
      autoRound = null;
    }, 2000);
  }

  if (!state.started || state.over || !yourTurn || !activeTurnPlayer) {
    setActions(false);
  } else {
    setActions(true);
    const panel = activeTurnPlayer.nickname === SEAT_LABELS[0] ? slots[0].panel : slots[1].panel;
    panel.appendChild(ui.actions);
  }
}
window.addEventListener("load", joinGame);
window.addEventListener("beforeunload", leaveGame);
document.addEventListener("keydown", (e) => {
  const action = ACTION_BY_KEY[e.key.toLowerCase()];
  if (action) sendAction(action);
});
ui.hit.addEventListener("click", () => sendAction("hit"));
ui.stand.addEventListener("click", () => sendAction("stand"));
