# 3D 双方全动作修正 — approved 2026-11-19

User approved: 3D player and foe; all existing 12 cards + hit_light/hit_heavy/block;
taikou and realtime; arcade anticipation/impact/overshoot; native multi-axis poses
with the existing models, 13 driven bones, neutral_bone, costume and hand shapes.

Actual install target: D:/Projects/CardBoxer/CardBoxer
Isolated implementation: this folder's project/. Baseline: baseline/.
Do not modify the install target until changes are tested and packaged.

1. Native pose library and authored player/foe clips, rest-relative quaternions,
   stance/idle/walk/ko support. First validate guard, jab, cross, sweep visually.
2. Driver applies q_rest*q_delta, rest translations/scales, one root offset;
   layer no longer appends old stance bias for native poses; rotate model for facing.
3. Read-only Fighter snapshot + shared presentation controller. Realtime retains
   existing action/hit/movement clocks; wave release != later projectile impact.
4. Taikou reveal 1.5s, resolve 1.9s, attack 1.12s; contact 0.48s by piecewise
   sampling to final active frame. Present hit/FX/knockback/tilt once at contact,
   hold 0.24s; damage/rage/rules still settle at the original point.
5. Preserve terminal exchange across freeze; contact then 0.45s KO, hold;
   pause freezes visual time, slow motion uses world dt; reset discards old cues.
6. Isolate visual RNG. Test fixed decks/inputs and same-version 2D/3D logic;
   no promise to reproduce old mixed-RNG seed sequences.
7. Data/driver/controller tests, legacy logic regression, actual state-machine
   matches, both models' deformation/grounding, preview GIFs and frame boards.

Defaults: 0.06s normal blends, immediate hit/contact/KO impulse; priority terminal
KO after its contact > hit/block > contact latch > action > walking/idle.
CARD_BOXER_BATTLE_MODE=taikou|realtime, taikou default; existing 3D toggle retained.

No new gameplay cards, damage, reach, meter, invulnerability, or combo recipes.
Fix shoulder/elbow/hip/knee weights if new motion exposes seams, keeping shape,
topology, material and bone names. Preserve old 2D tables and legacy apply_frame.

Prior baseline: motion_check 228 frames/5016 values passed, combo_check 8/8,
taikou_rules_check 90/90. Godot console executable is a wrapper around the GUI
executable. NEVER use --log-file NUL: Godot 4.5 crashes on that reserved path.
Use an absolute real log file in this folder. Headless tests emit an existing
Windows certificate-store diagnostic; combo fixture also leaks pre-existing RIDs.
