#!/usr/bin/env python3
"""엔진 패치 프로브 롬 — 프리픽스 인식과 뱅크 전환을 한 화면에서 판정한다.

빈 아이템 창을 열면 나오는 메시지를 프로브로 바꾼다.
  원문: 「何も持っていません！」  (게임 시작 직후 아이템 창에서 바로 볼 수 있다)

프로브 내용
  <5D><00>  프리픽스 $5D + 인덱스 0 -> 글리프 인덱스 1024 -> ROM 0x300000 에 '한'
  <D5><00>  프리픽스 $D5 + 인덱스 0 -> 글리프 인덱스 1280 -> ROM 0x304000 에 '글'
  ！

판정
  「한글！」 이 보이면      -> 프리픽스 두 개와 뱅크 전환이 모두 작동
  「한」 만 보이면          -> $5D 만 작동 ($D5 는 다른 데서 쓰이는 중)
  아무것도/깨져 보이면      -> 프리픽스 인식 또는 뱅크 전환 실패
  게임이 멈추면            -> 패치가 코드 흐름을 깼다
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patch_engine, makefont

# 프로브를 심을 세그먼트: 「何も持っていません！」
PROBE_ADDR, PROBE_LEN = None, None
PROBE_BYTES = bytes([0xFA, 0x01,          # 창 제어 (원본과 동일)
                     0x5D, 0x00,          # 프리픽스 4 + 인덱스 0 -> 1024
                     0xD5, 0x00,          # 프리픽스 5 + 인덱스 0 -> 1280
                     0x21])               # ！

# 프로브를 심을 설명문 본문 (마법 -> 설명 에서 바로 보인다)
#   PREFIX=9 바이트가 마법 이름, 그 뒤가 본문
DESC_SPOTS = [(0x05b512, 26), (0x05b52d, 24), (0x05b546, 37)]
DESC_PREFIX = 9


def main(src, dst, tsv):
    global PROBE_ADDR, PROBE_LEN
    for line in open(tsv, encoding='utf-8'):
        if line.startswith('#'): continue
        c = line.rstrip('\n').split('\t')
        if c[0] == '6':
            PROBE_ADDR, PROBE_LEN = int(c[2], 16), int(c[3])
            break
    assert PROBE_ADDR, "세그먼트 #6 을 못 찾음"
    assert len(PROBE_BYTES) <= PROBE_LEN, f"프로브가 예산 초과 {len(PROBE_BYTES)}>{PROBE_LEN}"

    rom = patch_engine.apply(src, dst, verbose=True)

    # 새 폰트 영역에 글리프 기록
    rom[0x300000:0x300000+64] = makefont.encode('한')   # 인덱스 1024
    rom[0x304000:0x304000+64] = makefont.encode('글')   # 인덱스 1280
    print(f"  글리프: 인덱스 1024 <- '한' (0x300000), 인덱스 1280 <- '글' (0x304000)")

    # 프로브 메시지 삽입 (남는 자리는 공백)
    rom[PROBE_ADDR:PROBE_ADDR+PROBE_LEN] = (
        PROBE_BYTES + b'\x20' * (PROBE_LEN - len(PROBE_BYTES)))
    print(f"  프로브(아이템 창): {PROBE_ADDR:#08x} ({PROBE_LEN}바이트)")

    # 설명문 본문에도 심는다 — 마법 -> 설명 에서 바로 확인 가능
    body = bytes([0x5D, 0x00, 0xD5, 0x00, 0x21])      # 한 글 ！
    for ad, ln in DESC_SPOTS:
        cap = ln - DESC_PREFIX
        assert len(body) <= cap, f"{ad:#x} 예산 초과"
        rom[ad+DESC_PREFIX:ad+ln] = body + b'\x20' * (cap - len(body))
        print(f"  프로브(설명문): {ad+DESC_PREFIX:#08x} ({cap}바이트)")

    patch_engine.fix_checksum(rom)
    open(dst, 'wb').write(rom)
    print(f"저장: {dst}  ({len(rom)}바이트)")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
