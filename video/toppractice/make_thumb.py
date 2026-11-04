"""Compose an on-brand SALISBURY CFO thumbnail (1280x720): navy bg + relevant photo (right,
cover-fit, scrim) + "SALISBURY CFO" wordmark + gold kicker + bold serif title that AUTO-FITS the left
column (wrap + shrink) so it can never run over the photo or off the canvas. Returns a layout report.
Cloned from video/tbai/make_thumb.py, re-themed navy/gold.
Usage: from make_thumb import build; build(photo, "KICKER", "Full title string", out_jpg)"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1280, 720
BG_TOP, BG_BOT = (24, 34, 49), (15, 22, 33)
NAVY, GOLD, GOLD_SOFT, TEAL, INK, INK2 = (
    (46, 64, 87), (185, 143, 66), (241, 216, 136), (7, 102, 122), (253, 249, 243), (196, 188, 174))
SERIF = "C:/Windows/Fonts/georgiab.ttf"; SANSB = "C:/Windows/Fonts/segoeuib.ttf"

PW, PH = 588, 556
PX, PY = W - PW - 52, (H - PH) // 2
TX = 64
TEXT_MAXW = PX - TX - 34


def F(p, s):
    try: return ImageFont.truetype(p, s)
    except Exception: return ImageFont.load_default()


def _bg():
    col = Image.new("RGB", (1, H))
    for y in range(H):
        k = y / H
        col.putpixel((0, y), tuple(int(BG_TOP[c] + (BG_BOT[c] - BG_TOP[c]) * k) for c in range(3)))
    img = col.resize((W, H)).convert("RGBA")
    g = Image.new("RGBA", (W, H), (0, 0, 0, 0)); gd = ImageDraw.Draw(g)
    gd.ellipse([-300, -360, 720, 560], fill=(*GOLD, 44))
    gd.ellipse([W - 560, H - 360, W + 320, H + 300], fill=(*TEAL, 26))
    img = Image.alpha_composite(img, g.filter(ImageFilter.GaussianBlur(200)))
    d = ImageDraw.Draw(img)
    for gx in range(120, W, 130):
        for gy in range(120, H, 130):
            d.ellipse([gx - 2, gy - 2, gx + 2, gy + 2], fill=(*GOLD, 42))
    return img


def _cover(photo, bw, bh):
    im = Image.open(photo).convert("RGB"); iw, ih = im.size
    s = max(bw / iw, bh / ih); im = im.resize((int(iw * s), int(ih * s)))
    x = (im.width - bw) // 2; y = (im.height - bh) // 2
    return im.crop((x, y, x + bw, y + bh))


def _fit_title(draw, title, maxw, top, bottom, start=66, lo=32):
    words = title.split()
    for size in range(start, lo - 1, -3):
        f = F(SERIF, size); lines, cur, ok = [], "", True
        for w in words:
            t = (cur + " " + w).strip()
            if draw.textlength(t, font=f) <= maxw:
                cur = t
            else:
                if cur:
                    lines.append(cur)
                if draw.textlength(w, font=f) > maxw:
                    ok = False; break
                cur = w
        if cur:
            lines.append(cur)
        lh = int(size * 1.16)
        if ok and top + lh * len(lines) <= bottom:
            return f, lines, lh
    f = F(SERIF, lo)
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        cur = t if draw.textlength(t, font=f) <= maxw else (lines.append(cur) or w) if cur else w
    if cur: lines.append(cur)
    return f, lines, int(lo * 1.16)


def build(photo, kicker, title, out_jpg):
    if isinstance(title, (list, tuple)):
        title = " ".join(title)
    img = _bg(); d = ImageDraw.Draw(img)
    photo_im = _cover(photo, PW, PH)
    mask = Image.new("L", (PW, PH), 0); ImageDraw.Draw(mask).rounded_rectangle([0, 0, PW, PH], radius=26, fill=255)
    img.paste(photo_im, (PX, PY), mask)
    sc = Image.new("RGBA", (PW, PH), (0, 0, 0, 0)); scd = ImageDraw.Draw(sc)
    for x in range(PW):
        scd.line([(x, 0), (x, PH)], fill=(15, 22, 33, int(200 * max(0.0, 1 - x / (PW * 0.5)))))
    img.paste(sc, (PX, PY), Image.composite(sc.split()[3], Image.new("L", (PW, PH), 0), mask))
    d.rounded_rectangle([PX, PY, PX + PW, PY + PH], radius=26, outline=(*GOLD, 130), width=2)
    # wordmark: gold crest + "TOP PRACTICE CFO" in serif
    d.rounded_rectangle([60, 60, 90, 90], radius=8, fill=GOLD)
    d.text((104, 60), "TOP PRACTICE CFO", font=F(SERIF, 30), fill=INK)
    # kicker (gold, tracked, clamped to the column)
    kf = F(SANSB, 23); kx, ky = TX, 250
    for ch in kicker.upper():
        if kx + d.textlength(ch, font=kf) > TX + TEXT_MAXW: break
        d.text((kx, ky), ch, font=kf, fill=GOLD); kx += d.textlength(ch, font=kf) + 6
    # title (auto-fit)
    f, lines, lh = _fit_title(d, title, TEXT_MAXW, 300, 632)
    ty = 300
    for ln in lines:
        d.text((TX, ty), ln, font=f, fill=INK); ty += lh
    d.rounded_rectangle([TX + 2, ty + 14, TX + 2 + 220, ty + 22], radius=4, fill=GOLD)
    d.rounded_rectangle([TX + 2 + 230, ty + 14, TX + 2 + 300, ty + 22], radius=4, fill=TEAL)
    img.convert("RGB").save(out_jpg, quality=92)
    widest = max((d.textlength(ln, font=f) for ln in lines), default=0)
    report = {"out": out_jpg, "lines": lines, "font_px": f.size, "widest_px": int(widest),
              "maxw": TEXT_MAXW, "fits": widest <= TEXT_MAXW and ty + 22 <= H - 24}
    print("THUMB", out_jpg, "| lines:", lines, "| fits:", report["fits"])
    return report
