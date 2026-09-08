#!/usr/bin/env python3
"""메뉴 폰트 압축 해제 — Dark Half 전용 코덱. **실기 VRAM 과 1024/1024 일치 검증됨.**

## 왜 필요한가

세이브 선택 화면·아이템 목록 창·오프닝은 대사 폰트가 아닌 **별도 4bpp 폰트**를
쓴다 (PROGRESS 4.17.1). 그 폰트는 롬에 압축돼 있어 문자열 검색으로 못 찾는다.
디스어셈블리($C03300~$C034CD)를 읽어 여기 구현했다.

## 구조

    0x100000 ($D00000)  압축 블록 인덱스. 4바이트/엔트리, 41개
    엔트리 -> 서브 표    16비트 오프셋 목록. 0xFFFF = 데이터 없음
    $2C                 비트 스트림 ($34CF 가 최상위부터 1비트씩)
    $28 = $2C + [$2C-1] 데이터 스트림 (헤더가 비트 스트림 길이)
    $7E273B             출력 0x400바이트 = 32타일. VRAM 인터리브 형태로 바로 만든다

세이브 화면 폰트 = 엔트리 [22](`0x169a53`) 의 9번째 오프셋 `0x0FC2`
-> **`0x16aa16`, 785바이트 -> 1024바이트**. VRAM `0x4800` 에 올라간다.

## 명령

명령 바이트 하나가 핸들러 **4회**를 담당한다. 각자 상위 2비트를 먹으므로
4×2 = 8비트가 정확히 맞는다. 출력 위치는 `$53`, `$53+1`, `$53+0x10`, `$53+0x11`.

| 비트 | 주소 | 동작 |
|---|---|---|
| `0,1` | `$C033EE` | 8바이트를 `0x00`/`0xFF` 로 채움 (비트 1개) |
| `0,0` | `$C033A1` | **니블 역인터리브** 4회 (비트 1개 + 마스크 + 리터럴) |
| `1,1` | `$C0346A` | 리터럴 8개, 또는 마스크+채움 |
| `1,0` | `$C03414` | **복사 + 부분 덮어쓰기** |

### 니블 역인터리브가 이 코덱의 핵심이다

원본은 두 플레인의 니블을 한 바이트에 붙여 담고, 하드웨어 곱셈기
(`WRMPYA=0x10`)로 `<<4`/`>>4` 해서 갈라 놓는다.

    out[X]   = (L1 & 0xF0) | (L2 & 0x0F)
    out[X+2] = (L1 << 4)   | (L2 >> 4)

### 복사 + 부분 덮어쓰기 — 이걸 놓쳐서 오래 헤맸다

`$C03452` 의 `PLY` 가 단서였다. 8바이트를 복사한 **뒤** `$C03455` 의 마스크
루프로 떨어져 일부를 리터럴로 덮어쓴다. 복사만 보고 덮어쓰기를 빼먹으면
36개 핸들러가 어긋난다 (84% 에서 멈춘다).

원본 인덱스는 어셈블리를 그대로 옮겨야 맞는다. `ASL`/`ROL` 이 8비트 A 에
걸리므로 최상위 비트가 최하위로 돌아 들어오고, 상위 바이트는 `b & 3` 이다.
'그럴듯한' 공식(`b*4` 등)은 89% 에서 멈춘다.
"""
import sys

TABLE = 0x100000
BUFLEN = 0x400


def blocks(rom, entry):
    """엔트리의 서브 블록 절대 주소 목록. 0xFFFF 는 건너뛴다."""
    a = TABLE + entry * 4
    base = ((rom[a + 2] - 0xC0) << 16) | rom[a] | (rom[a + 1] << 8)
    out = []
    for k in range(64):
        o = rom[base + k*2] | (rom[base + k*2 + 1] << 8)
        if o == 0xFFFF: out.append(None); continue
        out.append(base + 1 + o)          # $30 은 표 시작+1 이다
    return out


