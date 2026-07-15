"""
attentional_spatial_bias_colab.py
==================================
Single-file version of the Attentional Spatial Bias analysis pipeline,
meant to be pasted into a Google Colab notebook (one cell, or split at the
`# %%` markers into several cells).

WHAT TO DO IN COLAB
--------------------
1. Create a new Colab notebook.
2. Paste this whole file into a cell and run it.
3. When prompted, upload your `subject-*.csv` OpenSesame trial-log files
   (the ones with 48 rows/subject -- NOT the raw *.tsv gaze-sample files
   or *_log.txt PyGaze message logs; those aren't needed here because
   OpenSesame/PyGaze already computed first_fix_side/first_fix_rt for you).
4. Tables print inline; plots render inline; everything also gets saved
   into a `results/` folder you can download via the Colab file browser
   (left sidebar -> folder icon), or zip + download with the snippet at
   the very bottom of this file.

WHAT THIS REPRODUCES (from Ehinger et al.)
--------------------------------------------
- Mean choice proportion (P(first fixation = right stimulus)) per
  arrangement, bootstrapped 95% CIs -> paper's Figure 2 (left)
- 20%-winsorized mean RT per clock location, bootstrapped CIs -> Figure 2
  (right)
- A Bradley-Terry-style logistic regression of first-fixation side

EXTRA (LTR vs RTL comparison, not in the paper)
-------------------------------------------------
- Recodes each fixation as matching / not matching the participant's
  reading-onset side (left for LTR readers, right for RTL readers) and
  compares groups.

READ BEFORE INTERPRETING RESULTS
----------------------------------
If you only have one participant per reading-direction group, `group` and
`subject_nr` are perfectly confounded -- any LTR-vs-RTL contrast is
equally well described as "this subject vs that subject." The script
still runs and reports numbers, but treats them as descriptive/pilot
output, not as evidence for/against a reading-direction effect, until you
have >=2 subjects per group.
"""

# %% [1] Setup -----------------------------------------------------------
import sys
import subprocess

def _pip_install(pkg):
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", pkg], check=True)

for _pkg in ["statsmodels"]:
    try:
        __import__(_pkg)
    except ImportError:
        _pip_install(_pkg)

import glob
import os

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.formula.api as smf
import matplotlib.pyplot as plt

# %% [2] Upload data -------------------------------------------------------
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

try:
    from google.colab import files  # type: ignore
    IN_COLAB = True
except ImportError:
    IN_COLAB = False

if IN_COLAB:
    print("Please select your subject-*.csv file(s) to upload "
          "(you can select multiple at once).")
    uploaded = files.upload()
    for fname, content in uploaded.items():
        dest = os.path.join(DATA_DIR, fname)
        with open(dest, "wb") as f:
            f.write(content)
        print(f"Saved {dest}")
else:
    print(f"Not running in Colab -- put your subject-*.csv files in "
          f"'{DATA_DIR}/' manually and re-run this cell.")

# %% [3] Config: arrangement / clock mapping, exclusion + bootstrap settings
# The six `position` codes logged by OpenSesame correspond to the six
# diagonal/horizontal/vertical stimulus arrangements from the reference
# paper. We identified this mapping by reading back the logged
# (x_left, y_left, x_right, y_right) pixel offsets for each position and
# converting to clock-face angles (see the `inspect_positions()` helper
# below if you change the .osexp and need to re-derive it).

POSITION_LABELS = {
    "1": "nine-three", "2": "eight-two", "3": "seven-one",
    "4": "twelve-six", "5": "eleven-five", "6": "ten-four",
}
ARRANGEMENT_ORDER = [
    "nine-three", "ten-four", "eleven-five",
    "twelve-six", "seven-one", "eight-two",
]
CLOCK_MAP = {
    ("nine-three", "left"): 9, ("nine-three", "right"): 3,
    ("ten-four", "left"): 10, ("ten-four", "right"): 4,
    ("eleven-five", "left"): 11, ("eleven-five", "right"): 5,
    ("twelve-six", "left"): 6, ("twelve-six", "right"): 12,
    ("seven-one", "left"): 7, ("seven-one", "right"): 1,
    ("eight-two", "left"): 8, ("eight-two", "right"): 2,
}
CLOCK_ORDER = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

