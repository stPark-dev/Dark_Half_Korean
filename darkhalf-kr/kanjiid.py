#!/usr/bin/env python3
"""한자 뱅크 글리프 식별 — 시각 템플릿 매칭 + 문맥 수집 워크시트 생성.

ROM 폰트는 16x16 전용으로 손으로 그린 비트맵이라 TrueType 축소와 성질이 다르다.
그래서 단일 렌더 방식으로는 top-1 이 60% 대에 머문다. 두 가지 렌더러를 앙상블한다.

  aa-Bold     : 안티에일리어싱 후 임계값. 획이 굵어 ROM 폰트 밀도에 가깝다.
  supersample : 4배 렌더 후 max-pool. 얇은 획이 사라지지 않아 복잡한 한자에 강하다.

측정 결과 (정답 라벨 53자, 후보 풀 1546자):
  aa thr100 Bold        top1 83.0%  top3 92.5%  top8 92.5%  top30 98.1%
  supersample maxpool   top1 79.2%  top3 86.8%  top8 98.1%  top30 98.1%
  (기준: aa thr100 Regular  top1 66.0%  top3 79.2%)

매처의 역할은 '정답을 맞히는 것'이 아니라 '후보를 30개로 좁히는 것'이다.
최종 확정은 문맥(주변 가나는 전부 해독됨)으로 하고, 확정 후에는
verify 로 렌더 역검증한다.
"""
import sys, os, json, functools
import numpy as np
from PIL import Image, ImageDraw, ImageFont

SINGLE_BASE = 0x2F0000
BANKS = {0xF5: 0x2F4000, 0xF6: 0x2F8000, 0xF7: 0x2FC000}
NOTO = "/usr/share/fonts/opentype/noto/NotoSansCJK-%s.ttc"

# ---------- ROM 글리프 ----------

def glyph_rows(rom, o):
    """64바이트 글리프 -> 16행 × 16비트 (bit15 = 왼쪽). dumpfont.py 와 동일."""
    rows = []
    for half in (0, 1):
        for r in range(8):
            l  = rom[o+(half*2)*16   + r*2] | rom[o+(half*2)*16   + r*2+1]
            rr = rom[o+(half*2+1)*16 + r*2] | rom[o+(half*2+1)*16 + r*2+1]
            rows.append((l << 8) | rr)
    return rows

def rows_to_arr(rows):
    a = np.zeros((16, 16), np.uint8)
    for y, v in enumerate(rows):
        for x in range(16):
            if (v >> (15-x)) & 1: a[y, x] = 1
    return a

def rom_glyph(rom, bank, idx):
    base = SINGLE_BASE if bank is None else BANKS[bank]
    return rows_to_arr(glyph_rows(rom, base + idx*64))

# ---------- 후보 문자 집합 ----------

def _sjis(his):
    out = []
    for hi in his:
        for lo in list(range(0x40, 0x7F)) + list(range(0x80, 0xFD)):
            try: ch = bytes([hi, lo]).decode('shift_jis')
            except UnicodeDecodeError: continue
            if len(ch) == 1: out.append(ch)
    return out

def jis_kanji():
    return [c for c in _sjis(list(range(0x88, 0xA0)) + list(range(0xE0, 0xF0)))
            if '一' <= c <= '鿿']

def jis_kana_sym():
    """가나·기호도 후보에 넣는다 (뱅크에 한자만 있다고 단정하지 않기 위해)."""
    return [c for c in _sjis(range(0x81, 0x88)) if not c.isspace()]

def candidates():
    return jis_kanji() + jis_kana_sym()

# ---------- 렌더러 ----------

@functools.lru_cache(maxsize=None)
def _f(weight, size):
    return ImageFont.truetype(NOTO % weight, size, index=0)   # index 0 = CJK JP

def _place(f, ch, box, dx, dy):
    bb = f.getbbox(ch)
    return ((box - (bb[2]-bb[0]))//2 - bb[0] + dx,
            (box - (bb[3]-bb[1]))//2 - bb[1] + dy)

def render_aa(ch, size, dx, dy, weight="Bold", thr=100):
    im = Image.new("L", (16, 16), 0)
    f = _f(weight, size)
    ImageDraw.Draw(im).text(_place(f, ch, 16, dx, dy), ch, fill=255, font=f)
    return (np.asarray(im) >= thr).astype(np.uint8)

def render_ss(ch, size, dx, dy, weight="Regular", S=4):
    """4배 해상도로 렌더한 뒤 max-pool. 얇은 획이 살아남는다."""
    f = _f(weight, size*S)
    im = Image.new("L", (16*S, 16*S), 0)
    ImageDraw.Draw(im).text(_place(f, ch, 16*S, dx*S, dy*S), ch, fill=255, font=f)
    a = (np.asarray(im) >= 128).astype(np.uint8)
    return a.reshape(16, S, 16, S).max(axis=(1, 3))

OFFSETS = ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1))
SIZES   = (15, 16, 17)
RENDERERS = (render_aa, render_ss)

