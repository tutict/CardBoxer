class_name CardDefs
extends RefCounted
## 卡牌与连招的唯一定义处。
##
## 设计取自 Fantasy-Agent 流水线给出的四动词（position / attack / evade /
## recover），映射成四类牌：进攻、位移、守御、蓄力。流水线的规格里没有
## 「手牌」「连招」这两个概念，所以这部分是手工设计的 —— 但它的每一条
## 失败压力（贪伤害会被惩罚、位置本身是伤害来源）都来自那份 spec。

const FRAME := 1.0 / 60.0

## 四类牌的语义，用于卡面配色与 AI 判断。
const KIND_ATTACK := "attack"
const KIND_MOVE := "move"
const KIND_GUARD := "guard"
const KIND_POWER := "power"

## 一套牌。字段单位：时间用帧（60fps），距离用像素，气用整点。
const CARDS := {
	"jab": {
		"name": "刺拳",
		"tag": "刺",
		"kind": KIND_ATTACK,
		"cost": 0,
		"windup": 4,
		"active": 3,
		"recover": 7,
		"damage": 4,
		"reach": 118,
		"bullet": false,
		"text": "最快的起手。0 气，收招短，能接任何招。",
	},
	"cross": {
		"name": "交叉反击",
		"tag": "反",
		"kind": KIND_ATTACK,
		"cost": 1,
		"windup": 6,
		"active": 4,
		"recover": 12,
		"damage": 6,
		"reach": 124,
		"bullet": false,
		"text": "对手出招时打中，伤害翻倍。",
	},
	"uppercut": {
		"name": "上勾拳",
		"tag": "升",
		"kind": KIND_ATTACK,
		"cost": 1,
		"windup": 7,
		"active": 4,
		"recover": 13,
		"damage": 8,
		"reach": 112,
		"bullet": false,
		"text": "起手慢，命中把人打离地面。连招核心。",
	},
	"sweep": {
		"name": "扫腿",
		"tag": "扫",
		"kind": KIND_ATTACK,
		"cost": 1,
		"windup": 8,
		"active": 5,
		"recover": 15,
		"damage": 7,
		"reach": 138,
		"bullet": false,
		"text": "范围长，命中造成长硬直。",
	},
	"wave": {
		"name": "气功波",
		"tag": "波",
		"kind": KIND_ATTACK,
		"cost": 2,
		"windup": 10,
		"active": 8,
		"recover": 18,
		"damage": 10,
		"reach": 470,
		"bullet": true,
		"text": "唯一能打到全屏的牌。前摇长，会被读。",
	},
	"throw": {
		"name": "投技",
		"tag": "投",
		"kind": KIND_ATTACK,
		"cost": 1,
		"windup": 5,
		"active": 4,
		"recover": 11,
		"damage": 9,
		"reach": 98,
		"bullet": false,
		"text": "无视格挡。必须贴身，远了打空。",
	},
	"rush": {
		"name": "突进",
		"tag": "进",
		"kind": KIND_MOVE,
		"cost": 1,
		"windup": 4,
		"active": 0,
		"recover": 9,
		"damage": 0,
		"reach": 0,
		"bullet": false,
		"text": "向前冲 170 像素。把距离变成资源。",
	},
	"backstep": {
		"name": "后撤",
		"tag": "退",
		"kind": KIND_MOVE,
		"cost": 0,
		"windup": 3,
		"active": 0,
		"recover": 8,
		"damage": 0,
		"reach": 0,
		"bullet": false,
		"text": "退 150 像素。退完立刻发波是经典套路。",
	},
	"guard": {
		"name": "格挡",
		"tag": "守",
		"kind": KIND_GUARD,
		"cost": 0,
		"windup": 2,
		"active": 0,
		"recover": 12,
		"damage": 0,
		"reach": 0,
		"bullet": false,
		"text": "0.55 秒内受伤减 80%。投技挡不住。",
	},
	"sidestep": {
		"name": "侧闪",
		"tag": "闪",
		"kind": KIND_GUARD,
		"cost": 0,
		"windup": 2,
		"active": 0,
		"recover": 8,
		"damage": 0,
		"reach": 0,
		"bullet": false,
		"text": "0.18 秒无敌。闪过之后反击有额外伤害。",
	},
	"focus": {
		"name": "蓄势",
		"tag": "蓄",
		"kind": KIND_POWER,
		"cost": 0,
		"windup": 10,
		"active": 0,
		"recover": 12,
		"damage": 0,
		"reach": 0,
		"bullet": false,
		"text": "原地凝神，+2 气。贪这一下要付出位置。",
	},
	"recover": {
		"name": "卸力",
		"tag": "卸",
		"kind": KIND_POWER,
		"cost": 0,
		"windup": 4,
		"active": 0,
		"recover": 10,
		"damage": 0,
		"reach": 0,
		"bullet": false,
		"text": "+1 气，并缩短自身硬直。被动挨打时用。",
	},
}

## 抽牌池。进攻牌占比 15/23：这个比例是调出来的——早期 10/18 的时候，
## 一副 5 张手牌经常整手没有能打出去的牌，双方贴脸站十几秒谁也不掉血。
const DECK := [
	"jab", "jab", "jab", "jab",
	"cross", "cross", "cross",
	"uppercut", "uppercut", "uppercut",
	"sweep", "sweep",
	"wave",
	"throw", "throw",
	"rush", "rush",
	"backstep",
	"guard", "guard",
	"sidestep",
	"focus",
	"recover",
]

## 普通连招。`seq` 是打出顺序，匹配时取最长命中。
## `bonus` 是额外伤害；`extra` 是附带效果。
const COMBOS := [
	{
		"seq": ["jab", "jab", "wave"],
		"name": "三连气弹",
		"bonus": 8,
		"extra": "launch",
	},
	{
		"seq": ["jab", "uppercut"],
		"name": "升龙连",
		"bonus": 5,
		"extra": "launch",
	},
	{
		"seq": ["jab", "cross"],
		"name": "双刺交叉",
		"bonus": 4,
		"extra": "",
	},
	{
		"seq": ["sweep", "jab"],
		"name": "下段追击",
		"bonus": 4,
		"extra": "stagger",
	},
	{
		"seq": ["uppercut", "wave"],
		"name": "空中追击",
		"bonus": 6,
		"extra": "launch",
	},
	{
		"seq": ["rush", "throw"],
		"name": "贴身摔",
		"bonus": 6,
		"extra": "stagger",
	},
	{
		"seq": ["guard", "cross"],
		"name": "防守反击",
		"bonus": 5,
		"extra": "",
	},
	{
		"seq": ["backstep", "wave"],
		"name": "退步发波",
		"bonus": 4,
		"extra": "",
	},
]

## 大招：要三张连续牌 + 3 点气。命中即改局。
const SUPERS := [
	{
		"seq": ["jab", "uppercut", "wave"],
		"name": "终幕·三重奏",
		"cost": 3,
		"bonus": 22,
		"extra": "super",
	},
	{
		"seq": ["rush", "throw", "uppercut"],
		"name": "铁壁崩",
		"cost": 3,
		"bonus": 20,
		"extra": "super",
	},
]

## 打出后多久还算在连段里（秒）。超过就断。
const COMBO_WINDOW := 1.9


static func card(id: String) -> Dictionary:
	return CARDS.get(id, {})