RT_EXCLUSION_MS = 2000
WINSOR_PROP = 0.2
N_BOOT = 5000        # lower than the paper's 10,000 for speed; raise if you like
RANDOM_SEED = 42
OUT_DIR = "results"
os.makedirs(OUT_DIR, exist_ok=True)


def inspect_positions(data_dir=DATA_DIR):
    """Utility: print how position codes map to clock angles, to sanity-check
    POSITION_LABELS/CLOCK_MAP above if you change the .osexp stimulus layout."""
    import math
    paths = sorted(glob.glob(os.path.join(data_dir, "subject-*.csv")))
    seen = {}
    for p in paths:
        df = pd.read_csv(p, dtype=str)
        for _, row in df.iterrows():
            pos = row["position"]
            if pos not in seen:
                seen[pos] = (float(row["x_left"]), float(row["y_left"]),
                             float(row["x_right"]), float(row["y_right"]))

    def clock_hour(angle_deg):
        hour = (3 - (angle_deg / 30.0)) % 12
        return 12 if hour == 0 else round(hour)

    for pos in sorted(seen):
        xl, yl, xr, yr = seen[pos]
        la = math.degrees(math.atan2(yl, xl))
        ra = math.degrees(math.atan2(yr, xr))
        print(pos, seen[pos], "-> left_clock", clock_hour(la),
              "right_clock", clock_hour(ra))


