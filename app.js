/* EarRepair: study app for spatial audio repair of voice commands.
   The recogniser is simulated: every trial pretends the assistant is unsure between three contacts.

   1. SETTINGS  timing and input thresholds
   2. SOUND     clips through the browser's HRTF panner, scheduled on the audio clock
                (playback chain adapted from the AudioPIN prototype)
   3. TRIAL     plays one request and its options, waits for a swipe, returns one log row
   4. SESSION   earphone check -> 3 x (practice, trials, workload) -> preference -> export
   5. LOG       saved after every row, so a reload loses nothing */

// ================= 1. SETTINGS =================
const AZIMUTH = [-90, 0, 90];         // degrees: left, front, right. Options play in this order
const CENTRE = 0;
const PRE_MS = 700;                   // silence before each request
const AFTER_REQUEST_MS = 450;         // between the request and "Which one?"
const AFTER_WHICH_MS = 250;           // between "Which one?" and the first option
const NUMBER_GAP_MS = 60;             // between "One." and the name
const OPTION_GAP_MS = 300;            // between options: stops one name smearing into the next
const TIMEOUT_MS = 10000;             // after the list ends, with no answer
const ITI_MS = 900;                   // after an answer, before the next trial
const FEEDBACK_MS = 2600;             // practice only: time to read and hear the feedback
const SWIPE_MIN_PX = 45;              // shorter movement counts as a tap
const TAP_MAX_MS = 400;               // a longer press that goes nowhere is ignored
const AXIS_RATIO = 1.3;               // main axis must beat the other by this much, or we ask again
const GESTURE_POS = { left: 0, up: 1, right: 2, down: -1 };
const POS_GESTURE = { 0: 'left', 1: 'up', 2: 'right', '-1': 'down' };
const STORE = 'earrepair-session-v1';

const LABELS = {
  numbered: { name: 'Numbered list', cues: ['1', '2', '3'],
    text: 'You will hear a request, then three names, each with a number. Swipe left for 1, up for 2, right for 3.' },
  plain: { name: 'Plain list', cues: ['First', 'Second', 'Third'],
    text: 'You will hear a request, then three names in a row. Swipe left for the first, up for the second, right for the third.' },
  spatial: { name: 'Names around you', cues: ['Left', 'Front', 'Right'],
    text: 'You will hear a request, then three names around you: left, front, right. Swipe towards the name you want.' }
};
const TLX = [
  ['mental', 'How mentally demanding was it?', 'Very low', 'Very high'],
  ['physical', 'How physically demanding was it?', 'Very low', 'Very high'],
  ['temporal', 'How hurried or rushed did you feel?', 'Very low', 'Very high'],
  ['performance', 'How successful were you?', 'Perfect', 'Failure'],
  ['effort', 'How hard did you have to work?', 'Very low', 'Very high'],
  ['frustration', 'How irritated or stressed were you?', 'Very low', 'Very high']
];

// ================= helpers =================
const $ = id => document.getElementById(id);
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const SCREENS = ['setup', 'check', 'intro', 'ready', 'paused', 'tlx', 'final', 'done'];
function show(name) {
  for (const s of SCREENS) $(s).hidden = s !== name;
  $('pad').hidden = name !== 'pad';
  window.scrollTo(0, 0);
}
function clicked(id) {
  return new Promise(resolve => { $(id).onclick = () => { $(id).onclick = null; resolve(); }; });
}
function legendCells(condition) {
  const [a, b, c] = LABELS[condition].cues;
  return [['', ''], ['up', '↑ ' + b], ['', ''], ['left', '← ' + a], ['', ''], ['right', c + ' →'], ['', ''], ['down', '↓ None of these'], ['', '']]
    .map(([kind, text]) => {
      const d = document.createElement('div');
      d.textContent = text;
      if (!text) d.style.visibility = 'hidden';
      return d;
    });
}

// ================= 2. SOUND =================
let ctx = null, tick = null, buzz = null;
const clips = {};
const live = new Set();

