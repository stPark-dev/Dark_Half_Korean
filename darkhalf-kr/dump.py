#!/usr/bin/env python3
"""Dark Half 스크립트 추출 (v3 - 메시지 경계 확정판).

확정된 구조:
  0xFF                = 메시지 종료  (포인터 테이블 목적지 직전이 100% 0xFF)
  0x01                = 탁점, 앞 글자에 결합 (ト+01=ド, か+01=が)
  0xF5 xx / 0xF6 xx   = 한자 뱅크 0/1
  0xE3                = 개행
  그 외 0x00-0x1F, 0xE6-0xFF = 제어 코드 (미해독, <XX> 로 표기)

탁음을 항상 결합형으로 쓰므로 완성형 글리프 슬롯의 코드값이 통째로
제어 코드 공간으로 비어 있다. 한글화 때 이 공간을 그대로 쓸 수 있다.
"""
import sys, collections

DAKU = dict(zip("かきくけこさしすせそたちつてとはひふへほカキクケコサシスセソタチツテトハヒフヘホウ",
                "がぎぐげござじずぜぞだぢづでどばびぶべぼガギグゲゴザジズゼゾダヂヅデドバビブベボヴ"))
CTRL = set(range(0x00, 0x20)) | set(range(0xE6, 0x100))
CTRL.discard(0x01)

def load_tbl(path):
    t = {}
    for line in open(path, encoding='utf-8'):
        line = line.split('#')[0].rstrip('\n')
        if not line or line[0] == '/': continue
        k, _, v = line.partition('=')
        if len(k) == 2 and v: t[int(k, 16)] = v
    return t

# 이스케이프 프리픽스 $F4~$F7. 렌더러($5CFA)는 AND #$03 으로 하위 2비트만
# 글리프 인덱스 상위 바이트에 넣는다. 즉 F4 xx = 인덱스 xx (0~255) 로,
# 맨바이트로는 쓸 수 없는 제어 범위 인덱스(0x00-0x1F, 0xE0-0xFF)에 닿는 경로다.
# 원문도 그렇게 쓴다: F4 00=魔 F4 01=士 F4 02=見 F4 FF=★ (맨바이트면 결합부호/종료자)
BANK_CH = {0xF4: 'D', 0xF5: 'A', 0xF6: 'B', 0xF7: 'C', 0x5D: 'E', 0xD5: 'F'}

# 제어 코드 범위에 있는데 실제로는 한자 글리프인 코드. 단어 안에 쓰이므로
# 판독 시 글자를 보여줘야 읽히고, 번역에서는 버려도 된다(제어 기능이 없다).
# 나머지 0x06~0x1E 는 탁음 가타카나, 0xE6~ 는 탁음 히라가나로 제어에만 쓰인다.
CTRL_KANJI = {0x00: '魔', 0x01: '士', 0x02: '見', 0x1F: '入'}

def ambiguous(t):
    """여러 코드가 공유하는 글리프의 코드 집합.

    판독 모드에서 이런 글리프를 문자로 렌더하면 번역문에 그대로 옮겼을 때
    역매핑이 엉뚱한 코드를 고른다. 실제로 ★ 은 0xE2/0xE4/0xE5/0xFF 가
    공유하고 역매핑은 0xFF(메시지 종료자)를 고르므로 메시지가 잘린다.
    따라서 이런 코드는 판독 모드에서도 태그로 남긴다.
    """
    import collections
    n = collections.Counter(t.values())
    return {c for c, g in t.items() if n[g] > 1}

def decode(b, t, kanji=None, amb=None):
    """바이트열 -> 텍스트.

    kanji 를 주면 뱅크 이스케이프를 실제 한자로 렌더한다 (판독용).
    주지 않으면 <A05> 형태의 태그로 남긴다 (왕복 삽입용).
    kanji 를 준 결과는 krcodec.encode 로 되돌아가지 않으므로 읽기 전용이다.
    """
    if kanji is not None and amb is None: amb = ambiguous(t)
    amb = amb or set()
    out = []; i = 0
    while i < len(b):
        x = b[i]
        if x == 0xE3:
            # 개행. ★ 과 글리프를 공유하지만 인코딩이 되돌아가므로 \n 으로 보여준다.
            # 줄바꿈 위치는 번역문 길이 판단에 필요하다.
            out.append('\\n'); i += 1
        elif kanji is not None and x in amb and x not in CTRL:
            out.append(f"<{x:02X}>"); i += 1
        elif x == 0x01:
            # 앞 글자가 탁음 가능한 가나면 탁점으로 결합, 아니면 글리프 士
            if out and out[-1] in DAKU: out[-1] = DAKU[out[-1]]
            elif kanji is not None: out.append('<士>')
            else: out.append('<01>')
            i += 1
        elif x in BANK_CH and i+1 < len(b):
            idx = b[i+1]
            if x == 0xF4:
                # 인덱스 0~255 = 단일바이트 글리프표와 같은 자리
                if kanji is not None and idx in t: out.append(t[idx])
                else: out.append(f"<D{idx:02X}>")
            elif kanji is not None and (x, idx) in kanji:
                out.append(kanji[(x, idx)])
            else:
                out.append(f"<{BANK_CH[x]}{idx:02X}>")
            i += 2
        elif x in CTRL:
            # 태그로 남기되, 한자 글리프인 4개는 글자를 보여준다 (<魔> 형태).
            # 제어 코드와 한눈에 구분되고, krcodec 이 같은 표기를 되받는다.
            if kanji is not None and x in CTRL_KANJI:
                out.append(f"<{CTRL_KANJI[x]}>")
            else:
                out.append(f"<{x:02X}>")
            i += 1
        else:
            out.append(t.get(x, f"[{x:02X}]")); i += 1
    return ''.join(out)

def text_regions(rom, blk=0x1000, thr=0.25):
    runs = []; cur = None
    for b in range(0, len(rom), blk):
        seg = rom[b:b+blk]
        d = sum(1 for x in seg if 0xA1 <= x <= 0xDD) / max(1, len(seg))
        if d > thr:
            if cur is None: cur = [b, b+blk]
            else: cur[1] = b+blk
        elif cur:
            runs.append(tuple(cur)); cur = None
    if cur: runs.append(tuple(cur))
    return runs

def main(rom_path, out_path):
    rom = open(rom_path, 'rb').read()
    t = load_tbl(__file__.rsplit('/', 1)[0] + '/darkhalf.tbl')
    msgs = []
    for ra, rb in text_regions(rom):
        s = ra
        for i in range(ra, rb):
            if rom[i] == 0xFF:
                if i > s: msgs.append((s, rom[s:i]))
                s = i + 1
    kept = [(o, m) for o, m in msgs
            if len(m) >= 4 and sum(1 for x in m if 0xA1 <= x <= 0xDD)/len(m) >= 0.30]
    with open(out_path, 'w', encoding='utf-8') as f:
        for o, m in kept: f.write(f"{o:#08x}\t{len(m)}\t{decode(m, t)}\n")
    ln = sorted(len(m) for _, m in kept)
    print(f"메시지 {len(kept)}개 (0xFF 종료) -> {out_path}")
    print(f"바이트 길이: 중앙값 {ln[len(ln)//2]}  최대 {ln[-1]}  총 {sum(ln)}")
    ctl = collections.Counter(x for _, m in kept for x in m if x in CTRL)
    print("미해독 제어 코드 상위:", [(f"{k:02X}", v) for k, v in ctl.most_common(10)])

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "darkhalf-kr/script.tsv")
