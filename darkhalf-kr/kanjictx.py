#!/usr/bin/env python3
"""미식별 한자 코드의 출현 문맥 수집.

주변 가나는 전부 해독돼 있으므로, 같은 코드가 나타나는 문맥들을 모으면
어떤 한자인지 문맥으로 좁혀진다. 시각 매칭의 후보 목록과 교차하면
후보가 사실상 하나로 결정된다.
"""
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dump import load_tbl, decode, DAKU

TBL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "darkhalf.tbl")
REGIONS = [(0x040C00, 0x050000), (0x05B000, 0x05B800), (0x05BC00, 0x05C400)]

def tokens(seg):
    """바이트열 -> 토큰 리스트. 한자는 ('K',bank,idx) 또는 ('S',code)"""
    out = []; i = 0
    while i < len(seg):
        x = seg[i]
        if x in (0xF5, 0xF6, 0xF7) and i+1 < len(seg):
            out.append(('K', x, seg[i+1])); i += 2
        else:
            out.append(('S', x)); i += 1
    return out

def render(toks, tbl, kanji, focus=None):
    """토큰 -> 사람이 읽는 문자열. focus 위치는 【】로 감싼다.

    0x00-0x05 는 제어 코드가 아니라 실제 글리프다 (00=魔 01=士 02=見 03=ヴ).
    0x01 만 예외로, 앞 글자가 탁음 가능한 가나면 탁점으로 결합한다.
    """
    out = []
    for j, t in enumerate(toks):
        if t[0] == 'K':
            key = (t[1], t[2])
            s = kanji.get(key) or f"<{'A' if t[1]==0xF5 else 'B' if t[1]==0xF6 else 'C'}{t[2]:02X}>"
        else:
            c = t[1]
            if c == 0x01:
                if out and out[-1] and out[-1][-1] in DAKU:
                    out[-1] = out[-1][:-1] + DAKU[out[-1][-1]]
                    continue
                s = tbl.get(c, '')
            elif c == 0xE3: s = ' / '
            elif c <= 0x05: s = tbl.get(c, '')
            elif c < 0x20 or c >= 0xE0: s = ''
            else: s = tbl.get(c, f'[{c:02X}]')
        out.append(f"【{s}】" if j == focus else s)
    return ''.join(out)

def collect(rom_path, win=12):
    rom = open(rom_path, 'rb').read()
    tbl = load_tbl(TBL)
    try:
        from kanji import KANJI
    except Exception:
        KANJI = {}
    ctx = collections.defaultdict(list)
    for a, b in REGIONS:
        area = rom[a:b]
        for msg in area.split(b'\xff'):
            if len(msg) < 3: continue
            toks = tokens(msg)
            for j, t in enumerate(toks):
                if t[0] != 'K': continue
                lo, hi = max(0, j-win), min(len(toks), j+win+1)
                ctx[(t[1], t[2])].append(render(toks[lo:hi], tbl, KANJI, focus=j-lo))
    return ctx, KANJI

if __name__ == "__main__":
    ctx, KANJI = collect(sys.argv[1])
    out = sys.argv[2] if len(sys.argv) > 2 else "kanji_ctx.json"
    data = {f"{b:02X}{i:02X}": {"n": len(v), "known": KANJI.get((b, i)),
                                "ctx": v[:12]}
            for (b, i), v in sorted(ctx.items(), key=lambda kv: -len(kv[1]))}
    json.dump(data, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f"한자 코드 {len(data)}개 문맥 수집 -> {out}")
    print(f"  출현 1회뿐인 코드: {sum(1 for v in data.values() if v['n']==1)}개")
    print(f"  출현 5회 이상: {sum(1 for v in data.values() if v['n']>=5)}개")