# %% [4] Load + tidy all uploaded subject CSVs -----------------------------
def load_subject_csv(path):
    df = pd.read_csv(path, dtype=str)
    keep_cols = [
        "subject_nr", "group", "lang", "trial_nr", "block_index",
        "position", "img_left", "img_right",
        "first_fix_side", "first_fix_rt", "response_time", "correct",
    ]
    missing = [c for c in keep_cols if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing expected columns {missing}")
    df = df[keep_cols].copy()

    df["trial_nr"] = df["trial_nr"].astype(int)
    df["block_index"] = df["block_index"].astype(int)
    df["first_fix_rt"] = pd.to_numeric(df["first_fix_rt"], errors="coerce")
    df["response_time"] = pd.to_numeric(df["response_time"], errors="coerce")

    df["arrangement"] = df["position"].map(POSITION_LABELS)
    if df["arrangement"].isna().any():
        bad = df.loc[df["arrangement"].isna(), "position"].unique()
        raise ValueError(f"{path}: unmapped position code(s) {bad} -- update "
                          f"POSITION_LABELS")

    def fix_direction(row):
        if row["first_fix_side"] == row["img_left"]:
            return "left"
        elif row["first_fix_side"] == row["img_right"]:
            return "right"
        return "none"

    df["first_fix_direction"] = df.apply(fix_direction, axis=1)

    reading_start_side = {"LTR": "left", "RTL": "right"}
    df["reading_start_side"] = df["group"].map(reading_start_side)
    df["fix_matches_reading_onset"] = (
        df["first_fix_direction"] == df["reading_start_side"]
    ).where(df["first_fix_direction"] != "none")

    df.rename(columns={"first_fix_rt": "first_fix_rt_ms",
                        "response_time": "response_time_ms"}, inplace=True)
    return df


def apply_exclusions(df, rt_cutoff_ms=RT_EXCLUSION_MS):
    df = df.copy()
    df["exclusion_reason"] = "none"
    no_fix = df["first_fix_direction"] == "none"
    df.loc[no_fix, "exclusion_reason"] = "no_first_fixation_registered"
    too_slow = (~no_fix) & (df["first_fix_rt_ms"] > rt_cutoff_ms)
    df.loc[too_slow, "exclusion_reason"] = "first_fix_rt_over_cutoff"
    df["excluded"] = df["exclusion_reason"] != "none"
    return df


paths = sorted(glob.glob(os.path.join(DATA_DIR, "subject-*.csv")))
if not paths:
    raise SystemExit(f"No subject-*.csv files found in '{DATA_DIR}/'. "
                      f"Re-run cell [2] to upload, or add files manually.")

frames = [load_subject_csv(p) for p in paths]
trials = pd.concat(frames, ignore_index=True)
trials = apply_exclusions(trials)
trials.to_csv(os.path.join(OUT_DIR, "trials_combined.csv"), index=False)

n_subj = trials["subject_nr"].nunique()
n_excl = trials["excluded"].sum()
print(f"Loaded {len(paths)} file(s), {n_subj} subject(s), {len(trials)} trials.")
print(f"Excluded {n_excl}/{len(trials)} trials ({n_excl/len(trials):.1%}) "
      f"(no fixation registered, or RT > {RT_EXCLUSION_MS} ms).")

df_valid = trials[~trials["excluded"]].copy()

# %% [5] Bootstrap helpers -------------------------------------------------
rng = np.random.default_rng(RANDOM_SEED)


def bootstrap_ci(values, stat_fn, n_boot=N_BOOT):
    values = np.asarray(values)
    if len(values) == 0:
        return np.nan, np.nan, np.nan
    point = stat_fn(values)
    if len(values) < 2:
        return point, np.nan, np.nan
    boots = np.empty(n_boot)
    n = len(values)
    for i in range(n_boot):
        boots[i] = stat_fn(values[rng.integers(0, n, n)])
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return point, lo, hi


def winsorized_mean(x, prop=WINSOR_PROP):
    x = np.sort(np.asarray(x, dtype=float))
    n = len(x)
    if n == 0:
        return np.nan
    k = int(np.floor(prop * n))
    if k > 0:
        x = np.concatenate([np.full(k, x[k]), x[k:n - k], np.full(k, x[n - 1 - k])])
    return x.mean()


# %% [6] Analysis 1: mean choice proportion per arrangement (Fig 2, left) --
rows = []
for (subj, group, arr), g in df_valid.groupby(["subject_nr", "group", "arrangement"]):
    is_right = (g["first_fix_direction"] == "right").astype(float).values
    point, lo, hi = bootstrap_ci(is_right, np.mean)
    rows.append(dict(subject_nr=subj, group=group, arrangement=arr,
                      n_trials=len(g), mean_p_right=point, ci_lo=lo, ci_hi=hi))
choice_df = pd.DataFrame(rows)
choice_df["arrangement"] = pd.Categorical(choice_df["arrangement"], ARRANGEMENT_ORDER, ordered=True)
choice_df = choice_df.sort_values(["arrangement", "subject_nr"]).reset_index(drop=True)
choice_df.to_csv(os.path.join(OUT_DIR, "choice_proportion_by_arrangement.csv"), index=False)

print("\n=== Mean choice proportion by arrangement (cf. paper Figure 2, left) ===")
print(choice_df.to_string(index=False))

fig, ax = plt.subplots(figsize=(6, 5))
colors = {"LTR": "#1f77b4", "RTL": "#d62728"}
y_pos = {a: i for i, a in enumerate(ARRANGEMENT_ORDER)}
groups_sorted = sorted(choice_df["group"].unique())
offsets = {g: (i - (len(groups_sorted) - 1) / 2) * 0.15 for i, g in enumerate(groups_sorted)}
for _, row in choice_df.iterrows():
    y = y_pos[row["arrangement"]] + offsets[row["group"]]
    ax.errorbar(row["mean_p_right"], y,
                xerr=[[row["mean_p_right"] - row["ci_lo"]], [row["ci_hi"] - row["mean_p_right"]]],
                fmt="o", color=colors.get(row["group"], "gray"),
                label=f"{row['group']} (subj {row['subject_nr']})", capsize=3)
ax.axvline(0.5, linestyle="--", color="black", linewidth=1)
ax.set_yticks(range(len(ARRANGEMENT_ORDER)))
ax.set_yticklabels(ARRANGEMENT_ORDER)
ax.set_xlabel("mean P(first fixation = RIGHT stimulus)")
ax.set_xlim(0, 1)
ax.set_title("Spatial bias by arrangement (cf. Figure 2, left)")
handles, labels = ax.get_legend_handles_labels()
ax.legend(dict(zip(labels, handles)).values(), dict(zip(labels, handles)).keys(), fontsize=8)
fig.tight_layout()
fig.savefig(os.path.join(OUT_DIR, "fig2_left_choice_proportion.png"), dpi=150)
plt.show()

# %% [7] Analysis 2: winsorized RT per clock location (Fig 2, right) -------
df_rt = df_valid.copy()
df_rt["clock"] = df_rt.apply(lambda r: CLOCK_MAP[(r["arrangement"], r["first_fix_direction"])], axis=1)

rows = []
for (subj, group, clock), g in df_rt.groupby(["subject_nr", "group", "clock"]):
    rt = g["first_fix_rt_ms"].values / 1000.0
    point, lo, hi = bootstrap_ci(rt, winsorized_mean)
    rows.append(dict(subject_nr=subj, group=group, clock=clock,
                      n_trials=len(g), winsor_mean_rt_s=point, ci_lo=lo, ci_hi=hi))
rt_df = pd.DataFrame(rows)
rt_df["clock"] = pd.Categorical(rt_df["clock"], CLOCK_ORDER, ordered=True)
rt_df = rt_df.sort_values(["clock", "subject_nr"]).reset_index(drop=True)
rt_df.to_csv(os.path.join(OUT_DIR, "reaction_time_by_location.csv"), index=False)

print("\n=== 20%-winsorized mean RT by clock location (cf. paper Figure 2, right) ===")
print(rt_df.to_string(index=False))

fig, ax = plt.subplots(figsize=(6, 6))
y_pos = {c: i for i, c in enumerate(CLOCK_ORDER)}
for _, row in rt_df.iterrows():
    y = y_pos[row["clock"]] + offsets.get(row["group"], 0)
    lo = row["winsor_mean_rt_s"] - row["ci_lo"] if not np.isnan(row["ci_lo"]) else 0
    hi = row["ci_hi"] - row["winsor_mean_rt_s"] if not np.isnan(row["ci_hi"]) else 0
    ax.errorbar(row["winsor_mean_rt_s"], y, xerr=[[lo], [hi]], fmt="o",
                color=colors.get(row["group"], "gray"),
                label=f"{row['group']} (subj {row['subject_nr']})", capsize=3)
ax.set_yticks(range(len(CLOCK_ORDER)))
ax.set_yticklabels([str(c) for c in CLOCK_ORDER])
ax.set_ylabel("first-fixation clock location")
ax.set_xlabel("20%-winsorized mean RT [s]")
ax.set_title("Reaction time by location (cf. Figure 2, right)")
handles, labels = ax.get_legend_handles_labels()
ax.legend(dict(zip(labels, handles)).values(), dict(zip(labels, handles)).keys(), fontsize=8)
fig.tight_layout()
fig.savefig(os.path.join(OUT_DIR, "fig2_right_reaction_times.png"), dpi=150)
plt.show()

# %% [8] Analysis 3: Bradley-Terry-style logistic regression ---------------
d = df_valid.copy()
d["y_right"] = (d["first_fix_direction"] == "right").astype(int)
d["arrangement"] = pd.Categorical(d["arrangement"], ARRANGEMENT_ORDER)
mod = smf.logit("y_right ~ C(arrangement) + C(group)", data=d)
try:
    model = mod.fit(disp=False)
    note = ""
except np.linalg.LinAlgError:
    model = mod.fit_regularized(alpha=0.5, disp=False)
    note = ("[NOTE: unregularized fit hit perfect separation -- some "
            "arrangement x group cells are all-left or all-right with this "
            "small n. Refit with an L1 penalty below; treat coefficients as "
            "descriptive only, not as p<.05-testable effects, until you add "
            "more subjects.]\n")

print("\n=== Bradley-Terry-style logistic regression: P(right) ~ arrangement + group ===")
if note:
    print(note)
print(model.summary() if hasattr(model, "summary") else model.params)
print("\nCAUTION: `group` is confounded with `subject_nr` whenever you have "
      "only 1 subject per reading-direction group -- see discussion below.")

with open(os.path.join(OUT_DIR, "bradley_terry_model_summary.txt"), "w") as f:
    f.write(note)
    f.write(str(model.summary() if hasattr(model, "summary") else model.params))

# %% [9] Extra: LTR vs RTL reading-onset congruence ------------------------
rows = []
for (subj, group), g in df_valid.groupby(["subject_nr", "group"]):
    match = g["fix_matches_reading_onset"].dropna().astype(float).values
    point, lo, hi = bootstrap_ci(match, np.mean)
    rows.append(dict(subject_nr=subj, group=group, n_trials=len(match),
                      p_reading_congruent=point, ci_lo=lo, ci_hi=hi))
congruence_df = pd.DataFrame(rows)
congruence_df.to_csv(os.path.join(OUT_DIR, "reading_congruence_by_group.csv"), index=False)

table = (df_valid.dropna(subset=["fix_matches_reading_onset"])
         .groupby(["group", "fix_matches_reading_onset"]).size().unstack(fill_value=0))
odds_ratio, fisher_p = (np.nan, np.nan)
if table.shape == (2, 2):
    odds_ratio, fisher_p = stats.fisher_exact(table.values)

print("\n=== Extra: P(first fixation matches reading-onset side), by group ===")
print("(reading-onset side = left for LTR readers, right for RTL readers)")
print(congruence_df.to_string(index=False))
print("\n2x2 table (group x matches-reading-onset):")
print(table)
if not np.isnan(fisher_p):
    print(f"\nFisher's exact test: odds ratio = {odds_ratio:.3f}, p = {fisher_p:.4f}")
print("\nCAUTION: with 1 subject per group this test compares two "
      "individuals, not two populations -- see discussion below.")

fig, ax = plt.subplots(figsize=(5, 4))
for i, row in enumerate(congruence_df.itertuples()):
    lo = row.p_reading_congruent - row.ci_lo if not np.isnan(row.ci_lo) else 0
    hi = row.ci_hi - row.p_reading_congruent if not np.isnan(row.ci_hi) else 0
    ax.errorbar(i, row.p_reading_congruent, yerr=[[lo], [hi]], fmt="o",
                markersize=10, color=colors.get(row.group, "gray"), capsize=4)
ax.axhline(0.5, linestyle="--", color="black", linewidth=1)
ax.set_xticks(range(len(congruence_df)))
ax.set_xticklabels([f"{r.group}\n(subj {r.subject_nr})" for r in congruence_df.itertuples()])
ax.set_ylabel("P(first fixation matches reading-onset side)")
ax.set_ylim(0, 1)
ax.set_title("Reading-direction-congruent first fixations")
fig.tight_layout()
fig.savefig(os.path.join(OUT_DIR, "extra_reading_congruence.png"), dpi=150)
plt.show()

print(f"\nAll tables/plots also saved under '{OUT_DIR}/'.")

# %% [10] (optional) zip + download results in Colab -----------------------
# Uncomment to download a results.zip via your browser:
#
# import shutil
# shutil.make_archive("results", "zip", OUT_DIR)
# if IN_COLAB:
#     files.download("results.zip")
