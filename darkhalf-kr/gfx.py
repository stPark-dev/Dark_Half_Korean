#!/usr/bin/env python3
"""메뉴 폰트 압축 해제 — Dark Half 전용 코덱.

## 왜 필요한가

세이브 선택 화면·아이템 목록 창·오프닝은 대사 폰트가 아닌 **별도 4bpp 폰트**를
쓴다 (PROGRESS 4.17.1). 그 폰트는 롬에 압축돼 있어 문자열 검색으로 못 찾는다.
디스어셈블리로 코덱을 읽어 여기 구현했다.

## 코덱 구조 (디스어셈블리 $C03300~$C034CD)

    $C03311  LDA $D00000,X    인덱스 표: 4바이트/엔트리, 24비트 포인터
    $C03328  STZ $273B,X      출력 버퍼 0x400바이트(32타일) 를 0 으로 지움
    $C03346  $28 = $2C + [$2C-1]   비트 스트림 뒤에 데이터 스트림이 온다
    $C0334F  WRMPYA = $10     하드웨어 곱셈기로 <<4 / >>4 를 한다

스트림이 **둘**이다.

    $2C  비트 스트림 — $34CF 가 1비트씩 꺼낸다 ($4E 가 8회 세고 리필)
    $28  데이터 스트림 — 리터럴 바이트와 명령 바이트

출력은 VRAM 인터리브 형태로 바로 만든다 (간격 2).

## 검증 상태 (2026-09-08)

VRAM 덤프와 대조해 **네 핸들러 중 셋이 바이트 단위로 정확히 일치**한다.

    X=0x00  니블 역인터리브   0026340e06070300   일치
    X=0x01  채움 0x00         0000000000000000   일치
    X=0x10  니블 역인터리브   001a3c0602050101   일치
    X=0x11  역참조            불일치 ← 남은 문제

**역참조가 이전 블록의 잔존 데이터를 가리킨다.** $C03321 을 보면 출력 버퍼를
지우는 것은 서브 오프셋이 `0xFFFF`(데이터 없음) 일 때뿐이다. 그래서 블록
하나만 따로 풀면 역참조 원본이 없어 재현되지 않는다. **블록을 순서대로 이어
풀어야 한다.**

역참조의 원본 인덱스 계산($C03414~$C03421)도 미확정이다.

    LDA [$28],Y / TAY / AND #$03 / XBA / TYA / AND #$FC / ASL / ROL / TAY

8비트 A 와 16비트 Y 가 섞여 있어 정적으로는 확정이 어렵다. 소비 바이트 수도
1바이트가 아닐 수 있다 (역참조 이후 스트림이 어긋난다).

## 명령 (한 바이트 $50 의 상위 비트부터)

    bit7=0, bit6=1  ->  $C033EE  8바이트를 0x00 또는 0xFF 로 채움
    bit7=0, bit6=0  ->  $C033A1  니블 역인터리브 4회 (16바이트)
    bit7=1, bit6=1  ->  $C0346A  8바이트 리터럴, 또는 마스크+채움
    bit7=1, bit6=0  ->  $C03414  이전 출력에서 8바이트 복사 (역참조)

니블 역인터리브가 이 코덱의 핵심이다. 원본은 두 플레인의 니블을 한 바이트에
붙여 담고, 해제할 때 갈라 놓는다.

    out[X]   = (L1 & 0xF0) | (L2 & 0x0F)
    out[X+2] = (L1 << 4)   | (L2 >> 4)
"""
import sys, os

TABLE = 0x100000          # $D00000 — 압축 블록 인덱스
BUFLEN = 0x400            # 32타일 × 32바이트


class Bits:
    """$34CF — 별도 비트 스트림에서 최상위 비트부터 꺼낸다."""
    def __init__(self, rom, addr):
        self.rom, self.a, self.cur, self.n = rom, addr, 0, 0

    def bit(self):
        if self.n == 0:
            self.cur = self.rom[self.a]; self.a += 1; self.n = 8
        b = (self.cur >> 7) & 1
        self.cur = (self.cur << 1) & 0xFF; self.n -= 1
        return b


def unpack(rom, addr, verbose=False):
    """압축 블록 하나를 풀어 1024바이트(32타일, VRAM 인터리브)로 돌려준다."""
    hdr = rom[addr - 1]
    bits = Bits(rom, addr)
    dp = addr + hdr                      # 데이터 스트림
    out = bytearray(BUFLEN)

    def lit():
        nonlocal dp
        v = rom[dp]; dp += 1; return v

    # 명령 바이트 하나가 핸들러 4회를 담당한다 ($53, $53+1, $53+0x10, +1).
    # 각 핸들러가 상위 2비트를 먹으므로 4×2 = 8비트가 정확히 맞는다.
    base = 0
    while base < 0x100:
        cmd = lit()
        for x in (base, base + 1, base + 0x10, base + 0x11):
            hi, lo = (cmd >> 7) & 1, (cmd >> 6) & 1
            cmd = (cmd << 2) & 0xFF
            if hi == 0 and lo == 1:                    # $C033EE 채움
                f = 0x00 if bits.bit() else 0xFF   # LDA #$00 / SBC #$00
                for k in range(8): out[x + k*2] = f
            elif hi == 0:                              # $C033A1 니블 역인터리브
                f = 0x00 if bits.bit() else 0xFF   # LDA #$00 / SBC #$00
                mask = lit()
                for _ in range(4):
                    l1 = lit() if (mask & 0x80) else f; mask = (mask << 1) & 0xFF
                    l2 = lit() if (mask & 0x80) else f; mask = (mask << 1) & 0xFF
                    out[x]     = (l1 & 0xF0) | (l2 & 0x0F)
                    out[x + 2] = ((l1 << 4) & 0xFF) | (l2 >> 4)
                    x += 4
            elif lo == 1:                              # $C0346A 리터럴 8개 or 마스크
                if bits.bit() == 0:
                    for k in range(8): out[x + k*2] = lit()
                else:
                    f = lit() if bits.bit() == 0 else (0x00 if bits.bit() else 0xFF)
                    mask = lit()
                    for k in range(8):
                        out[x + k*2] = lit() if (mask & 0x80) else f
                        mask = (mask << 1) & 0xFF
            else:                                      # $C03414 역참조
                b = lit()
                src = ((b & 0xFC) << 1) & 0x1FF
                for k in range(8): out[x + k*2] = out[src + k*2]
        base += 0x20
    if verbose:
        print(f"  블록 {addr:#08x} 헤더 {hdr:#04x} 비트끝 {bits.a:#08x} 데이터끝 {dp:#08x}")
    return bytes(out)


if __name__ == "__main__":
    rom = open(sys.argv[1], 'rb').read()
    a = int(sys.argv[2], 16)
    out = unpack(rom, a, verbose=True)
    print(out[:64].hex())
