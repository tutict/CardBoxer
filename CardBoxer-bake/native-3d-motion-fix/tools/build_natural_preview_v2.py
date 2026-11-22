"""Tools-only continuous V2 render review package; no project mutation."""
import json
import math
from pathlib import Path
from collections import defaultdict
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'reports'
QA = OUT / 'natural-v2-visual-boards'
QA.mkdir(exist_ok=True)
CAP = json.loads((ROOT/'shots/natural-v2-final/manifest.json').read_text(encoding='utf-8'))
TIM = json.loads((ROOT/'shots/natural-v2-final-timeline/manifest.json').read_text(encoding='utf-8'))
CLIPS = TIM['clips']
BG = '#242932'
FONT_PATH = Path('C:/Windows/Fonts/segoeui.ttf')
def font(size):
    return ImageFont.truetype(str(FONT_PATH),size) if FONT_PATH.exists() else ImageFont.load_default()

def rgba(path):
    return Image.open(path).convert('RGBA')

def composite(path, size=None, crop=None):
    im=rgba(path)
    if crop: im=im.crop(crop)
    bg=Image.new('RGBA',im.size,BG)
    bg.alpha_composite(im)
    if size: bg=bg.resize(size,Image.Resampling.LANCZOS)
    return bg.convert('RGB')

def crop_union(rows):
    bounds=[]
    for r in rows:
        with Image.open(r['path']) as im:
            b=im.getchannel('A').point(lambda v:255 if v>16 else 0).getbbox()
            if b: bounds.append(b)
    return (max(0,min(b[0] for b in bounds)-30),max(0,min(b[1] for b in bounds)-24),
            min(720,max(b[2] for b in bounds)+30),min(680,max(b[3] for b in bounds)+24))

crop=crop_union(TIM['rows'])
tile_w=440
tile_h=round((crop[3]-crop[1])*tile_w/(crop[2]-crop[0]))
timeline={(r['clip'],r['step'],r['role']):r for r in TIM['rows']}
frames=[]
for clip in CLIPS:
    for step in range(TIM['steps_per_clip']):
        im=Image.new('RGB',(tile_w*2,tile_h+74),BG)
        d=ImageDraw.Draw(im)
        d.text((18,8),f'{clip.upper()}  |  Natural motion V2',font=font(20),fill='white')
        d.text((18,36),'PLAYER',font=font(13),fill='#d4d9df')
        d.text((tile_w+18,36),'FOE',font=font(13),fill='#d4d9df')
        for role_index,role in enumerate(('player','foe')):
            r=timeline[(clip,step,role)]
            im.paste(composite(r['path'],(tile_w,tile_h),crop),(role_index*tile_w,54))
        d.text((18,tile_h+55),'Full cycle | 60Hz taikou timing | repeated separately for each role',font=font(12),fill='#bbc4d0')
        frames.append(im)

palette_board=Image.new('RGB',(440*5,350),BG)
for i in range(5):
    sample=frames[i*83+33].resize((440,350))
    palette_board.paste(sample,(i*440,0))
palette=palette_board.quantize(colors=192)
indexed=[f.quantize(palette=palette,dither=Image.Dither.NONE) for f in frames]
durations=[round((i+1)*100/60)*10-round(i*100/60)*10 for i in range(len(indexed))]
normal_path=OUT/'natural-preview-v2.gif'
slow_path=OUT/'natural-preview-v2-slow.gif'
indexed[0].save(normal_path,save_all=True,append_images=indexed[1:],duration=durations,loop=0,optimize=False,disposal=1)
slow=[]
for f in frames:
    s=f.copy()
    d=ImageDraw.Draw(s)
    d.rectangle((0,s.height-20,s.width,s.height),fill=BG)
    d.text((18,s.height-19),'3x slow motion | 50ms per source frame | same complete cycles',font=font(12),fill='#bbc4d0')
    slow.append(s.quantize(palette=palette,dither=Image.Dither.NONE))
slow[0].save(slow_path,save_all=True,append_images=slow[1:],duration=50,loop=0,optimize=False,disposal=1)

groups=defaultdict(list)
for r in CAP['rows']: groups[(r['clip'],r['relative_facing'])].append(r)
def phase_frames(rows):
    stop=max(r['frame'] for r in rows)
    contact=rows[0]['contact_frame']
    wanted=[0,round(stop*.2*2)/2,contact if contact>=0 else round(stop*.5*2)/2,round(stop*.75*2)/2,stop]
    available=sorted(set(r['frame'] for r in rows))
    return [min(available,key=lambda f:abs(f-w)) for w in wanted]

for facing in (1,-1):
    for page_start in range(0,len(CAP['clips']),4):
        clips=CAP['clips'][page_start:page_start+4]
        tw,th=240,round(680*240/720)
        band=th*2+50
        board=Image.new('RGB',(tw*5,band*len(clips)),BG)
        d=ImageDraw.Draw(board)
        for j,clip in enumerate(clips):
            rows=groups[(clip,facing)]
            lookup={(r['role'],r['frame']):r for r in rows}
            samples=phase_frames(rows)
            d.text((10,j*band+4),f'{clip.upper()} | facing {facing} | player / foe | start, load, contact/middle, return, end',font=font(14),fill='white')
            for k,f in enumerate(samples):
                for ri,role in enumerate(('player','foe')):
                    y=j*band+30+ri*(th+10)
                    board.paste(composite(lookup[(role,f)]['path'],(tw,th)),(k*tw,y))
                    d.text((k*tw+5,y),f'{role} f{f:g}',font=font(12),fill='#d9e2ee')
        board.save(QA/f'all19-facing{facing}-page{page_start//4+1}.png')

