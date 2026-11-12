# EarRepair: PerCom 2027 WiP paper

PerCom 2027 Work-in-Progress. Deadline **17 Nov 2026, 23:59 AoE**. **4 pages including
references**, IEEE two-column conference format, US letter, PDF, submitted through HotCRP.
Single-blind, so the authors are named. At least one author must register for the full conference
and present in person in Goa. Call: https://percom.org/?p=564

## Compile

- **Overleaf:** upload the zip as a new project. The default compiler (pdfLaTeX) is right.
- **Locally:** `pdflatex main`, `bibtex main`, `pdflatex main`, `pdflatex main`.
- **Tectonic:** `tectonic main.tex` also works. The preamble switches to a Times clone under XeTeX.

The template is the official `IEEEtran` class (v1.8b) and `IEEEtran.bst`, taken from CTAN.

## Results come from the analysis, not from typing

Without `results.tex`, the paper compiles as a design-and-system WiP with no results section. After
the pilot:

```
python analysis/analyze.py data/ --latex paper/results.tex
```

This switches on the Preliminary Results section and fills Table I. Rerun it whenever data change.
Never edit the numbers by hand.

## Before submitting

- [ ] Replace the red TODOs: authors, affiliations and emails. With results, also the abstract sentence,
      the results paragraph, and the discussion paragraph.
- [ ] If there is no pilot data, the paper stands as it is: check that nothing red is left.
- [ ] The Discussion says "Data collection with 12 participants is in progress". Make sure that is true
      on the submission date, or reword it.
- [ ] Check that the system numbers still hold if the stimuli or positions change: 3.54 s and 4.77 s
      list durations, 3.2 dB and 0.79 ms interaural cues, 45 triples (24 confusable, 21 distinct).
      They come from the audio files and from `tests/test_app.py`.
- [ ] If issue 2 moves the positions away from -90/0/+90 degrees, update the Spatial rendering
      paragraph and Fig. 1.
- [ ] The page count must be 4 or fewer, including references.
- [ ] Recompile on Overleaf (pdfLaTeX) and open the PDF. The fonts should be Times.

## Every citation was checked

Each entry in `refs.bib` was matched to its DOI through Crossref: title, authors, venue, year and
pages. If you add one, check it the same way, and only cite what you have read.
