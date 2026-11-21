"""Character concept sheets for CardBoxer, SDXL 1.0 Base via ComfyUI 8188.

Usage:  python gen_character_sdxl.py <V1|V2|V3> [count]

Scope: STYLING REFERENCE ONLY. These are concept illustrations, not game-ready
sprites and not a copy of any existing IP character. The in-game fighters stay
the 11-joint procedural rig; this file only fixes silhouette / costume / palette
language to design against.

Three presets are kept so every archived image is reproducible:
  V1  "costume design sheet"  -- clean turnaround + garment callouts, red hair
  V2  "equipment design sheet" -- teal palette + big boxing glove callouts
  V3  "single full-body pin-up" -- no panels, guard stance, human face cat ears
  V4  "Dialyn" direction -- black/white panda palette, Chinese knots, ring blades

Reuses the allowlisted API-format ComfyUI template (CheckpointLoaderSimple graph)
and overrides resolution / sampler only. No repository file is modified.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8188"
TEMPLATE = Path(r"C:\Users\tutic\IdeaProjects\Fantasy-Agent\templates\comfyui\ui-reference.json")
OUT = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer-bake\角色建模")
CHECKPOINT = "sd_xl_base_1.0.safetensors"

_COMMON_NEG = (
    "photo, photorealistic, 3d render, realistic skin texture, noise, grain, "
    "watermark, logo, signature, UI, HUD, cards, "
    "boxing ring, arena, audience, ropes, stage, background scenery, "
    "smoking, cigarette, smoke, ash, "
    "moe, chibi, big head, child, cute pose, wink, smile, "
    "nudity, sexy pose, cleavage, revealing clothes, fanservice, "
    "cropped, cut off, head out of frame, feet cut off, close-up, portrait only, "
    "upper body only, weapon, blood, violence, busy, clutter, high contrast, "
    "neon, lens flare, deformed, extra limbs, extra ears, extra tail, bad anatomy, "
    "jpeg artifacts"
)

PRESETS = {
    "V1": {
        "prompt": (
            "2D fighting game character concept sheet, one single full-body figure, "
            "centered, head to toe fully visible, standing in a relaxed boxing guard stance "
            "with both fists raised near the face, three-quarter front view, "
            "a lazy unbothered cat-eared beast girl boxer, human face and human proportions, "
            "short mint green bob hair, two soft green cat ears, one long slim cat tail, "
            "red heavy-lidded bored eyes, flat unimpressed expression, slightly slouched shoulders, "
            "oversized loose off-white training t-shirt, baggy dark indigo track pants, "
            "worn hand wraps and warm amber oxidized copper boxing gloves, "
            "unbothered lazy slacker attitude, anti-cute, not posing, not smiling, "
            "readable clean silhouette, flat cel-shaded vector shapes, thin dark outline, "
            "limited muted palette, soft rim lighting, game character design sheet, "
            "plain empty neutral dark gray-blue background, no scenery"
        ),
        "negative": (
            "photo, photorealistic, 3d render, realistic skin texture, noise, grain, "
            "multiple characters, duplicate figure, multiple panels, collage, comic layout, "
            "character sheet grid, turnaround, text, letters, watermark, logo, signature, "
            "UI, HUD, cards, boxing ring, arena, audience, ropes, stage, background scenery, "
            "smoking, cigarette, smoke, ash, "
            "moe, chibi, big head, child, cute pose, wink, smile, "
            "nudity, sexy pose, cleavage, revealing clothes, fanservice, "
            "cropped, cut off, head out of frame, feet cut off, close-up, portrait only, "
            "weapon, blood, violence, busy, clutter, high contrast, neon, lens flare, "
            "deformed, extra limbs, extra ears, extra tail, bad anatomy, jpeg artifacts"
        ),
        "seeds": [20261106, 812345, 774411],
    },
    "V2": {
        "prompt": (
            "2D fighting game character design sheet, clean organized tidy layout, "
            "one large central full-body front-view figure, head to toe fully visible, "
            "plus a few small neat detail callouts of costume pieces, "
            "a lazy cat-eared beast girl boxer in a boxing guard stance, "
            "both arms bent, both oversized round padded boxing gloves raised up beside the cheeks, "
            "human face and normal human proportions, "
            "vivid mint green short bob hair, pale cream oversized loose t-shirt, "
            "two mint green cat ears with pink inner fur, "
            "one long slim mint green cat tail curving out to the side clearly visible, "
            "bright red irises, heavy-lidded bored unimpressed expression, "
            "baggy dark indigo track pants, simple flat sneakers, "
            "warm amber oxidized copper boxing gloves and hand wraps, "
            "slouched unbothered slacker attitude, anti-cute, not smiling, "
            "readable silhouette, flat cel-shaded vector shapes, thin dark outline, "
            "limited muted palette, soft rim light, "
            "plain empty neutral gray-blue background, no scenery"
        ),
        "negative": (
            "photo, photorealistic, 3d render, realistic skin texture, noise, grain, "
            "multiple full-body figures, duplicate main character, messy collage, comic strips, "
            "watermark, logo, signature, UI, HUD, cards, "
            "boxing ring, arena, audience, ropes, stage, background scenery, "
            "smoking, cigarette, smoke, ash, "
            "moe, chibi, big head, child, cute pose, wink, smile, "
            "nudity, sexy pose, cleavage, revealing clothes, fanservice, "
            "cropped, cut off, head out of frame, feet cut off, close-up, portrait only, "
            "weapon, blood, violence, busy, clutter, high contrast, neon, lens flare, "
            "deformed, extra limbs, extra ears, extra tail, bad anatomy, "
            "red hair, pink hair, orange hair, blonde hair, dark hair, "
            "arms hanging down, hands at sides, bare hands, no gloves, jpeg artifacts"
        ),
        "seeds": [551199, 906271, 331877],
    },
    "V3": {
        "prompt": (
            "single 2D game character illustration, exactly one full-body figure only, "
            "no panels, no callouts, no infographic, no text, "
            "centered front view, head to toe fully visible, "
            "standing boxing guard pose, both arms bent, "
            "both large round padded boxing gloves held up beside the cheeks, "
            "a lazy cat-eared girl boxer with a normal human face and human skin, "
            "cat ears sit on top of the head, not an animal head, "
            "short mint green bob hair, bright red irises, heavy-lidded bored expression, "
            "two mint green cat ears with pink inner fur, "
            "one long slim mint green cat tail visible curving behind her, "
            "oversized loose pale cream t-shirt, baggy dark indigo track pants, flat sneakers, "
            "large warm amber oxidized copper boxing gloves, hand wraps, "
            "slouched unbothered slacker attitude, anti-cute, not smiling, "
            "flat cel-shaded vector art, thin dark outline, limited muted palette, "
            "plain empty neutral gray-blue background, no scenery"
        ),
        "negative": (
            _COMMON_NEG + ", "
            "design sheet, character sheet, turnaround, multiple views, detail callouts, "
            "product sheet, infographic, text, letters, labels, annotations, "
            "animal head, cat head, cat face, furry face, muzzle, snout, whiskers on face, "
            "full body fur, anthropomorphic cat, "
            "arms hanging down, hands in pockets, hands at sides, bare hands, no gloves, "
            "red hair, pink hair, orange hair, blonde hair, dark hair"
        ),
        "seeds": [424242, 616161, 909090],
    },
    "V4": {
        # Styling reference derived from public character descriptions of
        # Dialyn (Zenless Zone Zero 2.4): black/white "panda" palette, two-tone
        # hair with hollow ring buns, red Chinese knots, gold clasp sash,
        # pom-poms, chunky gold-buckled platform shoes, a retro rotary phone
        # with a turquoise cord, and a paired black/white split ring weapon.
        # Deliberately rendered as a MODEST, fully covered fighting-game
        # costume: no bare shoulders, no midriff, no stockings focus.
        "prompt": (
            "2D fighting game character design sheet, clean organized tidy layout, "
            "one large central full-body front-view figure, head to toe fully visible, "
            "plus a few small neat detail callouts of costume pieces and a paired ring weapon, "
            "a petite Chinese-style martial arts girl boxer, modest fully covered outfit, "
            "black and white two-tone hair, white hair with black streaks and black hair "
            "with white streaks, two hollow ring-shaped hair buns on top of the head, "
            "short braids, one gold and one silver hair clip on the bangs, "
            "small panda motifs on the headband, collar, waist charm and shoe tongue, "
            "white outer short jacket over a black inner layer, bamboo-leaf Mandarin collar, "
            "red Chinese knot fasteners on the chest and at the waist, "
            "black sash with a gold clasp, frilled cuff sleeves, "
            "loose black shorts over opaque white tights, white ruffled ankle socks, "
            "chunky platform shoes with gold buckles and a gold dial ornament, "
            "one black and one white pom-pom at the hair and at the shoe heels, "
            "a retro rotary dial telephone mounted at the back with a turquoise coiled cord, "
            "a pair of black and white split ring blades shown as a small detail callout, "
            "both arms bent, both large padded boxing gloves raised beside the cheeks "
            "in a boxing guard stance, warm amber oxidized copper boxing gloves, "
            "sharp sly half-lidded eyes, faint smug smirk, playful but principled expression, "
            "flat cel-shaded vector shapes, thin dark outline, "
            "limited black white red gold palette, soft rim light, "
            "plain empty neutral gray-blue background, no scenery"
        ),
        "negative": (
            _COMMON_NEG + ", "
            "design sheet grid, messy collage, comic strips, multiple full-body figures, "
            "duplicate main character, text, letters, labels, annotations, "
            "panda head, animal head, mascot costume, full body fur, panda suit, "
            "bare shoulders, off shoulder, midriff, crop top, cleavage, "
            "revealing clothes, lingerie, stockings focus, thigh focus, "
            "fanservice, sexualized pose, child-like erotic, "
            "cat ears, animal ears, hood, hoodie, "
            "green hair, red hair, pink hair, blonde hair, "
            "arms hanging down, hands in pockets, bare hands, no gloves, "
            "smoking, cigarette, smoke"
        ),
        "seeds": [24932493, 58285828, 11122611],
    },
    "V5": {
        # V4 produced excellent black/white/red/gold costume sheets but NO
        # boxing gloves and arms hanging down. V5 front-loads the glove and
        # guard pose and strips competing costume detail words.
        "prompt": (
            "2D fighting game character concept sheet, one large central full-body figure, "
            "head to toe fully visible, front view, boxing guard stance, "
            "huge round padded boxing gloves on BOTH hands, both gloved fists raised "
            "beside the cheeks, large warm amber oxidized copper boxing gloves clearly visible, "
            "large round gloves are the most prominent feature, "
            "a petite Chinese-style martial arts girl boxer, modest fully covered outfit, "
            "white short jacket over a black inner vest, cross-collar Mandarin neckline, "
            "red sash with a red Chinese knot at the waist, gold clasp and gold trim, "
            "black hair in two hollow ring-shaped buns on top of the head, short braids, "
            "one black and one white pom-pom at the hair, gold and silver hair clips, "
            "white loose pants, chunky black platform shoes with gold buckles, "
            "small panda motif on the collar, "
            "a retro rotary dial telephone with a turquoise coiled cord "
            "as a small detail callout, "
            "a pair of black and white split ring blades as a small detail callout, "
            "sharp sly half-lidded eyes, faint smug smirk, playful principled expression, "
            "flat cel-shaded vector shapes, thin dark outline, "
            "limited black white red gold amber palette, "
            "plain empty neutral gray background, no scenery"
        ),
        "negative": (
            _COMMON_NEG + ", "
            "messy collage, comic strips, multiple full-body figures, duplicate main character, "
            "text, letters, labels, annotations, "
            "bare hands, exposed fingers, uncovered hands, empty hands, "
            "thin gloves, small gloves, arms hanging straight down, arms straight, "
            "hands at sides, hands in pockets, "
            "panda head, animal head, mascot costume, full body fur, panda suit, "
            "cat ears, animal ears, hood, hoodie, "
            "bare shoulders, off shoulder, midriff, crop top, cleavage, "
            "revealing clothes, lingerie, stockings focus, thigh focus, "
            "fanservice, sexualized pose, child-like erotic, "
            "green hair, red hair, pink hair, blonde hair, "
            "smoking, cigarette, smoke"
        ),
        "seeds": [770077, 330033, 515015],
    },
}

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    try:
        with OPENER.open(req, timeout=180) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code} on {path}: {exc.read().decode('utf-8', 'replace')[:1600]}")
        raise


def inject(value, values):
    if isinstance(value, dict):
        return {k: inject(v, values) for k, v in value.items()}
    if isinstance(value, list):
        return [inject(v, values) for v in value]
    if isinstance(value, str):
        for key, replacement in values.items():
            token = "{{ " + key + " }}"
            if value == token:
                return replacement
            value = value.replace(token, str(replacement))
    return value


def workflow(tag: str, seed: int, index: int) -> dict:
    preset = PRESETS[tag]
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    values = {
        "prompt": preset["prompt"],
        "negative_prompt": preset["negative"],
        "seed": seed,
        "output_path": "unused",
        "job_id": f"cardboxer-character-{tag.lower()}-{index}",
        "gameplay_constraint": "2D side-view fighting game full-body character concept",
        "checkpoint_name": CHECKPOINT,
        "filename_prefix": f"CardBoxer/character_{tag.lower()}_{index:02d}",
    }
    wf = inject(template, values)
    # Portrait aspect for a full-body sheet; 768x1024 keeps VAE decode well under
    # the RAM ceiling that broke the earlier 1024x640 full-frame decode.
    wf["4"]["inputs"]["width"] = 768
    wf["4"]["inputs"]["height"] = 1024
    wf["5"]["inputs"]["steps"] = 26
    wf["5"]["inputs"]["cfg"] = 6.5
    wf["5"]["inputs"]["sampler_name"] = "dpmpp_2m"
    wf["5"]["inputs"]["scheduler"] = "karras"
    return wf


_STEMS = {"V4": "琉音-拳手设定", "V5": "琉音-拳手设定"}


def out_name(tag: str, index: int) -> str:
    # V1 was archived before tags existed; keep that exact filename reproducible.
    if tag == "V1":
        return f"尼古喵喵-拳手设定-{index:02d}.png"
    stem = _STEMS.get(tag, "尼古喵喵-拳手设定")
    return f"{stem}-{tag}-{index:02d}.png"


def main() -> int:
    tag = (sys.argv[1] if len(sys.argv) > 1 else "V3").upper()
    if tag not in PRESETS:
        print(f"UNKNOWN_TAG {tag}; choose from {sorted(PRESETS)}")
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    seeds = PRESETS[tag]["seeds"]
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    print(
        f"tag={tag} count={count} checkpoint={CHECKPOINT} "
        f"latent=768x1024 steps=26 cfg=6.5 dpmpp_2m/karras",
        flush=True,
    )

    for index, seed in enumerate(seeds[:count], start=1):
        response = request(
            "/prompt",
            {"prompt": workflow(tag, seed, index), "client_id": "cardboxer-character"},
        )
        prompt_id = response.get("prompt_id")
        if not prompt_id:
            print(f"[{index}] no prompt_id: {response}")
            return 1
        print(f"[{index}] queued prompt_id={prompt_id} seed={seed}", flush=True)
        deadline = time.monotonic() + 900
        images: list[dict] = []
        while time.monotonic() < deadline:
            history = request(f"/history/{prompt_id}")
            record = history.get(prompt_id, {})
            status = record.get("status", {})
            if status.get("status_str") == "error":
                print(f"[{index}] ComfyUI error: {json.dumps(status, ensure_ascii=False)[:1200]}")
                return 1
            for output in record.get("outputs", {}).values():
                images.extend(output.get("images", []))
            if images:
                break
            time.sleep(2.0)
        if not images:
            print(f"[{index}] TIMEOUT")
            return 1
        image = images[0]
        query = urllib.parse.urlencode(
            {
                "filename": image["filename"],
                "subfolder": image.get("subfolder", ""),
                "type": image.get("type", "output"),
            }
        )
        with OPENER.open(urllib.request.Request(BASE + "/view?" + query), timeout=180) as resp:
            blob = resp.read()
        target = OUT / out_name(tag, index)
        target.write_bytes(blob)
        print(f"[{index}] saved {target.name} ({len(blob)} bytes, source={image['filename']})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
