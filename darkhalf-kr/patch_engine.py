#!/usr/bin/env python3
"""엔진 패치 — 글리프 인덱스를 10비트에서 11비트로 넓힌다.

## 왜 필요한가

고유 음절 상한이 811자인데 전량 번역에는 약 1,200자가 필요하다 (PROGRESS 2.5).
상한의 원인은 글리프 인덱스가 10비트라는 것이다 (PROGRESS 1.2.1).

## 확정된 렌더러 구조

이스케이프 판별이 두 곳에 있다. 둘 다 같은 논리의 복사본이다.

  0x00950F  메인 대사 렌더러용
  0x005CFA  옵션/엔딩 텍스트 렌더러용

    LDA $69 / CMP #$F8 / BCS single / CMP #$F4 / BCC single
    AND #$03 / PHA / JSR (다음바이트) / PLA / BRA (상위바이트 저장)

인덱스는 $69(하위)/$6A(상위)에 16비트로 놓이고, DMA 큐 설정이 이를 x64 해서
소스 주소로 쓴다.

  0x009548  REP #$20 / LDA $69 / ASL x6 / ... / LDA #$80EF / STA $0700,X
                                                      ^^ 소스 뱅크 $EF 고정

## 패치 원리

인덱스 1024를 x64 하면 0x10000 이 되어 16비트에서 하위 0x0000 으로 감긴다.
즉 하위 16비트는 이미 '다음 뱅크 내 오프셋'으로 정확하다. 바꿀 것은 뱅크
바이트 하나뿐이다.

    뱅크 = $EF + ($6A >> 2)

$6A 가 0~3 이면 $EF, 4~5 이면 $F0. HiROM 에서 뱅크 $F0 = ROM 0x300000 이므로
롬을 4MB 로 확장하면 그 자리가 새 폰트 영역이 된다 (헤더 롬 크기 바이트는
이미 0x0C = 4MB).

프리픽스로는 $5D(備) 와 $D5(ゆ) 를 쓴다. 이 두 바이트는 우리가 번역하지 않는
구간(설명문 A/B, 옵션·엔딩 텍스트)에서 한 번도 쓰이지 않는다. 대사 뱅크 0x04
에서는 쓰이지만 그건 전량 번역하므로 우리가 통제한다.

## 주의

$6A 는 0x9552 의 STA $69 (16비트) 에서 덮인다. 그래서 뱅크 계산을 인덱스
시프트보다 **먼저** 해야 한다. 그 때문에 0x9548 이후 꼬리를 빈 공간으로
옮겨 재구성한다.
"""
import sys, os

ROM_4MB = 4 * 1024 * 1024
FREE_A  = 0x00F200      # 이스케이프 판별 — 메인 대사 렌더러 (뱅크 $C0)
FREE_C  = 0x00F260      # 이스케이프 판별 — 옵션/엔딩 렌더러 ($5CFA 용)
FREE_B  = 0x00F300      # DMA 꼬리      (뱅크 $C0, addr $F300)
NEWFONT = 0x300000      # 뱅크 $F0 = 인덱스 1024~

PFX4, PFX5 = 0x5D, 0xD5


def asm(items, org):
    """(바이트열 | ('label',이름) | ('rel',이름) | ('abs',이름)) -> 바이트열.

    rel = 8비트 상대 분기 오프셋, abs = 16비트 절대 주소.
    """
    # 1차: 크기 계산과 라벨 주소 확정
    labels, pc = {}, org
    for it in items:
        if isinstance(it, tuple) and it[0] == 'label':
            labels[it[1]] = pc
        elif isinstance(it, tuple):
            pc += 1 if it[0] == 'rel' else 2
        else:
            pc += len(it)
    # 2차: 방출
    out, pc = bytearray(), org
    for it in items:
        if isinstance(it, tuple) and it[0] == 'label':
            continue
        if isinstance(it, tuple) and it[0] == 'rel':
            pc += 1
            d = labels[it[1]] - pc
            assert -128 <= d <= 127, f"분기 범위 초과 {it[1]} {d}"
            out.append(d & 0xFF)
        elif isinstance(it, tuple) and it[0] == 'abs':
            pc += 2
            out += labels[it[1]].to_bytes(2, 'little')
        else:
            pc += len(it); out += it
    return bytes(out)