async function initAudio() {
  if (!ctx) {
    try { if (navigator.audioSession) navigator.audioSession.type = 'playback'; } catch (e) {} // iPhone: ignore the silent switch
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    ctx.createPanner().panningModel = 'HRTF';          // start loading the HRTF data now
    tick = tone(1000, 0.04);
    buzz = tone(220, 0.16);
  }
  if (ctx.state !== 'running') await ctx.resume();
}
function tone(freq, seconds) {
  const n = Math.round(ctx.sampleRate * seconds), b = ctx.createBuffer(1, n, ctx.sampleRate), d = b.getChannelData(0);
  for (let i = 0; i < n; i++) d[i] = 0.25 * Math.sin(2 * Math.PI * freq * i / ctx.sampleRate) * Math.sin(Math.PI * i / n);
  return b;
}
function decode(bytes) {                               // the callback form also works on older Safari
  return new Promise((resolve, reject) => ctx.decodeAudioData(bytes, resolve, reject));
}
async function loadClips(ids, report) {
  const todo = ids.filter(id => !clips[id]);
  let done = 0;
  const worker = async () => {
    while (todo.length) {
      const id = todo.pop();
      const response = await fetch(`audio/${id}.wav`);
      if (!response.ok) throw new Error(`audio/${id}.wav: HTTP ${response.status}`);
      clips[id] = await decode(await response.arrayBuffer());
      report(++done);
    }
  };
  await Promise.all([worker(), worker(), worker(), worker()]);
}

// Every sound goes through the same HRTF panner, also at the centre, so the spatial condition
// differs from the others in position only and not in how the voice has been filtered.
function playAt(buffer, azimuth, when) {
  const a = azimuth * Math.PI / 180, x = Math.sin(a), z = -Math.cos(a); // listener faces -z, +x is right
  const panner = ctx.createPanner();
  panner.panningModel = 'HRTF';
  if (panner.positionX) { panner.positionX.value = x; panner.positionY.value = 0; panner.positionZ.value = z; }
  else panner.setPosition(x, 0, z);
  panner.connect(ctx.destination);
  const source = ctx.createBufferSource();
  source.buffer = buffer;
  source.connect(panner);
  source.start(when);
  live.add(source);
  source.onended = () => { live.delete(source); panner.disconnect(); };
}
function stopAll() {
  for (const s of live) { try { s.stop(); } catch (e) {} }
  live.clear();
}
function outputDelayMs() { return ((ctx.baseLatency || 0) + (ctx.outputLatency || 0)) * 1000; }
// When a sound scheduled at audio time `when` reaches the ears, on the performance.now() clock.
function heardAt(when) { return performance.now() + (when - ctx.currentTime) * 1000 + outputDelayMs(); }

// Plays the three options from audio time `when`. Returns when each name is heard, and when it all ends.
function scheduleOptions(trial, condition, when) {
  let t = when;
  const onsets = [];
  trial.options.forEach((name, i) => {
    if (condition === 'numbered') {
      const number = clips[['a_one', 'a_two', 'a_three'][i]];
      playAt(number, CENTRE, t);
      if (i === 0) onsets.first = heardAt(t);
      t += number.duration + NUMBER_GAP_MS / 1000;
    }
    const clip = clips['n_' + EarPlan.slug(name)];
    playAt(clip, condition === 'spatial' ? AZIMUTH[i] : CENTRE, t);
    onsets.push(heardAt(t));
    t += clip.duration + (i < 2 ? OPTION_GAP_MS / 1000 : 0);
  });
  if (onsets.first === undefined) onsets.first = onsets[0];
  return { onsets, first: onsets.first, end: heardAt(t), endWhen: t };
}

// ================= 3. TRIAL =================
let interruptTrial = null;   // set while a trial runs; ends it when the page is hidden

function readGesture(down, up) {
  const dx = up.x - down.x, dy = up.y - down.y, ax = Math.abs(dx), ay = Math.abs(dy);
  if (Math.max(ax, ay) < SWIPE_MIN_PX) return { kind: up.t - down.t <= TAP_MAX_MS ? 'tap' : 'none', dx, dy };
  if (Math.max(ax, ay) < AXIS_RATIO * Math.min(ax, ay)) return { kind: 'ambiguous', dx, dy };
  return { kind: ax > ay ? (dx < 0 ? 'left' : 'right') : (dy < 0 ? 'up' : 'down'), dx, dy };
}

