"""Neuron long-form animation engine — crash-safe (PIL -> ffmpeg raw-frame pipe). NO Remotion/headless.

A *video* is a list of BEATS. Each beat = one narration line (spoken in Cory's blended voice) + a
parameterized SCENE template + a content dict. A beat's on-screen window == its own spoken duration,
so visuals never get squeezed. This is the reusable foundation for all 5 custom-agent long-form videos.

Public API:
  render_body(beats, out_mp4, voice="blend", cache_dir=...) -> seconds   # animated body only
  assemble_final(intro_mp4, body_mp4, outro_mp4, out_mp4)               # HeyGen intro + body + outro

Scenes (content dict `c` per scene): title, chapter, hook, define, stat, chat, process, cards,
  checklist, compare, learn, secure, calendar, result, quote, cta.
"""
from __future__ import annotations
import importlib.util, math, pathlib, subprocess
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = pathlib.Path("C:/Users/you/Downloads/ServiceTitan Agent platform/video/tbai")
W, H, FPS = 1920, 1080, 30
# Corner-badge wordmark. Default = the OS product (most vid_*.py scripts cover Top Builder OS,
# the field-software+books line). A script whose topic is the AI agent-orchestration line should
# set `ae.WORDMARK = "TOP BUILDER AI"` BEFORE calling render_body() (which rebuilds BG from this).
WORDMARK = "TOP BUILDER OS"
BG_TOP, BG_BOT = (8, 8, 12), (13, 12, 22)
VIOLET, VIOLET_B, CYAN, INK, INK_SOFT, GREEN, RED, AMBER = (
    (99, 102, 241), (139, 147, 255), (52, 211, 153), (244, 240, 255),
    (175, 167, 200), (92, 230, 150), (255, 92, 122), (255, 196, 92))
SERIF = "C:/Windows/Fonts/georgiab.ttf"; SANS = "C:/Windows/Fonts/segoeui.ttf"
SANSB = "C:/Windows/Fonts/segoeuib.ttf"; MONO = "C:/Windows/Fonts/consolab.ttf"
EMOJI = "C:/Windows/Fonts/seguiemj.ttf"
VS_PATH = "C:/Users/you/.claude/skills/cory-voice/references/voice_synth.py"

# ---------- primitives ----------
def F(p, s):
    try: return ImageFont.truetype(p, s)
    except Exception: return ImageFont.load_default()
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def ease_out(p): p = clamp(p); return 1 - (1 - p) ** 3
def ease_in_out(p): p = clamp(p); return 4*p*p*p if p < 0.5 else 1 - (-2*p+2)**3/2
def ease_back(p):
    p = clamp(p); c1 = 1.70158; c3 = c1 + 1
    return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2
def lerp(a, b, p): return a + (b - a) * p