def escape_patch(org, next_byte_jsr, store_hi_jmp, single_jmp):
    """이스케이프 판별 확장판.

    원본과 같되 $5D -> 상위 4, $D5 -> 상위 5 를 추가한다.
    A 에 상위 바이트를 담고 store_hi_jmp 로 간다 (원본의 BRA 목적지).
    """
    return asm([
        b'\xa5\x69',                              # LDA $69
        b'\xc9' + bytes([PFX4]), b'\xf0', ('rel','p4'),   # CMP #PFX4 / BEQ p4
        b'\xc9' + bytes([PFX5]), b'\xf0', ('rel','p5'),   # CMP #PFX5 / BEQ p5
        b'\xc9\xf8', b'\xb0', ('rel','sng'),      # CMP #$F8 / BCS sng
        b'\xc9\xf4', b'\x90', ('rel','sng'),      # CMP #$F4 / BCC sng
        b'\x29\x03',                              # AND #$03
        b'\x80', ('rel','tail'),                  # BRA tail
        ('label','p4'), b'\xa9\x04',              # LDA #$04
        b'\x80', ('rel','tail'),                  # BRA tail
        ('label','p5'), b'\xa9\x05',              # LDA #$05
        ('label','tail'),
        b'\x48',                                  # PHA
        b'\x20' + next_byte_jsr.to_bytes(2,'little'),   # JSR 다음바이트 읽기
        b'\x68',                                  # PLA
        b'\x4c' + store_hi_jmp.to_bytes(2,'little'),    # JMP 상위바이트 저장
        ('label','sng'),
        b'\x4c' + single_jmp.to_bytes(2,'little'),      # JMP 단일바이트 경로
    ], org)


def escape_patch_5cfa(org):
    """$5CFA 확장판.

    $5CFA 는 바이트를 A 로 받는다 ($5CF1 의 반환값). 그리고 상위 바이트를
    직접 $01 에 저장한 뒤 다음 바이트를 읽어 $00 에 넣는다 — $950F 쪽과
    구조가 달라 따로 만든다.
    """
    return asm([
        b'\xc9' + bytes([PFX4]), b'\xf0', ('rel','p4'),
        b'\xc9' + bytes([PFX5]), b'\xf0', ('rel','p5'),
        b'\xc9\xf8', b'\xb0', ('rel','sng'),
        b'\xc9\xf4', b'\x90', ('rel','sng'),
        b'\x29\x03',                              # AND #$03
        b'\x80', ('rel','tail'),
        ('label','p4'), b'\xa9\x04', b'\x80', ('rel','tail'),
        ('label','p5'), b'\xa9\x05',
        ('label','tail'),
        b'\x85\x01',                              # STA $01  인덱스 상위
        b'\x20\xf1\x5c',                         # JSR $5CF1  다음 바이트
        b'\x85\x00',                              # STA $00  인덱스 하위
        b'\x60',                                   # RTS
        ('label','sng'), b'\x4c\x0c\x5d',        # JMP $5D0C  단일바이트 경로
    ], org)


def dma_tail():
    """0x9548 이후 꼬리 재구성. 뱅크를 $6A 에서 계산해 먼저 저장한다."""
    return (
        b'\xc2\x20'              # REP #$20        16비트 A (원본과 동일)
        b'\xa6\x55'              # LDX $55         큐 인덱스
        b'\xa5\x6a'              # LDA $6A         (16비트 읽기)
        b'\x29\xff\x00'          # AND #$00FF      인덱스 상위 바이트만
        b'\x4a\x4a'              # LSR A / LSR A   >>2  -> 0 또는 1
        b'\x18'                  # CLC
        b'\x69\xef\x80'          # ADC #$80EF      파라미터|뱅크
        b'\x9d\x00\x07'          # STA $0700,X
        b'\xa5\x69'              # LDA $69         인덱스
        b'\x0a\x0a\x0a\x0a\x0a\x0a'   # ASL x6     x64 (1024 이상은 자연히 감긴다)
        b'\x85\x69'              # STA $69
        b'\xa4\x6d'              # LDY $6D
        b'\x98'                  # TYA
        b'\x0a\x0a\x0a'          # ASL x3
        b'\x69\x00\x18'          # ADC #$1800
        b'\x9d\x80\x07'          # STA $0780,X
        b'\xa5\x69'              # LDA $69
        b'\x69\x00\x00'          # ADC #$0000
        b'\x9d\x40\x07'          # STA $0740,X
        b'\xa9\x40\x00'          # LDA #$0040      전송 크기 64바이트
        b'\x9d\x60\x07'          # STA $0760,X
        b'\xa9\x80\x01'          # LDA #$0180
        b'\x9d\x20\x07'          # STA $0720,X
        b'\x4c\x7c\x95'          # JMP $957C       원래 흐름으로 복귀
    )