function runTrial(trial, block, phase) {
  return new Promise(resolve => {
    const condition = block.condition, pad = $('pad');
    const started = new Date().toISOString();
    const request = clips['t_' + EarPlan.slug(trial.target)], which = clips.a_which;
    const whenRequest = ctx.currentTime + PRE_MS / 1000;
    const whenWhich = whenRequest + request.duration + AFTER_REQUEST_MS / 1000;
    const whenList = whenWhich + which.duration + AFTER_WHICH_MS / 1000;
    playAt(request, CENTRE, whenRequest);
    playAt(which, CENTRE, whenWhich);
    const firstList = scheduleOptions(trial, condition, whenList);
    let list = firstList;
    let replays = 0, early = 0, ambiguous = 0, timer = null, down = null, finished = false;

    const armTimeout = () => {
      clearTimeout(timer);
      timer = setTimeout(() => finish({ status: 'timeout' }), Math.max(0, list.end - performance.now()) + TIMEOUT_MS);
    };
    const finish = result => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      pad.onpointerdown = pad.onpointerup = pad.onpointercancel = null;
      window.onkeydown = null;
      interruptTrial = null;
      stopAll();
      resolve(makeRow(trial, block, phase, started, firstList, list, result, { replays, early, ambiguous }));
    };
    const handle = (gesture, input, downAt, upAt) => {
      if (gesture.kind === 'none') return;
      if (performance.now() < firstList.first) { early++; return; }
      if (gesture.kind === 'tap') {
        replays++;
        stopAll();
        list = scheduleOptions(trial, condition, ctx.currentTime + 0.1);
        armTimeout();
        return;
      }
      if (gesture.kind === 'ambiguous') {
        ambiguous++;
        playAt(buzz, CENTRE, ctx.currentTime);
        return;
      }
      finish({ status: 'ok', gesture: gesture.kind, dx: gesture.dx, dy: gesture.dy, input, downAt, upAt });
    };

    pad.onpointerdown = e => { down = { x: e.clientX, y: e.clientY, t: performance.now() }; };
    pad.onpointercancel = () => { down = null; };
    pad.onpointerup = e => {
      if (!down) return;
      const up = { x: e.clientX, y: e.clientY, t: performance.now() }, start = down;
      down = null;
      handle(readGesture(start, up), e.pointerType || 'pointer', start.t, up.t);
    };
    window.onkeydown = e => {                          // desktop rehearsal
      const key = { ArrowLeft: 'left', ArrowUp: 'up', ArrowRight: 'right', ArrowDown: 'down', ' ': 'tap' }[e.key];
      if (!key) return;
      e.preventDefault();
      const now = performance.now();
      handle({ kind: key, dx: 0, dy: 0 }, 'key', now, now);
    };
    interruptTrial = () => finish({ status: 'interrupted' });
    armTimeout();
  });
}

function makeRow(trial, block, phase, started, firstList, list, r, counts) {
  const answered = r.status === 'ok';
  const chosen = answered ? GESTURE_POS[r.gesture] : '';
  const round = v => (v === undefined || v === null ? '' : Math.round(v));
  const heard = answered ? list.onsets.filter(t => t <= r.downAt).length : '';
  return {
    wall: started, pid: session.pid, context: session.context, block: block.position, condition: block.condition,
    set: block.set, phase, trial: phase === 'test' ? session.trialIndex + 1 : '', item_id: trial.item_id,
    similarity: trial.similarity, absent: trial.absent ? 1 : 0, target: trial.target, target_pos: trial.target_pos,
    option1: trial.options[0], option2: trial.options[1], option3: trial.options[2],
    status: r.status, gesture: answered ? r.gesture : '', chosen_pos: chosen,
    correct: answered ? (chosen === trial.target_pos ? 1 : 0) : (r.status === 'timeout' ? 0 : ''),
    // Time to touch: the decision is made when the finger lands, not when it lifts.
    rt_from_list_ms: answered ? round(r.downAt - firstList.first) : '',
    rt_release_ms: answered ? round(r.upAt - firstList.first) : '',
    rt_from_target_ms: answered && !trial.absent ? round(r.downAt - list.onsets[trial.target_pos]) : '',
    rt_from_list_end_ms: answered ? round(r.downAt - list.end) : '',
    list_ms: round(firstList.end - firstList.first), options_heard: heard,
    replays: counts.replays, ambiguous: counts.ambiguous, early_gestures: counts.early,
    swipe_dx: answered ? round(r.dx) : '', swipe_dy: answered ? round(r.dy) : '',
    input: answered ? r.input : '', delay_ms: round(outputDelayMs())
  };
}

