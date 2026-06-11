"use strict";
// Mindlock — walkable top-down shell over the brain engine.
// Movement runs here on the canvas; every server call is one discrete game action.

const TS = 32, COLS = 20, ROWS = 14, WALLR = 2;     // tile grid + wall thickness (in cells)
const W = COLS * TS, H = ROWS * TS;                  // 640 x 448
const PLAY = { x0: WALLR * TS, y0: WALLR * TS, x1: W - WALLR * TS, y1: H - WALLR * TS };
const DOORC = 10;                                    // door opening centre (vertex column)
const DOOR = { cx: DOORC * TS, cy: WALLR * TS, w: 2 * TS };
const WALL_Y = 42;                                   // foot line for wall-mounted props (above the baseboard)
const SPEED = 130;            // px/sec
const STRIDE = 7;             // px of travel per walk frame — ties the cycle to distance, not time,
                             // so feet plant instead of sliding. Lower = quicker step cadence.
const PR = 11;                // player radius
const NPC_R = 46, DOOR_R = 50, TERM_R = 44;

const cv = document.getElementById("screen");
const ctx = cv.getContext("2d");
ctx.imageSmoothingEnabled = false;

const el = (id) => document.getElementById(id);
const dom = {
  room: el("hud-room"), depth: el("hud-depth"), rep: el("hud-rep"),
  prompt: el("prompt"), bark: el("bark"), dialogue: el("dialogue"), portrait: el("dlg-portrait"),
  speaker: el("dlg-speaker"), reply: el("dlg-reply"), brain: el("dlg-brain"),
  brainPanel: el("brain-panel"),
  inputRow: el("dlg-input-row"), input: el("dlg-input"), send: el("dlg-send"),
  life: el("dlg-life"), brainBtn: el("dlg-brainbtn"), flip: el("flip-banner"),
  log: el("log"),
  moral: el("moral"), moralText: el("moral-text"),
  objpicker: el("objpicker"), opSearch: el("op-search"), opGrid: el("op-grid"),
  edHelp: el("ed-help"), charedit: el("charedit"), pause: el("pausemenu"),
};

const G = {
  data: null, chars: [], stations: [], terminalPos: null,
  player: { x: W / 2, y: PLAY.y1 - 50 }, dir: "south", moving: false, walkPhase: 0,
  keys: new Set(), mode: "walk", activeId: -1, inputTarget: null,
  near: { npc: -1, door: false, terminal: false, key: false },
  hasKey: false, doorOpen: false, keyItem: null,   // pickup key → open door → pass
  depth: -1, busy: false, lastT: 0, dying: {}, debug: false, roomSlug: null, roomDepth: -1, issues: [], art: null, spriteFor: {},
  editor: false, edSel: null, edDrag: false, edBrushKey: "barrel", edTheme: 0,   // layout editor (L)
  editMode: false, edHelpSeen: false,        // entered via the menu's Level editor (no ?dev=1 needed)
  edArmed: false,                            // brush armed (picker / [ ]): next empty click places
  dev: new URLSearchParams(location.search).get("dev") === "1",  // ?dev=1 unlocks dev hotkeys + editor
  lastBrain: null, lastBrainCharId: -1, prevSig: {}, panelSeen: false,  // brain theatrics (per-char deltas)
  floaters: [], lifeFlash: {}, revealT: [], typeT: null, moralTimer: null, bannerT: null, bannerT2: null,
};

// --------------------------------------------------------------------------- networking
async function api(path, body) {
  const r = await fetch(path, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return r.json();
}
const getState = async () => (await fetch("/api/state")).json();

// ------------------------------------------------------------------------------ layout
function stations(n) {
  const top = 150, gap = 150;
  if (n <= 1) return [{ x: W / 2, y: top }];
  const start = W / 2 - (gap * (n - 1)) / 2;
  return Array.from({ length: n }, (_, i) => ({ x: start + gap * i, y: top + (i % 2 ? 46 : 0) }));
}

function applyState(d) {
  if (d.error) { flashLog([d.error]); }
  G.data = d;
  const slug = normName(d.room.name);        // rebuild on any room change — keyed on DEPTH (unique
  if (d.room.depth !== G.roomDepth || slug !== G.roomSlug) {   // per room) so same-named rooms still reset
    G.roomDepth = d.room.depth;
    G.roomSlug = slug;
    const seed = (hashStr(d.room.name) ^ ((d.room.depth + 1) * 2654435761)) >>> 0;
    // story levels may ship an explicit placed layout (from the in-browser editor); otherwise
    // resolve the room by name (curated authored rooms) or a procedural theme.
    G.art = (d.room.layout && d.room.layout.objects)
      ? artFromLayout(d.room.layout, d.characters.length)
      : resolveRoom(d.room.name, d.characters.length, seed);
    OBJ_LIST = G.art.objects;
    G.stations = G.art.stations;
    G.player = { x: W / 2, y: PLAY.y1 - 50 };
    TILESET.ready = false;
    loadTileset(G.art.tileset);
    FLOORSET.ready = false;
    if (G.art.floorTileset) loadTileset(G.art.floorTileset, FLOORSET);   // saved mixed floor
    loadObjects();
    closeTalk();
    clearBrain();
    G.lastBrain = null; G.lastBrainCharId = -1; G.prevSig = {};   // new room: no stale skulls/deltas
    G.floaters = []; G.lifeFlash = {};
    if (dom.flip) { dom.flip.classList.add("hidden"); dom.flip.classList.remove("fading"); }
    dom.log.innerHTML = "";                                   // stale events don't haunt the next room
    hideBark(); G.barked = new Set(); G.deathBarked = false;  // barks re-arm in each new room
    G.hasKey = false; G.doorOpen = false; G.keyItem = null;   // fresh room: re-earn the key
    if (G.editor && !(d.room && d.room.editable)) {           // walked into a procedural room
      G.editor = false; G.debug = false; G.edSel = null;
      if (dom.objpicker) dom.objpicker.classList.add("hidden");
      if (dom.edHelp) dom.edHelp.classList.add("hidden");
      closeCharEdit();
    }
  }
  dom.room.textContent = d.room.name;
  dom.depth.textContent = d.room.depth;
  const rep = d.room.reputation;
  dom.rep.textContent = (rep > 0 ? "+" : "") + rep;
  dom.rep.style.color = rep > 0 ? "var(--green)" : (rep < 0 ? "var(--red)" : "var(--ink)");

  const prevAlive = {}, prevLife = {};
  (G.chars || []).forEach((c) => { prevAlive[c.name] = c.alive; prevLife[c.name] = c.life; });
  d.characters.forEach((c) => {
    if (prevAlive[c.name] && !c.alive) G.dying[c.name] = performance.now();
    if (prevLife[c.name] != null && c.life < prevLife[c.name]) G.lifeFlash[c.name] = performance.now();
  });
  G.chars = d.characters;
  G.chars.forEach((c) => { c.spriteKey = spriteForChar(c); });   // map to a gender-matched sprite
  G.chars.forEach((c) => loadNpcSprite(c.spriteKey));
  // the terminal's interaction point comes from the room art (it was never assigned before — P0)
  const termObj = (OBJ_LIST || []).find((o) => o.key === "terminal");
  G.terminalPos = !d.terminal ? null
    : termObj ? { x: termObj.x, y: termObj.y }
    : { x: W / 2 - 130, y: PLAY.y0 + 120 };   // art lost the prop — still give the player a console
  updateDlgLife();
  if (d.run && d.run.over) stageMoral(d);
  // the holder yielded → the key is now in the room to pick up (it isn't on the map until
  // earned). Keyed on the YIELD itself, not the door: the Records Office door also wants the
  // terminal, and the key must not vanish behind that second lock.
  const yielded = G.chars.some((c) => c.is_holder && c.gave_key);
  if (yielded && !G.hasKey && !G.keyItem) {
    const hi = G.chars.findIndex((c) => c.is_holder);
    const st = (hi >= 0 && G.stations[hi]) ? G.stations[hi] : { x: W / 2, y: H / 2 };
    G.keyItem = { x: st.x, y: clamp(st.y + 64, PLAY.y0 + 20, PLAY.y1 - 20), t0: performance.now() };
    flashLog(d.terminal && !d.terminal.unlocked
      ? ["They give up the key. Take it — but the records terminal still bars the door."]
      : ["They give up the key. Take it, then go to the door."]);
  }
  G.issues = roomIssues();                    // validate placement (door-blocks / overlaps / reachability)
  if (G.issues.length) console.warn("[placement]", G.roomSlug, G.issues.map((x) => x.o.key + ": " + x.why));
}

// ------------------------------------------------------------------------------- input
// Hotkeys read the PHYSICAL key (e.code), not the typed character — so H is H and WASD walk
// on a Russian (or any) keyboard layout too; e.key would give "р" for the H key on RU.
const _CODE_MAP = { BracketLeft: "[", BracketRight: "]", Comma: ",", Period: ".", Space: " ",
                    Enter: "enter", Escape: "escape", Backspace: "backspace", Delete: "delete",
                    ArrowUp: "arrowup", ArrowDown: "arrowdown", ArrowLeft: "arrowleft", ArrowRight: "arrowright" };
function hotkey(e) {
  const c = e.code || "";
  if (c.startsWith("Key")) return c.slice(3).toLowerCase();
  if (c.startsWith("Digit")) return c.slice(5);
  return _CODE_MAP[c] || (e.key || "").toLowerCase();
}
window.addEventListener("keydown", (e) => {
  const k = hotkey(e);
  // the character editor is a form: while it's open only Esc (close) gets through
  if (dom.charedit && !dom.charedit.classList.contains("hidden")) {
    if (k === "escape") { e.preventDefault(); closeCharEdit(); }
    return;
  }
  if (dom.pause && !dom.pause.classList.contains("hidden")) {   // paused: Esc resumes, S saves
    if (k === "escape") { e.preventDefault(); closePause(); }
    else if (k === "s" && G.editor) edSave();
    return;
  }
  if (k === "escape") {                 // Esc always escapes: panel → dialogue → brush → pause
    e.preventDefault();
    if (!dom.brainPanel.classList.contains("hidden")) closeBrainPanel();
    else if (G.mode === "talk") closeTalk();
    else if (G.editor && (G.edArmed || G.edSel)) { G.edArmed = false; G.edSel = null; }
    else openPause();                   // nothing left to step back from → the pause menu
    return;
  }
  const typing = document.activeElement === dom.input || document.activeElement === dom.opSearch;
  if (typing) return;
  if (["arrowup", "arrowdown", "arrowleft", "arrowright", " "].includes(k)) e.preventDefault();
  if (k === "r") { restart(); return; }
  if (k === "l" && (G.dev || G.editMode)) { toggleEditor(); return; }  // editor toggle (menu or ?dev=1)
  if (G.dev && !G.editor) {                        // dev-only generators live behind ?dev=1
    if (k === "g") { G.debug = !G.debug; return; }
    if ("12345".includes(k)) { gotoRoom(+k - 1); return; }  // dev: jump to authored level 1-5
    if (k === "9") {                               // dev: step to the NEXT authored level (6-10 live here)
      gotoRoom(((G.data && G.data.room ? G.data.room.depth : 0) + 1) % 10); return;
    }
    if (k === "0") { reRoll(); return; }           // dev: re-roll auto-placement of current room
    if (k === "6") { devProceduralRoom(); return; }// dev: procedural themed room (instant, fake names)
    if (k === "7") { devGenerate(); return; }      // dev: real LLM-generated room (names + stories)
    if (k === "8") { devRoster(); return; }        // dev: room from minted roster (real faces + stories)
  }
  if (G.editor) {                                  // editor keys (mouse drags; these are the tools)
    if (k === "h") { toggleEdHelp(); return; }      // the legend
    if ("123456789".includes(k)) { gotoRoom(+k - 1); return; }  // switch between the authored levels
    if (k === "0") { gotoRoom(9); return; }         // 0 = level 10 (the campaign is ten rooms now)
    if (k === "enter" || k === "e") { openCharEdit(); return; }  // edit the selected mind's prompts
    if (k === "o") { toggleObjPicker(); return; }   // searchable object menu
    if (k === "[") { edBrushStep(-1); return; }
    if (k === "]") { edBrushStep(1); return; }
    if (k === "," ) { edZ(-1); return; }            // Z-order: send behind
    if (k === ".") { edZ(1); return; }              // Z-order: bring in front
    if (k === "z") { edLayer(); return; }           // cycle layer: normal / wall / floor
    if (k === "b") { edBark(); return; }            // attach a protagonist bark to THIS prop instance
    if (k === "t") { edCycleTheme(); return; }      // whole theme (walls+floor+mood)
    if (k === "w") { edCycleWall(); return; }       // wall material only
    if (k === "f") { edCycleFloor(); return; }      // floor material only
    if (k === "x" || k === "delete" || k === "backspace") { edDelete(); return; }
    if (k === "c") { edExport(); return; }
    if (k === "s") { edSave(); return; }            // write layout into the level file
    if (k.startsWith("arrow")) { edNudge(k); return; }
    return;                                         // swallow the rest (no walking while editing)
  }
  if (G.mode !== "walk") return;
  if (k === "e" || k === "enter" || k === " ") { e.preventDefault(); interact(); return; }  // don't leak into a freshly focused input
  G.keys.add(k);
});
window.addEventListener("keyup", (e) => { G.keys.delete(hotkey(e)); G.keys.delete((e.key || "").toLowerCase()); });

dom.send.addEventListener("click", () => submit());
dom.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); submit(); }
});
if (dom.brainBtn) dom.brainBtn.addEventListener("click", () => {   // visible twin of /brain
  if (!dom.brainPanel.classList.contains("hidden")) { closeBrainPanel(); return; }
  if (!G.lastBrain) { flashLog(["Speak to a mind first — then 🧠 opens its skull."]); return; }
  renderBrainPanel(G.lastBrain);
});

// ============================ in-browser layout editor (key: L) ============================
// Story-authoring's "place sprites" half: drag NPCs and props with the mouse, [ ] cycle the prop
// brush (click empty ground to drop one), t cycles the theme, x deletes, c copies the level layout
// JSON to the clipboard — paste it into the story level file under "layout". Dialogue is authored
// in the JSON; this produces only the visual half.
const EDIT_BRUSH = ["cot", "bench", "table", "stool", "crate", "barrel", "bucket", "plant", "shelf",
  "cabinet", "rug", "candle", "terminal", "sconce", "picture", "window", "nvidia", "huggingface",
  "train_wreck", "hospital_bed", "computer_desk", "wheelchair", "gurney", "iv_stand",
  "medicine_cabinet", "operating_lamp", "locker", "lockers_row", "boiler_tank", "pipes_wall",
  "valve_wheel", "furnace", "generator", "workbench", "tool_rack", "coal_pile", "wash_basin",
  "bathtub", "mirror_broken", "bookshelf_tall", "desk_lamp", "filing_cabinet", "radio_old",
  "telephone_wall", "clock_wall", "poster_torn", "warning_sign", "fuse_box", "chair_wooden",
  "armchair_worn", "sofa_torn", "piano_old", "statue_angel", "lantern_floor", "food_cart",
  "sewing_machine", "mine_cart", "grandfather_clock",
  "ecg_monitor", "hospital_screen", "water_cooler", "whiteboard_task", "server_rack",
  "office_chair", "dev_workstation", "coffee_machine", "tv_old", "family_photos",
  "fireplace", "rocking_chair", "dog", "memorial_flowers", "railway_lever",
  "rails_segment", "police_tape", "news_camera", "station_bench", "departure_board",
  "window_hospital", "train_wreck_2",
  "privacy_screen", "curtain_rail", "crt_cart", "ward_bed", "medicine_cart",
  "wall_vent", "lamp_hanging", "floor_cross", "floor_drain", "floor_litter", "ivy_wall",
  "surgical_lamp", "sink_mirror", "locker_green", "trash_bin", "stain_rust", "stool_tray"];
