# EarRepair

Study app for one question: when a voice assistant is unsure which contact you meant, can you
pick the right one faster and with less effort if the options play around your head, without
looking at the phone and without speaking again?

The speech recogniser is simulated. Every trial pretends the assistant has three candidates, so
the study measures the repair step only.

## Working on this repo

Start with the open issues: they are in the order they need doing. Target: PerCom 2027 WiP,
deadline 17 Nov 2026.

- **No participant data in git.** `data/` and the exported CSVs are ignored on purpose. Never force-add them.
- **No data collection before ethics approval.**
- **Freeze the design before P01.** After the first participant, don't change `app.js`, `plan.js`,
  `stimuli.js` or the audio. A change there changes the study. If something must change, discuss it
  first and note it in the issue.
- **Run the test before pushing changes to the app:**
  ```
  pip install -r tests/requirements.txt
  python tests/test_app.py
  ```
  It uses Chrome, and takes about 4 minutes.
- **Results come only from real sessions.** Test output and scripted runs never go in the paper.

## Design

Within-subjects, three conditions. All play the names one at a time in the same order and use the
same swipes. Only the cue differs:

| Condition | What you hear | Swipe left / up / right |
|---|---|---|
| `numbered` | "One, Riya Shah. Two, ..." from the centre (baseline) | 1 / 2 / 3 |
| `plain` | "Riya Shah. ..." from the centre (control) | first / second / third |
| `spatial` | "Riya Shah. ..." from left, front, right | left / front / right |

- **Why `plain` exists:** numbers make the list about 1.3 s longer (4.8 s vs 3.5 s). Without
  `plain`, any spatial win could just be a shorter list. `spatial` vs `plain` isolates space.
- **Per block:** 4 practice trials with feedback, then 15 trials: 12 with the contact present (each
  position 4 times, half confusable names, half distinct) and 3 where it is absent (swipe down).
- **Counterbalancing:** by the number in the id. 6 orders of conditions, and each group of 6 rotates
  the item sets. P01–P12 give each order twice. P01–P18 cover every order and rotation.
- **Measures:** time to answer, accuracy, replays, errors by position, raw NASA-TLX per block,
  walking speed vs baseline, preference. The rules are fixed at the top of `analysis/analyze.py`.

## Run it

The page has to be served over http, because `file://` blocks loading the audio.

```
python -m http.server 8000
```

- Laptop: open `http://localhost:8000`. Arrow keys and Space stand in for swipes.
- Phone on the same Wi-Fi: open `http://<laptop-ip>:8000`.
- Over plain http the screen-awake lock is not available, so set the phone's screen timeout to
  10 minutes. Hosting over https (GitHub Pages works) removes this.

## Before the first participant

1. Get ethics approval. Walking with earphones needs a safe, traffic-free route.
2. Open `listen.html` and listen to every name. Fix or re-record any that sound wrong.
3. Wear earphones and check by ear that left, front and right sound distinct while walking. This
   has only been measured in software (see Checked so far). If `front` sounds inside the head, or
   gets confused with the sides, change `AZIMUTH` in `app.js` before any data is collected.
4. Run one full rehearsal on the actual phone and earphones, then export both CSVs.
5. Use wired earphones if possible, and the same pair for everyone. Check `delay_ms` in the CSV.

## Each session (about 25–30 minutes, to be confirmed in the rehearsal)

1. Consent. Ids are P01, P02, and so on, and the id-to-name list stays on paper.
2. Walk one lap of the route with no task, and time it. Enter the lap length and the time.
3. The participant does the earphone check, then each part's practice while standing still.
4. At "Start trials", the participant starts walking and the experimenter taps Start. Count laps.
5. After each part: stop, fill in the workload sliders, enter the laps.
6. At the end, download both CSVs into `data/` before starting the next session.

Reloading or switching apps is safe: progress is saved after every trial, and an interrupted trial
is repeated and logged. A new session can't start over an unfinished one.

## Analyse

```
python analysis/analyze.py data/
```

With 10–15 people, report effect sizes and intervals as preliminary. Don't describe them as proof.

## Files

| Path | Purpose |
|---|---|
| `index.html`, `app.js` | The study app |
| `plan.js` | Conditions, counterbalancing, trial lists (pure logic) |
| `stimuli.js` | Generated name sets. Edit `tools/make_stimuli.py` instead |
| `audio/` | 305 speech clips, equal loudness |
| `listen.html` | Clip check for pronunciation |
| `tools/` | Rebuild the clips: `make_stimuli.py`, then `make_audio.ps1`, then `finish_audio.py` |
| `tests/test_app.py` | Plays a whole session in real Chrome with touch input |
| `analysis/analyze.py` | The analysis, with `--selftest` |

## Checked so far

`tests/test_app.py` passes in desktop Chrome with an emulated phone screen and touch. It covers:
counterbalancing for 18 ids, all clips present, a full session of 45 trials, and early, diagonal,
replay, wrong, timeout, interrupted and reload paths.

Measured through Chrome's HRTF: left and right differ by 3.2 dB and about 790 microseconds, on the
correct side. Front is balanced.

**Not checked:** a real phone, iOS Safari, real earphones, or anyone listening. Software can confirm
the cues exist, not that people hear them.

## Known limits

- Speech is synthetic, at 16 kHz. Left and right are unaffected, but the high frequencies that help
  tell front from back are missing, so `front` may sound central or inside the head.
- Generic HRTF with no head tracking. The sound moves with the head.
- The request gives the full name, so the task is matching a name just heard. That is easier than
  recognising a real contact from a vague memory of what you said.
- The recogniser is simulated, so real error patterns and confidence are not modelled.
- Spatial order is fixed (left, front, right), so space is a redundant cue on top of order.
- Selection is by swipe. Saying "the second one" isn't tested, and is worth adding if time allows.
- Swiping still needs a free hand, so the "carrying something" case in the motivation isn't covered.

The playback chain in `app.js` is adapted from the AudioPIN prototype.
