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
