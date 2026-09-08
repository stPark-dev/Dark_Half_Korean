#!/usr/bin/env python3
"""엔딩 텍스트 추출 — 구조는 PROGRESS 4.8 참조.

## 확정된 구조

  0x2FCFC0  포인터 표 4개 (16비트, 오프셋은 0x2FCFC0 기준)
  0x2FCFC8  본문 시작
  0x2FF780  본문 끝 (이후 0xFF 채움 2,176바이트 = F7 상위 슬롯 자리)

  읽는 코드 0x005666  LDA $EFCFC0,X
  진입점    0x0051F2  LDA $EFCFC0,X 로 표를 읽어 $FDCE 에 오프셋 저장

## 제어 바이트 (렌더러 0x5666~0x5696 에서 확인)

  0xFF  본문 종료 (RTS)
  0xFE  페이지 정지 — 입력 대기          118회
  0xFD  줄 넘김 후 계속                   26회
  0xF1  줄바꿈                           239회

## 외부 참조 없음

구간을 롱주소로 가리키는 명령을 전수 조사했다 (14곳 발견). 전부 그래픽·
데이터 뱅크(0x05 0x09 0x0f 0x12 0x13 0x14 0x19 0x1d 0x2a 0x2b 0x2c)에
흩어져 있다. 이 게임의 코드는 뱅크 0x00~0x02 이므로 오탐이다.
접근 경로는 포인터 표 4개와 순차 읽기뿐이다.
"""
import sys, os, struct, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dump import load_tbl, decode
from kanji import KANJI

BASE  = 0x2FCFC0
BODY  = BASE + 8
END   = 0x2FF780
NPTR  = 4
TBL   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "darkhalf.tbl")
KANA  = re.compile(r'[ぁ-んァ-ヶ]')


def pointers(rom):
    return [struct.unpack_from("<H", rom, BASE + 2*k)[0] for k in range(NPTR)]


def lines(rom):
    """0xF1(줄바꿈) / 0xFE(페이지) / 0xFD(줄넘김) 로 쪼갠 조각.

    반환: [(오프셋, 바이트열, 끝맺은 제어바이트)]
    제어 바이트는 조각에 포함하지 않고 따로 돌려준다. 다시 합칠 때 필요하다.
    """
    body = rom[BODY:END]
    out, s = [], 0
    for i, x in enumerate(body):
        if x in (0xF1, 0xFD, 0xFE, 0xFF):
            if i > s: out.append((s, bytes(body[s:i]), x))
            else: out.append((s, b"", x))
            s = i + 1
    if s < len(body): out.append((s, bytes(body[s:]), None))
    return out


def main(rom_path, out_tsv):
    rom = open(rom_path, 'rb').read()
    t = load_tbl(TBL)
    print(f"포인터 표: {[hex(p) for p in pointers(rom)]}")
    ls = lines(rom)
    prose = [(o, b, c) for o, b, c in ls if len(KANA.findall(decode(b, t, KANJI))) >= 1]
    with open(out_tsv, 'w', encoding='utf-8') as f:
        f.write("#id\toff\tlen\tend\thex\treadable\ttranslation\n")
        for i, (o, b, c) in enumerate(ls):
            f.write(f"{i}\t{o:#06x}\t{len(b)}\t"
                    f"{'%02X' % c if c is not None else ''}\t{b.hex()}\t"
                    f"{decode(b, t, KANJI)}\t\n")
    tot = sum(len(b) for _, b, _ in prose)
    ln = sorted(len(b) for _, b, _ in prose)
    print(f"조각 {len(ls)}개 -> {out_tsv}")
    print(f"  그중 가나 포함 {len(prose)}개 / {tot}바이트")
    if ln:
        print(f"  길이 중앙값 {ln[len(ln)//2]}  최대 {ln[-1]}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "darkhalf-kr/script_ending.tsv")
