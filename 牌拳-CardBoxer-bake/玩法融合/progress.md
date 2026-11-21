# SDD ledger — plan: C:/Users/tutic/Desktop/学习资料/牌拳-CardBoxer-bake/玩法融合/plan.md

2026-11-21 continuation: previous three-beat implementation passed 20/20 full-suite scripts and a fresh review before the user's requested redesign. Release was prepared but not installed. Do not redo the completed baseline feature.

Revision: latest user reply requests five actions, three actual enemy cards visible with exactly two randomly masked, one-page optional swaps and a larger window. Godot's existing visible window was confirmed maximized (title-bar Restore control) after the requested restart. Continue revision tasks A–C.

Ruling: keep three-action pure combat characterization scenarios behind an explicit action_count=3 context while the actual match defaults to five — validates existing combat arithmetic and makes plan length configurable — production planning always requires five, so the old mandatory three-card workflow cannot reappear.

Ruling: use 1600×900 tactical UI with the existing 1280×720 authored stage scaled visually — adds readable decision space without changing physical combat coordinates — final GPU/contact checks must verify transforms and mouse targets.

Pre-flight revision: definitions/effects feed Rules; Rules and bounded AI feed Match; Match.enemy_preview/swaps_used and five-slot selection feed HUD. Three Joker slots are separately configured. Mask RNG is independent of the player's deck RNG.

Revision A: complete — tactical_planning_check RED1/26 → GREEN113/113; tactical_match_check267/267; rules2045/2045. Exhaustive 18×18 pairings at three distances now run five beats; literal combat arithmetic fixtures retain explicit three-action context. Enemy locks before planning, preview has exactly two masks, swaps conserve all 36 physical cards, and AI simulates at most24 full plans from a bounded beam.

Revision B: complete — UI RED84/87 → GREEN161/161; integration74/74; native contact1/1 with dx=0.000. The new window setting encountered a null Window during manual pre-tree test initialization; guarded that optional Window operation, preserving real startup sizing and independent HUD coordinates. GPU captures succeeded in both 2D and native3D (12 frames per mode) under shots/five-2d and shots/five-3d. Inspected five-card plans, ten-card hand, hidden-card explanation, Joker draft and17-damage riposte.

Execution: native, approved by user's “Please implement the plan.” No further plan approval or execution-method prompt is needed.

Ruling: The root Git repository has no HEAD and the real game is an untracked sibling. Use the approved isolated game copy plus baseline hashes/patch artifact instead of a Git worktree or commits; staging the user's historical asset collection would be unrelated work. Preserve this ledger and delivery evidence because there is no Git history to recover it from.

Pre-flight: Task 1 produces tactical catalog/state/event contracts; Tasks 2/3/4 consume these names. Task 2 owns all authoritative HP and deck mutation; Task 3 consumes idempotent contacts and only mirrors HP into visual actors. Task 4 consumes Match state and delegates all input to Match. No conflicting ownership.

Task 1: in progress. Spec is the approved source of truth; defense becomes active upon windup completion, equal-time nonattack effects precede atomic hits, and recover clears a previous opening at beat start as its explicit special effect.

Task 1: complete — tactical_rules_check.gd RED 0/1 (missing feature) → GREEN 2045/2045, console exit 0. Includes all 18x18 pairings at three distances and side-symmetry invariants. Catalog is separate from the unchanged twelve-card realtime contract.

Baseline: taikou_rules_check 90/90 and combo_check 8/8 passed on the copied game. Windows certificate-store diagnostic and the legacy combo fixture's object/RID leaks predate this feature. GUI Godot executable does not reliably propagate the child exit status; all verification uses Godot_v4.5-stable_win64_console.exe and explicit result markers.

Task 2: in progress — finite deck, draft, fair AI and event scheduler.

Task 2: complete — tactical_match_check.gd RED 0/1 → GREEN 267/267, console exit0. Seeded drafts/hands, all physical-card counts, commit-before-selection, pause/large-delta idempotence, bonus hand, 18-exchange all-draw match limit, and 30/120 FPS seeded full matches passed.

Task 2 implementation detail: AI enumerates distinct ordered card sequences, retains eight candidates per first-action category (maximum48), then evaluates those with the same pure resolver against eight fixed styles and up to three publicly revealed recent plans. This bounds decision latency while keeping defensive styles represented; hidden player hand/selection never enters its function signatures.

Task 3: in progress — integrate Arena default mode and a visual-only actor/presentation adapter.

Task 3: complete — integration RED 0/2 → GREEN75/75. All eighteen clips sample authored native poses. Actual contact mirrors13 riposte damage; realtime hit/projectile signals remain absent. Terminal-pose regression RED73/75 → GREEN75/75: preserve fully down poses across phase changes and mirror KO elapsed time into the 2D actor. Legacy taikou flow remains52/52 with explicit mode fixture; old default assertions now name the approved tactical default.

Task 4: in progress — expanded HUD implemented, UI RED0/1 → GREEN85/85 for geometry/keyboard/mouse. Independent layout assessment informed moving decision controls above actors and shrinking rank/typography on the ten-card hand. Incumbent GPU screenshot captured; Godot GDScript is not meaningfully covered by Impeccable's web-oriented detector (empty scan), so actual renders and geometry checks are the evidence. Real 2D/3D visual QA remains pending.

Revision C: complete — sequential `py -3 project/tools/verify_tactical.py --output <absolute workspace log path>` passed 21/21. Initial relative output invocation exited 0/21 because Godot resolved the relative `--log-file` path under `user://玩法融合/logs` and could not create it; absolute output path fixed the invocation.
Final review: independent read-only reviewer found no concrete user-impacting issues and marked ready.
Install: `release_tactical.py --install` installed 27/27 files into the authorized original project. All installed SHA-256 digests were rechecked at 27/27. Original project launched from its installed path, and the visible game window is maximized with the revised Joker draft on screen.


2026-11-21 compact-card iteration: user feedback requested a smaller two-row planning block and less repeated hand-card text, plus low-saturation card colors. Planning slots are 54 logical pixels high. The standalone distance box and hidden-card label were removed. Card faces show type icon, rank, name, and one tactical value. Full card rules remain in hover details. Both 2D and native 3D captures verified the actors remain clear, including a 10-card hand.

Comfy Desktop was used with local SDXL to generate the arena-ring hidden-card emblem. The source image was cropped and color graded to a restrained dark plum/teal treatment. It appears only as a low-opacity background on the two enemy hidden slots. The saturated intermediate generations were discarded. Final shipped design asset: assets/tactical/hidden_card_back.png plus its correctly named Godot import metadata.

Verification: the post-redesign tactical and legacy suite completed 21/21. HUD checks passed 190/190. The installed original project separately passed tactical_ui_check.gd 190/190 and tactical_planning_check.gd 113/113. The first direct installed UI test exposed a missing `.godot/imported` texture cache. Godot editor import recreated the cache, then both installed checks passed. Installed source manifest hashes remain 29/29 verified.

Final delivery: prepared 29 files, including `hidden_card_back.png.import`, then installed and independently SHA-256 checked 29/29 against the source tree. The initial installed run lacked `.godot/imported`; headless editor import created the texture, after which installed HUD and planning regressions passed 190/190 and 113/113. The restarted game window was verified on screen and maximized.