async function practiceFeedback(row, trial) {
  const right = row.correct === 1;
  const clip = trial.absent ? (right ? 'a_none_right' : 'a_none_wrong') : (right ? 'a_correct' : 'a_wrong');
  const answer = trial.absent ? 'None of these' : trial.target;
  $('padNote').textContent = row.status === 'timeout' ? `No answer. It was: ${answer}.`
    : right ? 'Correct.' : `Not that one. It was: ${answer} (swipe ${POS_GESTURE[trial.target_pos]}).`;
  playAt(clips[clip], CENTRE, ctx.currentTime + 0.05);
  await sleep(FEEDBACK_MS);
  $('padNote').textContent = '';
}

// ================= 4. SESSION =================
let session = null, plan = null;

function save() { try { localStorage.setItem(STORE, JSON.stringify(session)); } catch (e) {} }
function loadSaved() { try { return JSON.parse(localStorage.getItem(STORE)); } catch (e) { return null; } }
async function keepAwake() { try { if (navigator.wakeLock) await navigator.wakeLock.request('screen'); } catch (e) {} }

async function runSession() {
  plan = EarPlan.buildPlan(session.pid, STIMULI);
  if (!session.checked) await earphoneCheck();
  while (session.blockIndex < plan.blocks.length) {
    await runBlock(plan.blocks[session.blockIndex]);
    session.blockIndex++;
    session.trialIndex = 0;
    session.practiceDone = false;
    save();
  }
  await finalQuestions();
  session.finished = true;
  save();
  showDone();
}

async function earphoneCheck() {
  show('check');
  await loadClips(['a_which'], () => {});
  let streak = 0, side = null;
  await new Promise(resolve => {
    $('checkPlay').onclick = async () => {
      await initAudio();
      side = crypto.getRandomValues(new Uint8Array(1))[0] % 2 ? 'right' : 'left';
      playAt(clips.a_which, side === 'left' ? -90 : 90, ctx.currentTime + 0.05);
    };
    const answer = picked => {
      if (!side) return;
      streak = picked === side ? streak + 1 : 0;
      side = null;
      session.checkAttempts = (session.checkAttempts || 0) + 1;
      $('checkStreak').textContent = `${Math.min(streak, 3)} / 3`;
      if (streak >= 3) resolve();
    };
    $('checkLeft').onclick = () => answer('left');
    $('checkRight').onclick = () => answer('right');
  });
  session.checked = true;
  save();
}

async function runBlock(block) {
  const label = LABELS[block.condition];
  $('introTitle').textContent = `Part ${block.position} of ${plan.blocks.length}: ${label.name}`;
  $('introText').textContent = label.text + ' If the contact you were asked to call is not there, swipe down.';
  $('introLegend').replaceChildren(...legendCells(block.condition));
  $('padLegend').replaceChildren(...legendCells(block.condition));
  $('introBtn').textContent = session.practiceDone ? 'Continue' : 'Start practice';
  $('loadMsg').classList.remove('bad');
  $('loadMsg').textContent = '';
  show('intro');
  await clicked('introBtn');
  await initAudio();
  await keepAwake();
  const needed = EarPlan.clipsFor(block).concat(['a_which', 'a_one', 'a_two', 'a_three', 'a_correct', 'a_wrong', 'a_none_right', 'a_none_wrong']);
  $('introBtn').disabled = true;
  try {
    await loadClips(needed, n => { $('loadMsg').textContent = `Loading sounds: ${n}`; });
  } catch (e) {
    $('loadMsg').classList.add('bad');
    $('loadMsg').textContent = `Could not load the sounds (${e.message}). Serve this folder over http, then reload.`;
    throw e;
  }
  $('introBtn').disabled = false;

  if (!session.practiceDone) {
    $('padLegend').hidden = false;
    show('pad');
    for (const trial of block.practice) {
      const row = await runUninterrupted(trial, block, 'practice');
      await practiceFeedback(row, trial);
    }
    session.practiceDone = true;
    save();
  }
  $('readyNote').textContent = session.context === 'walking' ? 'Experimenter: start the walk now, then tap the button. Write down the laps at the end.' : '';
  show('ready');
  await clicked('readyBtn');
  await initAudio();
  await keepAwake();

  $('padLegend').hidden = true;
  show('pad');
  const startedAt = session.blockStart && session.trialIndex > 0 ? session.blockStart : new Date().toISOString();
  session.blockStart = startedAt;
  while (session.trialIndex < block.trials.length) {
    await runUninterrupted(block.trials[session.trialIndex], block, 'test');
    session.trialIndex++;
    save();
    await sleep(session.trialIndex < block.trials.length ? ITI_MS : 200);
  }
  const endedAt = new Date().toISOString();
  await workload(block, startedAt, endedAt);
}