def unpack(rom, addr, buf=None):
    """압축 블록 하나를 풀어 1024바이트(32타일, VRAM 인터리브)로 돌려준다.

    buf 를 주면 이어서 쓴다 ($C03321 은 서브 오프셋이 0xFFFF 일 때만 지운다).
    """
    hdr = rom[addr - 1]
    bp, cur, nb = addr, 0, 0
    dp = addr + hdr
    out = bytearray(BUFLEN) if buf is None else buf

    def bit():
        nonlocal bp, cur, nb
        if nb == 0:
            cur = rom[bp]; bp += 1; nb = 8
        b = (cur >> 7) & 1; cur = (cur << 1) & 0xFF; nb -= 1
        return b

    def lit():
        nonlocal dp
        x = rom[dp]; dp += 1; return x

    base = 0
    while base < BUFLEN:
        cmd = lit()
        for x in (base, base + 1, base + 0x10, base + 0x11):
            hi, lo = (cmd >> 7) & 1, (cmd >> 6) & 1
            cmd = (cmd << 2) & 0xFF

            if hi == 0 and lo == 1:                       # $C033EE
                f = 0x00 if bit() else 0xFF               # LDA #$00 / SBC #$00
                for k in range(8): out[x + k*2] = f

            elif hi == 0:                                 # $C033A1
                f = 0x00 if bit() else 0xFF
                m = lit(); xx = x
                for _ in range(4):
                    l1 = lit() if (m & 0x80) else f; m = (m << 1) & 0xFF
                    l2 = lit() if (m & 0x80) else f; m = (m << 1) & 0xFF
                    out[xx]     = (l1 & 0xF0) | (l2 & 0x0F)
                    out[xx + 2] = ((l1 << 4) & 0xFF) | (l2 >> 4)
                    xx += 4

            elif lo == 1:                                 # $C0346A
                if bit() == 0:
                    for k in range(8): out[x + k*2] = lit()
                else:
                    f = lit() if bit() == 0 else (0x00 if bit() else 0xFF)
                    m = lit()
                    for k in range(8):
                        out[x + k*2] = lit() if (m & 0x80) else f
                        m = (m << 1) & 0xFF

            else:                                         # $C03414 복사 + 덮어쓰기
                b = lit()
                v = b & 0xFC                              # AND #$FC
                a1 = (v << 1) & 0xFF; c1 = (v >> 7) & 1   # ASL
                a2 = ((a1 << 1) | c1) & 0xFF              # ROL
                c2 = (a1 >> 7) & 1
                y = (((b & 3) << 8) | a2) & 0x3FF         # XBA 로 상위가 b&3
                for k in range(8): out[x + k*2] = out[(y + k*2) & 0x3FF]
                if c2 == 0:                               # BCS $C03469 를 안 탄 경우
                    m = lit()
                    for k in range(8):                    # $10 이 0 이면 조기 종료
                        if m == 0: break
                        if m & 0x80: out[x + k*2] = lit()
                        m = (m << 1) & 0xFF
        base += 0x20
    return bytes(out)


def tiles(buf):
    """1024바이트 버퍼 -> 8x8 4bpp 타일 32개의 (16,16) 비트맵 16개.

    16x16 글자는 2x2 타일이고 배치는 n, n+1 / n+16, n+17 (16타일 폭 시트).
    """
    def px(t, r, c):
        o = t * 32
        p = (buf[o+r*2], buf[o+r*2+1], buf[o+16+r*2], buf[o+16+r*2+1])
        return sum(((x >> (7-c)) & 1) << i for i, x in enumerate(p))
    return px


if __name__ == "__main__":
    rom = open(sys.argv[1], 'rb').read()
    a = int(sys.argv[2], 16)
    out = unpack(rom, a)
    print(f"{a:#08x} -> {len(out)}바이트")
    print(out[:64].hex())
