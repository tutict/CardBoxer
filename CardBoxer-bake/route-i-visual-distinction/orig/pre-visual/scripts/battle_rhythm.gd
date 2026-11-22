extends RefCounted
## 由 side-view-rhythm/gen_rhythm_gd.py 从 battle_rhythm_spec.json 生成，勿手改。
## KOF 式命中节奏：赢家三角脉冲前压、输家击退后仰、星芒火花、短斜速度线、HIT! 停顿。
## 纯常量 + 纯函数，无节点无状态；数值真相来源只有那份 JSON。
## 视觉位移由 arena.gd 写进 fighter.visual_shift / visual_tilt，
## 只在 _draw() 的 draw_set_transform 内生效，不碰 position 与任何判定。

const SPEC_VERSION := "1.0"
const FRAME_S := 0.08
const ATTACK_S := 1.12
const SETTLE_S := 0.56
const RECOVER_S := 0.22
const TOTAL_S := 1.9
const HIT_AT_S := 0.48
const HITSTOP_S := 0.24

const PRESS_PX := 110.0
const PRESS_CENTER := 0.45
const PRESS_HALF_WIDTH := 0.3
const KNOCK_PX := 40.0
const KNOCK_DECAY := 1.7
const TILT_DEG := 9.0
const TILT_DECAY := 1.4
const SHAKE_AMP_PX := 3.0
const SHAKE_FREQ_X_PER_FRAME := 2.7
const SHAKE_FREQ_Y_PER_FRAME := 4.1
const FLASH_FIRST_FRAMES := 3.0
const SPARK_CORE_PX := 11.0
const SPARK_RAYS := 12.0
const SPARK_RADIUS_BASE_PX := 14.0
const SPARK_RADIUS_GROWTH_PX := 30.0
const SPARK_ALPHA := 250.0
const SPARK_ALPHA_DECAY := 1.25
const SPARK_TAIL_FRAMES := 3.0
const SPARK_RAY_EXT_PX := 18.0
const SPARK_RAY_PHASE := 0.22
const SPARK_RAY_INNER_RATIO := 0.42
const SPARK_RAY_WIDTH_MAIN := 3.0
const SPARK_RAY_WIDTH_SUB := 2.0
const SPEED_LINE_COUNT := 4.0
const SPEED_LINE_ALPHA := 84.0
const SPEED_LINE_DECAY := 2.0
const SPEED_LINE_CUTOFF := 0.42
const SPEED_LINE_LEN_BASE := 16.0
const SPEED_LINE_LEN_AMP := 18.0
const SPEED_LINE_Y_STEP := 30.0
const SPEED_LINE_PHASE_STEP := 0.08
const SPEED_LINE_DY := 2.0
const HITSTOP_LABEL := "HIT!"

# 画布重映射（游戏 1280x720；离线 880x500 的绝对坐标不共用）
const GAME_PLAYER_X := 430.0
const GAME_FOE_X := 850.0
const GAME_GROUND_Y := 520.0
const GAME_SPARK_Y_OFFSET := -130.0
const GAME_SPEED_LINE_MID_X := 640.0
const GAME_SPEED_LINE_Y0 := 300.0
const GAME_HIT_LABEL_SIZE := 28.0
const GAME_HIT_LABEL_POS := Vector2(690.0, 330.0)

static func pulse(t: float) -> float:
	return maxf(0.0, 1.0 - absf(t - PRESS_CENTER) / PRESS_HALF_WIDTH)

static func press_px(t: float) -> float:
	return PRESS_PX * pulse(t)

static func knock_px(t: float) -> float:
	return KNOCK_PX * maxf(0.0, 1.0 - t * KNOCK_DECAY)

static func tilt_rad(t: float) -> float:
	return deg_to_rad(TILT_DEG) * maxf(0.0, 1.0 - t * TILT_DECAY)

static func spark_alpha01(t: float) -> float:
	return (SPARK_ALPHA / 255.0) * maxf(0.0, 1.0 - t * SPARK_ALPHA_DECAY)

static func speed_alpha01(t: float) -> float:
	return (SPEED_LINE_ALPHA / 255.0) * maxf(0.0, 1.0 - t * SPEED_LINE_DECAY)

static func speed_len(t: float, k: int) -> float:
	return SPEED_LINE_LEN_BASE + SPEED_LINE_LEN_AMP * sin(PI * minf(1.0, t * SPEED_LINE_DECAY + float(k) * SPEED_LINE_PHASE_STEP))

static func phase_at(elapsed: float) -> String:
	if elapsed < 0.0: return "off"
	if elapsed <= ATTACK_S: return "attack"
	if elapsed <= ATTACK_S + SETTLE_S: return "settle"
	if elapsed <= TOTAL_S: return "recover"
	return "off"

## attack 窗内 t∈[0,1]；settle 窗内淡出；recover 后归零。
static func fade_at(elapsed: float) -> float:
	if elapsed < 0.0 or elapsed > TOTAL_S: return 0.0
	if elapsed <= ATTACK_S: return 1.0
	return clampf(1.0 - (elapsed - ATTACK_S) / SETTLE_S, 0.0, 1.0)

static func attack_t(elapsed: float) -> float:
	return clampf(elapsed / ATTACK_S, 0.0, 1.0)

## 命中帧起的 spark 尾窗（离线 f <= HIT_FRAME + 3）。
static func spark_active(elapsed: float) -> bool:
	return elapsed >= HIT_AT_S and elapsed <= HIT_AT_S + FRAME_S * SPARK_TAIL_FRAMES

static func speed_active(elapsed: float) -> bool:
	return elapsed >= 0.0 and attack_t(elapsed) <= SPEED_LINE_CUTOFF

static func hit_label_active(elapsed: float) -> bool:
	return elapsed >= HIT_AT_S and elapsed <= HIT_AT_S + HITSTOP_S