// Runs a trial, and runs it again if the page was hidden part-way. Each attempt is logged.
async function runUninterrupted(trial, block, phase) {
  for (;;) {
    const row = await runTrial(trial, block, phase);
    session.trials.push(row);
    save();
    if (row.status !== 'interrupted') {
      if (row.status === 'ok') {
        playAt(tick, CENTRE, ctx.currentTime);
        try { if (navigator.vibrate) navigator.vibrate(25); } catch (e) {}
      }
      return row;
    }
    show('paused');
    await clicked('pausedBtn');
    await initAudio();
    await keepAwake();
    show('pad');
  }
}

async function workload(block, startedAt, endedAt) {
  const moved = new Set();
  $('tlxItems').replaceChildren(...TLX.map(([key, question, low, high]) => {
    const box = document.createElement('div');
    box.className = 'tlx';
    const label = document.createElement('label');
    label.textContent = question;
    const input = document.createElement('input');
    input.type = 'range'; input.min = 0; input.max = 100; input.step = 5; input.value = 50; input.id = 'tlx_' + key;
    input.oninput = () => { moved.add(key); ready(); };
    label.append(input);
    const ends = document.createElement('div');
    ends.className = 'ends';
    ends.append(Object.assign(document.createElement('span'), { textContent: low }),
                Object.assign(document.createElement('span'), { textContent: high }));
    box.append(label, ends);
    return box;
  }));
  const walking = session.context === 'walking';
  $('lapsBox').hidden = !walking;
  $('laps').value = '';
  const ready = () => {
    $('tlxBtn').disabled = moved.size < TLX.length || (walking && !(Number($('laps').value) > 0));
  };
  $('laps').oninput = ready;
  ready();
  show('tlx');
  await clicked('tlxBtn');
  const row = { pid: session.pid, context: session.context, block: block.position, condition: block.condition,
                set: block.set, started: startedAt, ended: endedAt,
                duration_s: Math.round((new Date(endedAt) - new Date(startedAt)) / 100) / 10,
                laps: walking ? Number($('laps').value) : '', lap_m: session.lapM, baseline_lap_s: session.lapS,
                earphones: session.earphones };
  for (const [key] of TLX) row['tlx_' + key] = Number($('tlx_' + key).value);
  session.blocks.push(row);
  session.blockStart = null;
  save();
}

async function finalQuestions() {
  for (const id of ['best', 'worst']) {
    $(id).replaceChildren(new Option('Choose one', ''), ...EarPlan.CONDITIONS.map(c => new Option(LABELS[c].name, c)));
  }
  show('final');
  for (;;) {
    await clicked('finalBtn');
    if (!$('best').value || !$('worst').value) { $('finalMsg').textContent = 'Please answer both.'; continue; }
    if ($('best').value === $('worst').value) { $('finalMsg').textContent = 'Best and least liked must differ.'; continue; }
    break;
  }
  for (const row of session.blocks) {
    row.pref_best = $('best').value; row.pref_worst = $('worst').value; row.comments = $('comments').value.trim();
  }
}

