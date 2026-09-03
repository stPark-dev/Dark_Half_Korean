#!/usr/bin/env python3
"""프로브 롬 — <EB>xx 가 화면에 무엇을 그리는지 판정한다.

## 왜 필요한가

대사 원문에 <EB>xx 형태가 51종 1,403회 나온다. 문법으로 보면 명사가 들어갈
자리다. 예: 「わしも<EB><14>は滅ぶべきものと」 에서 <EB><14> 를 빼면 조사만
남아 문장이 성립하지 않는다. 리터럴 人間(f505f506)이 「人間ども」로 쓰인
세그먼트와 <EB><14> 가 「<EB><14>ども」로 쓰인 세그먼트가 함께 있으므로
<EB><14> = 人間 으로 보인다.

그런데 단어표를 ROM 에서 찾지 못했다. 찾은 것은 두 개다.
  0x040000  UI 메시지표   (뱅크상대 포인터, 0xFF 종료)
  0x040260  아이템 이름표 (같은 형식)
UI 메시지표 안에도 <EB><18> <EB><19> 가 있고 「<EB><18>이 …가 되었습니다」
처럼 쓰인다. 정적 단어가 아니라 런타임 버퍼(몬스터 이름 등)일 수 있다.

둘 중 어느 쪽이냐에 따라 대응이 갈린다.
  정적 단어표   -> 표 51개만 번역하면 1,403곳이 한 번에 해결된다.
                   단어 하나가 2바이트라 예산도 크게 벌린다.
  런타임 버퍼   -> 버퍼를 채우는 원본 표(이름·몬스터·아이템)를 번역해야 한다.

## 판정 방법

힐(ヒール) 설명문 본문을 <EB>xx 나열로 바꾼다. 게임에서 맨 처음 얻는
마법이라 실기 확인이 가장 쉽다 (image/002.png 와 같은 자리).

  <EB><04> <EB><14> <EB><15> <EB><16>

## 읽는 법

  일본어 단어 네 개가 보이면   -> 정적 단어표. 각 단어가 무엇인지도 함께 알 수 있다
  인물 이름이 보이면           -> 런타임 이름 버퍼
  빈칸이거나 깨져 보이면       -> 그 자리에서는 버퍼가 비어 있다 (문맥 의존)
  글자 하나씩만 보이면         -> 단어 삽입이 아니라 한 글자 제어였다는 뜻
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patch_engine

DESC_SPOTS = [
    (0x05b5cf, 38),   # #6 힐 — 게임 최초 습득 마법
    (0x05b5f6, 45),   # #7 상태회복
    (0x05b512, 26),   # #0 파이어
    (0x05b52d, 24),   # #1 냉기
]
DESC_PREFIX = 9      # 앞 9바이트는 마법 이름

# 자주 쓰이는 네 개를 공백으로 띄워 넣는다. 어디까지 그려지는지 봐야 하므로
# 사이에 공백(0x20)을 둔다.
PROBE = bytes([0xEB,0x04, 0x20, 0xEB,0x14, 0x20, 0xEB,0x15, 0x20, 0xEB,0x16])


def main(src, dst):
    rom = patch_engine.apply(src, dst, verbose=True)
    for ad, ln in DESC_SPOTS:
        cap = ln - DESC_PREFIX
        assert len(PROBE) <= cap, f"{ad:#x} 예산 초과 {len(PROBE)}>{cap}"
        rom[ad+DESC_PREFIX:ad+ln] = PROBE + b'\x20' * (cap - len(PROBE))
        print(f"  프로브: {ad+DESC_PREFIX:#08x} ({cap}바이트)")
    patch_engine.fix_checksum(rom)
    open(dst, 'wb').write(rom)
    print(f"저장: {dst}  ({len(rom)}바이트)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