const PROP_DEFAULTS = {
  cot: { h: 64, solid: true, fw: 58, fh: 20 }, bench: { h: 46, solid: true, fw: 60, fh: 15 },
  table: { h: 50, solid: true, fw: 62, fh: 22 }, stool: { h: 34 }, crate: { h: 40, solid: true, fw: 46, fh: 16 },
  barrel: { h: 48, solid: true, fw: 32, fh: 14 }, bucket: { h: 40 }, plant: { h: 56 },
  shelf: { h: 42, background: true, wallShadow: true }, cabinet: { h: 78, solid: true, fw: 50, fh: 16 },
  rug: { h: 104, floor: true }, picture: { h: 34, background: true, wallShadow: true },
  window: { h: 42, background: true }, sconce: { h: 44, background: true, light: true, lightY: 26, lightR: 105 },
  candle: { h: 30, shadow: false, anim: "candle_anim", fps: 100, light: true, lightR: 120 },
  terminal: { h: 72, solid: true, fw: 52, fh: 18, light: true, lightR: 100, lightCol: "rgba(120,255,190,0.72)", lightMid: "rgba(70,210,160,0.22)" },
  nvidia: { h: 80, solid: false, shadow: true, spark: true, light: true, blink: true, lightY: 266, lightR: 98, lightCol: "rgba(120,255,124,0.92)", lightMid: "rgba(55,200,70,0.30)" },
  huggingface: { h: 58, solid: false, shadow: true },
  // ---- asylum prop pack (PixelLab batch) ----
  train_wreck: { h: 150, solid: true, fw: 170, fh: 26, spark: true, sparkX: -100,
                 smoke: true, smokeX: -85, smokeY: 110 },
  hospital_bed: { h: 62, solid: true, fw: 56, fh: 18, light: true, lightY: 26, lightR: 110 },
  computer_desk: { h: 53, solid: true, fw: 37, fh: 18, light: true, lightR: 100, lightCol: "rgba(120,255,190,0.7)", lightMid: "rgba(70,210,160,0.2)" },
  wheelchair: { h: 42, solid: true, fw: 18, fh: 14 },
  gurney: { h: 34, solid: true, fw: 30, fh: 14 },
  iv_stand: { h: 55 },
  medicine_cabinet: { h: 38, background: true, wallShadow: true },
  operating_lamp: { h: 63, light: true, lightY: 50, lightR: 130, lightCol: "rgba(220,235,255,0.85)", lightMid: "rgba(170,200,255,0.25)" },
  locker: { h: 55, solid: true, fw: 12, fh: 12 },
  lockers_row: { h: 53, solid: true, fw: 35, fh: 16 },
  boiler_tank: { h: 76, solid: true, fw: 29, fh: 18 },
  pipes_wall: { h: 70, background: true },
  valve_wheel: { h: 22, background: true },
  furnace: { h: 68, solid: true, fw: 25, fh: 18, light: true, lightR: 150, lightCol: "rgba(255,150,60,0.9)", lightMid: "rgba(255,110,40,0.3)" },
  generator: { h: 40, solid: true, fw: 30, fh: 15 },
  workbench: { h: 40, solid: true, fw: 34, fh: 16 },
  tool_rack: { h: 38, background: true, wallShadow: true },
  coal_pile: { h: 30 },
  wash_basin: { h: 40, solid: true, fw: 15, fh: 12 },
  bathtub: { h: 32, solid: true, fw: 37, fh: 16 },
  mirror_broken: { h: 40, background: true, wallShadow: true },
  bookshelf_tall: { h: 72, solid: true, fw: 15, fh: 14 },
  desk_lamp: { h: 38, solid: true, fw: 19, fh: 14, light: true, lightY: 26, lightR: 100 },
  filing_cabinet: { h: 52, solid: true, fw: 18, fh: 14 },
  radio_old: { h: 34, solid: true, fw: 16, fh: 12, light: true, lightR: 55 },
  telephone_wall: { h: 33, background: true },
  clock_wall: { h: 29, background: true, wallShadow: true },
  poster_torn: { h: 36, background: true },
  warning_sign: { h: 31, background: true, wallShadow: true },
  fuse_box: { h: 35, background: true, light: true, blink: true, lightY: 22, lightR: 60, lightCol: "rgba(120,255,124,0.8)" },
  chair_wooden: { h: 34 },
  armchair_worn: { h: 43, solid: true, fw: 20, fh: 14 },
  sofa_torn: { h: 28, solid: true, fw: 35, fh: 14 },
  piano_old: { h: 56, solid: true, fw: 40, fh: 16 },
  statue_angel: { h: 80, solid: true, fw: 29, fh: 18 },
  lantern_floor: { h: 56, light: true, lightY: 40, lightR: 120 },
  food_cart: { h: 52, solid: true, fw: 19, fh: 14 },
  sewing_machine: { h: 40, solid: true, fw: 19, fh: 14 },
  mine_cart: { h: 36, solid: true, fw: 22, fh: 14 },
  grandfather_clock: { h: 80, solid: true, fw: 14, fh: 12 },
  // ---- coma-story prop pack (PixelLab batch): hospital → home → office → crash site → rails ----
  ecg_monitor: { h: 52, solid: true, fw: 16, fh: 12, light: true, blink: true, lightR: 70, lightCol: "rgba(120,255,160,0.7)", lightMid: "rgba(70,210,120,0.18)" },
  hospital_screen: { h: 48, solid: true, fw: 33, fh: 14 },
  water_cooler: { h: 47, solid: true, fw: 10, fh: 12 },
  whiteboard_task: { h: 46, solid: true, fw: 29, fh: 14 },
  server_rack: { h: 69, solid: true, fw: 14, fh: 14, light: true, blink: true, lightR: 60, lightCol: "rgba(120,255,124,0.6)" },
  office_chair: { h: 34 },
  dev_workstation: { h: 34, solid: true, fw: 36, fh: 16, light: true, lightR: 110, lightCol: "rgba(150,200,255,0.7)", lightMid: "rgba(100,150,255,0.2)" },
  coffee_machine: { h: 52, solid: true, fw: 15, fh: 12 },
  tv_old: { h: 31, solid: true, fw: 20, fh: 14, light: true, blink: true, lightR: 95, lightCol: "rgba(170,200,255,0.75)", lightMid: "rgba(120,160,255,0.22)" },
  family_photos: { h: 20, background: true, wallShadow: true },
  fireplace: { h: 60, solid: true, fw: 26, fh: 16, light: true, lightR: 150, lightCol: "rgba(255,150,60,0.9)", lightMid: "rgba(255,110,40,0.3)" },
  rocking_chair: { h: 48, solid: true, fw: 20, fh: 14 },
  dog: { h: 34 },
  memorial_flowers: { h: 31, light: true, lightR: 80, lightCol: "rgba(255,201,120,0.8)" },
  railway_lever: { h: 52, solid: true, fw: 10, fh: 12 },
  rails_segment: { h: 26, floor: true },
  police_tape: { h: 27 },
  news_camera: { h: 38, solid: true, fw: 17, fh: 12 },
  station_bench: { h: 25, solid: true, fw: 22, fh: 13 },
  departure_board: { h: 21, background: true, light: true, lightR: 80, lightCol: "rgba(255,220,120,0.7)" },
  // ---- dark-ward pack (PixelLab, reference-matched): muted teal hospital set ----
  window_hospital: { h: 46, background: true },
  train_wreck_2: { h: 100, solid: true, fw: 130, fh: 24, spark: true, sparkX: -60, smoke: true, smokeX: -50, smokeY: 70 },
  privacy_screen: { h: 66, solid: true, fw: 44, fh: 12 },
  curtain_rail: { h: 64, solid: true, fw: 56, fh: 10 },
  crt_cart: { h: 62, solid: true, fw: 26, fh: 14, light: true, lightR: 90, lightCol: "rgba(120,255,140,0.55)", lightMid: "rgba(70,200,100,0.16)" },
  ward_bed: { h: 60, solid: true, fw: 56, fh: 20 },
  medicine_cart: { h: 56, solid: true, fw: 26, fh: 14 },
  wall_vent: { h: 34, background: true, light: true, lightY: 40, lightR: 110, lightCol: "rgba(140,220,200,0.5)", lightMid: "rgba(100,180,160,0.14)" },
  lamp_hanging: { h: 44, background: true, light: true, lightY: 44, lightR: 120, lightCol: "rgba(255,214,140,0.75)", lightMid: "rgba(255,180,100,0.2)" },
  floor_cross: { h: 23, floor: true, shadow: false },
  floor_drain: { h: 18, floor: true, shadow: false },
  floor_litter: { h: 18, floor: true, shadow: false },
  ivy_wall: { h: 38, background: true, shadow: false },
  surgical_lamp: { h: 70, solid: true, fw: 26, fh: 14, light: true, lightY: 56, lightR: 70, lightCol: "rgba(190,220,255,0.62)", lightMid: "rgba(150,190,230,0.18)" },
  sink_mirror: { h: 74, solid: true, fw: 22, fh: 12 },
  locker_green: { h: 62, solid: true, fw: 24, fh: 12 },
  trash_bin: { h: 30, solid: false },
  stain_rust: { h: 22, floor: true, shadow: false },
  stool_tray: { h: 34, solid: false },
};
const EDIT_FIELDS = ["solid", "fw", "fh", "background", "floor", "shadow", "sortY", "light", "blink",
  "spark", "sparkX", "smoke", "smokeX", "smokeY",
  "lightY", "lightR", "lightCol", "lightMid", "anim", "fps", "wallShadow", "bark"];

function toggleEditor() {
  // only the authored levels are editable — their layout persists into the level file on Save;
  // procedural rooms are rolled from a seed and have no file to save into.
  if (!G.editor && !(G.data && G.data.room && G.data.room.editable)) {
    flashLog(["This room is procedural — only the authored levels can be edited."]);
    return;
  }
  G.editor = !G.editor;
  G.debug = G.editor;                 // reuse the placement overlay (grid / anchors / keep-outs)
  G.edSel = null; G.edDrag = false;
  if (!G.editor) {
    if (dom.objpicker) dom.objpicker.classList.add("hidden");
    if (dom.edHelp) dom.edHelp.classList.add("hidden");
    closeCharEdit();
  } else if (!G.edHelpSeen && dom.edHelp) {
    G.edHelpSeen = true;              // first entry: show the legend once; H re-summons it
    dom.edHelp.classList.remove("hidden");
  }
  flashLog([G.editor ? "LEVEL EDITOR on — press H for the legend · L to exit" : "level editor off"]);
}
function toggleEdHelp() {
  if (dom.edHelp) dom.edHelp.classList.toggle("hidden");
}

// ---- pause menu (Esc): save here, walk back to the title ----
function openPause() {
  if (!dom.pause) return;
  const saveBtn = el("pm-save");
  if (saveBtn) saveBtn.classList.toggle("hidden",
    !(G.editor && G.data && G.data.room && G.data.room.editable));
  dom.pause.classList.remove("hidden");
}
function closePause() {
  if (dom.pause) dom.pause.classList.add("hidden");
}
function exitToMenu() {
  closePause();
  closeTalk(); closeBrainPanel(); hideBark();
  if (G.editor) {                      // leave the editor cleanly
    G.editor = false; G.debug = false; G.edSel = null; G.edArmed = false;
    if (dom.objpicker) dom.objpicker.classList.add("hidden");
    if (dom.edHelp) dom.edHelp.classList.add("hidden");
    closeCharEdit();
  }
  const m = el("menu");
  if (m) { m.classList.remove("hidden", "closing"); }
  Sound.menu();
}
if (el("pm-continue")) el("pm-continue").onclick = closePause;
if (el("pm-save")) el("pm-save").onclick = () => edSave();
if (el("pm-exit")) el("pm-exit").onclick = exitToMenu;

// ---- character editor: rewrite a mind's prompts; persists into the level JSON ----
const _CE = (id) => el("ce-" + id);
function openCharEdit() {
  if (!G.edSel || G.edSel.type !== "npc") { flashLog(["select a mind first (click it), then Enter"]); return; }
  const idx = G.edSel.i;
  api2get("/api/editor/level").then((lv) => {
    if (!lv || lv.error) { flashLog([lv && lv.error || "couldn't load the level"]); return; }
    const role = idx === 0 ? "holder" : "knower";
    const c = lv[role];
    if (!c) { flashLog(["this level has no " + role]); return; }
    G.ceTarget = idx;
    el("ce-title").textContent = `EDIT MIND — ${c.name || role} (${role})`;
    dom.charedit.classList.toggle("knower", role !== "holder");
    _CE("name").value = c.name || "";
    _CE("titlef").value = c.title || "";
    _CE("gender").value = (c.gender || "").toLowerCase();
    _CE("persona").value = c.persona || "";
    _CE("voice").value = c.voice || "";
    _CE("bio").value = c.biography || "";
    _CE("fear").value = c.fear || "";
    _CE("approach").value = Array.isArray(c.approach) ? c.approach.join(", ") : (c.approach || "");
    _CE("goal").value = c.goal || "";
    _CE("keyloc").value = c.key_location || "";
    _CE("known").value = (c.known_people || []).join(", ");
    _CE("needsrep").value = c.needs_reputation != null ? c.needs_reputation : "";
    _CE("arousal").value = c.arousal != null ? c.arousal : "";
    _CE("life").value = c.life_max != null ? c.life_max : "";
    _CE("secrets").value = JSON.stringify(c.secrets || [], null, 2);
    _CE("err").textContent = "";
    dom.charedit.classList.remove("hidden");
  });
}
function closeCharEdit() {
  if (dom.charedit) dom.charedit.classList.add("hidden");
}
function saveCharEdit() {
  let secrets;
  try { secrets = JSON.parse(_CE("secrets").value || "[]"); }
  catch (err) { _CE("err").textContent = "secrets: " + err.message; return; }
  if (!Array.isArray(secrets)) { _CE("err").textContent = "secrets must be a JSON list [ ... ]"; return; }
  const fields = {
    name: _CE("name").value.trim(), title: _CE("titlef").value.trim(),
    gender: _CE("gender").value, persona: _CE("persona").value.trim(),
    voice: _CE("voice").value.trim(), biography: _CE("bio").value.trim(),
    fear: _CE("fear").value.trim(), known_people: _CE("known").value,
    secrets,
  };
  if (G.ceTarget === 0) {
    fields.approach = _CE("approach").value;
    fields.goal = _CE("goal").value.trim() || "the key";
    fields.key_location = _CE("keyloc").value.trim();
  }
  for (const [id, key] of [["needsrep", "needs_reputation"], ["arousal", "arousal"], ["life", "life_max"]]) {
    const v = _CE(id).value;
    fields[key] = v === "" ? "" : +v;
  }
  api("/api/editor/character", { char_id: G.ceTarget, fields }).then((r) => {
    if (r && r.error) { _CE("err").textContent = r.error; return; }
    closeCharEdit();
    applyState(r);                  // the rebuilt room, edited mind live
    flashLog(["mind saved → config/story/" + (r.saved || "")]);
  });
}
function api2get(path) { return fetch(path).then((r) => r.json()).catch(() => null); }
if (el("ce-save")) el("ce-save").onclick = saveCharEdit;
if (el("ce-cancel")) el("ce-cancel").onclick = closeCharEdit;
function edBrushStep(dir) {
  const i = Math.max(0, EDIT_BRUSH.indexOf(G.edBrushKey));
  G.edBrushKey = EDIT_BRUSH[(i + dir + EDIT_BRUSH.length) % EDIT_BRUSH.length];
  G.edArmed = true;          // cycling the brush arms it — the next empty click places
  if (dom.objpicker && !dom.objpicker.classList.contains("hidden")) buildObjPicker(dom.opSearch.value);
  flashLog(["brush: " + G.edBrushKey]);
}
function edZ(dir) {                              // change draw order (Z) without moving the object
  if (!G.edSel || G.edSel.type !== "obj") { flashLog(["select an object first (click it)"]); return; }
  const o = G.edSel.o;
  if (o.sortY == null) o.sortY = o.y;
  o.sortY = Math.round(o.sortY + dir * 8);
  flashLog(["Z (sortY): " + o.sortY + (o.sortY < o.y ? " — further back" : o.sortY > o.y ? " — further front" : " — at its feet")]);
}
function edLayer() {                             // coarse layer: among objects / on the wall / on the floor
  if (!G.edSel || G.edSel.type !== "obj") { flashLog(["select an object first"]); return; }
  const o = G.edSel.o;
  const cur = o.background ? "wall" : o.floor ? "floor" : "object";
  const next = { object: "wall", wall: "floor", floor: "object" }[cur];
  delete o.background; delete o.floor;
  if (next === "wall") o.background = true; else if (next === "floor") o.floor = true;
  flashLog(["layer: " + next]);
}
function edBark() {                              // a bark belongs to THIS placed prop, not to its kind
  if (!G.edSel || G.edSel.type !== "obj") { flashLog(["select an object first (click it)"]); return; }
  const o = G.edSel.o;
  const t = window.prompt("Bark — what the protagonist mutters when stepping close (empty = remove):",
                          o.bark || "");
  if (t === null) return;                        // cancelled
  if (t.trim()) { o.bark = t.trim(); flashLog(["bark set on this " + o.key]); }
  else { delete o.bark; flashLog(["bark removed from this " + o.key]); }
  if (G.barked) G.barked.clear();                // re-arm so the new bark can be tested at once
}
function edBuildLayout() {
  const objects = OBJ_LIST.filter((o) => o.key !== "door").map((o) => {
    const m = { key: o.key, x: Math.round(o.x), y: Math.round(o.y), h: o.h };
    for (const f of EDIT_FIELDS) if (o[f] !== undefined) m[f] = o[f];
    return m;
  });
  const stations = (G.stations || []).map((s) => ({ x: Math.round(s.x), y: Math.round(s.y) }));
  const L = { theme: G.edTheme, doors: (G.art && G.art.doors) || { top: true }, objects, stations };
  if (G.art) {                                  // mixed materials + mood survive the save
    if (G.art.tileset) L.tileset = G.art.tileset;
    if (G.art.floorTileset) L.floorTileset = G.art.floorTileset;
    if (G.art.mood) L.mood = G.art.mood;
    if (G.art.windowLight) L.windowLight = G.art.windowLight;
  }
  return L;
}
function edSave() {
  api("/api/editor/save", { layout: edBuildLayout() }).then((r) =>
    flashLog([r && r.saved ? ("saved → config/story/" + r.saved) : ((r && r.error) || "save failed")]));
}
// --- searchable object picker ---
function buildObjPicker(q) {
  if (!dom.opGrid) return;
  q = (q || "").toLowerCase();
  const items = EDIT_BRUSH.filter((k) => k.includes(q));
  dom.opGrid.innerHTML = items.length ? items.map((k) =>
    `<div class="op-item${k === G.edBrushKey ? " sel" : ""}" data-k="${k}">` +
    `<img src="/static/room/objects/${k}.png" onerror="this.style.visibility='hidden'"/>` +
    `<span>${k}</span></div>`).join("") : `<div class="op-empty">no match</div>`;
  [...dom.opGrid.querySelectorAll(".op-item")].forEach((it) => {
    it.onclick = () => { G.edBrushKey = it.dataset.k; G.edArmed = true; buildObjPicker(dom.opSearch.value);
      toggleObjPicker(false); flashLog(["brush armed: " + G.edBrushKey + " — click the room to place (Esc to drop)"]); };
  });
}
function toggleObjPicker(force) {
  if (!dom.objpicker) return;
  const open = force != null ? force : dom.objpicker.classList.contains("hidden");
  dom.objpicker.classList.toggle("hidden", !open);
  if (open) { dom.opSearch.value = ""; buildObjPicker(""); setTimeout(() => dom.opSearch.focus(), 0); }
  else dom.opSearch.blur();
}
if (dom.opSearch) {
  dom.opSearch.addEventListener("input", () => buildObjPicker(dom.opSearch.value));
  dom.opSearch.addEventListener("keydown", (e) => { e.stopPropagation(); if (e.key === "Escape") toggleObjPicker(false); });
}
function edPos(e) {
  const r = cv.getBoundingClientRect();
  return { x: (e.clientX - r.left) * (W / r.width), y: (e.clientY - r.top) * (H / r.height) };
}
cv.addEventListener("pointerdown", (e) => {
  if (!G.editor) return;
  e.preventDefault();
  const p = edPos(e);
  let sel = null;
  G.stations.forEach((s, i) => { if (Math.hypot(p.x - s.x, p.y - s.y) < 26) sel = { type: "npc", i }; });
  if (!sel) for (let i = OBJ_LIST.length - 1; i >= 0; i--) {
    const o = OBJ_LIST[i];
    if (o.key !== "door" && Math.hypot(p.x - o.x, p.y - o.y) < 30) { sel = { type: "obj", o }; break; }
  }
  if (!sel) {
    // empty ground: with the brush ARMED (picker / [ ]) a click places the prop; otherwise it
    // deselects. Alt+click / double-click always place, armed or not.
    if (G.edArmed || e.altKey || e.detail >= 2) {
      const key = G.edBrushKey;
      const o = { key, x: Math.round(p.x), y: Math.round(p.y), ...(PROP_DEFAULTS[key] || { h: 40 }) };
      OBJ_LIST.push(o); sel = { type: "obj", o };
      edHydrate(o);          // a fresh prop must live fully: image, anim frames, collision box
    } else {
      G.edSel = null; G.edDrag = false;
      return;
    }
  } else {
    G.edArmed = false;       // touching an existing thing switches from placing to arranging
  }
  G.edSel = sel; G.edDrag = true;
  if (sel.type === "npc" && e.detail >= 2) { G.edDrag = false; openCharEdit(); }  // dbl-click a mind → its prompts
});
// a prop placed (or moved) in the editor must behave exactly like a room-built one — load its
// sprite + animation frames, and keep its collision footprint glued to where it actually is.
async function edHydrate(o) {
  if (o.solid) o.box = footprint(o);
  if (!OBJECTS[o.key]) {
    const im = await loadImg("/static/room/objects/" + o.key + ".png");
    if (im) OBJECTS[o.key] = prep(im);
  }
  if (o.anim && !o.frames) {
    const frames = await loadFrames("room/objects/" + o.anim, 24);
    if (frames.length) o.frames = frames;
  }
}
window.addEventListener("pointermove", (e) => {
  if (!G.editor || !G.edDrag || !G.edSel) return;
  const p = edPos(e);
  const x = Math.round(clamp(p.x, PLAY.x0, PLAY.x1)), y = Math.round(clamp(p.y, PLAY.y0, PLAY.y1));
  if (G.edSel.type === "obj") {
    const o = G.edSel.o;
    o.x = x; o.y = y;
    if (o.sortY != null) o.sortY = y;
    if (o.solid) o.box = footprint(o);   // collision (and the debug rect) move WITH the prop
  } else G.stations[G.edSel.i] = { x, y };
});
window.addEventListener("pointerup", () => { G.edDrag = false; });