// ================= 5. LOG =================
const TRIAL_COLUMNS = ['wall', 'pid', 'context', 'block', 'condition', 'set', 'phase', 'trial', 'item_id', 'similarity',
  'absent', 'target', 'target_pos', 'option1', 'option2', 'option3', 'status', 'gesture', 'chosen_pos', 'correct',
  'rt_from_list_ms', 'rt_release_ms', 'rt_from_target_ms', 'rt_from_list_end_ms', 'list_ms', 'options_heard', 'replays',
  'ambiguous', 'early_gestures', 'swipe_dx', 'swipe_dy', 'input', 'delay_ms'];
const BLOCK_COLUMNS = ['pid', 'context', 'block', 'condition', 'set', 'started', 'ended', 'duration_s', 'laps', 'lap_m',
  'baseline_lap_s', 'earphones', 'tlx_mental', 'tlx_physical', 'tlx_temporal', 'tlx_performance', 'tlx_effort',
  'tlx_frustration', 'pref_best', 'pref_worst', 'comments'];

function toCsv(columns, rows) {
  const quote = v => {
    const s = v === undefined || v === null ? '' : String(v);
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  return [columns.join(',')].concat(rows.map(r => columns.map(c => quote(r[c])).join(','))).join('\n');
}
function download(name, text) {
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob([text], { type: 'text/csv' }));
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
}
const trialsCsv = () => toCsv(TRIAL_COLUMNS, session.trials);
const blocksCsv = () => toCsv(BLOCK_COLUMNS, session.blocks);

function showDone() {
  const test = session.trials.filter(r => r.phase === 'test' && r.status !== 'interrupted');
  $('doneSummary').textContent = `${session.pid}: ${test.length} trials, ${session.blocks.length} blocks saved.`;
  $('dlTrials').onclick = () => download(`earrepair_${session.pid}_trials.csv`, trialsCsv());
  $('dlBlocks').onclick = () => download(`earrepair_${session.pid}_blocks.csv`, blocksCsv());
  $('showCsv').onclick = () => {
    const box = $('csvText');
    box.hidden = !box.hidden;
    box.value = trialsCsv() + '\n\n' + blocksCsv();
    if (!box.hidden) box.select();
  };
  show('done');
}

// ================= start =================
document.addEventListener('visibilitychange', () => {
  if (document.hidden && interruptTrial) interruptTrial();
});

function fail(error) {
  console.error(error);
  if (!$('intro').hidden) return;                      // the load message is already on screen
  $('setupMsg').textContent = String(error.message || error);
  show('setup');
}

function setupScreen() {
  const saved = loadSaved();
  show('setup');
  if (saved && !saved.finished) {
    $('resumeBox').hidden = false;
    $('resumeBtn').textContent = `Resume ${saved.pid}: part ${saved.blockIndex + 1}, trial ${saved.trialIndex + 1}`;
    $('resumeBtn').onclick = () => { session = saved; initAudio().then(runSession).catch(fail); };
  }
  if (saved && saved.trials.length) {
    $('exportOld').hidden = false;
    $('exportOld').textContent = `Export the saved session (${saved.pid})`;
    $('exportOld').onclick = () => { session = saved; showDone(); };
  }
  $('startBtn').onclick = async () => {
    const pid = $('pid').value.trim(), context = $('context').value;
    const lapM = Number($('lapM').value), lapS = Number($('lapS').value);
    if (!/^[A-Za-z]*\d+$/.test(pid)) { $('setupMsg').textContent = 'Use an id ending in a number, such as P01. Never a name.'; return; }
    if (context === 'walking' && !(lapM > 0 && lapS > 0)) { $('setupMsg').textContent = 'Enter the lap length and the baseline lap time.'; return; }
    if (saved && !saved.finished && saved.trials.length) { $('setupMsg').textContent = `Export or resume ${saved.pid} first.`; return; }
    session = { pid, context, earphones: $('earphones').value.trim(), lapM: lapM || '', lapS: lapS || '',
                blockIndex: 0, trialIndex: 0, practiceDone: false, checked: false, trials: [], blocks: [],
                finished: false, created: new Date().toISOString() };
    save();
    try { await initAudio(); await runSession(); } catch (e) { fail(e); }
  };
}
$('newSession').onclick = () => {
  try { localStorage.removeItem(STORE); } catch (e) {}
  location.reload();
};
setupScreen();
