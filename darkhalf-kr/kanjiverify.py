#!/usr/bin/env python3
"""식별 결과 역검증.

확정한 매핑에 대해 ROM 글리프와 렌더 글리프의 IoU 를 계산한다.
오식별이면 IoU 가 낮게 나오므로 자동으로 색출된다.
side-by-side 시트도 만들어 눈으로 일괄 확인할 수 있게 한다.

usage:
  kanjiverify.py check <rom> [mapping.json]     IoU 계산 + 하위 목록
  kanjiverify.py sheet  <rom> <out.png> [mapping.json]
"""
import sys, os, json
import numpy as np
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kanjiid as K

def load_map(path=None):
    """{(bank, idx): 문자}"""
    if path:
        d = json.load(open(path, encoding='utf-8'))
        return {(int(k[:2], 16), int(k[2:], 16)): v for k, v in d.items() if v}
    from kanji import KANJI
    return dict(KANJI)

def best_render(ch):
    """모든 변형 중 최고 IoU 를 낼 후보 비트맵들"""
    out = []
    for fn in K.RENDERERS:
        for s in K.SIZES:
            for dx, dy in K.OFFSETS:
                try: out.append(fn(ch, s, dx, dy))
                except Exception: pass
    return out

def iou(a, b):
    a = a.astype(bool); b = b.astype(bool)
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 0.0

def score_all(rom, mapping):
    res = []
    for (bank, idx), ch in sorted(mapping.items()):
        g = K.rom_glyph(rom, bank, idx)
        cands = best_render(ch)
        if not cands:
            res.append((bank, idx, ch, 0.0, None)); continue
        vals = [iou(g, c) for c in cands]
        k = int(np.argmax(vals))
        res.append((bank, idx, ch, vals[k], cands[k]))
    return res

def cmd_check(rom_path, mpath=None):
    rom = open(rom_path, 'rb').read()
    mapping = load_map(mpath)
    res = score_all(rom, mapping)
    v = np.array([r[3] for r in res])
    print(f"매핑 {len(res)}개  IoU 평균 {v.mean():.3f}  중앙값 {np.median(v):.3f}")
    for lo, hi, tag in ((0.0, 0.30, "매우 낮음 (오식별 의심)"),
                        (0.30, 0.45, "낮음 (확인 필요)"),
                        (0.45, 0.60, "보통"),
                        (0.60, 1.01, "높음")):
        n = int(((v >= lo) & (v < hi)).sum())
        print(f"  IoU {lo:.2f}-{hi:.2f} {tag:24s} {n:4d}개")
    bad = sorted([r for r in res if r[3] < 0.45], key=lambda r: r[3])
    if bad:
        print(f"\nIoU 0.45 미만 {len(bad)}개:")
        for b, i, ch, s, _ in bad:
            print(f"  {b:02X}{i:02X} {ch}  IoU {s:.3f}")

def cmd_sheet(rom_path, out, mpath=None, cols=8, scale=3):
    """ROM 글리프 | 렌더 글리프 를 나란히 놓은 확인 시트"""
    rom = open(rom_path, 'rb').read()
    res = score_all(rom, load_map(mpath))
    try:
        lab = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 13, index=0)
    except Exception:
        lab = ImageFont.load_default()
    cw, ch_ = 16*scale, 16*scale
    cellw, cellh = cw*2 + 10 + 62, ch_ + 16
    rows = (len(res) + cols - 1)//cols
    img = Image.new("RGB", (cols*cellw + 8, rows*cellh + 8), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for n, (bank, idx, c, s, rend) in enumerate(res):
        gy, gx = divmod(n, cols)
        ox, oy = 4 + gx*cellw, 4 + gy*cellh
        g = K.rom_glyph(rom, bank, idx)
        for y in range(16):
            for x in range(16):
                if g[y, x]:
                    d.rectangle([ox+x*scale, oy+y*scale, ox+x*scale+scale-1, oy+y*scale+scale-1],
                                fill=(0, 0, 0))
                if rend is not None and rend[y, x]:
                    bx = ox + cw + 6
                    d.rectangle([bx+x*scale, oy+y*scale, bx+x*scale+scale-1, oy+y*scale+scale-1],
                                fill=(190, 30, 30))
        tx = ox + cw*2 + 12
        col = (0, 130, 0) if s >= 0.45 else (200, 0, 0)
        d.text((tx, oy),      f"{bank:02X}{idx:02X}", fill=(60, 60, 60), font=lab)
        d.text((tx, oy+15),   c,                      fill=(0, 0, 0),    font=lab)
        d.text((tx, oy+31),   f"{s:.2f}",             fill=col,          font=lab)
    img.save(out)
    print(f"확인 시트 {len(res)}개 -> {out} ({img.width}x{img.height})  검정=ROM 빨강=렌더")

if __name__ == "__main__":
    c = sys.argv[1]
    if   c == "check": cmd_check(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif c == "sheet": cmd_sheet(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
