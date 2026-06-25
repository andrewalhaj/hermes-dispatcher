# DM Voice Board — NPC Voice-Model Pipeline (RVC)

**Last updated:** 2026-06-09
**Engine:** RVC v2 (training) → w-okada VC Client (real-time runtime on 3070)
**Grounding:** w-okada official RVC tutorial; RVC community dataset/epoch norms (2024).

## Key architectural fact
**w-okada does NOT train.** It only runs conversion in real time. Training happens
separately in an RVC WebUI (RVC-Project original, or ddPn08-RVC, or a Colab/Pinokio
one-click). This is GOOD: training can happen on ANY box (even Andrew's GPU-less dev
machine via Colab), and only the finished `.pth` + `.index` files ship to the 3070 laptop.

Each NPC = one `.pth` (the model) + one `.index` (timbre retrieval). Drop both into
w-okada's model folder → NPC appears in the swap dropdown. That pair IS a board slot.

---

## Stage 1 — Source audio (the real cost center)
Goal: clean, dry, single-speaker audio of the TARGET voice you want each NPC to sound like.

**Where target voices come from (pick per NPC):**
- Your own voice doing a character → record fresh (most control, no legal questions).
- A public-domain / open voice sample.
- AVOID training on copyrighted actor voices you plan to distribute — fine for a private
  home table, dicey if shared. Flagging once; your call.

**Quality bar (matters more than quantity):**
- Mono, no background music, no reverb, no other speakers.
- Consistent mic/volume. Dry recording > processed.
- If source has music/noise → clean it with **Ultimate Vocal Remover (UVR)** first.

**How much audio per tier:**
- **Hero NPC (recurring):** 10–25 min of clean speech. This is the documented sweet spot.
- **One-off NPC (throwaway):** 2–5 min works. ~2 min can yield a usable voice; fidelity
  is lower but fine for a shopkeeper nobody remembers.
- More than ~25 min rarely helps on modern pretrains and slows training.

---

## Stage 2 — Prep the dataset
1. Split long recordings into 3–10s clips (RVC WebUI auto-slices, or do it manually).
2. Remove silence-only and garbled clips.
3. Normalize levels. Target sample rate 40k or 48k (pick one and stay consistent).
4. One speaker per dataset folder. Never mix two voices into one NPC model.

**Capture shortcut:** w-okada ships a browser recording app
(https://w-okada.github.io/voice-changer/) that's purpose-built for capturing training
voice in-browser — convenient when recording fresh.

---

## Stage 3 — Train the RVC model
Run in an RVC WebUI (local GPU, or free Colab if dev box has no GPU).

**Settings that matter:**
- **f0 / pitch extraction method: `rmvpe`** — best quality + robust, current default. Use it.
- **Epochs:**
  - Hero (10–25 min data): ~200–400 epochs.
  - One-off (2–5 min data): ~300–500 epochs (small data needs more passes).
  - 1000 is the ceiling and brings diminishing returns + can ADD noise. Don't chase it.
- **Batch size:** fit to training GPU VRAM (Colab T4 ≈ 7–8; tune down if OOM).
- **Save frequency:** every 25–50 epochs so you can pick the best checkpoint, not just the last.
- Train produces the `.pth`; build/save the **`.index`** too — it's required for good timbre.

**Overtraining is real:** if output gets robotic/noisy at high epochs, step back to an
earlier checkpoint. More epochs ≠ better past the knee.

---

## Stage 4 — Deploy to the board
1. Copy each NPC's `.pth` + `.index` into w-okada's RVC model directory on the laptop.
2. They appear in the model dropdown = your live NPC board.
3. Per-NPC runtime knobs in w-okada (set once, save per slot):
   - **Pitch shift:** offset to fit the NPC (e.g. +12 gruff→higher, −12 deep villain).
   - **Index ratio:** ~0.5–0.75. Higher = more target timbre, lower = more of your clarity.
   - **f0: rmvpe** here too.
   - **Chunk / extra buffer:** the latency vs. stability tradeoff — tune in Stage-0 POC.

---

## Tiering strategy (matches "mixture of both")
SINGLE ENGINE (RVC). "Trained vs zero-shot" is just data volume:
- **Full-train** the 3–5 hero voices you reuse every session. Invest the 10–25 min each.
- **Quick-train** one-offs from 2–5 min as needed between sessions.
- True no-train spontaneous NPCs → seed-vc (zero-shot reference clip) is the only real
  option, but hold it as PHASE 2. Don't run two engines at the table in v1.

## Build a small library, not a perfect one
Front-load 3–5 hero voices. Add one-offs incrementally. The board grows session over
session; you do NOT need a full cast before first use.

## Hard pitfalls
- Dirty/multi-speaker datasets = muddy model. Garbage in, garbage out — Stage 1 quality
  is 80% of the result.
- Skipping the `.index` file = weak timbre transfer. Always ship both files.
- Chasing epochs into the noise zone. Checkpoint and compare.
- Mic feedback at the table (speakers → open mic): headset/directional mic. (Runtime, but
  it will ruin a good model if ignored.)