function edCycleTheme() {
  G.edTheme = (G.edTheme + 1) % THEMES.length;
  const th = THEMES[G.edTheme];
  if (G.art) { G.art.tileset = th.tileset; G.art.mood = th.mood; G.art.windowLight = th.windowLight;
               G.art.floorTileset = null; }
  G.edWallIdx = G.edTheme; G.edFloorIdx = null;
  FLOORSET.ready = false;                       // theme resets both halves
  TILESET.ready = false; loadTileset(th.tileset);
  flashLog(["theme " + G.edTheme + " — " + (th.name || th.tileset.split("/").pop())]);
}
function edCycleWall() {                        // W: walls (+transitions) only; mood/light stay
  G.edWallIdx = ((G.edWallIdx == null ? G.edTheme : G.edWallIdx) + 1) % THEMES.length;
  const th = THEMES[G.edWallIdx];
  if (G.art) G.art.tileset = th.tileset;
  TILESET.ready = false; loadTileset(th.tileset);
  flashLog(["walls: " + th.tileset.split("/").pop()]);
}
function edCycleFloor() {                       // F: floor material only; wraps back to "same as walls"
  G.edFloorIdx = (G.edFloorIdx == null ? 0 : G.edFloorIdx + 1);
  if (G.edFloorIdx >= THEMES.length) {
    G.edFloorIdx = null;
    if (G.art) G.art.floorTileset = null;
    FLOORSET.ready = false;
    flashLog(["floor: same as walls"]);
    return;
  }
  const th = THEMES[G.edFloorIdx];
  if (G.art) G.art.floorTileset = th.tileset;
  loadTileset(th.tileset, FLOORSET);
  flashLog(["floor: " + th.tileset.split("/").pop()]);
}
function edDelete() {
  if (G.edSel && G.edSel.type === "obj") {
    const i = OBJ_LIST.indexOf(G.edSel.o);
    if (i >= 0) OBJ_LIST.splice(i, 1);
    G.edSel = null;
  }
}
function edNudge(arrow) {
  if (!G.edSel) return;
  const d = { arrowleft: [-1, 0], arrowright: [1, 0], arrowup: [0, -1], arrowdown: [0, 1] }[arrow];
  if (!d) return;
  const p = G.edSel.type === "obj" ? G.edSel.o : G.stations[G.edSel.i];
  p.x = Math.round(clamp(p.x + d[0], PLAY.x0, PLAY.x1));
  p.y = Math.round(clamp(p.y + d[1], PLAY.y0, PLAY.y1));
  if (G.edSel.type === "obj") {
    if (G.edSel.o.sortY != null) G.edSel.o.sortY = p.y;
    if (G.edSel.o.solid) G.edSel.o.box = footprint(G.edSel.o);
  }
}
function edExport() {
  const layout = edBuildLayout();
  const json = JSON.stringify(layout, null, 2);
  console.log('LEVEL LAYOUT JSON (paste under "layout"):\n' + json);
  const n = layout.objects.length, s = layout.stations.length;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(json).then(
      () => flashLog(["layout JSON copied (" + n + " props, " + s + " NPCs) — paste under \"layout\""]),
      () => flashLog(["layout JSON in console (clipboard blocked) — copy it there"]));
  } else flashLog(["layout JSON printed to console (open devtools)"]);
}
function drawEditorHUD() {
  if (!G.editor) return;
  ctx.save();
  let selinfo = "";
  if (G.edSel) {
    const p = G.edSel.type === "obj" ? G.edSel.o : G.stations[G.edSel.i];
    if (p) { ctx.strokeStyle = "#ffd866"; ctx.lineWidth = 2; ctx.strokeRect(p.x - 17, p.y - 17, 34, 34); }
    if (G.edSel.type === "obj") {
      const o = G.edSel.o, layer = o.background ? "wall" : o.floor ? "floor" : "object";
      selinfo = ` · sel:${o.key} (${layer})`;
    } else selinfo = " · sel:NPC";
  }
  ctx.fillStyle = "rgba(0,0,0,0.72)"; ctx.fillRect(0, 0, W, 18);
  ctx.fillStyle = "#ffd866"; ctx.font = "10px ui-monospace, monospace"; ctx.textAlign = "left";
  ctx.fillText(`EDITOR · brush: ${G.edBrushKey}${G.edArmed ? " ● ARMED — click to place" : ""} · H help · S save · L exit${selinfo}`, 5, 13);
  ctx.restore();
}
el("moral-restart").addEventListener("click", restart);

function interact() {
  if (G.data && G.data.run && G.data.run.over) {
    flashLog(["No way forward remains. Press R to begin again."]);
    return;
  }
  if (G.near.npc >= 0) {
    const c = G.chars[G.near.npc];
    if (c.engageable) openTalk(G.near.npc);
    else flashLog([c.why || `${c.name} won't speak to you.`]);
    return;
  }
  if (G.near.key) { pickUpKey(); return; }
  if (G.near.terminal) { openTerminal(); return; }
  if (G.near.door) {
    const solved = G.data && !G.data.door.locked;
    if (!solved) {
      flashLog([G.hasKey && G.data && G.data.terminal && !G.data.terminal.unlocked
        ? "The key turns, but a second lock holds — the records terminal still wants its name."
        : "The door is locked. The way out runs through the minds in this room."]);
      return;
    }
    if (!G.hasKey) { flashLog(["The key is yours now — pick it up first."]); return; }
    if (!G.doorOpen) { G.doorOpen = true; flashLog(["You turn the key. The door swings half-open."]); return; }
    goNextRoom();
  }
}

// ---------------------------------------------------------------------------- dialogue
function openTalk(id) {
  G.mode = "talk"; G.activeId = id; G.inputTarget = "talk";
  const c = G.chars[id];
  if (G.lastBrainCharId !== id) { G.lastBrain = null; G.lastBrainCharId = id; }  // no stale skulls
  clearReveal();
  dom.prompt.classList.add("hidden");          // the "Press E" hint isn't refreshed in talk mode
  dom.dialogue.classList.remove("hidden");
  dom.speaker.textContent = `${c.name}${c.title ? " — " + c.title : ""}`;
  dom.reply.textContent = `(${c.decision}) …`;
  dom.reply.className = "muted";
  clearBrain();
  if (dom.brainBtn) dom.brainBtn.classList.remove("hidden");
  updateDlgLife();
  drawPortrait(id);
  dom.input.placeholder = "Speak plainly… (Enter to say, Esc to step back)";
  focusInputClean();
}

function openTerminal() {
  const t = G.data.terminal || {};
  G.mode = "talk"; G.inputTarget = "terminal"; G.activeId = -1;
  dom.prompt.classList.add("hidden");
  dom.dialogue.classList.remove("hidden");
  dom.speaker.textContent = "▣ TERMINAL";
  clearBrain();
  if (dom.brainBtn) dom.brainBtn.classList.add("hidden");
  updateDlgLife();
  drawPortrait(-1);
  if (t.browser) {                 // flavor terminal: a read-only file listing, no code lock
    G.inputTarget = "terminal-browser";
    dom.reply.textContent = t.listing || "";
    dom.reply.className = "muted listing";
    dom.inputRow.classList.add("hidden");
    return;
  }
  dom.reply.textContent = t.prompt || "";
  dom.reply.className = "muted";
  dom.input.placeholder = "Enter a name…";
  focusInputClean();
}

function focusInputClean() {        // focus on the next tick + re-clear, so the triggering 'E' keydown
  dom.input.value = "";             // can never type itself into the box ("eelias" → rejected)
  setTimeout(() => { dom.input.value = ""; dom.input.focus(); }, 0);
}

function closeTalk() {
  G.mode = "walk"; G.activeId = -1; G.inputTarget = null;
  clearReveal();
  dom.dialogue.classList.add("hidden");
  dom.brainPanel.classList.add("hidden");
  dom.inputRow.classList.remove("hidden");   // the browser terminal hides it
  dom.input.blur();
}

async function submit() {
  const text = dom.input.value.trim();
  if (!text || G.busy) return;
  if (text[0] === "/") { handleSlash(text); dom.input.value = ""; return; }   // command, not speech
  G.busy = true; dom.send.disabled = true;
  dom.input.value = "";                     // the line is said — the field empties at once
  if (G.inputTarget === "talk") {           // the brain takes a few seconds — show it's thinking
    dom.reply.textContent = "thinking…"; dom.reply.className = "thinking"; clearBrain();
  }
  let res;
  if (G.inputTarget === "terminal") res = await api("/api/terminal", { code: text });
  else res = await api("/api/talk", { char_id: G.activeId, message: text });
  G.busy = false; dom.send.disabled = false;
  if (res.reply !== undefined) {
    G.lastBrain = res; G.lastBrainCharId = G.activeId;
    playTalkResult(res);
  } else if (res.blocked !== undefined || res.error !== undefined) {
    // a refusal/error must never leave the box stuck on "thinking…" — say it, then step back
    const refusal = String(res.blocked || res.error);
    if (G.inputTarget === "talk") {
      showReply(res.blocked ? ((G.chars[G.activeId] || {}).name || "…") : "⚠ SYSTEM", refusal);
      dom.reply.className = "muted";
      const id = G.activeId;
      setTimeout(() => { if (G.mode === "talk" && G.activeId === id) closeTalk(); }, 2000);
    } else flashLog([refusal]);
  }
  if (res.events) flashLog(res.events);
  const granted = G.inputTarget === "terminal" &&
    (res.events || []).some((ev) => String(ev).includes("ACCESS GRANTED"));
  applyState(res);
  if (res.run && res.run.over) return;
  if (G.inputTarget === "talk") { dom.input.focus(); return; }
  if (granted) {                      // hold the green confirmation ~2s before the modal closes
    dom.reply.textContent = "▣ ACCESS GRANTED";
    dom.reply.className = "granted";
    dom.input.blur();                 // no second submit while the confirmation holds
    setTimeout(() => { if (G.inputTarget === "terminal") closeTalk(); }, 2000);
    return;
  }
  closeTalk();
}

// one talk result → the staged performance: damage float, cascade reveal, flip banner, typed reply
function playTalkResult(res) {
  const st = G.stations[G.activeId];
  if (st && res.burned) G.floaters.push({ x: st.x, y: st.y - 40, t0: performance.now(), text: "-" + res.burned, col: "#ff5555" });
  revealCascade(res, () => {
    if (res.gave_key || res.submitted) showFlipBanner(res);
    typeReply(res.speaker, res.reply, () => {
      if (!G.panelSeen) {        // first verdict: a hint, not a takeover — the panel is the player's call
        G.panelSeen = true;
        flashLog(["🧠 Open the skull (button or /brain) to watch the regions argue. Esc closes."]);
      }
    });
  });
  if (!dom.brainPanel.classList.contains("hidden")) renderBrainPanel(res);
}

function showReply(name, reply) {
  dom.speaker.textContent = name;
  dom.reply.textContent = reply;
  dom.reply.className = "said";
}

function flashLog(events) {
  G.lastEvents = events || [];
  for (const e of G.lastEvents) {            // stack the last few, each fading out on its own clock
    const s = document.createElement("span");
    s.className = "ev"; s.textContent = "› " + e;
    dom.log.appendChild(s);
    setTimeout(() => { s.classList.add("fade"); setTimeout(() => s.remove(), 750); }, 6500);
  }
  while (dom.log.children.length > 3) dom.log.removeChild(dom.log.firstChild);
}

