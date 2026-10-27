# Place Resolution Development Calibration v1

**Date:** 2026-08-13
**Evaluator:** `1.0`
**Corpus:** `1.0`
**Command:** `uv run python scripts/evaluate_places.py`

This is a development calibration report, not a held-out release evaluation.

## Dataset

- 757 loaded `admin_boundary` rows
- 4 national, 8 province, 167 district, and 578 tehsil rows
- 124 repeated normalized names covering 256 rows
- Maximum normalized-name multiplicity: 4
- Gazetteer SHA-256:
  `80e25d8f67305cac15251716c14c0a7ea279fbc40b67679a0ddce5ad481d1b50`

Normalization increases the duplicate count because administrative suffixes and
punctuation collapse some source variants. This is intentional and means unit
IDs, levels, parents, and coordinates must remain part of resolution.

## Results

| Slice | Passed | Total | Accuracy |
|---|---:|---:|---:|
| Full-gazetteer exact-name behavior | 749 | 749 | 100% |
| Development spelling/ambiguity/negative corpus | 21 | 21 | 100% |

The exact-name slice expects unique names to resolve and same-level duplicate
names to remain ambiguous. It does not measure misspelling generalization.

The development corpus was used to tune the resolver and must not be interpreted
as held-out accuracy. The first run exposed a false ambiguity for `Atlantis`.
Further probing found false resolutions such as `Paris -> Wari` and
`Kathmandu -> Kahan`. The resolver now combines SequenceMatcher score with a
length-bounded Levenshtein edit-distance gate. This removes those known false
accepts while retaining the measured spelling variants.

Effective parameters are recorded by the evaluator output:

- Similarity threshold: `0.62`
- Ambiguity margin: `0.05`
- Ambiguity confidence threshold: `0.8`
- Maximum edit distance: 1 for 1-4 characters, 2 for 5-12, 3 for 13+

## Limitations

- The labeled corpus contains only 21 development cases and was used for tuning.
- Cases were authored by engineering, not sampled from operator corrections.
- Spatial resolution is covered by integration tests but not by a systematic
  boundary-edge and simplification-gap benchmark.
- The gazetteer hash covers identifiers and descriptive fields, not geometry.
- This is a preliminary calibration report, not a production acceptance set.
- Thresholds must be reassessed against held-out feed and operator data before
  place resolution is integrated into ingest or exposed as an AI tool.
