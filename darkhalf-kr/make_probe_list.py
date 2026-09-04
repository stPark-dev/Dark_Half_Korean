#!/usr/bin/env python3
"""프로브 롬 — 마법 목록 창이 2바이트 이스케이프를 처리하는지 판정한다.

## 왜 필요한가

마법 이름을 「힐」 로 넣었더니 창마다 다르게 나온다.
  버리기 확인 창   「♥힐을 버려도 괜찮습니까？」  -> 정상
  마법 목록 창     「♥」 + 알 수 없는 두 글자      -> 깨짐

「힐」 은 f6 8c (2바이트 이스케이프)로 배정됐다. 목록 창이 이스케이프를
처리하지 않으면 0xF6 과 0x8C 를 각각 한 글자로 그린다. 예상 출력은
glyph(0xF6) + glyph(0x8C) 두 글자다 (0xF6 자리는 F4 F6 을 받은 음절의
글리프가 들어가 있다).

원본 게임의 마법 이름은 전부 단일바이트 가나였으므로(ヒール = 8b b0 99)
목록 창이 이스케이프를 지원할 이유가 없었다. 그래서 의심스럽다.

다만 저해상도 화면으로는 확정할 수 없어서 이 프로브로 가른다.

## 프로브 내용

마법 [06] (힐) 의 이름을 단일바이트 코드만으로 「소생」 으로 바꾼다.
  소 = 0xB1, 생 = 0xD4   (둘 다 단일바이트 배정)

## 판정

  목록에 「♥소생」 이 보이면
      -> 목록 창은 이스케이프를 처리하지 않는다.
         이름표는 단일바이트 코드만 써야 한다.
  목록에 여전히 알 수 없는 글자가 보이면
      -> 이스케이프 문제가 아니다. 다른 원인을 찾아야 한다.
  버리기 확인 창은 어느 경우든 「♥소생을」 로 정상이어야 한다
      (그 창은 이스케이프를 처리하는 것이 이미 확인됐다).
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nametbl, pipeline

ENTRY = 0x06                 # 힐
PROBE = bytes([0xB1, 0xD4])  # 소생 — 단일바이트 코드만


def main(src, dst):
    rom = bytearray(open(src, 'rb').read())
    spec, _ = nametbl.TABLES[0]
    slots = nametbl.slots(bytes(open("Dark Half (Japan).sfc", 'rb').read()), spec)
    addr, cap = slots[ENTRY]
    assert len(PROBE) <= cap, f"프로브가 칸 초과 {len(PROBE)}>{cap}"
    rom[addr:addr+len(PROBE)] = PROBE
    rom[addr+len(PROBE)] = 0xFF
    for a in range(addr+len(PROBE)+1, addr+cap+1): rom[a] = 0xFF
    print(f"마법 [{ENTRY:02X}] {addr:#08x} (칸 {cap}바이트) <- {PROBE.hex()} '소생'")
    pipeline.fix_checksum(rom)
    open(dst, 'wb').write(rom)
    print(f"저장: {dst}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