// ------------------------------------------------------------- brain (folded "open the skull")
// The six regions argue as a compact strip inside the VN box — each chip carries the region's
// HEADLINE SIGNAL (threat 8, reward −3, value +7…), with a delta arrow vs the previous turn for
// the same character. The full reasoning stays one hover (or 🧠) away.
const SIG_RX = {
  amygdala: { rx: /threat\s*([+-]?\d+)/i, name: "threat", goodUp: false },
  striatum: { rx: /reward\s*([+-]?\d+)/i, name: "reward", goodUp: true },
  vmpfc: { rx: /value\s*([+-]?\d+)/i, name: "value", goodUp: true },
};
function sigOf(t) {                          // headline → comparable number (when the region has one)
  const s = SIG_RX[t.key];
  if (s) { const m = String(t.headline).match(s.rx); if (m) return { name: s.name, num: +m[1], goodUp: s.goodUp }; }
  if (t.key === "relationship") {
    const m = String(t.headline).match(/rapport\s*(\d+)\s*→\s*(\d+)/i);
    if (m) return { name: "rapport", num: +m[2], from: +m[1], goodUp: true };
  }
  return null;
}
function chipHtml(t, prev) {
  const sig = sigOf(t);
  let text = String(t.headline).replace(/\/10\b/, "").replace(/\s+·.*$/, "");   // "threat 8/10" → "threat 8"
  let cls = "";
  if (sig) {
    const before = sig.from !== undefined ? sig.from : prev[t.key];
    if (before != null && before !== sig.num) {
      const up = sig.num > before;
      const fv = (n) => (sig.name === "threat" || sig.name === "rapport") ? String(n) : (n > 0 ? "+" + n : String(n));
      text = `${sig.name} ${fv(before)}→${fv(sig.num)} ${up ? "▲" : "▼"}`;
      cls = (up === sig.goodUp) ? " d-good" : " d-bad";
      if (sig.name === "value" && (before < 0) !== (sig.num < 0)) cls += " flip";   // sign flip — the moment
    }
  }
  return `<span class="brain-chip pop${cls}" style="--c:${t.color}" ` +
    `title="${escapeHtml(t.label)}: ${escapeHtml(t.headline)} — ${escapeHtml(t.detail)}">${escapeHtml(text)}</span>`;
}
function clearReveal() {                     // cancel pending chip reveals + typewriter (stale-safe)
  (G.revealT || []).forEach(clearTimeout); G.revealT = [];
  if (G.typeT) { clearInterval(G.typeT); G.typeT = null; }
}
// The engine emits the WHOLE argument (raw read → ·checked → ·rumination …) as separate trace
// rows; that full transcript belongs in the 🧠 panel. The strip shows one SETTLED chip per
// region (last row wins), plus the rare dramatic moments as their own chips.
function settledTraces(traces) {
  const byKey = {}, extras = [];
  for (const tr of traces) {
    if (/^\+\d+\s*life/i.test(String(tr.headline))) { extras.push(tr); continue; }  // "+30 life" (rest)
    if (/resonance|broken/i.test(tr.label)) { extras.push(tr); continue; }  // "the word lands" / "fear wins"
    if (tr.key === "dlpfc") continue;        // the spoken reply IS the dlPFC's output
    byKey[tr.key] = tr;                      // later rows (checked/rumination) settle the signal
  }
  return ["amygdala", "hippocampus", "striatum", "acc", "vmpfc", "relationship"]
    .filter((k) => byKey[k]).map((k) => byKey[k]).concat(extras);
}
function revealCascade(res, done) {          // regions report one by one — the argument happens live
  clearReveal();
  const traces = settledTraces(res.traces || []);
  const prev = G.prevSig[G.lastBrainCharId] || {};
  dom.brain.innerHTML = `<div class="brain-regions"></div>`;
  dom.brain.classList.remove("hidden");
  const row = dom.brain.querySelector(".brain-regions");
  let t = 80;
  for (const tr of traces) {
    G.revealT.push(setTimeout(() => row.insertAdjacentHTML("beforeend", chipHtml(tr, prev)), t));
    t += 300;
  }
  G.revealT.push(setTimeout(() => {
    // no equation line here — the chips ARE those numbers; the vmPFC breakdown lives in 🧠
    const tell = traces.find((x) => x.key === "relationship" && x.lever);
    let tail = "";
    if (tell) tail += `<div class="brain-tell">💡 ${escapeHtml(tell.lever)}` +
      `<span class="brain-tell-more"> · 🧠 to read the whole mind</span></div>`;
    if (tail) dom.brain.insertAdjacentHTML("beforeend", tail);
    const sigs = {};                         // remember this turn's signals for next-turn deltas
    for (const tr of traces) { const s = sigOf(tr); if (s) sigs[tr.key] = s.num; }
    G.prevSig[G.lastBrainCharId] = sigs;
    if (done) G.revealT.push(setTimeout(done, 240));
  }, t));
}
function typeReply(name, text, done) {       // the verdict spoken only after the regions have argued
  dom.speaker.textContent = name;
  dom.reply.className = "saying";
  text = String(text);
  let i = 0;
  if (G.typeT) clearInterval(G.typeT);
  G.typeT = setInterval(() => {
    i += 2;
    dom.reply.textContent = text.slice(0, i);
    dom.reply.scrollTop = dom.reply.scrollHeight;   // long beats scroll inside the capped box
    if (i >= text.length) {
      clearInterval(G.typeT); G.typeT = null;
      dom.reply.className = "said";
      if (done) done();
    }
  }, 26);
}
function showFlipBanner(res) {               // the flip moment, stamped across the canvas
  if (!dom.flip) return;
  const c = G.chars.find((x) => x.name === res.speaker) || G.chars[G.activeId] || {};
  const broke = !!res.submitted;             // coerced yield reads darker than a won one
  const who = c.gender === "female" ? "SHE BREAKS" : c.gender === "male" ? "HE BREAKS" : "THEY BREAK";
  const keyImg = `<img src="/static/room/objects/key.png" alt="key" onerror="this.outerHTML='🔑'">`;
  dom.flip.innerHTML = `<span>${broke ? who : "REFUSE → HELP"}</span>${keyImg}`;
  dom.flip.classList.toggle("dark", broke);
  dom.flip.classList.remove("hidden", "fading");
  void dom.flip.offsetWidth;                 // restart the entrance animation if re-shown
  clearTimeout(G.bannerT); clearTimeout(G.bannerT2);
  // hold ~2.7s, then a slow ~1.2s fade — a judge has time to actually read the flip
  G.bannerT = setTimeout(() => dom.flip.classList.add("fading"), 2700);
  G.bannerT2 = setTimeout(() => dom.flip.classList.add("hidden"), 3900);
}
function updateDlgLife() {                   // life readout on the plaque + portrait fading with it
  if (!dom.life) return;
  const c = (G.inputTarget === "talk" && G.activeId >= 0) ? G.chars[G.activeId] : null;
  if (!c) { dom.life.textContent = ""; dom.portrait.style.filter = ""; return; }
  const pct = c.life_pct != null ? c.life_pct : 100;
  dom.life.textContent = (c.life != null && c.life_max != null) ? `life ${c.life}/${c.life_max}` : "";
  dom.life.style.color = lifeColor(pct);
  const f = clamp((100 - pct) / 85, 0, 1);   // grayscale(0) at full → grayscale(.9) brightness(.7) near death
  dom.portrait.style.filter = f < 0.02 ? "" :
    `grayscale(${(f * 0.9).toFixed(2)}) brightness(${(1 - f * 0.3).toFixed(2)})`;
}
function clearBrain() {
  dom.brain.classList.add("hidden");
  dom.brain.innerHTML = "";
}

// ---- /brain : open the skull — the full per-region reasoning, not just the numbers ----
function handleSlash(cmd) {
  const c = cmd.slice(1).toLowerCase().trim().split(/\s+/)[0];
  if (["brain", "skull", "think", "reason", "mind", "мозг", "череп"].includes(c)) {
    if (!dom.brainPanel.classList.contains("hidden")) { closeBrainPanel(); return; }
    if (!G.lastBrain) { flashLog(["Speak to a mind first — then /brain opens its skull."]); return; }
    renderBrainPanel(G.lastBrain);
  } else {
    flashLog([`Unknown command: ${cmd}  ·  try /brain`]);
  }
}
function renderBrainPanel(res) {
  const traces = res.traces || [];
  // each department now hands the player a lever — surface the 3 most actionable as a "how to
  // reach them" digest up top, then the full per-region read (reasoning + its lever) below.
  const leverOf = (k) => (traces.find((t) => t.key === k && t.lever) || {}).lever || "";
  const reach = ["relationship", "hippocampus", "amygdala"]
    .map(leverOf).filter(Boolean)
    .map((l) => `<li>${escapeHtml(l)}</li>`).join("");
  const rows = traces.map((t) => `
    <div class="bp-region" style="--c:${t.color}">
      <div class="bp-region-h">
        <span class="bp-label" style="--c:${t.color}">${escapeHtml(t.label)}</span>
        <span class="bp-head-line">${escapeHtml(t.headline)}</span>
      </div>
      <div class="bp-detail">${escapeHtml(t.detail)}</div>
      ${t.lever ? `<div class="bp-lever">▶ ${escapeHtml(t.lever)}</div>` : ""}
      <div class="bp-tok">${t.tokens} tokens spent</div>
    </div>`).join("");
  const verdict = res.gave_key ? "🔑 KEY GIVEN" : res.verdict;
  dom.brainPanel.innerHTML =
    `<div class="bp-head"><span>🧠 inside ${escapeHtml(res.speaker || "the mind")}'s skull</span>` +
    `<span class="bp-close">/brain or Esc to close</span></div>` +
    (reach ? `<div class="bp-reach"><div class="bp-reach-h">🗝️ how to reach them</div>` +
             `<ul>${reach}</ul></div>` : "") +
    rows +
    `<div class="bp-verdict${res.gave_key ? " key" : ""}">→ ${escapeHtml(verdict)}` +
    `<div class="bp-burn">burned ${res.burned} tokens · ${res.seconds}s of thinking</div></div>`;
  dom.brainPanel.classList.remove("hidden");
}
function closeBrainPanel() {
  dom.brainPanel.classList.add("hidden");
  if (G.mode === "talk") dom.input.focus();
}

// ----------------------------------------------------------------------------- VN portrait
// Authored cast → painterly FLUX portrait (cover-fit, smoothed). Procedural NPC (no portrait yet)
// → its own sprite zoomed in (pixelated). Terminal → a green ▣ motif.
const PORTRAIT_CACHE = {};                 // url -> Image | null | "loading"
function drawPortrait(charIndex) {
  const pc = dom.portrait, p = pc.getContext("2d"), w = pc.width, h = pc.height;
  p.clearRect(0, 0, w, h);
  p.fillStyle = "#0a0c14"; p.fillRect(0, 0, w, h);

  if (G.inputTarget === "terminal") {      // terminal: no face, green readout motif
    p.fillStyle = "#0a140d"; p.fillRect(0, 0, w, h);
    p.fillStyle = "#50fa7b"; p.font = "90px ui-monospace, monospace";
    p.textAlign = "center"; p.textBaseline = "middle";
    p.fillText("▣", w / 2, h / 2);
    return;
  }
  const c = G.chars[charIndex];
  if (!c) return;

  if (c.portrait) {                        // FLUX raster portrait
    // /api/portrait/{id} is room-relative — id 0 is a different person each room — so key the
    // cache (and bust the browser cache) per character identity, not by the reused URL.
    const ident = c.sprite_key || normName(c.name);
    const key = c.portrait + "|" + ident;
    let im = PORTRAIT_CACHE[key];
    if (im === undefined) {
      PORTRAIT_CACHE[key] = "loading";
      const url = c.portrait + (c.portrait.includes("?") ? "&" : "?") + "k=" + encodeURIComponent(ident);
      loadImg(url).then((img) => {
        PORTRAIT_CACHE[key] = img;
        if (G.mode === "talk" && G.activeId === charIndex) drawPortrait(charIndex);
      });
      im = "loading";
    }
    if (im && im !== "loading") { coverDraw(p, im, w, h); return; }
    // while loading (or on failure) fall through to the sprite so the frame is never blank
  }

  const sp = NPC_SPRITES[c.spriteKey || normName(c.name)];   // fallback: zoom the NPC's own sprite
  const entry = sp && sp.ready ? (sp.dir["south"] || Object.values(sp.dir)[0]) : null;
  if (entry) {
    p.imageSmoothingEnabled = false;
    const b = entry.bbox;
    const scale = Math.min(w / b.w, h / b.h) * 1.7;          // fill the frame, head near the top
    const dw = b.w * scale, dh = b.h * scale;
    p.drawImage(entry.img, b.x, b.y, b.w, b.h, Math.round((w - dw) / 2), Math.round(h * 0.12), dw, dh);
  } else {
    p.fillStyle = "#4a5066"; p.font = "80px ui-monospace, monospace";
    p.textAlign = "center"; p.textBaseline = "middle";
    p.fillText("?", w / 2, h / 2);
  }
}
function coverDraw(c2, img, w, h) {        // cover-fit, smoothed (painterly portraits downscale cleanly)
  c2.imageSmoothingEnabled = true;
  const s = Math.max(w / img.width, h / img.height);
  const dw = img.width * s, dh = img.height * s;
  c2.drawImage(img, (w - dw) / 2, (h - dh) / 2, dw, dh);
}

// ----------------------------------------------------------------------- room / restart
async function goNextRoom() {
  if (G.busy) return;
  G.busy = true; setPrompt("the way opens…");
  const res = await api("/api/next-room", {});
  G.busy = false;
  if (res.events) flashLog(res.events);
  applyState(res);
}
async function restart() {
  const res = await api("/api/reset", {});
  dom.moral.classList.add("hidden");
  clearTimeout(G.moralTimer); G.moralTimer = null;
  G.roomSlug = null;       // force room-art rebuild
  applyState(res);          // closes the VN box + clears the brain for the fresh run
  clearBrain();
}
function reRoll() {                         // dev: re-roll auto-placement of the current room
  if (!G.art) return;
  const layout = autoLayout(G.art.manifest, G.art.doors, Math.floor(Math.random() * 1e9), G.chars.length);
  if (layout) {
    G.art = { ...G.art, objects: layout.objects, stations: layout.stations };
    OBJ_LIST = layout.objects; G.stations = layout.stations;
    flashLog(["🎲 auto-placed: reachable, no door-blocks, no overlaps"]);
  } else flashLog(["auto-place failed — kept layout"]);
  G.issues = roomIssues();
}
const PROC_NAMES = ["A Forgotten Ward", "The Boiler Room", "A Sealed Office", "The Dispensary", "An Old Cellar", "The Morgue Annex", "A Locked Archive"];
function devProceduralRoom() {              // dev: assemble a procedural room from the theme library
  const name = PROC_NAMES[Math.floor(Math.random() * PROC_NAMES.length)];
  G.roomSlug = "proc:" + name + ":" + Math.floor(Math.random() * 1e6);
  G.art = resolveRoom(name, G.chars.length, Math.floor(Math.random() * 1e9));
  OBJ_LIST = G.art.objects; G.stations = G.art.stations;
  const MALE = ["Elias", "Tomas", "Viktor", "Hugo", "Cyrus", "Bram", "Sol", "Otto"];
  const FEMALE = ["Mara", "Nadia", "Iris", "Petra", "Ada", "Dora", "Noor", "Vera"];
  const ROLE = ["the keeper", "the night nurse", "the records clerk", "a former patient", "the orderly", "the widow", "an old guard", "the cousin"];
  const mp = MALE.slice(), fp = FEMALE.slice();
  G.chars = G.chars.map((c) => {                 // gendered name + matching sprite (consistent)
    const g = Math.random() < 0.5 ? "m" : "f", names = g === "f" ? fp : mp;
    const cast = NPC_CAST.filter((x) => x.g === g), arr = cast.length ? cast : NPC_CAST;
    return { ...c, name: names.splice(Math.floor(Math.random() * names.length), 1)[0] || c.name,
      gender: g === "f" ? "female" : "male", title: ROLE[Math.floor(Math.random() * ROLE.length)],
      portrait: null,                              // generated NPC has no FLUX portrait → sprite-zoom fallback
      spriteKey: arr[Math.floor(Math.random() * arr.length)].key };
  });
  if (G.data) G.data.room = { ...G.data.room, name };
  dom.room.textContent = name + "  (procedural)";
  G.player = { x: W / 2, y: PLAY.y1 - 50 };
  TILESET.ready = false; loadTileset(G.art.tileset); FLOORSET.ready = false; loadObjects();
  closeTalk(); clearBrain();
  G.hasKey = false; G.doorOpen = false; G.keyItem = null;
  G.issues = roomIssues();
}
async function devGenerate() {             // dev: real LLM-generated procedural room (names + stories + gender)
  flashLog(["generating a new room (LLM)…"]);
  G.roomSlug = null;                       // force room-art rebuild for the new room
  const res = await api("/api/dev/generate", {});
  if (res.error) { flashLog([res.error]); return; }
  applyState(res);
}
async function devRoster() {               // dev: room assembled from minted roster (real faces + stories)
  flashLog(["assembling a room from the roster…"]);
  G.roomSlug = null;                       // force room-art rebuild
  const res = await api("/api/dev/roster", {});
  if (res.error) { flashLog([res.error]); return; }
  applyState(res);
}
async function gotoRoom(idx) {             // dev: jump straight to a room (skips solving)
  dom.moral.classList.add("hidden");
  clearTimeout(G.moralTimer); G.moralTimer = null;
  G.roomSlug = null;       // force room-art rebuild
  closeTalk();
  clearBrain();
  applyState(await api("/api/dev/room", { idx }));
}
function stageMoral(d) {       // run over: the WIN gets the black epilogue card; a death stays in
  if (!dom.moral.classList.contains("hidden") || G.moralTimer || G.deathBarked) return;
  closeTalk();
  if (d.run.won) {             // walked out — let the open door breathe ~3s, then the card
    G.moralTimer = setTimeout(() => { G.moralTimer = null; showMoral(d.run.moral); }, 3000);
    return;
  }
  // a death: no modal — the body lies in the room, the verdict is spoken over it, and after a
  // few seconds the player is free to walk among what they've done. R starts over.
  G.deathBarked = true;
  const crit = (G.lastEvents || []).find((e) => /key is lost/i.test(e)) || (G.lastEvents || [])[0];
  if (crit) showBark(crit);
  const line = String(d.run.moral || "").split("\n").map(s => s.trim()).filter(Boolean)[0] || "";
  setTimeout(() => {
    showBark(line + "  ·  Press R to begin again.");
    setTimeout(hideBark, 4000);              // then the room is theirs to wander
  }, 4200);
}
function showMoral(text) {
  dom.moralText.textContent = text || "";    // server-side moral varies by how the run ended
  dom.moral.classList.remove("hidden");
  closeTalk();
}

// -------------------------------------------------------------------------------- loop
function update(dt) {
  if (G.editor) { G.moving = false; return; }     // layout editor: freeze the player, drag with mouse
  // after a death the run is over but the ROOM stays open — the player may walk among what
  // they've done; only the win epilogue card (or the pause menu) freezes the world.
  if (G.mode !== "walk" || !dom.moral.classList.contains("hidden")
      || (dom.pause && !dom.pause.classList.contains("hidden"))) { G.moving = false; return; }
  let dx = 0, dy = 0;
  const k = G.keys;
  if (k.has("a") || k.has("arrowleft")) dx -= 1;
  if (k.has("d") || k.has("arrowright")) dx += 1;
  if (k.has("w") || k.has("arrowup")) dy -= 1;
  if (k.has("s") || k.has("arrowdown")) dy += 1;
  G.moving = !!(dx || dy);
  if (dx || dy) {
    const m = Math.hypot(dx, dy) || 1;
    const nx = clamp(G.player.x + (dx / m) * SPEED * dt, PLAY.x0 + PR, PLAY.x1 - PR);
    const ny = clamp(G.player.y + (dy / m) * SPEED * dt, PLAY.y0 + PR, PLAY.y1 - PR);
    if (!blockedAt(nx, G.player.y)) G.player.x = nx;   // axis-separated: slide along props
    if (!blockedAt(G.player.x, ny)) G.player.y = ny;
    G.dir = dir8(dx, dy);
    G.walkPhase += SPEED * dt;        // advance the step cycle by distance travelled
  } else {
    G.walkPhase = 0;                  // reset so the next walk starts from the contact pose
  }
  computeNear();
  barkNear();
}