def build_templates(chars, cache=None):
    """(문자수 × 변형수, 256) float32 + 소유 문자 인덱스"""
    if cache and os.path.exists(cache):
        z = np.load(cache, allow_pickle=True)
        if len(z["chars"]) == len(chars):
            return z["mat"].astype(np.float32), z["owner"]
    nv = len(RENDERERS) * len(SIZES) * len(OFFSETS)
    mat = np.zeros((len(chars)*nv, 256), np.float32)
    owner = np.zeros(len(chars)*nv, np.int32)
    k = 0
    for ci, ch in enumerate(chars):
        for fn in RENDERERS:
            for s in SIZES:
                for dx, dy in OFFSETS:
                    try: mat[k] = fn(ch, s, dx, dy).reshape(-1)
                    except Exception: pass
                    owner[k] = ci; k += 1
        if cache and ci % 1000 == 0:
            print(f"  템플릿 {ci}/{len(chars)}", flush=True)
    if cache:
        np.savez(cache, mat=mat.astype(np.uint8), owner=owner, chars=np.array(chars))
    return mat, owner

# ---------- 매칭 ----------

def rank(glyphs, mat, owner, chars, n=30, chunk=48):
    """glyphs: (M,256) float32. 반환: M개의 [(문자, IoU), ...] top-n"""
    tsum = mat.sum(1)
    res = []
    for a in range(0, len(glyphs), chunk):
        G = glyphs[a:a+chunk]                       # (c,256)
        inter = mat @ G.T                           # (T,c)  BLAS
        union = tsum[:, None] + G.sum(1)[None, :] - inter
        iou = inter / np.maximum(union, 1e-6)
        for j in range(G.shape[0]):
            best = np.full(len(chars), -1.0, np.float32)
            np.maximum.at(best, owner, iou[:, j])
            order = np.argpartition(-best, n)[:n]
            order = order[np.argsort(-best[order])]
            res.append([(chars[i], round(float(best[i]), 3)) for i in order])
    return res

# ---------- 명령 ----------

CACHE = os.environ.get("DH_TPL_CACHE")

def cmd_selftest(rom_path):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from kanji import KANJI
    rom = open(rom_path, 'rb').read()
    chars = candidates()
    print(f"후보 {len(chars)}자, 템플릿 {len(chars)*len(RENDERERS)*len(SIZES)*len(OFFSETS)}개", flush=True)
    mat, owner = build_templates(chars, cache=CACHE)
    keys = sorted(KANJI)
    G = np.stack([rom_glyph(rom, b, i).reshape(-1) for b, i in keys]).astype(np.float32)
    out = rank(G, mat, owner, chars, n=30)
    hits = {1: 0, 3: 0, 8: 0, 30: 0}
    miss = []
    for (b, i), cand in zip(keys, out):
        truth = KANJI[(b, i)]
        names = [c for c, _ in cand]
        for k in hits:
            if truth in names[:k]: hits[k] += 1
        if truth not in names[:8]:
            miss.append((f"{b:02X}{i:02X}", truth, names[:4]))
    t = len(keys)
    print(f"\n정답 라벨 {t}자 / 후보 풀 {len(chars)}자")
    for k in (1, 3, 8, 30):
        print(f"  top-{k:<2}: {hits[k]}/{t} = {hits[k]/t*100:.1f}%")
    if miss:
        print(f"\ntop-8 실패 {len(miss)}건 (문맥으로 판정해야 하는 몫):")
        for c, tr, got in miss: print(f"  {c} 정답 {tr} / 후보 {' '.join(got)}")

def cmd_worksheet(rom_path, out):
    """식별 워크시트: 코드별 [출현수, 문맥, 시각후보 top-30]"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import kanjictx
    from kanji import KANJI
    rom = open(rom_path, 'rb').read()
    ctx, _ = kanjictx.collect(rom_path)
    keys = sorted(ctx, key=lambda k: -len(ctx[k]))
    chars = candidates()
    print(f"코드 {len(keys)}개 / 후보 {len(chars)}자", flush=True)
    mat, owner = build_templates(chars, cache=CACHE)
    G = np.stack([rom_glyph(rom, b, i).reshape(-1) for b, i in keys]).astype(np.float32)
    cands = rank(G, mat, owner, chars, n=30)
    data = {}
    for (b, i), cand in zip(keys, cands):
        data[f"{b:02X}{i:02X}"] = {
            "n": len(ctx[(b, i)]),
            "known": KANJI.get((b, i)),
            "cand": [c for c, _ in cand],
            "score": [s for _, s in cand],
            "ctx": ctx[(b, i)][:10],
        }
    json.dump(data, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f"워크시트 -> {out}")

if __name__ == "__main__":
    c = sys.argv[1]
    if   c == "selftest":  cmd_selftest(sys.argv[2])
    elif c == "worksheet": cmd_worksheet(sys.argv[2], sys.argv[3])
