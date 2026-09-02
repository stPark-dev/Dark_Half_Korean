#!/usr/bin/env python3
"""Dark Half (SNES) 인코딩 테이블 추출용 relative search (v2).

핵심: 3글자(델타 2개)는 3MB ROM에서 기대 오탐이 ~48개라 무의미하다.
5글자 이상(델타 4개+)을 쓰고, 서로 다른 단어들이 같은 base 코드에
합의하는지로 채점한다. 단일 단어의 히트는 증거로 치지 않는다.
"""
import sys, collections

BASIC = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん"
INLINE = ("あいうえお" "かがきぎくぐけげこご" "さざしじすずせぜそぞ" "ただちぢつづてでとど"
          "なにぬねの" "はばぱひびぴふぶぷへべぺほぼぽ" "まみむめも" "やゆよ" "らりるれろ" "わをん")
KATA  = "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン"
ORDERINGS = {"basic46": BASIC, "inline-dakuten": INLINE, "katakana46": KATA}

# 탁음/반탁음·요음 없는 5글자 이상 표현만 사용
WORDS = ["さようなら","こんにちは","ほんとうに","ちからをためる","おわりました","なにもない",
         "しかたない","ありません","そのとおり","あたらしい","うつくしい","おまえたち",
         "はなしかける","たたかう","そうびする","なにをする","わたしたち","おもしろい"]

def deltas(word, order):
    idx = []
    for ch in word:
        p = order.find(ch)
        if p < 0: return None
        idx.append(p)
    return [(idx[i+1]-idx[i]) % 256 for i in range(len(idx)-1)]

def search(rom, d, step):
    out=[]; n=len(rom); L=len(d)
    for p in range(0, n-(L+1)*step):
        for i in range(L):
            if (rom[p+(i+1)*step]-rom[p+i*step]) % 256 != d[i]: break
        else: out.append(p)
    return out

def main(path, step):
    rom = open(path,'rb').read()
    print(f"ROM {len(rom)} bytes  step={step}")
    for name, order in ORDERINGS.items():
        votes = collections.defaultdict(set)   # base -> {단어}
        detail = collections.defaultdict(list)
        used = 0
        for w in WORDS:
            d = deltas(w, order)
            if d is None or len(d) < 4: continue
            used += 1
            for p in search(rom, d, step):
                base = (rom[p] - order.find(w[0])) % 256
                votes[base].add(w); detail[base].append((w,p))
        print(f"\n### {name}  (사용 단어 {used}개, 델타 4개 이상)")
        multi = {b:ws for b,ws in votes.items() if len(ws) >= 2}
        if not multi:
            tot = sum(len(v) for v in detail.values())
            print(f"   합의 없음. 단일 단어 히트 총 {tot}개 -> 전부 오탐으로 판단")
            for b,ws in sorted(votes.items(), key=lambda kv:-len(kv[1]))[:3]:
                print(f"     base={b:#04x} {sorted(ws)} @ {[hex(p) for _,p in detail[b][:3]]}")
        else:
            for b, ws in sorted(multi.items(), key=lambda kv:-len(kv[1])):
                print(f"   *** base(あ)={b:#04x}  합의단어 {len(ws)}: {sorted(ws)}")
                for w,p in detail[b][:6]: print(f"        {w} @ {p:#08x}")

if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv)>2 else 1)