function computeNear() {
  const p = G.player;
  let best = -1, bd = NPC_R;
  G.chars.forEach((c, i) => {
    const st = G.stations[i]; if (!st || !c.alive) return;
    const d = Math.hypot(p.x - st.x, p.y - st.y);
    if (d < bd) { bd = d; best = i; }
  });
  G.near.npc = best;
  // key on the floor: auto-pick when you walk over it
  G.near.key = false;
  if (G.keyItem) {
    const dk = Math.hypot(p.x - G.keyItem.x, p.y - G.keyItem.y);
    if (dk < 22) { pickUpKey(); }
    else if (dk < 46 && best < 0) G.near.key = true;
  }
  G.near.terminal = !!(G.terminalPos && best < 0 && !G.near.key &&
    Math.hypot(p.x - G.terminalPos.x, p.y - G.terminalPos.y) < TERM_R);
  G.near.door = best < 0 && !G.near.terminal && !G.near.key &&
    Math.hypot(p.x - DOOR.cx, p.y - DOOR.cy) < DOOR_R;

  if (best >= 0) {
    const c = G.chars[best];
    setPrompt(c.engageable ? `Press E to speak with ${c.name}` : `${c.name} won't speak to you`);
  } else if (G.near.key) setPrompt("walk over the key to take it");
  else if (G.near.terminal) setPrompt("Press E to use the terminal");
  else if (G.near.door) setPrompt(doorPrompt());
  else setPrompt(null);
}
function doorPrompt() {
  if (!(G.data && !G.data.door.locked)) {
    return (G.hasKey && G.data && G.data.terminal && !G.data.terminal.unlocked)
      ? "🔒 the records terminal still bars the way"
      : "🔒 locked — change a mind here first";
  }
  if (!G.hasKey) return "take the key first";
  if (!G.doorOpen) return "Press E to unlock the door";
  return "Press E to step through";
}
function pickUpKey() {
  if (!G.keyItem) return;
  G.keyItem = null; G.hasKey = true;
  flashLog(["🔑 You take the key. Now the door."]);
}
function setPrompt(text) {
  if (!text || G.mode !== "walk") { dom.prompt.classList.add("hidden"); return; }
  dom.prompt.textContent = text;
  dom.prompt.classList.remove("hidden");
}

// ------------------------------------------------------------------------------ render
// --- barks: a black, light-framed remark the protagonist mutters. showBark(text) on demand;
// objects tagged with a `bark` string fire it once when you step up close (re-arms per room). ---
let barkTimer = null;
function showBark(text, speaker) {
  if (!dom.bark) return;
  dom.bark.innerHTML = (speaker ? `<span class="bark-who">${escapeHtml(speaker)}</span>` : "") +
    escapeHtml(text);
  dom.bark.classList.remove("hidden");
  clearTimeout(barkTimer);
  barkTimer = setTimeout(() => dom.bark.classList.add("hidden"), 4800);
}
function hideBark() { if (dom.bark) dom.bark.classList.add("hidden"); clearTimeout(barkTimer); }
function barkNear() {
  if (!G.barked) G.barked = new Set();
  for (const o of OBJ_LIST) {
    if (!o.bark) continue;
    const id = o.key + o.x + "," + o.y;
    if (Math.hypot(G.player.x - o.x, G.player.y - o.y) < 58 && !G.barked.has(id)) {
      G.barked.add(id); showBark(o.bark, o.barkWho);
    }
  }
}

function render() {
  ctx.clearRect(0, 0, W, H);
  drawRoom();
  drawFloorDecals();         // rugs etc. flat on the floor, under everyone
  drawBackgroundObjects();   // windows + door + wall props — always behind the cast
  drawDoor();
  // the terminal prop carries the visual; the fallback box only if the room art lost the sprite
  if (G.terminalPos && !(OBJ_LIST || []).some((o) => o.key === "terminal"))
    drawTerminal(G.terminalPos, G.data && G.data.terminal && G.data.terminal.unlocked);
  // y-sorted entities so the player passes in front of / behind the minds
  const ents = [];
  G.chars.forEach((c, i) => {
    if (G.stations[i]) ents.push({ y: G.stations[i].y, fn: () => drawChar(c, G.stations[i], i === G.near.npc) });
  });
  ents.push({ y: G.player.y, fn: drawPlayer });
  for (const o of OBJ_LIST) {
    const sp = OBJECTS[o.key];
    if (!sp || o.background || o.floor) continue;   // walls/floor drawn in their own layers
    ents.push({
      y: o.sortY != null ? o.sortY : o.y, fn: () => {   // sortY lets a prop sit on furniture (candle on table)
        if (o.shadow !== false && sp.sil) {       // shadow = flattened silhouette → matches shape & angle
          const scale = o.h / sp.bbox.h;
          const w = sp.bbox.w * scale, sh = sp.bbox.h * scale * 0.32;
          ctx.save();
          ctx.globalAlpha = 0.3;
          ctx.drawImage(sp.sil, o.x - w / 2 + 5, o.y - sh + 3, w, sh);
          ctx.restore();
        }
        const e = o.frames ? o.frames[Math.floor(performance.now() / (o.fps || 110)) % o.frames.length] : sp;
        blitSprite(e, o.x, o.y, o.h);
      },
    });
  }
  ents.sort((a, b) => a.y - b.y).forEach((e) => e.fn());
  drawLighting();
  drawKeyItem();             // after lighting → the pickup stays bright and findable
  drawSignFx();              // NVIDIA relic flare + sparks, above the light-map so they glow
  drawLabels();
  drawFloaters();            // token-burn damage numbers, above everything readable
  drawDebug();
  drawEditorHUD();           // layout-editor selection + help bar (only when editor is on)
}

function drawDebug() {                      // toggle with G — see anchors/footprints instead of guessing
  if (!G.debug) return;
  ctx.save();
  ctx.strokeStyle = "rgba(0,255,255,0.12)"; ctx.lineWidth = 1;
  for (let x = 0; x <= W; x += TS) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); }
  for (let y = 0; y <= H; y += TS) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }
  ctx.font = "9px ui-monospace, monospace"; ctx.textAlign = "center";
  for (const o of OBJ_LIST) {
    if (o.box) { ctx.strokeStyle = "rgba(255,90,90,0.9)"; ctx.strokeRect(o.box.x0, o.box.y0, o.box.x1 - o.box.x0, o.box.y1 - o.box.y0); }
    ctx.fillStyle = "#0ff"; ctx.beginPath(); ctx.arc(o.x, o.y, 2.5, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#fff"; ctx.fillText(o.key, o.x, o.y + 11);   // name only — coords are noise here
  }
  G.chars.forEach((c, i) => { const s = G.stations[i]; if (!s) return; ctx.fillStyle = "#ff0"; ctx.beginPath(); ctx.arc(s.x, s.y, 2.5, 0, Math.PI * 2); ctx.fill(); });
  ctx.fillStyle = "#0f0"; ctx.beginPath(); ctx.arc(G.player.x, G.player.y, 2.5, 0, Math.PI * 2); ctx.fill();
  for (const k of keepOuts()) {              // placement keep-out zones (doors)
    ctx.fillStyle = "rgba(255,60,60,0.12)"; ctx.fillRect(k.x0, k.y0, k.x1 - k.x0, k.y1 - k.y0);
    ctx.strokeStyle = "rgba(255,60,60,0.5)"; ctx.strokeRect(k.x0, k.y0, k.x1 - k.x0, k.y1 - k.y0);
  }
  for (const is of G.issues || []) {         // flag violating props
    const f = footprint(is.o);
    ctx.strokeStyle = "#ff2020"; ctx.lineWidth = 2; ctx.strokeRect(f.x0, f.y0, f.x1 - f.x0, f.y1 - f.y0);
  }
  ctx.restore();
}

let LIGHTC = null;                          // offscreen light-map
function addLight(lx, x, y, r, col, mid) {  // additive radial light onto the map
  const g = lx.createRadialGradient(x, y, Math.min(6, r * 0.1), x, y, r);
  g.addColorStop(0, col);
  g.addColorStop(0.6, mid);
  g.addColorStop(1, "rgba(0,0,0,0)");
  lx.fillStyle = g;
  lx.fillRect(x - r, y - r, r * 2, r * 2);
}
function drawLighting() {
  if (!LIGHTC) { LIGHTC = document.createElement("canvas"); LIGHTC.width = W; LIGHTC.height = H; }
  const lx = LIGHTC.getContext("2d");
  const t = performance.now();
  // 1) ambient darkness with a built-in vignette (dim centre, near-black edges)
  lx.globalCompositeOperation = "source-over";
  const mood = (G.art && G.art.mood) || { in: "rgb(64,66,84)", out: "rgb(10,11,18)" };
  const amb = lx.createRadialGradient(W / 2, H * 0.46, H * 0.18, W / 2, H / 2, H * 0.85);
  amb.addColorStop(0, mood.in);
  amb.addColorStop(1, mood.out);
  lx.fillStyle = amb; lx.fillRect(0, 0, W, H);
  // 2) light sources add brightness/colour
  lx.globalCompositeOperation = "lighter";
  for (const o of OBJ_LIST) {                // warm candle / wall-sconce pools (flicker); sign blinks
    if (!o.light) continue;
    const fl = o.blink ? signBlink(t)
      : 1 + Math.sin(t / 90 + o.x) * 0.07 + Math.sin(t / 37 + o.y) * 0.04;
    addLight(lx, o.x, o.lightY != null ? o.lightY : o.y - 16, (o.lightR || 95) * Math.max(0.12, fl),
      o.lightCol || "rgba(255,201,120,0.95)", o.lightMid || "rgba(255,150,70,0.33)");
  }
  const wl = (G.art && G.art.windowLight) || MOONLIGHT;   // window light varies (moonlight / daylight)
  for (const o of OBJ_LIST) {
    if (o.key !== "window") continue;
    addLight(lx, o.x, o.y + 46, wl.r, wl.col, wl.mid);
  }
  addLight(lx, G.player.x, G.player.y - 12, 78, "rgba(238,228,202,0.62)", "rgba(232,220,190,0.18)"); // player readability
  lx.globalCompositeOperation = "source-over";
  // 3) composite: scene × lightmap → revealed in light pools, dark elsewhere
  ctx.save();
  ctx.globalCompositeOperation = "multiply";
  ctx.drawImage(LIGHTC, 0, 0);
  ctx.restore();
}