def fix_checksum(rom):
    rom[0xFFDC] = rom[0xFFDD] = 0xFF
    rom[0xFFDE] = rom[0xFFDF] = 0x00
    c = 0
    n = len(rom)
    # 4MB 는 2의 거듭제곱이므로 단순 합
    for i in range(0, n, 65536):
        c += sum(rom[i:i+65536])
    c &= 0xFFFF
    comp = c ^ 0xFFFF
    rom[0xFFDC] = comp & 0xFF; rom[0xFFDD] = comp >> 8
    rom[0xFFDE] = c & 0xFF;    rom[0xFFDF] = c >> 8


def apply(src, dst, verbose=True):
    rom = bytearray(open(src, 'rb').read())
    log = []

    # 1) 4MB 확장
    if len(rom) < ROM_4MB:
        rom += b'\xff' * (ROM_4MB - len(rom))
        log.append(f"롬 확장 -> {len(rom)}바이트 (4MB)")

    # 2) 빈 공간 확인 (덮어쓰기 사고 방지)
    for a, n, name in ((FREE_A, 0x60, "이스케이프 판별 A"),
                       (FREE_B, 0x60, "DMA 꼬리"),
                       (FREE_C, 0x40, "이스케이프 판별 C")):
        blk = rom[a:a+n]
        if any(b != 0xFF for b in blk):
            raise SystemExit(f"!! {name} 자리 {a:#08x} 가 비어 있지 않습니다")

    # 3) 이스케이프 판별 확장 — 메인 대사 렌더러
    code = escape_patch(FREE_A, next_byte_jsr=0x94A5, store_hi_jmp=0x9546,
                        single_jmp=0x9522)
    rom[FREE_A:FREE_A+len(code)] = code
    rom[0x00950F:0x00950F+3] = b'\x4c' + (FREE_A & 0xFFFF).to_bytes(2, 'little')
    log.append(f"이스케이프 판별: 0x00950F -> JMP ${FREE_A & 0xFFFF:04X} ({len(code)}바이트)")

    # 3b) 이스케이프 판별 확장 — 옵션/엔딩 렌더러 ($5CFA)
    code_c = escape_patch_5cfa(FREE_C)
    rom[FREE_C:FREE_C+len(code_c)] = code_c
    rom[0x005CFA:0x005CFA+3] = b'\x4c' + (FREE_C & 0xFFFF).to_bytes(2, 'little')
    log.append(f"이스케이프 판별($5CFA): 0x005CFA -> JMP ${FREE_C & 0xFFFF:04X} ({len(code_c)}바이트)")

    # 4) DMA 꼬리 재구성 — 뱅크 = $EF + ($6A >> 2)
    tail = dma_tail()
    rom[FREE_B:FREE_B+len(tail)] = tail
    rom[0x009548:0x009548+3] = b'\x4c' + (FREE_B & 0xFFFF).to_bytes(2, 'little')
    log.append(f"DMA 꼬리: 0x009548 -> JMP ${FREE_B & 0xFFFF:04X} ({len(tail)}바이트)")

    fix_checksum(rom)
    open(dst, 'wb').write(rom)
    if verbose:
        for l in log: print("  " + l)
        print(f"저장: {dst}")
    return rom


if __name__ == "__main__":
    apply(sys.argv[1], sys.argv[2])