def build_bg():
    img = Image.new("RGB", (1, H))
    for y in range(H):
        k = y / H; img.putpixel((0, y), tuple(int(BG_TOP[c] + (BG_BOT[c] - BG_TOP[c]) * k) for c in range(3)))
    img = img.resize((W, H)).convert("RGBA")
    g = Image.new("RGBA", (W, H), (0, 0, 0, 0)); gd = ImageDraw.Draw(g)
    gd.ellipse([W // 2 - 760, -360, W // 2 + 760, 960], fill=(*VIOLET, 54))
    gd.ellipse([W - 980, H - 620, W + 260, H + 440], fill=(*CYAN, 20))
    img = Image.alpha_composite(img, g.filter(ImageFilter.GaussianBlur(210)))
    d = ImageDraw.Draw(img)
    for gx in range(150, W, 150):
        for gy in range(150, H, 150): d.ellipse([gx - 2, gy - 2, gx + 2, gy + 2], fill=(99, 102, 241, 60))
    d.ellipse([130, 124, 156, 150], fill=VIOLET); d.text((170, 121), WORDMARK, font=F(SANSB, 30), fill=INK)
    return img.convert("RGB")
BG = build_bg()

SPR = {}
def get_sprite(ch, px):
    if (ch, px) not in SPR:
        im = Image.new("RGBA", (int(px * 1.4), int(px * 1.4)), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((im.width // 2, im.height // 2), ch, font=F(EMOJI, px), anchor="mm", embedded_color=True)
        SPR[(ch, px)] = im
    return SPR[(ch, px)]
def paste_sprite(base, ch, px, cx, cy, scale=1.0, angle=0.0, alpha=1.0):
    if scale <= 0 or alpha <= 0: return
    s = get_sprite(ch, px)
    if scale != 1.0: s = s.resize((max(1, int(s.width * scale)), max(1, int(s.height * scale))), Image.LANCZOS)
    if angle: s = s.rotate(angle, expand=True, resample=Image.BICUBIC)
    if alpha < 1.0:
        s = s.copy(); s.putalpha(s.split()[3].point(lambda v: int(v * alpha)))
    base.paste(s, (int(cx - s.width // 2), int(cy - s.height // 2)), s)

def wrap_lines(d, s, font, maxw):
    words, lines, cur = s.split(), [], ""
    for w in words:
        if d.textlength((cur + " " + w).strip(), font=font) < maxw: cur = (cur + " " + w).strip()
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines

def text_block(base, s, font, cx, y, fill, alpha, maxw=1500, anchor="ma", lh_mult=1.18):
    if alpha <= 0: return y
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    lines = wrap_lines(d, s, font, maxw); lh = int(font.size * lh_mult); yy = y
    for ln in lines:
        d.text((cx, yy), ln, font=font, fill=(*fill, int(255 * clamp(alpha))), anchor=anchor); yy += lh
    base.alpha_composite(layer)
    return yy

def soft_glow(base, cx, cy, r, color, alpha):
    g = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(g).ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*color, int(140 * clamp(alpha))))
    base.alpha_composite(g.filter(ImageFilter.GaussianBlur(70)))

def eyebrow(img, text, A, y=120, color=CYAN):
    f = F(SANSB, 26)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    tw = d.textlength(text.upper(), font=f)
    d.line([W // 2 - tw // 2 - 60, y + 16, W // 2 - tw // 2 - 24, y + 16], fill=(*color, int(220 * A)), width=3)
    d.line([W // 2 + tw // 2 + 24, y + 16, W // 2 + tw // 2 + 60, y + 16], fill=(*color, int(220 * A)), width=3)
    d.text((W // 2, y), text.upper(), font=f, fill=(*color, int(235 * A)), anchor="ma")
    img.alpha_composite(layer)

def panel(img, x0, y0, x1, y1, A, fill=(22, 17, 44), border=VIOLET, bw=2, radius=22, ba=150):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    d.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=(*fill, int(238 * A)),
                        outline=(*border, int(ba * A)), width=bw)
    img.alpha_composite(layer)

def bookend_card(eyebrow, title, sub, out_png):
    """Static left-aligned brand title card for HeyGen bookends (presenter composited on the right).
    Matches the intro/outro card style: NEURON HQ logo (baked in BG), cyan tracked eyebrow,
    big serif title (left, wrapped), gray sub, cyan underline. Right ~45% left clear for the avatar."""
    img = BG.copy().convert("RGBA")
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    x = 132
    ef = F(SANSB, 27); ey = 372; cx = x
    for ch in eyebrow.upper():
        d.text((cx, ey), ch, font=ef, fill=(*CYAN, 235))
        cx += d.textlength(ch, font=ef) + (8 if ch != " " else 6)
    tf = F(SERIF, 108); ty = 448
    for ln in wrap_lines(d, title, tf, 800):
        d.text((x, ty), ln, font=tf, fill=(*INK, 255), anchor="la"); ty += int(tf.size * 1.02)
    sf = F(SANS, 40); d.text((x, ty + 20), sub, font=sf, fill=(*INK_SOFT, 235), anchor="la")
    d.rectangle([x, ty + 96, x + 158, ty + 102], fill=(*CYAN, 255))
    img.alpha_composite(layer)
    img.convert("RGB").save(out_png, "PNG")
    return out_png

# ---------- scenes (lt=time within beat, bd=beat duration, A=fade alpha, c=content) ----------
def sc_title(img, lt, bd, A, c):
    if c.get("eyebrow"): eyebrow(img, c["eyebrow"], A * ease_out(lt / 0.4), y=300)
    soft_glow(img, W // 2, 200, 120, VIOLET, A * 0.4)
    y = text_block(img, c.get("title", ""), F(SERIF, 92), W // 2, 380, INK, A * ease_out((lt - 0.15) / 0.5), maxw=1500)
    if c.get("sub"): text_block(img, c["sub"], F(SANS, 40), W // 2, y + 30, INK_SOFT, A * ease_out((lt - 0.45) / 0.5), maxw=1300)

def sc_chapter(img, lt, bd, A, c):
    num = c.get("num", "")
    f = F(MONO, 150)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    d.text((W // 2, 300), num, font=f, fill=(*VIOLET, int(120 * A * ease_back(clamp(lt / 0.5)))), anchor="ma")
    img.alpha_composite(layer)
    text_block(img, c.get("title", ""), F(SERIF, 80), W // 2, 520, INK, A * ease_out((lt - 0.2) / 0.5), maxw=1400)

def sc_hook(img, lt, bd, A, c):
    cx, cy = W // 2, 330
    appear = ease_back(clamp(lt / 0.5))
    if c.get("pulse", True):
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
        for k in range(3):
            ph = (lt * 1.2 - k * 0.33) % 1.0; r = int(120 + ph * 230); al = int(140 * (1 - ph) * A)
            if al > 0: d.arc([cx - r, cy - r, cx + r, cy + r], -42, 42, fill=(*CYAN, al), width=8)
        img.alpha_composite(layer)
    paste_sprite(img, c.get("icon", "\U0001F4DE"), 220, cx, cy, scale=appear, angle=math.sin(lt * 13) * 6, alpha=A)
    y = text_block(img, c.get("title", ""), F(SERIF, 74), W // 2, 540, INK, A * ease_out((lt - 0.2) / 0.4), maxw=1500)
    if c.get("sub"): text_block(img, c["sub"], F(SANS, 38), W // 2, y + 20, INK_SOFT, A * ease_out((lt - 0.5) / 0.4), maxw=1300)

def sc_define(img, lt, bd, A, c):
    if c.get("eyebrow"): eyebrow(img, c["eyebrow"], A * ease_out(lt / 0.4), y=140)
    panel(img, 360, 280, W - 360, 760, A * ease_back(clamp(lt / 0.5)), fill=(20, 15, 40), bw=2, radius=28)
    text_block(img, c.get("term", ""), F(SERIF, 60), W // 2, 340, VIOLET_B, A * ease_out((lt - 0.25) / 0.4), maxw=1100)
    text_block(img, c.get("body", ""), F(SANS, 40), W // 2, 460, INK, A * ease_out((lt - 0.45) / 0.5), maxw=1080, lh_mult=1.3)

def sc_stat(img, lt, bd, A, c):
    val = c.get("value", ""); a = ease_out(clamp(lt / 0.8))
    # count-up for pure-number/percent values
    disp = val
    if val.endswith("%") and val[:-1].isdigit():
        disp = f"{int(int(val[:-1]) * a)}%"
    elif val.replace("x", "").replace("X", "").isdigit():
        disp = val  # leave multipliers static
    soft_glow(img, W // 2, 360, 200, VIOLET, A * 0.45)
    text_block(img, disp, F(SERIF, 220), W // 2, 230, INK, A * ease_out(lt / 0.3))
    y = text_block(img, c.get("label", ""), F(SANSB, 46), W // 2, 560, INK, A * ease_out((lt - 0.3) / 0.4), maxw=1300)
    if c.get("source"): text_block(img, "Source: " + c["source"], F(SANS, 26), W // 2, y + 30, INK_SOFT, A * ease_out((lt - 0.6) / 0.4), maxw=1200)

def sc_chat(img, lt, bd, A, c):
    msgs = c.get("msgs", []); n = max(1, len(msgs))
    step = max(0.55, (bd - 0.8) / n); bf = F(SANS, 34); y0 = 220
    for i, (right, msg) in enumerate(msgs):
        bp = ease_back(clamp((lt - (0.2 + i * step)) / 0.4))
        if bp <= 0: continue
        w = int(bf.getlength(msg)) + 56; h = 76
        x = (W // 2 + 60) if right else (W // 2 - 60 - w)
        x += (1 - bp) * (70 if right else -70)
        col = VIOLET if right else (44, 40, 70)
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
        d.rounded_rectangle([int(x), y0 + i * 104, int(x) + w, y0 + i * 104 + h], radius=26,
                            fill=(*col, int(235 * A * min(1, bp))))
        d.text((int(x) + 28, y0 + i * 104 + h // 2), msg, font=bf, fill=(*INK, int(255 * A * min(1, bp))), anchor="lm")
        img.alpha_composite(layer)
    if c.get("title"): text_block(img, c["title"], F(SERIF, 56), W // 2, y0 + n * 104 + 30, INK, A * ease_out((lt - 0.2) / 0.5))

def sc_process(img, lt, bd, A, c):
    if c.get("title"): text_block(img, c["title"], F(SERIF, 64), W // 2, 130, INK, A * ease_out(lt / 0.4))
    steps = c.get("steps", []); n = max(1, len(steps))
    step_t = max(0.5, (bd - 1.0) / n); y0 = 320; rh = 118
    sf = F(SANS, 40); nf = F(MONO, 40)
    for i, s in enumerate(steps):
        p = ease_back(clamp((lt - (0.3 + i * step_t)) / 0.45))
        if p <= 0: continue
        dx = int((1 - p) * -60); y = y0 + i * rh
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
        d.ellipse([430 + dx, y, 430 + dx + 64, y + 64], fill=(*VIOLET, int(255 * A * p)))
        d.text((430 + dx + 32, y + 32), str(i + 1), font=nf, fill=(*INK, int(255 * A * p)), anchor="mm")
        if i < n - 1:
            d.line([430 + dx + 32, y + 70, 430 + dx + 32, y + rh - 6], fill=(*VIOLET, int(150 * A * p)), width=3)
        d.text((525 + dx, y + 32), s, font=sf, fill=(*INK, int(255 * A * p)), anchor="lm")
        img.alpha_composite(layer)

def sc_cards(img, lt, bd, A, c):
    if c.get("title"): text_block(img, c["title"], F(SERIF, 64), W // 2, 130, INK, A * ease_out(lt / 0.4))
    items = c.get("items", []); cardw, cardh, gx, gy = 600, 168, 40, 38
    x0 = W // 2 - cardw - gx // 2; y0 = 320; bf = F(SANSB, 36)
    for i, it in enumerate(items[:4]):
        ic, label = it[0], it[1]
        bp = ease_back(clamp((lt - (0.3 + i * 0.3)) / 0.4))
        if bp <= 0: continue
        r, col = divmod(i, 2); bx = x0 + col * (cardw + gx); by = y0 + r * (cardh + gy) + int((1 - bp) * 40)
        panel(img, bx, by, bx + cardw, by + cardh, A * min(1, bp), fill=(26, 21, 48), bw=2, ba=150)
        paste_sprite(img, ic, 88, bx + 92, by + cardh // 2, scale=min(1, bp), alpha=A)
        text_block(img, label, bf, bx + 162, by + cardh // 2 - 24, INK, A * min(1, bp), maxw=cardw - 184, anchor="la")

def sc_checklist(img, lt, bd, A, c):
    if c.get("title"): text_block(img, c["title"], F(SERIF, 68), W // 2, 150, INK, A * ease_out(lt / 0.4))
    items = c.get("items", []); n = max(1, len(items)); step = max(0.4, (bd - 1.0) / n)
    lf = F(SANS, 42); y0 = 360
    for i, ln in enumerate(items):
        p = ease_out(clamp((lt - (0.4 + i * step)) / 0.45))
        if p <= 0: continue
        y = y0 + i * 118; dx = int((1 - p) * -50)
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
        paste_sprite(img, "✅", 56, 500 + dx, y + 22, scale=min(1, ease_back(p)), alpha=A)
        d.text((560 + dx, y), ln, font=lf, fill=(*INK, int(255 * A * p)), anchor="la")
        img.alpha_composite(layer)

def sc_compare(img, lt, bd, A, c):
    """3-column authority compare. c: {title, cols:[a,b,c], rows:[(label,[bool,bool,bool]), ...]}"""
    if c.get("title"): text_block(img, c["title"], F(SERIF, 58), W // 2, 100, INK, A * ease_out(lt / 0.4))
    cols = c.get("cols", []); rows = c.get("rows", [])
    tx0, ty0 = 300, 270; labw = 470; cw = (W - 2 * tx0 - labw) // max(1, len(cols)); rh = 92
    hf = F(SANSB, 25); lf = F(SANS, 32)
    appear = ease_out(lt / 0.4)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    for j, col in enumerate(cols):
        cx = tx0 + labw + j * cw + cw // 2
        hi = (j == 0)
        d.rounded_rectangle([cx - cw // 2 + 8, ty0 - 8, cx + cw // 2 - 8, ty0 + 54], radius=14,
                            fill=(*(VIOLET if hi else (40, 36, 64)), int((255 if hi else 180) * A * appear)))
        d.text((cx, ty0 + 24), col, font=hf, fill=(*INK, int(255 * A * appear)), anchor="mm")
    img.alpha_composite(layer)
    for r, (label, marks) in enumerate(rows):
        p = ease_out(clamp((lt - (0.4 + r * 0.28)) / 0.4))
        if p <= 0: continue
        y = ty0 + 80 + r * rh
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
        d.text((tx0 + 10, y + rh // 2), label, font=lf, fill=(*INK, int(255 * A * p)), anchor="lm")
        img.alpha_composite(layer)
        for j, ok in enumerate(marks):
            cx = tx0 + labw + j * cw + cw // 2
            paste_sprite(img, "✅" if ok else "❌", 50, cx, y + rh // 2, scale=min(1, ease_back(p)), alpha=A)

def sc_learn(img, lt, bd, A, c):
    text_block(img, c.get("title", "Designed to learn and adapt"), F(SERIF, 66), W // 2, 64, INK, A * ease_out(lt / 0.4))
    nodes = c.get("steps", ["You correct it once", "A human approves the change", "It remembers — and improves"])
    cx, cy, rad = W // 2, 540, 210
    bf = F(SANSB, 34)
    # circular learning loop with flowing spark
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    ring_a = ease_out(lt / 0.5)
    d.arc([cx - rad, cy - rad, cx + rad, cy + rad], 0, int(360 * ring_a), fill=(*VIOLET, int(170 * A)), width=5)
    img.alpha_composite(layer)
    ang0 = -math.pi / 2
    for i, txt in enumerate(nodes[:3]):
        ang = ang0 + i * (2 * math.pi / 3)
        nx, ny = cx + int(math.cos(ang) * rad), cy + int(math.sin(ang) * rad)
        p = ease_back(clamp((lt - (0.4 + i * 0.45)) / 0.4))
        if p <= 0: continue
        soft_glow(img, nx, ny, 60, VIOLET, A * 0.5 * min(1, p))
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
        d.ellipse([nx - 30, ny - 30, nx + 30, ny + 30], fill=(*VIOLET_B, int(255 * A * min(1, p))))
        img.alpha_composite(layer)
        ty = ny + (70 if math.sin(ang) >= 0 else -90)
        text_block(img, txt, bf, nx, ty, INK, A * min(1, p), maxw=460, anchor="ma")
    # orbiting spark
    sp = (lt * 1.4) % 1.0; sang = ang0 + sp * 2 * math.pi
    sx, sy = cx + int(math.cos(sang) * rad), cy + int(math.sin(sang) * rad)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse([sx - 9, sy - 9, sx + 9, sy + 9], fill=(*CYAN, int(255 * A)))
    img.alpha_composite(layer)

def sc_secure(img, lt, bd, A, c):
    text_block(img, c.get("title", "Safe by design"), F(SERIF, 68), W // 2, 120, INK, A * ease_out(lt / 0.4))
    items = c.get("items", [
        ("\U0001F6E1️", "Guardrails", "It stays in its lane — no off-task actions"),
        ("\U0001F464", "Human in the loop", "Escalates to a person instead of guessing"),
        ("\U0001F512", "Secure", "Your data stays yours — isolated per client")])
    cardw, gap = 460, 50; x0 = W // 2 - (cardw * 3 + gap * 2) // 2; y0 = 330; ch = 430
    tf = F(SANSB, 40); sf = F(SANS, 30)
    for i, (ic, t, s) in enumerate(items[:3]):
        p = ease_back(clamp((lt - (0.3 + i * 0.32)) / 0.45))
        if p <= 0: continue
        bx = x0 + i * (cardw + gap); by = y0 + int((1 - p) * 40)
        panel(img, bx, by, bx + cardw, by + ch, A * min(1, p), fill=(20, 16, 40), border=CYAN, bw=2, ba=130)
        soft_glow(img, bx + cardw // 2, by + 130, 70, CYAN, A * 0.4 * min(1, p))
        paste_sprite(img, ic, 110, bx + cardw // 2, by + 130, scale=min(1, p), alpha=A)
        text_block(img, t, tf, bx + cardw // 2, by + 215, INK, A * min(1, p), maxw=cardw - 50)
        text_block(img, s, sf, bx + cardw // 2, by + 278, INK_SOFT, A * min(1, p), maxw=cardw - 70, lh_mult=1.3)

def sc_calendar(img, lt, bd, A, c):
    a = ease_back(clamp(lt / 0.5)); cw, ch = max(180, int(560 * min(1, a))), max(180, int(430 * min(1, a)))
    cx, cy = W // 2 - cw // 2, 230
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0)); ld = ImageDraw.Draw(layer)
    ld.rounded_rectangle([cx, cy, cx + cw, cy + ch], radius=24, fill=(20, 16, 40, int(245 * A)),
                         outline=(*VIOLET, int(255 * A)), width=3)
    ld.rounded_rectangle([cx, cy, cx + cw, cy + 72], radius=24, fill=(*VIOLET, int(255 * A)))
    ld.rectangle([cx, cy + 40, cx + cw, cy + 72], fill=(*VIOLET, int(255 * A)))
    ld.text((cx + cw // 2, cy + 36), c.get("header", "THIS WEEK"), font=F(MONO, 26), fill=(255, 255, 255, int(255 * A)), anchor="mm")
    gx0, gy0, cwid, chei = cx + 30, cy + 96, (cw - 60) // 5, (ch - 120) // 3
    fillp = ease_out(clamp((lt - 1.0) / 0.8))
    for r in range(3):
        for col in range(5):
            bx, by = gx0 + col * cwid, gy0 + r * chei; booked = (r == 1 and col == 3)
            if booked and fillp > 0:
                cc = tuple(int(lerp(VIOLET[k], GREEN[k], fillp)) for k in range(3))
                ld.rounded_rectangle([bx + 6, by + 6, bx + cwid - 6, by + chei - 6], radius=12, fill=(*cc, int(255 * A)))
            else:
                ld.rounded_rectangle([bx + 6, by + 6, bx + cwid - 6, by + chei - 6], radius=12, fill=(255, 255, 255, int(22 * A)))
    img.alpha_composite(layer)
    if fillp > 0.45:
        paste_sprite(img, "✅", 88, gx0 + 3 * cwid + cwid // 2, gy0 + chei + chei // 2,
                     scale=ease_back(clamp((lt - 1.4) / 0.4)), alpha=A)
    text_block(img, c.get("caption", "Booked on your real calendar"), F(SERIF, 60), W // 2, cy + ch + 28, INK, A * ease_out((lt - 0.3) / 0.4))

def sc_result(img, lt, bd, A, c):
    a = ease_back(clamp(lt / 0.55)); breathe = 1 + 0.03 * math.sin(lt * 4)
    soft_glow(img, W // 2, 320, 210, GREEN, A * 0.5)
    paste_sprite(img, c.get("icon", "✅"), 190, W // 2, 320, scale=a * breathe, alpha=A)
    text_block(img, c.get("title", ""), F(SERIF, 64), W // 2, 540, INK, A * ease_out((lt - 0.3) / 0.4), maxw=1500)

def sc_quote(img, lt, bd, A, c):
    f = F(SERIF, 160)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((W // 2, 240), "“", font=f, fill=(*VIOLET, int(160 * A * ease_out(lt / 0.4))), anchor="ma")
    img.alpha_composite(layer)
    y = text_block(img, c.get("quote", ""), F(SERIF, 52), W // 2, 420, INK, A * ease_out((lt - 0.2) / 0.5), maxw=1300, lh_mult=1.3)
    if c.get("who"): text_block(img, "— " + c["who"], F(SANS, 34), W // 2, y + 30, INK_SOFT, A * ease_out((lt - 0.5) / 0.4))

def sc_cta(img, lt, bd, A, c):
    if c.get("eyebrow"): eyebrow(img, c["eyebrow"], A * ease_out(lt / 0.4), y=240)
    soft_glow(img, W // 2, 200, 130, VIOLET, A * 0.4)
    y = text_block(img, c.get("title", ""), F(SERIF, 78), W // 2, 330, INK, A * ease_out((lt - 0.15) / 0.5), maxw=1400)
    if c.get("sub"): y = text_block(img, c["sub"], F(SANS, 38), W // 2, y + 24, INK_SOFT, A * ease_out((lt - 0.4) / 0.5), maxw=1200)
    url = c.get("url", "neuron-hq.com/ai-agents")
    bp = ease_back(clamp((lt - 0.6) / 0.4)); bw = 620; bx = W // 2 - bw // 2; by = y + 70
    panel(img, bx, by, bx + bw, by + 92, A * min(1, bp), fill=VIOLET, border=VIOLET_B, bw=2, radius=46, ba=255)
    text_block(img, url, F(SANSB, 40), W // 2, by + 24, (255, 255, 255), A * min(1, bp))

# ---------- PREMIUM IMAGE-BACKED SCENES (photoreal humans + motion graphics) ----------
_PHOTO = {}
def _load_big(path, Z=1.16):
    """Cover-fit a generated photo to (W*Z, H*Z) so Ken Burns can crop/zoom within it."""
    key = (path, Z)
    if key not in _PHOTO:
        im = Image.open(path).convert("RGB")
        tw, th = int(W * Z), int(H * Z)
        sc = max(tw / im.width, th / im.height)
        im = im.resize((max(tw, int(im.width * sc)), max(th, int(im.height * sc))), Image.LANCZOS)
        # center-crop to exactly (tw, th)
        ox, oy = (im.width - tw) // 2, (im.height - th) // 2
        _PHOTO[key] = im.crop((ox, oy, ox + tw, oy + th))
    return _PHOTO[key]

def kb_frame(big, p, zoom_in=True, panx=0.5):
    """Ken Burns: crop a moving/zooming (W,H) window from `big` at progress p in [0,1]."""
    Z = big.width / W
    ws = lerp(Z, 1.0, ease_in_out(clamp(p))) if zoom_in else lerp(1.0, Z, ease_in_out(clamp(p)))
    cw, ch = int(W * ws), int(H * ws)
    maxx, maxy = big.width - cw, big.height - ch
    ox = int(maxx * clamp(panx + 0.10 * (p - 0.5)))
    oy = int(maxy * 0.46)
    ox = max(0, min(maxx, ox)); oy = max(0, min(maxy, oy))
    return big.crop((ox, oy, ox + cw, oy + ch)).resize((W, H), Image.LANCZOS).convert("RGBA")

def _scrim(img, top=False, h=420, strength=210):
    """Dark gradient scrim at bottom (or top) so text stays legible over a photo."""
    g = Image.new("L", (1, h))
    for y in range(h):
        k = y / h; g.putpixel((0, y), int(strength * (k if not top else 1 - k)))
    g = g.resize((W, h))
    sc = Image.new("RGBA", (W, h), (5, 4, 14, 0)); sc.putalpha(g)
    img.alpha_composite(sc, (0, H - h if not top else 0))

def _logo(img, A=1.0):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    d.ellipse([130, 124, 156, 150], fill=(*VIOLET, int(255 * A)))
    d.text((170, 121), WORDMARK, font=F(SANSB, 30), fill=(*INK, int(255 * A)))
    img.alpha_composite(layer)

def sc_photo(img, lt, bd, A, c):
    """Full-bleed photoreal image with Ken Burns + bottom scrim + lower-third caption."""
    big = _load_big(c["photo"], c.get("zoom", 1.16))
    frame = kb_frame(big, clamp(lt / max(bd, 0.1)), zoom_in=c.get("zoom_in", True), panx=c.get("panx", 0.5))
    if A < 1.0:
        frame = frame.copy(); frame.putalpha(frame.split()[3].point(lambda v: int(v * A)))
    img.alpha_composite(frame); _scrim(img, h=460, strength=215); _logo(img, A)
    x = 132; y = H - 320
    if c.get("eyebrow"):
        ef = F(SANSB, 27); cx = x
        for ch in c["eyebrow"].upper():
            ImageDraw.Draw(img).text((cx, y), ch, font=ef, fill=(*CYAN, int(235 * A)))
            cx += ImageDraw.Draw(img).textlength(ch, font=ef) + (8 if ch != " " else 6)
        y += 50
    if c.get("title"):
        y = text_block(img, c["title"], F(SERIF, 78), x, y, INK, A * ease_out((lt - 0.1) / 0.5), maxw=1400, anchor="la")
    if c.get("sub"):
        text_block(img, c["sub"], F(SANS, 38), x, y + 14, INK_SOFT, A * ease_out((lt - 0.3) / 0.5), maxw=1300, anchor="la")

def sc_split_photo(img, lt, bd, A, c):
    """Text on the left, photoreal image inset (rounded, Ken Burns, cover-fit) on the right."""
    big = _load_big(c["photo"], 1.14)
    frame = kb_frame(big, clamp(lt / max(bd, 0.1)), zoom_in=c.get("zoom_in", True))
    iw, ih = 760, 860; ix, iy = W - iw - 120, 110
    fw, fh = frame.width, frame.height
    sc = max(iw / fw, ih / fh)
    inset = frame.resize((max(iw, int(fw * sc)), max(ih, int(fh * sc))), Image.LANCZOS)
    ox, oy = (inset.width - iw) // 2, int((inset.height - ih) * 0.42)
    crop = inset.crop((ox, oy, ox + iw, oy + ih))
    mask = Image.new("L", (iw, ih), 0); ImageDraw.Draw(mask).rounded_rectangle([0, 0, iw, ih], radius=28, fill=int(255 * A))
    img.paste(crop, (ix, iy), mask)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle([ix, iy, ix + iw, iy + ih], radius=28, outline=(*VIOLET, int(150 * A)), width=2)
    img.alpha_composite(layer)
    tx = 132; y = 300
    if c.get("eyebrow"):
        ef = F(SANSB, 27); cx = tx; ea = A * ease_out(lt / 0.4)
        for ch in c["eyebrow"].upper():
            ImageDraw.Draw(img).text((cx, y), ch, font=ef, fill=(*CYAN, int(235 * ea)))
            cx += ImageDraw.Draw(img).textlength(ch, font=ef) + (8 if ch != " " else 6)
        y += 56
    y = text_block(img, c.get("title", ""), F(SERIF, 70), tx, y, INK, A * ease_out((lt - 0.15) / 0.5), maxw=720, anchor="la")
    if c.get("sub"): text_block(img, c["sub"], F(SANS, 38), tx, y + 24, INK_SOFT, A * ease_out((lt - 0.4) / 0.5), maxw=700, anchor="la", lh_mult=1.34)

def _card_incoming(img, lt, A, label, sub, accent=CYAN):
    """A sliding-in 'incoming call / new lead' card with pulsing ring — top-center over a photo."""
    p = ease_back(clamp(lt / 0.5)); cw, ch = 720, 150
    cx = W // 2 - cw // 2; cy = 90 - int((1 - p) * 80)
    panel(img, cx, cy, cx + cw, cy + ch, A * min(1, p), fill=(16, 12, 32), border=accent, bw=2, radius=20, ba=200)
    ring = 50 + 14 * math.sin(lt * 6)
    soft_glow(img, cx + 86, cy + ch // 2, int(ring), accent, A * 0.5)
    paste_sprite(img, "\U0001F4DE", 70, cx + 86, cy + ch // 2, scale=min(1, p), alpha=A)
    text_block(img, label, F(SANSB, 40), cx + 170, cy + 34, INK, A * min(1, p), maxw=cw - 200, anchor="la")
    text_block(img, sub, F(SANS, 28), cx + 170, cy + 86, INK_SOFT, A * min(1, p), maxw=cw - 200, anchor="la")

def _card_booked(img, lt, A, text):
    p = ease_back(clamp((lt) / 0.5))
    soft_glow(img, W // 2, 250, 110, GREEN, A * 0.45 * min(1, p))
    paste_sprite(img, "✅", 130, W // 2, 250, scale=min(1, p), alpha=A)
    text_block(img, text, F(SERIF, 66), W // 2, 360, INK, A * ease_out((lt - 0.25) / 0.4), maxw=1400)

def _chips(img, lt, A, msgs):
    """Reply chat bubbles appearing bottom-right over a photo (the agent answering)."""
    bf = F(SANS, 32); y0 = H - 300
    for i, (right, m) in enumerate(msgs):
        bp = ease_back(clamp((lt - (0.2 + i * 0.6)) / 0.4))
        if bp <= 0: continue
        w = int(bf.getlength(m)) + 48; h = 66
        x = W - 130 - w if right else 130
        col = VIOLET if right else (44, 40, 70)
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
        d.rounded_rectangle([x, y0 + i * 84, x + w, y0 + i * 84 + h], radius=22, fill=(*col, int(240 * A * min(1, bp))))
        d.text((x + 24, y0 + i * 84 + h // 2), m, font=bf, fill=(*INK, int(255 * A * min(1, bp))), anchor="lm")
        img.alpha_composite(layer)

def sc_photo_overlay(img, lt, bd, A, c):
    """Photoreal image (Ken Burns) + one motion-graphic overlay that SHOWS the action."""
    big = _load_big(c["photo"], c.get("zoom", 1.14))
    frame = kb_frame(big, clamp(lt / max(bd, 0.1)), zoom_in=c.get("zoom_in", True), panx=c.get("panx", 0.5))
    if A < 1.0:
        frame = frame.copy(); frame.putalpha(frame.split()[3].point(lambda v: int(v * A)))
    img.alpha_composite(frame); _logo(img, A)
    kind = c.get("overlay")
    if kind == "incoming": _scrim(img, top=True, h=320, strength=180); _card_incoming(img, lt, A, c.get("label", "Incoming call"), c.get("sub", ""))
    elif kind == "booked": _scrim(img, h=420, strength=150); _card_booked(img, lt, A, c.get("title", ""))
    elif kind == "reply": _scrim(img, h=380, strength=150); _chips(img, lt, A, c.get("msgs", []))
    if kind in (None, "caption") or c.get("caption"):
        _scrim(img, h=300, strength=170)
        text_block(img, c.get("caption", c.get("title", "")), F(SERIF, 66), 132, H - 210, INK, A * ease_out((lt - 0.1) / 0.4), maxw=1500, anchor="la")

def sc_before_after(img, lt, bd, A, c):
    """Two photoreal images with a sweeping wipe + BEFORE/AFTER labels (the transformation)."""
    bigB = _load_big(c["before"], 1.12); bigA = _load_big(c["after"], 1.12)
    fB = kb_frame(bigB, clamp(lt / max(bd, 0.1)), zoom_in=False); fA = kb_frame(bigA, clamp(lt / max(bd, 0.1)), zoom_in=True)
    img.alpha_composite(fB)
    wipe = ease_in_out(clamp((lt - 0.6) / (max(bd, 0.1) * 0.5)))  # reveal "after" from the right
    sx = int(W * (1 - wipe))
    if sx < W:
        img.alpha_composite(fA.crop((sx, 0, W, H)), (sx, 0))
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(layer).rectangle([sx, 0, sx + 5, H], fill=(*CYAN, int(220 * A)))
        img.alpha_composite(layer)
    _scrim(img, top=True, h=200, strength=170); _logo(img, A)
    # labels
    lb = ease_out(clamp(lt / 0.4))
    def tag(txt, x, col):
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
        tw = d.textlength(txt, font=F(SANSB, 30))
        d.rounded_rectangle([x, 70, x + tw + 44, 124], radius=14, fill=(*col, int(235 * A * lb)))
        d.text((x + 22, 97), txt, font=F(SANSB, 30), fill=(255, 255, 255, int(255 * A * lb)), anchor="lm")
        img.alpha_composite(layer)
    tag(c.get("before_label", "BEFORE"), 150, (120, 60, 70) if wipe < 0.9 else (60, 50, 70))
    if wipe > 0.15: tag(c.get("after_label", "AFTER NEURON"), W - 360, (70, 120, 92))
    if c.get("caption"):
        _scrim(img, h=240, strength=180)
        text_block(img, c["caption"], F(SERIF, 60), W // 2, H - 170, INK, A * ease_out((lt - 0.3) / 0.4), maxw=1500)

SCENES = {
    "title": sc_title, "chapter": sc_chapter, "hook": sc_hook, "define": sc_define, "stat": sc_stat,
    "chat": sc_chat, "process": sc_process, "cards": sc_cards, "checklist": sc_checklist,
    "compare": sc_compare, "learn": sc_learn, "secure": sc_secure, "calendar": sc_calendar,
    "result": sc_result, "quote": sc_quote, "cta": sc_cta,
    "photo": sc_photo, "split_photo": sc_split_photo, "photo_overlay": sc_photo_overlay, "before_after": sc_before_after,
}

# ---------- driver ----------
def beat_alpha(lt, bd):
    return clamp(min(ease_out(lt / 0.3), ease_out((bd - lt) / 0.35)))

def ffprobe_dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout.strip())

def _load_vs():
    spec = importlib.util.spec_from_file_location("vs", VS_PATH)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def render_body(beats, out_mp4, cache_dir, voice="blend"):
    """Render the animated body. beats: [{vo, scene, c}]. Caches per-beat VO by index in cache_dir."""
    global BG
    BG = build_bg()  # rebuild in case the caller set WORDMARK after module load
    cache_dir = pathlib.Path(cache_dir); cache_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = pathlib.Path(out_mp4).resolve()
    vs = _load_vs()
    acc, audios = 0.0, []
    for i, b in enumerate(beats):
        mp3 = cache_dir / f"beat_{i:03d}.mp3"
        if not (mp3.exists() and mp3.stat().st_size > 1000):
            print(f"synth {i:03d} [{b['scene']}]: {b['vo'][:54]}...")
            getattr(vs, voice)(b["vo"], mp3)
        d = ffprobe_dur(mp3) + 0.45
        b["dur"] = d; b["start"] = acc; acc += d; audios.append(mp3)
        print(f"  {i:03d} {b['scene']:10s} {d:5.2f}s  @{b['start']:6.2f}")
    total = acc
    sil = cache_dir / "_sil45.mp3"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-t", "0.45", "-i", "anullsrc=r=44100:cl=stereo", str(sil)], check=True)
    lst = cache_dir / "_alist.txt"
    with open(lst, "w", encoding="utf-8") as f:
        for a in audios: f.write(f"file '{a.as_posix()}'\nfile '{sil.as_posix()}'\n")
    full = cache_dir / "_audio.mp3"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(full)], check=True)
    nframes = int(total * FPS)
    print(f"total {total:.1f}s -> {nframes} frames -> {out_mp4.name}")
    ff = subprocess.Popen(["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                           "-i", "-", "-i", str(full), "-map", "0:v", "-map", "1:a", "-c:v", "libx264",
                           "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                           "-shortest", str(out_mp4)], stdin=subprocess.PIPE)
    for fi in range(nframes):
        t = fi / FPS; bi = 0
        for j, b in enumerate(beats):
            if t >= b["start"]: bi = j
        b = beats[bi]; lt = t - b["start"]; A = beat_alpha(lt, b["dur"])
        img = BG.copy().convert("RGBA")
        SCENES[b["scene"]](img, lt, b["dur"], A, b.get("c", {}))
        ff.stdin.write(img.convert("RGB").tobytes())
    ff.stdin.close(); ff.wait()
    print("WROTE", out_mp4, f"({ffprobe_dur(out_mp4):.1f}s)")
    return total

def assemble_final(intro_mp4, body_mp4, outro_mp4, out_mp4, body_tail_trim=0.4, cooldown=1.6):
    """Normalize each clip to 1920x1080/30fps/sar1 and concat intro+body+outro. TWO finish fixes
    (lesson, 2026-06-18): (1) trim ~`body_tail_trim`s of trailing dead air off the BODY so the outro
    follows the last spoken word tightly instead of after a silent gap + hard cut that reads as "AI";
    (2) hold the final frame `cooldown`s with trailing silence — a breath after the last word so the
    video doesn't slam shut. Set either to 0 to disable."""
    out_mp4 = pathlib.Path(out_mp4).resolve()
    clips = [p for p in [intro_mp4, body_mp4, outro_mp4] if p]
    inputs = []
    for p in clips: inputs += ["-i", str(pathlib.Path(p).resolve())]
    n = len(clips)
    body_idx = 1 if (intro_mp4 and body_mp4) else (0 if body_mp4 else None)
    NORM = ("scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30")
    fc = ""
    for k in range(n):
        if k == body_idx and body_tail_trim > 0:
            bt = max(0.1, ffprobe_dur(clips[k]) - body_tail_trim)
            fc += f"[{k}:v]{NORM},trim=end={bt:.3f},setpts=PTS-STARTPTS[v{k}];"
            fc += f"[{k}:a]atrim=end={bt:.3f},asetpts=PTS-STARTPTS[a{k}];"
        else:
            fc += f"[{k}:v]{NORM}[v{k}];"
            fc += f"[{k}:a]anull[a{k}];"
    fc += "".join(f"[v{k}][a{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=1[cv][ca];"
    if cooldown > 0:
        fc += f"[cv]tpad=stop_mode=clone:stop_duration={cooldown}[v];[ca]apad=pad_dur={cooldown}[a]"
    else:
        fc += "[cv]null[v];[ca]anull[a]"
    subprocess.run(["ffmpeg", "-y", *inputs, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", str(out_mp4)], check=True)
    print("ASSEMBLED", out_mp4, f"({ffprobe_dur(out_mp4):.1f}s)")
    return ffprobe_dur(out_mp4)