// --- the broken NVIDIA relic: green neon blink + spark shower (deeper room, the NVIDIA-lane nod) ---
function signBlink(t) {                       // intensity 0..1 of a struggling green neon
  const c = t % 2600;
  if (c < 1700) return 0.82 + 0.18 * Math.sin(t / 130);   // steady hum
  if (c < 2080) return 0.12;                               // cuts out
  return (Math.floor(t / 80) % 2) ? 0.16 : 1.0;            // crackles back on
}
function spawnSpark(x, y, cols) {
  const a = -Math.PI / 2 + (Math.random() - 0.5) * 1.7, sp = 45 + Math.random() * 95;
  cols = cols || ["#b6ff8a", "#f2ffe0"];
  G.sparks.push({ x, y, vx: Math.cos(a) * sp, vy: Math.sin(a) * sp - 18,
    life: 0.45 + Math.random() * 0.45, max: 0.9, sz: 1 + Math.random() * 2,
    col: cols[(Math.random() * cols.length) | 0] });
}
// crash-hot colors for wreck-type spark sources (the neon sign keeps its green)
const _HOT_SPARKS = ["#ffb86c", "#ffe9c9", "#fff2a8"];
function spawnSmoke(x, y) {
  G.smoke.push({ x: x + (Math.random() - 0.5) * 14, y, vx: (Math.random() - 0.5) * 6,
    vy: -14 - Math.random() * 14, r: 3 + Math.random() * 4, grow: 7 + Math.random() * 6,
    life: 1.6 + Math.random() * 1.4, max: 3.0 });
}
function updateSparks(dt) {                    // runs every frame (also during dialogue) via frame()
  if (!G.sparks) G.sparks = [];
  if (!G.smoke) G.smoke = [];
  for (const o of OBJ_LIST) {
    if (o.spark) {
      const hot = !o.blink;                    // blinking neon = green crackle; wrecks = hot metal
      const ox = o.x + (o.sparkX != null ? o.sparkX : 14), oy = o.y - o.h * 0.66;
      const c = performance.now() % 2600;
      if (!hot && c > 2080 && Math.random() < 0.55) spawnSpark(ox, oy);  // neon burst on re-strike
      else if (Math.random() < (hot ? 0.05 : 0.02)) spawnSpark(ox, oy, hot ? _HOT_SPARKS : null);
    }
    if (o.smoke && Math.random() < 0.10) {     // a steady column of smoke off the wreck
      spawnSmoke(o.x + (o.smokeX != null ? o.smokeX : 0),
                 o.y - (o.smokeY != null ? o.smokeY : o.h * 0.8));
    }
  }
  for (const s of G.sparks) { s.x += s.vx * dt; s.y += s.vy * dt; s.vy += 270 * dt; s.life -= dt; }
  if (G.sparks.length) G.sparks = G.sparks.filter((s) => s.life > 0).slice(-140);
  for (const p of G.smoke) { p.x += p.vx * dt; p.y += p.vy * dt; p.r += p.grow * dt; p.life -= dt; }
  if (G.smoke.length) G.smoke = G.smoke.filter((p) => p.life > 0).slice(-60);
}
function drawSignFx() {                        // drawn above the light-map so it glows
  const sign = OBJ_LIST.find((o) => o.spark && o.blink);      // only the neon gets the face flare
  if (sign && signBlink(performance.now()) > 0.6) {           // emissive flare on the sign face
    const cx = sign.x, cy = sign.y - sign.h * 0.5, r = 62;
    ctx.save(); ctx.globalCompositeOperation = "lighter";
    const g = ctx.createRadialGradient(cx, cy, 4, cx, cy, r);
    g.addColorStop(0, "rgba(120,255,130,0.42)"); g.addColorStop(1, "rgba(60,200,70,0)");
    ctx.fillStyle = g; ctx.fillRect(cx - r, cy - r, r * 2, r * 2); ctx.restore();
  }
  if (G.smoke && G.smoke.length) {             // smoke under the sparks, soft round puffs
    ctx.save();
    for (const p of G.smoke) {
      const k = Math.max(0, Math.min(1, p.life / p.max));
      ctx.globalAlpha = 0.22 * k;
      ctx.fillStyle = "#9a948c";
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
  }
  if (G.sparks && G.sparks.length) {
    ctx.save();
    for (const s of G.sparks) {
      ctx.globalAlpha = Math.max(0, Math.min(1, s.life / s.max));
      ctx.fillStyle = s.col; ctx.fillRect(s.x | 0, s.y | 0, s.sz, s.sz);
    }
    ctx.restore();
  }
}

function drawRoom() {
  if (TILESET.ready) {
    for (let row = 0; row < ROWS; row++) {
      for (let col = 0; col < COLS; col++) {
        const idx = (vWall(col, row) ? 8 : 0) + (vWall(col + 1, row) ? 4 : 0) +
          (vWall(col, row + 1) ? 2 : 0) + (vWall(col + 1, row + 1) ? 1 : 0);
        // pure-floor cells may come from a different material (F in the editor); walls and the
        // wall→floor transitions always come from the wall set so the seams stay coherent
        const useF = idx === 0 && FLOORSET.ready && FLOORSET.wang[0];
        const set = useF ? FLOORSET : TILESET;
        const t = useF ? FLOORSET.wang[0] : (TILESET.wang[idx] || TILESET.wang[0]);
        if (t) ctx.drawImage(set.img, t.x, t.y, t.w, t.h, col * TS, row * TS, TS, TS);
      }
    }
    return;
  }
  // procedural fallback until the tileset image loads
  ctx.fillStyle = "#1b2030"; ctx.fillRect(0, 0, W, H);
  const t = 32;
  for (let y = PLAY.y0; y < PLAY.y1; y += t) {
    for (let x = PLAY.x0; x < PLAY.x1; x += t) {
      const even = ((x / t | 0) + (y / t | 0)) % 2 === 0;
      ctx.fillStyle = even ? "#0e1018" : "#0b0d14";
      ctx.fillRect(x, y, Math.min(t, PLAY.x1 - x), Math.min(t, PLAY.y1 - y));
    }
  }
}
function drawFloorDecals() {                // rugs: CENTER-anchored + squashed into the 3/4 floor plane
  for (const o of OBJ_LIST) {
    if (!o.floor) continue;
    const sp = OBJECTS[o.key];
    if (!sp) continue;
    const sc = o.h / sp.bbox.h;
    const w = sp.bbox.w * sc, h = sp.bbox.h * sc * 0.72;
    ctx.drawImage(sp.img, sp.bbox.x, sp.bbox.y, sp.bbox.w, sp.bbox.h,
      Math.round(o.x - w / 2), Math.round(o.y - h / 2), w, h);
  }
}
function drawBackgroundObjects() {          // wall-set objects (windows, door, sconces): behind the cast
  for (const o of OBJ_LIST) {
    if (!o.background) continue;
    const sp = OBJECTS[o.key];
    if (!sp) continue;
    if (o.key === "door" && o.lockedOnly) {     // exit door: closed, then half-open once turned
      const spr = (G.doorOpen && OBJECTS.door_open) ? OBJECTS.door_open : sp;
      blitSprite(spr, o.x, o.y, o.h);
      continue;
    }
    if (o.lockedOnly && !(G.data && G.data.door.locked)) continue;
    if (o.wallShadow) {                     // soft contact shadow so panels read off the wall, not glued
      const sc = o.h / sp.bbox.h, w = sp.bbox.w * sc;
      const g = ctx.createLinearGradient(0, o.y, 0, o.y + 13);
      g.addColorStop(0, "rgba(0,0,0,0.4)"); g.addColorStop(1, "rgba(0,0,0,0)");
      ctx.save(); ctx.fillStyle = g; ctx.fillRect(o.x - w / 2, o.y, w, 13); ctx.restore();
    }
    blitSprite(sp, o.x, o.y, o.h);
  }
}
function drawDoor() {
  // The door's own sprite (closed → half-open) carries the visual now — no green EXIT overlay.
  // Only draw a marker if the door sprite failed to load, so the exit is never invisible.
  if (OBJECTS.door) return;
  const x = DOOR.cx - DOOR.w / 2, h = WALLR * TS;
  const open = G.doorOpen;
  ctx.fillStyle = open ? "rgba(80,250,123,0.16)" : "rgba(255,85,85,0.13)";
  ctx.fillRect(x, 0, DOOR.w, h);
  ctx.strokeStyle = open ? "#50fa7b" : "#ff5555"; ctx.lineWidth = 2;
  ctx.strokeRect(x + 1, 1, DOOR.w - 2, h - 2);
  ctx.fillStyle = open ? "#50fa7b" : "#ff5555";
  ctx.font = "12px Pixel, ui-monospace, monospace"; ctx.textAlign = "center";
  ctx.fillText(open ? "▲" : "🔒", DOOR.cx, h - 7);
}
function drawKeyItem() {                     // the earned key, bobbing on the floor with a warm glow
  if (!G.keyItem) return;
  const k = OBJECTS.key;
  const bx = G.keyItem.x, by = G.keyItem.y, bob = Math.sin(performance.now() / 280) * 3;
  ctx.save();                                // soft golden glow so it reads as a pickup
  const g = ctx.createRadialGradient(bx, by, 1, bx, by, 20);
  g.addColorStop(0, "rgba(255,216,102,0.55)"); g.addColorStop(1, "rgba(255,216,102,0)");
  ctx.fillStyle = g; ctx.beginPath(); ctx.arc(bx, by, 20, 0, Math.PI * 2); ctx.fill();
  ctx.restore();
  ctx.fillStyle = "rgba(0,0,0,0.35)"; ellipse(bx, by + 9, 9, 3);
  if (k && k.bbox) blitSprite(k, bx, by + 9 + bob, 24);
  else { ctx.fillStyle = "#ffd866"; ctx.font = "20px serif"; ctx.textAlign = "center"; ctx.fillText("🔑", bx, by + bob); }
}
function drawTerminal(pos, unlocked) {
  ctx.fillStyle = "#11161f";
  ctx.fillRect(pos.x - 16, pos.y - 12, 32, 24);
  ctx.strokeStyle = unlocked ? "#50fa7b" : "#8be9fd";
  ctx.lineWidth = 2;
  ctx.strokeRect(pos.x - 16, pos.y - 12, 32, 24);
  ctx.fillStyle = unlocked ? "#50fa7b" : "#8be9fd";
  ctx.font = "9px ui-monospace, monospace";
  ctx.textAlign = "center";
  ctx.fillText("▣", pos.x, pos.y + 3);
}

function drawChar(c, st, near) {
  // shadow
  ctx.fillStyle = "rgba(0,0,0,0.4)";
  ellipse(st.x, st.y + 17, 14, 5);
  if (near && c.alive) {                         // proximity ring
    ctx.strokeStyle = c.engageable ? "#ffb86c" : "#ff5555";
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(st.x, st.y + 2, 24, 0, Math.PI * 2); ctx.stroke();
  }
  const sp = NPC_SPRITES[c.spriteKey || normName(c.name)];
  let headTop;
  if (sp && sp.ready) {
    let entry;
    if (!c.alive) {                               // dead: dying clip → lying pose
      entry = deadFrame(c, sp);
    } else {                                       // alive: breathing idle, facing the player
      const d = dir8(G.player.x - st.x, G.player.y - st.y);
      const idle = sp.idle[d];
      entry = (idle && idle.length) ? idle[Math.floor(performance.now() / 220) % idle.length]
        : (sp.dir[d] || sp.dir["south"]);
    }
    ctx.save();
    if (!c.alive && !sp.death.length) ctx.globalAlpha = 0.3;   // faded fallback if no death sprite
    blitScaled(entry, st.x, st.y + 16, sp.scale || 1);
    ctx.restore();
    headTop = st.y - 30;
  } else {
    ctx.save();
    ctx.globalAlpha = c.alive ? 1 : 0.3;
    const body = !c.alive ? "#555a68" : (c.is_holder ? "#ffd866" : "#6cd0c0");
    const head = !c.alive ? "#6a7080" : (c.is_holder ? "#ffe9a6" : "#a7e8df");
    ctx.fillStyle = body; ctx.fillRect(st.x - 9, st.y - 4, 18, 20);     // torso
    ctx.fillStyle = head; ctx.beginPath(); ctx.arc(st.x, st.y - 10, 8, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
    headTop = st.y - 20;
  }
}

function drawLabels() {                     // names + bars drawn AFTER lighting → stay readable
  ctx.font = "15px Pixel, ui-monospace, monospace"; ctx.textAlign = "center";
  G.chars.forEach((c, i) => {
    const st = G.stations[i]; if (!st) return;
    const sp = NPC_SPRITES[c.spriteKey || normName(c.name)];
    const headTop = (sp && sp.ready) ? st.y - 30 : st.y - 20;
    if (!c.engageable && c.alive) { ctx.fillStyle = "#ff5555"; ctx.fillText("✕", st.x, headTop + 8); }
    ctx.fillStyle = c.alive ? "#e6e6ee" : "rgba(160,150,140,0.65)";
    ctx.fillText(c.name + (c.is_holder && c.alive && !c.gave_key ? " 🔑" : ""), st.x, headTop - 6);
    if (!c.alive) return;                    // a dead mind has no life left to meter, no trust to win
    const fl = G.lifeFlash[c.name];          // the bar flashes red right after a hit
    const hit = fl && performance.now() - fl < 700;
    if (hit) { ctx.fillStyle = "rgba(255,40,40,0.85)"; ctx.fillRect(st.x - 23, st.y + 23, 46, 6); }
    bar(st.x - 22, st.y + 24, 44, 4, c.life_pct / 100,
      (hit && Math.floor(performance.now() / 90) % 2) ? "#ff2020" : lifeColor(c.life_pct));
    bar(st.x - 22, st.y + 30, 44, 4, (c.rapport || 0) / 10, "#ffb86c");
  });
}

function drawFloaters() {                    // "-N" token burn drifting up off the NPC, fading ~1.2s
  if (!G.floaters.length) return;
  const now = performance.now();
  G.floaters = G.floaters.filter((f) => now - f.t0 < 1200);
  ctx.save();
  ctx.font = "17px Pixel, ui-monospace, monospace"; ctx.textAlign = "center";
  for (const f of G.floaters) {
    const k = (now - f.t0) / 1200;
    ctx.globalAlpha = 1 - k;
    ctx.fillStyle = "#000"; ctx.fillText(f.text, f.x + 1, f.y - k * 28 + 1);   // hard pixel shadow
    ctx.fillStyle = f.col || "#ff5555"; ctx.fillText(f.text, f.x, f.y - k * 28);
  }
  ctx.restore();
}

function drawPlayer() {
  const p = G.player;
  ctx.fillStyle = "rgba(0,0,0,0.45)";
  ellipse(p.x, p.y + 13, 11, 4);
  if (PLAYER.ready) {
    let entry;
    const wf = PLAYER.walk[G.dir];
    if (G.moving && wf && wf.length) {
      entry = wf[Math.floor(G.walkPhase / STRIDE) % wf.length];
    } else if (!G.moving && G.dir === "south" && PLAYER.idle.length) {
      entry = PLAYER.idle[Math.floor(performance.now() / 170) % PLAYER.idle.length];
    } else {
      entry = PLAYER.dir[G.dir] || PLAYER.dir["south"];
    }
    if (entry) { blitSprite(entry, p.x, p.y + 15, 44); return; }
  }
  // fallback blob (until sprites load)
  ctx.fillStyle = "#50fa7b"; ctx.fillRect(p.x - 8, p.y - 4, 16, 18);
  ctx.fillStyle = "#b6ffce"; ctx.beginPath(); ctx.arc(p.x, p.y - 9, 7, 0, Math.PI * 2); ctx.fill();
}

// ----------------------------------------------------------------------------- helpers
function bar(x, y, w, h, frac, color) {
  frac = Math.max(0, Math.min(1, frac));
  ctx.fillStyle = "rgba(255,255,255,0.12)"; ctx.fillRect(x, y, w, h);
  ctx.fillStyle = color; ctx.fillRect(x, y, w * frac, h);
}
function ellipse(x, y, rx, ry) { ctx.beginPath(); ctx.ellipse(x, y, rx, ry, 0, 0, Math.PI * 2); ctx.fill(); }
function lifeColor(pct) { return pct > 50 ? "#50fa7b" : (pct > 20 ? "#f1fa8c" : "#ff5555"); }
function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// -------------------------------------------------------------------------------- sprites
// 8-rotation sprite sets (low top-down). Each frame is auto-cropped to its content bbox so
// a sprite's *feet* anchor to the world regardless of the transparent padding around it.
const DIRS8 = ["east", "south-east", "south", "south-west", "west", "north-west", "north", "north-east"];
const PLAYER = { dir: {}, idle: [], walk: {}, ready: false };
const NPC_SPRITES = {};          // normName -> { dir:{8 rotations}, ready } (lazy-loaded, blob fallback)
const normName = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const NPC_CAST = [
  { key: "the-warden", g: "m" }, { key: "doctor-aldous", g: "m" }, { key: "sam", g: "m" },
  { key: "guard", g: "m" }, { key: "shopkeeper", g: "m" }, { key: "worker", g: "m" },
  { key: "molly", g: "f" }, { key: "widow", g: "f" }, { key: "matron", g: "f" },
  { key: "clerk", g: "f" }, { key: "charwoman", g: "f" },
];
function spriteForChar(c) {       // roster slug wins; else authored-by-name; else gender-matched pool
  if (c.sprite_key) return c.sprite_key;
  if (NPC_SPRITES[normName(c.name)]) return normName(c.name);
  if (!G.spriteFor[c.name]) {
    const want = c.gender === "female" ? "f" : c.gender === "male" ? "m" : (Math.random() < 0.5 ? "m" : "f");
    const pool = NPC_CAST.filter((x) => x.g === want), arr = pool.length ? pool : NPC_CAST;
    G.spriteFor[c.name] = arr[Math.floor(Math.random() * arr.length)].key;
  }
  return G.spriteFor[c.name];
}

function dir8(dx, dy) {
  const i = ((Math.round(Math.atan2(dy, dx) / (Math.PI / 4)) % 8) + 8) % 8;
  return DIRS8[i];
}

function loadImg(url) {
  return new Promise((res) => {
    const im = new Image();
    im.onload = () => res(im);
    im.onerror = () => res(null);
    im.src = url;
  });
}

// Frame manifest: /api/manifest maps every frame-bearing dir (path relative to /static) to its
// frame count, so animations load with Promise.all instead of 404-probing for the end of each
// sequence. The fetch fires at script eval (parallel with asset loading); loaders await it once.
let FRAME_COUNTS = null;
const FRAME_MANIFEST = fetch("/api/manifest")
  .then((r) => (r.ok ? r.json() : null))
  .then((m) => (FRAME_COUNTS = m))
  .catch(() => null);

async function loadFrames(dir, maxProbe = 16) {   // dir relative to /static, e.g. "sprites/player/walk/north"
  await FRAME_MANIFEST;
  const url = (i) => "/static/" + dir + "/frame_" + String(i).padStart(3, "0") + ".png";
  if (FRAME_COUNTS) {                             // known count → load all frames in parallel, zero 404s
    const n = FRAME_COUNTS[dir] || 0;             // absent from a good manifest == no frames exist
    const imgs = await Promise.all(Array.from({ length: n }, (_, i) => loadImg(url(i))));
    return imgs.filter(Boolean).map(prep);
  }
  const frames = [];                              // manifest fetch failed → old probe-until-a-gap fallback
  for (let i = 0; i < maxProbe; i++) {
    const im = await loadImg(url(i));
    if (!im) break;
    frames.push(prep(im));
  }
  return frames;
}

function prep(img) {                 // measure the opaque content box once, at load time
  const oc = document.createElement("canvas");
  oc.width = img.width; oc.height = img.height;
  const o = oc.getContext("2d");
  o.drawImage(img, 0, 0);
  const d = o.getImageData(0, 0, img.width, img.height).data;
  let x0 = img.width, y0 = img.height, x1 = 0, y1 = 0, found = false;
  for (let y = 0; y < img.height; y++) {
    for (let x = 0; x < img.width; x++) {
      if (d[(y * img.width + x) * 4 + 3] > 16) {
        found = true;
        if (x < x0) x0 = x; if (x > x1) x1 = x;
        if (y < y0) y0 = y; if (y > y1) y1 = y;
      }
    }
  }
  const bbox = found ? { x: x0, y: y0, w: x1 - x0 + 1, h: y1 - y0 + 1 }
    : { x: 0, y: 0, w: img.width, h: img.height };
  const sil = document.createElement("canvas");          // black silhouette for shape-matched shadows
  sil.width = bbox.w; sil.height = bbox.h;
  const sx = sil.getContext("2d");
  sx.drawImage(img, bbox.x, bbox.y, bbox.w, bbox.h, 0, 0, bbox.w, bbox.h);
  sx.globalCompositeOperation = "source-in";
  sx.fillStyle = "#000"; sx.fillRect(0, 0, bbox.w, bbox.h);
  return { img, bbox, sil };
}

function blitSprite(entry, cx, footY, targetH) {
  const b = entry.bbox, s = targetH / b.h, w = b.w * s, h = b.h * s;
  ctx.drawImage(entry.img, b.x, b.y, b.w, b.h, Math.round(cx - w / 2), Math.round(footY - h), w, h);
}

function blitScaled(entry, cx, footY, scale) {   // fixed scale (poses of different heights stay sized right)
  const b = entry.bbox, w = b.w * scale, h = b.h * scale;
  ctx.drawImage(entry.img, b.x, b.y, b.w, b.h, Math.round(cx - w / 2), Math.round(footY - h), w, h);
}

async function loadPlayerSprites() {
  const base = "/static/sprites/player/";
  for (const d of DIRS8) {
    const im = await loadImg(base + d + ".png");
    if (im) PLAYER.dir[d] = prep(im);
  }
  PLAYER.idle = await loadFrames("sprites/player/idle_south", 4);
  await Promise.all(DIRS8.map(async (d) => {       // walk cycle per direction, counts from the manifest
    const frames = await loadFrames("sprites/player/walk/" + d, 16);
    if (frames.length) PLAYER.walk[d] = frames;
  }));
  PLAYER.ready = Object.keys(PLAYER.dir).length > 0;
}

async function loadNpcSprite(key) {       // rotations + idle (per dir) + death (south, reused)
  if (!key || NPC_SPRITES[key]) return;
  const set = { dir: {}, idle: {}, death: [], scale: 1, ready: false };
  NPC_SPRITES[key] = set;                 // claim the slot first so we don't double-load
  const base = "/static/sprites/npc/" + key + "/";
  for (const d of DIRS8) {
    const im = await loadImg(base + d + ".png");
    if (im) set.dir[d] = prep(im);
  }
  for (const d of DIRS8) {                 // breathing idle per facing (counts from the manifest)
    const frames = await loadFrames("sprites/npc/" + key + "/idle/" + d, 16);
    if (frames.length) set.idle[d] = frames;
  }
  // death (south) — dying clip + final lying pose
  set.death = await loadFrames("sprites/npc/" + key + "/death", 16);
  const ref = set.dir["south"] || Object.values(set.dir)[0];
  set.scale = ref ? 46 / ref.bbox.h : 1;   // fix scale from the standing pose so the lying body isn't huge
  set.ready = Object.keys(set.dir).length > 0;
}

function deadFrame(c, sp) {                 // dying plays once, then settles on the lying pose
  if (!sp.death.length) return sp.dir["south"] || Object.values(sp.dir)[0];
  const t0 = G.dying[c.name];
  if (t0 == null) return sp.death[sp.death.length - 1];
  const idx = Math.floor((performance.now() - t0) / 120);
  return idx < sp.death.length ? sp.death[idx] : sp.death[sp.death.length - 1];
}

// --------------------------------------------------------------------------- room tileset
// Wang (corner) tileset: idx = NW*8 + NE*4 + SW*2 + SE*1, corner=1 if wall ("upper") else floor.
const TILESET = { img: null, wang: {}, ready: false };
const FLOORSET = { img: null, wang: {}, ready: false };   // optional floor-only override (editor: F)

async function loadTileset(base = "/static/room", into = TILESET) {
  try {
    if (!base) { into.ready = false; into.img = null; into.wang = {}; return; }
    const res = await fetch(base + "/tileset.json");
    if (!res.ok) return;
    const meta = await res.json();
    const img = await loadImg(base + "/tileset.png");
    if (!img) return;
    const wang = {};
    const tiles = (meta.tileset_data && meta.tileset_data.tiles) || meta.tiles || [];
    for (const t of tiles) {
      const c = t.corners, b = t.bounding_box || t.bbox;
      if (!c || !b) continue;
      const idx = (c.NW === "upper" ? 8 : 0) + (c.NE === "upper" ? 4 : 0) +
        (c.SW === "upper" ? 2 : 0) + (c.SE === "upper" ? 1 : 0);
      wang[idx] = { x: b.x, y: b.y, w: b.width, h: b.height };
    }
    into.img = img; into.wang = wang;
    into.ready = Object.keys(wang).length >= 2;
  } catch (e) { /* keep procedural fallback */ }
}

function vWall(vx, vy) {                    // is this vertex wall terrain? (carve door openings)
  const d = currentDoors();
  if (vx >= DOORC - 1 && vx <= DOORC + 1) {
    if (d.top && vy <= WALLR - 1) return false;             // top exit opening
    if (d.bottom && vy >= ROWS - WALLR + 1) return false;   // bottom entry opening
  }
  return vx < WALLR || vy < WALLR || vx > COLS - WALLR || vy > ROWS - WALLR;
}

// ------------------------------------------------------------------------- room objects
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const OBJECTS = {};                         // key -> {img, bbox}
// Per-room layout + tileset. Object PNGs live in one shared pool (/static/room/objects);
// each room declares which props it uses and where, by the same category rules (wall/decal/floor).
const ROOMS = {
  "the-holding-cell": {
    tileset: "/static/room",
    mood: { in: "rgb(70,64,78)", out: "rgb(13,11,16)" },     // warm candlelit
    doors: { top: true },                                    // start room: exit only
    objects: [
      { key: "rug",     x: 452, y: 350, h: 104, floor: true },
      { key: "picture", x: 110, y: WALL_Y, h: 34, background: true, wallShadow: true },
      { key: "window",  x: 210, y: WALL_Y, h: 42, background: true },
      { key: "sconce",  x: 284, y: WALL_Y, h: 44, background: true, light: true, lightY: 26, lightR: 105 },
      { key: "door",    x: DOOR.cx, y: WALLR * TS + 14, h: 84, lockedOnly: true, shadow: false, background: true },
      { key: "sconce",  x: 376, y: WALL_Y, h: 44, background: true, light: true, lightY: 26, lightR: 105 },
      { key: "window",  x: 430, y: WALL_Y, h: 42, background: true },
      { key: "shelf",   x: 514, y: WALL_Y, h: 42, background: true, wallShadow: true },
      { key: "cot",     x: 130, y: 152, h: 64, solid: true,  fw: 58, fh: 20 },
      { key: "bench",   x: 504, y: 150, h: 46, solid: true,  fw: 60, fh: 15 },
      { key: "plant",   x: 548, y: 116, h: 56, solid: false },
      { key: "table",   x: 430, y: 352, h: 50, solid: true,  fw: 62, fh: 22 },
      { key: "stool",   x: 496, y: 360, h: 34, solid: false },
      { key: "candle",  x: 430, y: 327, h: 30, solid: false, shadow: false, sortY: 358, anim: "candle_anim", fps: 100, light: true, lightY: 314, lightR: 125 },
      { key: "crate",   x: 104, y: 362, h: 40, solid: true,  fw: 46, fh: 16 },
      { key: "barrel",  x: 152, y: 350, h: 48, solid: true,  fw: 32, fh: 14 },
      { key: "barrel",  x: 112, y: 326, h: 48, solid: true,  fw: 32, fh: 14 },
      { key: "bucket",  x: 196, y: 356, h: 40, solid: false },
    ],
  },
  "the-records-office": {
    tileset: "/static/room/records",
    mood: { in: "rgb(44,54,66)", out: "rgb(7,11,16)" },      // cold, blue-grey, terminal-lit
    doors: { top: true, bottom: true },                      // entered from bottom, exit at top
    objects: [
      { key: "rug",      x: 452, y: 372, h: 92, floor: true },
      { key: "door",     x: DOOR.cx, y: H - 4, h: 78, shadow: false, sortY: 999 },  // entry (closed behind you)
      { key: "picture",  x: 110, y: WALL_Y, h: 34, background: true, wallShadow: true },
      { key: "window",   x: 210, y: WALL_Y, h: 42, background: true },
      { key: "sconce",   x: 284, y: WALL_Y, h: 44, background: true, light: true, lightY: 26, lightR: 105 },
      { key: "door",     x: DOOR.cx, y: WALLR * TS + 14, h: 84, lockedOnly: true, shadow: false, background: true },
      { key: "sconce",   x: 376, y: WALL_Y, h: 44, background: true, light: true, lightY: 26, lightR: 105 },
      { key: "window",   x: 430, y: WALL_Y, h: 42, background: true },
      { key: "shelf",    x: 514, y: WALL_Y, h: 42, background: true, wallShadow: true },
      // the records terminal — glowing green console (Mellum lock), Aldous guards it
      { key: "terminal", x: 188, y: 168, h: 72, solid: true, fw: 52, fh: 18, light: true, lightY: 132, lightR: 100, lightCol: "rgba(120,255,190,0.72)", lightMid: "rgba(70,210,160,0.22)" },
      { key: "cabinet",  x: 108, y: 215, h: 78, solid: true, fw: 50, fh: 16 },
      { key: "cabinet",  x: 540, y: 250, h: 78, solid: true, fw: 50, fh: 16 },
      // clerk's desk vignette on the rug
      { key: "table",    x: 452, y: 372, h: 50, solid: true, fw: 62, fh: 22 },
      { key: "stool",    x: 516, y: 378, h: 34, solid: false },
      { key: "candle",   x: 452, y: 347, h: 30, solid: false, shadow: false, sortY: 380, anim: "candle_anim", fps: 100, light: true, lightY: 334, lightR: 120 },
      { key: "crate",    x: 110, y: 360, h: 40, solid: true, fw: 46, fh: 16 },
      { key: "bucket",   x: 165, y: 356, h: 40, solid: false },
      { key: "plant",    x: 548, y: 120, h: 56, solid: false },
      // sponsor relics, deeper rooms only (never round 1, to keep the opening melancholy clean).
      // NVIDIA still has residual power — green neon blink + sparks; HuggingFace is long dead.
      { key: "nvidia",      x: 116, y: 300, h: 80, solid: false, shadow: true, spark: true,
        light: true, blink: true, lightY: 266, lightR: 98,
        lightCol: "rgba(120,255,124,0.92)", lightMid: "rgba(55,200,70,0.30)" },
      { key: "huggingface", x: 506, y: 200, h: 58, solid: false, shadow: true,
        bark: "Is that... a face? Why is it hugging me?" },
    ],
  },
};
let OBJ_LIST = ROOMS["the-holding-cell"].objects;

async function loadObjects() {
  for (const o of OBJ_LIST) {
    if (!OBJECTS[o.key]) {                  // load each image once (some keys appear twice, e.g. window)
      const im = await loadImg("/static/room/objects/" + o.key + ".png");
      if (im) OBJECTS[o.key] = prep(im);
    }
    if (o.solid) o.box = { x0: o.x - o.fw / 2, y0: o.y - o.fh, x1: o.x + o.fw / 2, y1: o.y };
    if (o.anim) {                          // animated prop (e.g. candle flame) — counts from the manifest
      const frames = await loadFrames("room/objects/" + o.anim, 24);
      if (frames.length) o.frames = frames;
    }
  }
}

function blockedAt(px, py) {                 // solid-object footprints + living NPCs block the player
  for (const o of OBJ_LIST) {
    if (!o.box) continue;
    if (px > o.box.x0 - PR && px < o.box.x1 + PR && py > o.box.y0 - PR && py < o.box.y1 + PR) return true;
  }
  for (let i = 0; i < (G.stations || []).length; i++) {
    const c = G.chars[i], s = G.stations[i];
    if (!s || !c || !c.alive) continue;      // a body on the floor doesn't block
    if (Math.hypot(px - s.x, py - s.y) < PR + 13) return true;
  }
  return false;
}

// ---- PLACEMENT RULES (constrain where props may sit; used to validate authored rooms + drive procedural) ----
const currentDoors = () => (G.art && G.art.doors) || { top: true };
const footprint = (o) => ({ x0: o.x - o.fw / 2, y0: o.y - o.fh, x1: o.x + o.fw / 2, y1: o.y });
const rectsOverlap = (a, b) => a.x0 < b.x1 && a.x1 > b.x0 && a.y0 < b.y1 && a.y1 > b.y0;
function keepOuts(doors) {                    // clear zones: thresholds in front of each door
  doors = doors || currentDoors();
  const cx = DOORC * TS, hw = TS * 1.6, depth = TS * 3, out = [];
  if (doors.top) out.push({ x0: cx - hw, y0: 0, x1: cx + hw, y1: WALLR * TS + depth, tag: "top-door" });
  if (doors.bottom) out.push({ x0: cx - hw, y0: H - WALLR * TS - depth, x1: cx + hw, y1: H, tag: "bottom-door" });
  return out;
}
function issuesFor(objects, stations, doors) {   // door-block / overlap / out-of-bounds / reachability
  const issues = [], ko = keepOuts(doors);
  const foots = objects.filter((o) => o.solid).map((o) => ({ o, f: footAt(o, o.x, o.y) }));
  for (const { o, f } of foots) {
    for (const k of ko) if (rectsOverlap(f, k)) issues.push({ o, why: "blocks " + k.tag });
    if (f.x0 < PLAY.x0 - 6 || f.x1 > PLAY.x1 + 6 || f.y0 < PLAY.y0 - 48 || f.y1 > PLAY.y1 + 6) issues.push({ o, why: "out-of-bounds" });
  }
  for (let i = 0; i < foots.length; i++)
    for (let j = i + 1; j < foots.length; j++)
      if (rectsOverlap(foots[i].f, foots[j].f)) issues.push({ o: foots[i].o, why: "overlaps " + foots[j].o.key });
  if (!reachOK(objects, stations, doors)) issues.push({ o: { key: "(room)" }, why: "unreachable" });
  return issues;
}
const roomIssues = () => issuesFor(OBJ_LIST, G.stations || [], currentDoors());

// ---- REACHABILITY + AUTO-PLACEMENT (procedural rooms): valid positions, guaranteed reachable ----
function rng(seed) { let s = (seed >>> 0) || 1; return () => (s = (s * 1664525 + 1013904223) >>> 0) / 4294967296; }
const rand = (r, a, b) => a + r() * (b - a);
const footAt = (o, x, y) => { const fw = o.fw || 40, fh = o.fh || 16; return { x0: x - fw / 2, y0: y - fh, x1: x + fw / 2, y1: y }; };
const inKeepOut = (x, y, doors) => keepOuts(doors).some((k) => x > k.x0 && x < k.x1 && y > k.y0 && y < k.y1);
function sample(r, gen, ok, tries = 60) { for (let i = 0; i < tries; i++) { const c = gen(); if (ok(c)) return c; } return null; }
function footValid(f, placed, stations, doors) {
  const b = { x0: PLAY.x0 + 18, y0: PLAY.y0 + 64, x1: PLAY.x1 - 18, y1: PLAY.y1 - 18 };
  if (f.x0 < b.x0 || f.x1 > b.x1 || f.y0 < b.y0 || f.y1 > b.y1) return false;
  for (const k of keepOuts(doors)) if (rectsOverlap(f, k)) return false;
  for (const p of placed) if (rectsOverlap({ x0: f.x0 - 8, y0: f.y0 - 8, x1: f.x1 + 8, y1: f.y1 + 8 }, p)) return false;
  for (const s of stations) if (rectsOverlap(f, { x0: s.x - 24, y0: s.y - 34, x1: s.x + 24, y1: s.y + 8 })) return false;
  return true;
}
function reachOK(objects, stations, doors) {            // flood-fill from entry; every target must be reachable
  const cell = 16;
  const solids = objects.filter((o) => o.solid).map((o) => footAt(o, o.x, o.y));
  const walk = (cx, cy) => {
    const x = cx * cell + cell / 2, y = cy * cell + cell / 2;
    if (x < PLAY.x0 + PR || x > PLAY.x1 - PR || y < PLAY.y0 + PR || y > PLAY.y1 - PR) return false;
    for (const f of solids) if (x > f.x0 - PR && x < f.x1 + PR && y > f.y0 - PR && y < f.y1 + PR) return false;
    return true;
  };
  const sx = Math.round((DOORC * TS) / cell), sy = Math.round((PLAY.y1 - 36) / cell);
  if (!walk(sx, sy)) return false;
  const seen = new Set([sx + "," + sy]), q = [[sx, sy]];
  while (q.length) {
    const [cx, cy] = q.pop();
    for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const nx = cx + dx, ny = cy + dy, k = nx + "," + ny;
      if (!seen.has(k) && walk(nx, ny)) { seen.add(k); q.push([nx, ny]); }
    }
  }
  const near = (tx, ty, R) => {
    for (const k of seen) { const [cx, cy] = k.split(",").map(Number); if (Math.hypot(cx * cell + cell / 2 - tx, cy * cell + cell / 2 - ty) < R) return true; }
    return false;
  };
  for (const s of stations) if (!near(s.x, s.y, NPC_R)) return false;
  if (doors.top && !near(DOORC * TS, WALLR * TS + 12, DOOR_R)) return false;
  for (const o of objects) if (o.key === "terminal" && !near(o.x, o.y - 18, TERM_R)) return false;
  return true;
}
const WALL_SLOT = { sconce: [282, 378], window: [200, 460], picture: [110], shelf: [540] };
function zoneRect(z) {                                   // placement zones: furniture lines walls, clutter in corners
  const L = PLAY.x0, R = PLAY.x1, T = PLAY.y0, B = PLAY.y1;
  switch (z) {
    case "wallL": return { x0: L + 34, y0: T + 100, x1: L + 92, y1: B - 80 };
    case "wallR": return { x0: R - 92, y0: T + 100, x1: R - 34, y1: B - 80 };
    case "cornerBL": return { x0: L + 36, y0: B - 92, x1: L + 150, y1: B - 34 };
    case "cornerBR": return { x0: R - 150, y0: B - 92, x1: R - 36, y1: B - 34 };
    case "cornerTR": return { x0: R - 118, y0: T + 98, x1: R - 36, y1: T + 152 };
    case "center": return { x0: W / 2 - 60, y0: T + 178, x1: W / 2 + 60, y1: B - 96 };
    default: return { x0: L + 46, y0: T + 110, x1: R - 46, y1: B - 30 };
  }
}
function autoLayout(manifest, doors, seed, nChars) {     // build a room from a manifest; retry until valid
  for (let attempt = 0; attempt < 24; attempt++) {
    const r = rng(seed + attempt * 7919);
    const out = [], placed = [], stations = [], slotIdx = {};
    for (const def of manifest.filter((o) => o.background)) {       // wall props → slots
      const slots = WALL_SLOT[def.key] || [110, 540];
      const i = (slotIdx[def.key] = slotIdx[def.key] || 0); slotIdx[def.key]++;
      const o = { ...def, x: slots[i % slots.length], y: WALL_Y };
      if (def.key === "sconce") o.lightY = 26;
      out.push(o);
    }
    if (doors.top) out.push({ key: "door", x: DOOR.cx, y: WALLR * TS + 14, h: 84, lockedOnly: true, shadow: false, background: true });
    if (doors.bottom) out.push({ key: "door", x: DOOR.cx, y: H - 4, h: 78, shadow: false, sortY: 999 });
    let ok = true;
    for (let i = 0; i < nChars; i++) {                             // characters: upper-mid, spread
      const p = sample(r, () => ({ x: rand(r, PLAY.x0 + 80, PLAY.x1 - 80), y: rand(r, PLAY.y0 + 56, PLAY.y0 + 150) }),
        (c) => !inKeepOut(c.x, c.y, doors) && stations.every((s) => Math.hypot(s.x - c.x, s.y - c.y) > 100));
      if (!p) { ok = false; break; }
      stations.push(p);
    }
    // desk cluster (rug + table + candle-on-table + stool) — in the centre, leaving walking space
    if (ok && manifest.some((o) => o.key === "table")) {
      const z = zoneRect("center");
      const c = sample(r, () => ({ x: rand(r, z.x0, z.x1), y: rand(r, z.y0, z.y1) }),
        (cc) => footValid(footAt({ fw: 70, fh: 26 }, cc.x, cc.y), placed, stations, doors));
      if (!c) ok = false;
      else {
        const rug = manifest.find((o) => o.floor); if (rug) out.push({ ...rug, x: c.x, y: c.y });
        const td = manifest.find((o) => o.key === "table"); const tbl = { ...td, x: c.x, y: c.y + 6, box: footAt(td, c.x, c.y + 6) }; out.push(tbl); placed.push(tbl.box);
        const cd = manifest.find((o) => o.key === "candle"); if (cd) out.push({ ...cd, x: c.x, y: c.y - 12, sortY: c.y + 26, lightY: c.y - 28 });
        const sd = manifest.find((o) => o.key === "stool"); if (sd) out.push({ ...sd, x: c.x + (r() < 0.5 ? -62 : 62), y: c.y + 4 });
      }
    }
    // remaining floor props → their zones (walls / corners); optional clutter sometimes omitted
    if (ok) for (const def of manifest.filter((o) => !o.background && !o.floor && !["table", "candle", "stool"].includes(o.key))) {
      if (def.optional && r() < 0.35) continue;
      const o = { ...def }, zones = def.zones || ["any"];
      const p = sample(r, () => { const z = zoneRect(zones[Math.floor(r() * zones.length)]); return { x: rand(r, z.x0, z.x1), y: rand(r, z.y0, z.y1) }; },
        (c) => footValid(footAt(o, c.x, c.y), placed, stations, doors));
      if (!p) { ok = false; break; }
      o.x = p.x; o.y = p.y;
      if (o.solid) { o.box = footAt(o, o.x, o.y); placed.push(o.box); }
      if (o.sortY != null) o.sortY = o.y + 30;
      if (o.lightY != null) o.lightY = o.y - 20;
      out.push(o);
    }
    if (ok && issuesFor(out, stations, doors).length === 0) return { objects: out, stations };
  }
  return null;
}

// ---- THEME LIBRARY + room resolution: authored rooms use curated layouts; others are procedural ----
const WALLPROPS = [
  { key: "window", h: 42, background: true }, { key: "window", h: 42, background: true },
  { key: "sconce", h: 44, background: true, light: true, lightR: 105 }, { key: "sconce", h: 44, background: true, light: true, lightR: 105 },
  { key: "picture", h: 34, background: true, wallShadow: true }, { key: "shelf", h: 42, background: true, wallShadow: true },
];
const DESK = [
  { key: "rug", h: 94, floor: true },
  { key: "table", h: 50, solid: true, fw: 62, fh: 22 }, { key: "stool", h: 34 },
  { key: "candle", h: 30, shadow: false, anim: "candle_anim", fps: 100, light: true, lightR: 120 },
];
const CLUTTER = [
  { key: "crate", h: 40, solid: true, fw: 46, fh: 16, zones: ["cornerBL", "cornerBR"], optional: true },
  { key: "barrel", h: 48, solid: true, fw: 32, fh: 14, zones: ["cornerBL", "cornerBR"], optional: true },
  { key: "barrel", h: 48, solid: true, fw: 32, fh: 14, zones: ["cornerBR", "cornerBL"], optional: true },
  { key: "bucket", h: 40, zones: ["cornerBL", "cornerBR"], optional: true },
  { key: "plant", h: 56, zones: ["cornerTR", "cornerBR"], optional: true },
];
const CELL_PROPS = [...WALLPROPS, ...DESK,
  { key: "cot", h: 64, solid: true, fw: 58, fh: 20, zones: ["wallL", "wallR"] },
  { key: "bench", h: 46, solid: true, fw: 60, fh: 15, zones: ["wallR", "wallL"] }, ...CLUTTER];
const OFFICE_PROPS = [...WALLPROPS, ...DESK,
  { key: "terminal", h: 72, solid: true, fw: 52, fh: 18, light: true, lightR: 100, lightCol: "rgba(120,255,190,0.72)", lightMid: "rgba(70,210,160,0.22)", zones: ["wallL", "wallR"] },
  { key: "cabinet", h: 78, solid: true, fw: 50, fh: 16, zones: ["wallL", "wallR"] },
  { key: "cabinet", h: 78, solid: true, fw: 50, fh: 16, zones: ["wallR", "wallL"] }, ...CLUTTER];
// window light presets — day = bright/warm-ish through windows; night = dim cold moonlight
const MOONLIGHT = { col: "rgba(120,150,255,0.55)", mid: "rgba(105,135,255,0.16)", r: 78 };
const DAYLIGHT = { col: "rgba(255,236,180,0.85)", mid: "rgba(255,222,150,0.32)", r: 124 };
const OVERCAST = { col: "rgba(220,234,255,0.85)", mid: "rgba(198,218,255,0.30)", r: 122 };
const THEMES = [
  { tileset: "/static/room",         mood: { in: "rgb(70,64,78)",  out: "rgb(13,11,16)" }, windowLight: MOONLIGHT, manifest: CELL_PROPS },   // cell, night
  { tileset: "/static/room",         mood: { in: "rgb(122,112,94)", out: "rgb(38,30,24)" }, windowLight: DAYLIGHT,  manifest: CELL_PROPS },   // cell, day (bright, warm sun)
  { tileset: "/static/room/records", mood: { in: "rgb(44,54,66)",  out: "rgb(7,11,16)" },  windowLight: MOONLIGHT, manifest: OFFICE_PROPS }, // office, night cold
  { tileset: "/static/room/records", mood: { in: "rgb(98,106,118)", out: "rgb(28,32,40)" }, windowLight: OVERCAST, manifest: OFFICE_PROPS }, // office, day (bright overcast)
  { tileset: "/static/room/concrete", mood: { in: "rgb(58,62,70)",  out: "rgb(10,12,16)" }, windowLight: MOONLIGHT, manifest: CELL_PROPS },   // concrete, night
  { tileset: "/static/room/concrete", mood: { in: "rgb(108,112,120)", out: "rgb(30,32,38)" }, windowLight: OVERCAST, manifest: OFFICE_PROPS }, // concrete office, day
  { tileset: "/static/room/boiler",   mood: { in: "rgb(80,58,42)",  out: "rgb(18,12,8)" }, windowLight: { col: "rgba(255,150,60,0.5)", mid: "rgba(255,120,40,0.16)", r: 70 }, manifest: CELL_PROPS }, // boiler, warm furnace
  { tileset: "/static/room/brick",    mood: { in: "rgb(50,58,52)",  out: "rgb(9,13,10)" }, windowLight: MOONLIGHT, manifest: CELL_PROPS },     // brick cellar, damp green
  { tileset: "/static/room/hospital", mood: { in: "rgb(139,135,140)", out: "rgb(25,24,25)" }, windowLight: OVERCAST, manifest: CELL_PROPS },   // grimy hospital ward
  { tileset: "/static/room/wood",     mood: { in: "rgb(41,29,32)",  out: "rgb(6,4,5)" },   windowLight: MOONLIGHT, manifest: CELL_PROPS },     // dark timber room
  { tileset: "/static/room/metal",    mood: { in: "rgb(112,103,77)", out: "rgb(18,16,12)" }, windowLight: MOONLIGHT, manifest: OFFICE_PROPS }, // riveted iron deck
  { tileset: "/static/room/padded",   mood: { in: "rgb(140,123,107)", out: "rgb(25,22,19)" }, windowLight: OVERCAST, manifest: CELL_PROPS },   // padded asylum cell
  { tileset: "/static/room/stone",    mood: { in: "rgb(76,91,98)",  out: "rgb(12,14,15)" }, windowLight: MOONLIGHT, manifest: CELL_PROPS },    // stone block keep
  { tileset: "/static/room/rust",     mood: { in: "rgb(140,125,109)", out: "rgb(25,22,19)" }, windowLight: MOONLIGHT, manifest: CELL_PROPS },  // corroded rust hold
  { tileset: "/static/room/marble",   mood: { in: "rgb(140,131,137)", out: "rgb(25,23,24)" }, windowLight: OVERCAST, manifest: OFFICE_PROPS }, // faded marble hall
  { tileset: "/static/room/dirt",     mood: { in: "rgb(79,26,15)",  out: "rgb(12,4,2)" },  windowLight: MOONLIGHT, manifest: CELL_PROPS },     // earthen cave cell
  { tileset: "/static/room/library",  mood: { in: "rgb(99,64,38)",  out: "rgb(16,10,6)" }, windowLight: MOONLIGHT, manifest: OFFICE_PROPS },   // wood-paneled study
  { tileset: "/static/room/sewer",    mood: { in: "rgb(44,49,69)",  out: "rgb(7,7,11)" },  windowLight: MOONLIGHT, manifest: CELL_PROPS },     // slimy sewer vault
  // ---- BRIGHT moods: high ambient (mood.out is the un-lit base, so big values = lit room) ----
  { name: "operating theater", tileset: "/static/room/hospital", mood: { in: "rgb(212,222,224)", out: "rgb(108,118,120)" }, windowLight: DAYLIGHT, manifest: CELL_PROPS },   // surgical white
  { name: "clean ward",        tileset: "/static/room/hospital", mood: { in: "rgb(182,192,188)", out: "rgb(84,92,90)" },  windowLight: OVERCAST, manifest: CELL_PROPS },     // daylight ward
  { name: "bright office",     tileset: "/static/room/marble",   mood: { in: "rgb(196,188,176)", out: "rgb(96,90,82)" },  windowLight: DAYLIGHT, manifest: OFFICE_PROPS },   // working daytime office
  { name: "day library",       tileset: "/static/room/library",  mood: { in: "rgb(168,128,86)",  out: "rgb(74,54,36)" },  windowLight: DAYLIGHT, manifest: OFFICE_PROPS },   // warm sunlit study
];
const hashStr = (s) => { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; };
function manifestOf(objects) {                          // strip positions → a reusable manifest (for re-roll)
  const keep = ["background", "floor", "solid", "fw", "fh", "shadow", "anim", "fps", "light", "lightR", "lightCol", "lightMid", "sortY", "wallShadow"];
  return objects.filter((o) => o.key !== "door").map((o) => {
    const m = { key: o.key, h: o.h };
    for (const f of keep) if (o[f] !== undefined) m[f] = o[f];
    return m;
  });
}
function artFromLayout(L, nChars) {                     // story level's explicit placed layout → G.art
  const n = THEMES.length, th = THEMES[((((L.theme | 0) % n) + n) % n)] || THEMES[0];
  const objects = (L.objects || []).map((o) => ({ ...o }));
  // doors are never part of a saved layout (the editor strips them) — rebuild them from the
  // doors spec, or every saved room loses its visible exit (the "missing door" bug)
  const doors = L.doors || { top: true };
  if (doors.top && !objects.some((o) => o.key === "door" && o.y < H / 2))
    objects.push({ key: "door", x: DOOR.cx, y: WALLR * TS + 14, h: 84, lockedOnly: true, shadow: false, background: true });
  if (doors.bottom && !objects.some((o) => o.key === "door" && o.y >= H / 2))
    objects.push({ key: "door", x: DOOR.cx, y: H - 4, h: 78, shadow: false, sortY: 999 });
  return {
    tileset: L.tileset || th.tileset,
    floorTileset: L.floorTileset || null,
    mood: L.mood || th.mood,
    windowLight: L.windowLight || th.windowLight,
    doors: L.doors || { top: true },
    objects,
    stations: (L.stations && L.stations.length) ? L.stations.map((s) => ({ ...s })) : stations(nChars),
    manifest: manifestOf(objects),
  };
}
function resolveRoom(name, nChars, seed) {              // authored → curated; otherwise → procedural theme + autoLayout
  const authored = ROOMS[normName(name)];
  if (authored) return { tileset: authored.tileset, mood: authored.mood, windowLight: authored.windowLight || MOONLIGHT, doors: authored.doors || { top: true }, objects: authored.objects, stations: stations(nChars), manifest: manifestOf(authored.objects) };
  const theme = THEMES[seed % THEMES.length], doors = { top: true, bottom: true };   // seed mixes name+depth → varied
  const layout = autoLayout(theme.manifest, doors, seed, nChars) || { objects: [], stations: stations(nChars) };
  return { tileset: theme.tileset, mood: theme.mood, windowLight: theme.windowLight, doors, objects: layout.objects, stations: layout.stations, manifest: theme.manifest };
}

// --------------------------------------------------------------------------------- boot
function frame(t) {
  const dt = Math.min(0.05, (t - G.lastT) / 1000 || 0);
  G.lastT = t;
  update(dt);
  updateSparks(dt);          // sign sparks advance every frame (incl. while talking)
  render();
  requestAnimationFrame(frame);
}
(async function boot() {
  if (document.fonts && document.fonts.load) {     // canvas labels need the pixel font registered first
    try { await Promise.race([document.fonts.load("15px Pixel"), new Promise((r) => setTimeout(r, 1500))]); } catch (e) {}
  }
  loadPlayerSprites();          // fire-and-forget: sprites pop in when ready, blob until then
  NPC_CAST.forEach((c) => loadNpcSprite(c.key));   // preload the gendered cast for procedural reuse
  ["door_open", "key", "nvidia", "huggingface"].forEach(async (k) => {  // door · key · dead relics
    const im = await loadImg("/static/room/objects/" + k + ".png");
    if (im) OBJECTS[k] = prep(im);
  });
  const r = new URLSearchParams(location.search).get("room");   // dev: ?room=2 enters room 2
  if (r) await api("/api/dev/room", { idx: Math.max(0, parseInt(r, 10) - 1) });
  applyState(await getState()); // applyState loads the current room's tileset + objects
  requestAnimationFrame(frame);
})();

window.__mindlock = G;   // debug handle (dev only): inspect/teleport for testing

// ============================ audio + main menu ============================
// One decoded buffer, two renderings: the MENU plays the track full; in-game it runs through a
// lowpass+highpass so it reads as a muffled, lo-fi "behind the walls" version (the MIDI the player
// asked for isn't recoverable — Songscription fetches the transcription from its API at runtime, so
// the saved page holds only the app shell; this WebAudio filter is the offline stand-in).
const Sound = (() => {
  let ac, buf, master, cur, loading, mode = null, muted = false;
  function ctx() {
    if (!ac) {
      const AC = window.AudioContext || window.webkitAudioContext;
      ac = new AC();
      master = ac.createGain();
      master.gain.value = muted ? 0 : 1;
      master.connect(ac.destination);
    }
    return ac;
  }
  function load() {
    if (buf) return Promise.resolve(buf);
    if (!loading) loading = fetch("/static/audio/menu.mp3").then((r) => r.arrayBuffer())
      .then((a) => ctx().decodeAudioData(a)).then((b) => (buf = b)).catch(() => null);
    return loading;
  }
  async function play(m) {
    ctx();
    try { await ac.resume(); } catch (e) {}
    await load();
    if (!buf) return;
    const old = cur;
    const src = ac.createBufferSource();
    src.buffer = buf; src.loop = true;
    const g = ac.createGain(); g.gain.value = 0.0001;
    if (m === "game") {
      const lp = ac.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 720; lp.Q.value = 0.7;
      const hp = ac.createBiquadFilter(); hp.type = "highpass"; hp.frequency.value = 170;
      src.connect(lp); lp.connect(hp); hp.connect(g);
    } else {
      src.connect(g);
    }
    g.connect(master); src.start();
    const tgt = m === "game" ? 0.16 : 0.42;
    g.gain.exponentialRampToValueAtTime(tgt, ac.currentTime + 1.1);
    cur = { src, g }; mode = m;
    if (old) {                                  // crossfade the previous track out
      try {
        old.g.gain.exponentialRampToValueAtTime(0.0001, ac.currentTime + 0.7);
        setTimeout(() => { try { old.src.stop(); } catch (e) {} }, 820);
      } catch (e) {}
    }
  }
  return {
    menu() { return play("menu"); },
    game() { return play("game"); },
    mode() { return mode; },
    toggle() { muted = !muted; if (master) master.gain.linearRampToValueAtTime(muted ? 0 : 1, ctx().currentTime + 0.2); return muted; },
    muted() { return muted; },
  };
})();

(function mainMenu() {
  const m = el("menu");
  if (!m) return;
  const hint = el("menu-hint"), muteBtn = el("menu-mute"), snd = el("snd"),
        howBtn = el("menu-how"), howto = el("menu-howto"),
        storyBtn = el("menu-story"), endlessBtn = el("menu-endless"),
        editorBtn = el("menu-editor"),
        emb = el("menu-emblem-img"), keyimg = el("menu-key-img");
  // PixelLab art — drop in if present, fold away cleanly if a file is missing
  if (emb) { emb.onerror = () => { emb.parentElement.style.display = "none"; }; emb.src = "/static/menu/padlock.png"; }
  if (keyimg) { keyimg.onerror = () => { keyimg.parentElement.style.display = "none"; }; keyimg.src = "/static/menu/key.png"; }

  let woke = false;
  function wake() { if (woke) return; woke = true; if (hint) hint.classList.add("gone"); Sound.menu().then(syncSound); }
  document.addEventListener("pointerdown", wake, { once: true, capture: true });
  document.addEventListener("keydown", () => { if (!m.classList.contains("hidden")) wake(); }, { once: true });

  function enter(mode) {
    wake();
    m.classList.add("closing");
    setTimeout(() => m.classList.add("hidden"), 560);
    Sound.game().then(syncSound);
    api("/api/start", { mode }).then(applyState);   // begin the chosen run mode
  }
  if (storyBtn) storyBtn.onclick = () => enter("story");
  if (endlessBtn) endlessBtn.onclick = () => enter("endless");
  if (editorBtn) editorBtn.onclick = () => {       // straight into the level editor, no ?dev=1
    wake();
    m.classList.add("closing");
    setTimeout(() => m.classList.add("hidden"), 560);
    Sound.game().then(syncSound);
    G.editMode = true;                             // L toggles the editor for the whole session
    api("/api/start", { mode: "story" }).then((st) => {
      applyState(st);
      if (!G.editor) toggleEditor();               // open on level 1, legend up
    });
  };
  if (howBtn) howBtn.onclick = () => howto.classList.toggle("hidden");

  function toggleMute() { Sound.toggle(); syncSound(); }
  if (muteBtn) muteBtn.onclick = toggleMute;
  if (snd) snd.onclick = (e) => { e.stopPropagation(); toggleMute(); };
  function syncSound() {
    const mu = Sound.muted();
    if (muteBtn) { muteBtn.textContent = mu ? "♪ Sound: off" : "♪ Sound: on"; muteBtn.classList.toggle("off", mu); muteBtn.setAttribute("aria-pressed", String(mu)); }
    if (snd) { snd.textContent = mu ? "♪̶" : "♪"; snd.classList.toggle("off", mu); }
  }
  syncSound();
})();
