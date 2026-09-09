#!/usr/bin/env python3
"""메뉴 화면 글리프 교체 — 세이브 선택 화면 등.

## 왜 이렇게 하는가

이 화면들의 글자는 **텍스트가 아니라 그림**이다 (PROGRESS 4.17.7). 화면마다
필요한 글자를 모아 만든 타일 시트가 압축돼 있고, 타일맵은 그것을 통째로 붙인다.
그래서 **글리프 비트맵만 바꾸면** 화면이 바뀐다 — 타일맵도 텍스트도 글리프
번호도 건드릴 필요가 없다.

## 제자리 삽입

블록을 풀어 타일을 바꾸고 다시 인코딩해 **원래 자리에 쓴다.** 뱅크 `0x16` 에는
64바이트 이상 빈 구간이 하나도 없어서 이전이 불가능한데, 한글은 한자보다 획이
적어 재인코딩이 원본보다 작아진다.

남는 뒷부분은 그대로 둔다. 압축 해제기는 버퍼 1024바이트를 채우면 멈추므로
뒤쪽 바이트는 읽지 않는다.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gfx, menufont

# (블록 주소, 타일, 글자). 타일은 블록 안 번호이고 n,n+1,n+16,n+17 을 쓴다.
#
# 자리를 찾는 방법: VRAM 덤프를 템플릿 매칭해 글자의 VRAM 타일 번호를 얻고,
#
#     VRAM 타일 = 576 + 32*(블록순번 - 7) + 블록내타일
#
# 로 역산한다 (블록순번은 엔트리[22]를 주소순으로 정렬한 것). 0x16aa16 이
# VRAM 576 이라는 것은 실기 VRAM 과 1024/1024 일치로 확정했다 (4.17.6).
#
# 세이브 선택 화면 — 원문 「新規」「削除」「設定」
GLYPHS = [
    (0x16a6d5, 10, "신"),      # 新
    (0x16aa16, 10, "규"),      # 規
    (0x16ad27,  0, "삭"),      # 削
    (0x16ad27,  2, "제"),      # 除
    (0x16b9dc, 10, "설"),      # 設
    (0x16b9dc, 12, "정"),      # 定
]

# 문장 「セーブエリアを選んでください」 — 가나 13자다.
#
# 한 번 되돌렸다가 복구했다. 되돌린 이유는 「설정 화면이 「면공가했ジ땠곧」 처럼
# 깨졌으니 폰트 시트가 공유일 것」 이었는데, **그 추론이 틀렸다.** 깨진 18자를
# codes.json 에서 찾아보니 전부 **대사 폰트**에 배정된 글자였다. 설정 화면은
# 메뉴 폰트가 아니라 대사 폰트를 쓴다. 그 깨짐은 4.1 의 기존 증상이고 이 패치와
# 무관하다. 실제로 문장 번역판(image/메뉴시험3.png)에서 문장은 정상 출력됐다.
#
# 교훈: 두 화면이 같이 깨졌다는 사실만으로 원인을 잇지 말 것. 깨진 **글자가
# 어느 폰트에 있는지** 확인하면 1분에 갈린다.
#
# 이 여섯 블록은 gfx.blocks() 로 확인하면 전부 엔트리 22 전용이다.
#
# 글자 k = 블록 0x16b25b 타일 2k        (k < 8)
#          블록 0x16b4c6 타일 2(k-8)    (k >= 8)
# VRAM 으로는 타일 672+2k / 704+2(k-8).
# 타일맵은 0x7800 겹 행 24~25 이고 그 BG 의 문자 베이스는 512 다.
#
# 13칸에 맞춰 「 세이브 영역을 고르세요」 (앞 1칸 비움) 로 넣는다.
SENTENCE = " 세이브 영역을 고르세요"
for _k, _c in enumerate(SENTENCE):
    GLYPHS.append((0x16b25b, _k*2, _c) if _k < 8
                  else (0x16b4c6, (_k-8)*2, _c))


def block_limit(rom, addr):
    """이 블록이 쓸 수 있는 바이트 수 (다음 블록 시작까지)."""
    for e in range(41):
        try: bl = gfx.blocks(rom, e)
        except Exception: continue
        if addr not in [b for b in bl if b]: continue
        nxt = [b for b in bl if b and b > addr]
        if nxt: return min(nxt) - (addr - 1)
    return None


def apply(rom, items=None, verbose=False):
    """블록별로 묶어 한 번만 풀고 쓴다. 같은 블록에 두 글자가 들어가는 경우가
    있어서(削·除 는 0x16ad27, 設·定 은 0x16b9dc) 항목마다 다시 풀면 앞의
    수정이 날아간다."""
    rom = bytearray(rom)
    byblk = {}
    for addr, tile, ch in (items or GLYPHS):
        byblk.setdefault(addr, []).append((tile, ch))
    for addr, lst in byblk.items():
        cap = block_limit(bytes(rom), addr)
        buf = bytearray(gfx.unpack(bytes(rom), addr))
        for tile, ch in lst:
            menufont.put(buf, tile, menufont.render(ch))
        blk = gfx.block(bytes(buf))
        if cap is not None and len(blk) > cap:
            raise SystemExit(f"{addr:#08x} {[c for _, c in lst]}: "
                             f"{len(blk)}바이트 > 칸 {cap}")
        rom[addr-1:addr-1+len(blk)] = blk
        if verbose:
            print(f"  {addr:#08x} {[(t, c) for t, c in lst]}  {len(blk)}/{cap}바이트")
    return bytes(rom)


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    out = apply(open(src, 'rb').read(), verbose=True)
    open(dst, 'wb').write(out)
    print(f"-> {dst} ({len(out)}바이트)")