# Larger detailed timing filmstrips expose velocity/step continuity at regular60Hz intervals.
for clip in CLIPS:
    steps=[0,8,16,24,29,43,50,58,66,74,82]
    tw=220
    th=round((crop[3]-crop[1])*tw/(crop[2]-crop[0]))
    strip=Image.new('RGB',(tw*len(steps),th*2+55),BG)
    d=ImageDraw.Draw(strip)
    d.text((10,4),clip.upper()+' | complete production presentation timeline | source60Hz',font=font(15),fill='white')
    for k,s in enumerate(steps):
        for ri,role in enumerate(('player','foe')):
            strip.paste(composite(timeline[(clip,s,role)]['path'],(tw,th),crop),(k*tw,28+ri*th))
            d.text((k*tw+5,28+ri*th),f'{role} {s/60:.2f}s',font=font(12),fill='white')
    strip.save(QA/(clip+'-continuous.png'))

# A readable static companion contains the guard and five contact silhouettes.
selected=[('stance',0)]+[(c,groups[(c,1)][0]['contact_frame']) for c in CLIPS]
tw,th=250,round(680*250/720)
static=Image.new('RGB',(tw*len(selected),th*2+76),BG)
d=ImageDraw.Draw(static)
d.text((14,7),'Natural motion V2 | compact guard, hip-led strikes, low extended sweep',font=font(20),fill='white')
for k,(clip,f) in enumerate(selected):
    lookup={(r['role'],r['frame']):r for r in groups[(clip,1)]}
    d.text((k*tw+8,40),clip.upper(),font=font(14),fill='white')
    for ri,role in enumerate(('player','foe')):
        static.paste(composite(lookup[(role,f)]['path'],(tw,th)),(k*tw,62+ri*th))
static.save(OUT/'natural-preview-v2.png')

# Sample the historical GIF across its actual duration to ground the comparison.
old=Image.open(ROOT/'versions/v1/preview.gif')
old_stats={'frames':old.n_frames,'duration_ms':0,'size':old.size}
old_frames=[]
for i in range(old.n_frames):
    old.seek(i)
    old_stats['duration_ms']+=old.info.get('duration',0)
    if i%max(1,old.n_frames//8)==0: old_frames.append(old.convert('RGB').copy())
old_w=550
old_h=round(old_frames[0].height*old_w/old_frames[0].width)
board=Image.new('RGB',(old_w*4,old_h*math.ceil(len(old_frames)/4)+35),BG)
d=ImageDraw.Draw(board)
d.text((8,4),'Historical versions/v1/preview.gif | regularly spaced saved frames',font=font(16),fill='white')
for i,f in enumerate(old_frames): board.paste(f.resize((old_w,old_h)),((i%4)*old_w,35+(i//4)*old_h))
board.save(QA/'v1-continuous-samples.png')

def gif_meta(path):
    im=Image.open(path)
    durations=[]
    for i in range(im.n_frames):
        im.seek(i)
        durations.append(im.info.get('duration',0))
    return {'frames':im.n_frames,'size':im.size,'duration_ms':sum(durations),'loop':im.info.get('loop'),'frame_durations_ms':sorted(set(durations))}
result={'source_sha256':TIM['source_sha256'],'capture_images':len(CAP['rows']),'timeline_images':len(TIM['rows']),
        'source_frames':len(frames),'crop_constant_all_frames':crop,'tile_size':[tile_w,tile_h],
        'normal':gif_meta(normal_path),'slow':gif_meta(slow_path),'historical_v1':old_stats,
        'limitations':TIM['evidence']}
live_stats=[]
for source in sorted((ROOT/'shots/natural-v2-final-live').glob('*.json')):
    if source.name=='summary.json': continue
    scenario=json.loads(source.read_text(encoding='utf-8'))
    captures=[r for r in scenario['images'] if 'live' in r['capture']]
    full=[]
    for r in captures:
        im=Image.open(r['capture']['live']['path']).convert('RGB')
        im=im.resize((768,432),Image.Resampling.LANCZOS)
        framed=Image.new('RGB',(768,457),BG)
        framed.paste(im,(0,25))
        ImageDraw.Draw(framed).text((8,4),f"{source.stem} | real-state render | t{r['tick']/60:.2f}s | sampled10fps",font=font(14),fill='white')
        full.append(framed)
    if full:
        dest=QA/(source.stem+'-live-10fps.gif')
        full[0].save(dest,save_all=True,append_images=full[1:],duration=100,loop=0)
        indices=[round(i*(len(full)-1)/5) for i in range(6)]
        board=Image.new('RGB',(768*3,457*2),BG)
        for i,index in enumerate(indices): board.paste(full[index],((i%3)*768,(i//3)*457))
        board.save(QA/(source.stem+'-live-scenes.png'))
    roles=[item['capture'][role] for item in scenario['images'] for role in ('player','foe') if role in item['capture']]
    failed=[]
    for r in roles:
        with Image.open(r['path']) as im:
            b=im.getchannel('A').point(lambda v:255 if v>16 else 0).getbbox()
            if not b or b[0]<4 or b[1]<4 or b[2]>im.width-4 or b[3]>im.height-4: failed.append(r['path'])
    live_stats.append({'scenario':source.stem,'role_images':len(roles),'clipped_or_empty':failed,'full_scene_images':len(full),
                       'source_motion_sha256':scenario['motion_source_sha256'],'config_distance_px':scenario['config'].get('distance',85),
                       'hits':len([e for e in scenario['events'] if e['kind']=='hit'])})
result['live_scenarios']=live_stats
(OUT/'natural-preview-v2-metadata.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
