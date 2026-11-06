/* One participant's study plan. Pure logic with no page or audio, so it can be tested alone.

   Conditions differ only in the cue that marks each option. All three play the names one at a
   time in the same order, and all three use the same swipes:
     numbered  "One, Riya Shah..."      from the centre: the baseline
     plain     "Riya Shah..."           from the centre: controls for the time the numbers take
     spatial   "Riya Shah..."           left, front, right
   Comparing spatial with plain isolates space. Comparing spatial with numbered is the practical
   question: is it better than what a voice assistant would do today?

   Counterbalancing: all 6 condition orders repeat every 6 participants, and each group of 6
   rotates which item set goes with which block, so 18 ids cover every order x rotation. */
(function (root) {
  var CONDITIONS = ['numbered', 'plain', 'spatial'];
  var ORDERS = [[0, 1, 2], [1, 2, 0], [2, 0, 1], [0, 2, 1], [2, 1, 0], [1, 0, 2]];

  function hash(text) {                                // FNV-1a
    var h = 2166136261;
    for (var i = 0; i < text.length; i++) { h ^= text.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }
  function rng(seed) {                                 // mulberry32: same id, same plan
    return function () {
      seed = (seed + 0x6D2B79F5) | 0;
      var t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function shuffle(list, random) {
    var a = list.slice();
    for (var i = a.length - 1; i > 0; i--) {
      var j = Math.floor(random() * (i + 1));
      var x = a[i]; a[i] = a[j]; a[j] = x;
    }
    return a;
  }
  function slug(name) { return name.toLowerCase().replace(/[^a-z]+/g, '_').replace(/^_+|_+$/g, ''); }
  function participantNumber(pid) {
    var digits = String(pid).replace(/\D/g, '');
    return digits ? parseInt(digits, 10) : (hash(String(pid)) % 18) + 1;
  }

  // Puts `target` at position `pos` and the other two names in random order.
  function arrange(names, target, pos, random) {
    var others = shuffle(names.filter(function (n) { return n !== target; }), random);
    others.splice(pos, 0, target);
    return others;
  }

  function buildSet(items, random) {
    var trials = [];
    ['confusable', 'distinct'].forEach(function (similarity) {
      var present = items.filter(function (i) { return i.similarity === similarity && !i.foil; });
      var positions = shuffle([0, 0, 1, 1, 2, 2], random); // each position twice per similarity level
      present.forEach(function (item, k) {
        var target = item.names[Math.floor(random() * 3)];
        trials.push({ item_id: item.id, similarity: similarity, absent: false, target: target,
                      target_pos: positions[k], options: arrange(item.names, target, positions[k], random) });
      });
    });
    items.filter(function (i) { return i.foil; }).forEach(function (item) {
      trials.push({ item_id: item.id, similarity: item.similarity, absent: true, target: item.foil,
                    target_pos: -1, options: shuffle(item.names, random) });
    });
    return shuffle(trials, random);
  }

  function buildPractice(triples, random) {
    var positions = shuffle([0, 1, 2], random);
    var trials = triples.map(function (names, k) {
      var target = names[Math.floor(random() * 3)];
      return { item_id: 'practice' + (k + 1), similarity: 'practice', absent: false, target: target,
               target_pos: positions[k], options: arrange(names, target, positions[k], random) };
    });
    // One "none of these" in the practice: the request comes from a different triple.
    trials.push({ item_id: 'practice4', similarity: 'practice', absent: true, target: triples[1][0],
                  target_pos: -1, options: shuffle(triples[0], random) });
    return shuffle(trials, random);
  }

  function buildPlan(pid, stimuli) {
    var n = participantNumber(pid);
    var order = ORDERS[(n - 1) % 6];
    var rotation = Math.floor((n - 1) / 6) % 3;
    var random = rng(hash(String(pid)));
    var blocks = order.map(function (c, position) {
      var setIndex = (position + rotation) % 3;
      return { position: position + 1, condition: CONDITIONS[c], set: setIndex + 1,
               practice: buildPractice(stimuli.practice, random),
               trials: buildSet(stimuli.sets[setIndex], random) };
    });
    return { pid: String(pid), number: n, order: order.map(function (c) { return CONDITIONS[c]; }),
             rotation: rotation, blocks: blocks };
  }

  function clipsFor(block) {
    var ids = {};
    block.practice.concat(block.trials).forEach(function (t) {
      ids['t_' + slug(t.target)] = true;
      t.options.forEach(function (n) { ids['n_' + slug(n)] = true; });
    });
    return Object.keys(ids);
  }

  var api = { CONDITIONS: CONDITIONS, ORDERS: ORDERS, buildPlan: buildPlan, clipsFor: clipsFor, slug: slug,
              participantNumber: participantNumber };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.EarPlan = api;
})(typeof self !== 'undefined' ? self : this);
