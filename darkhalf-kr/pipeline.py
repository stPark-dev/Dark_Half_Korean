#!/usr/bin/env python3
"""번역 추출/삽입 파이프라인.

usage:
  pipeline.py export <rom> <out.tsv>
  pipeline.py insert <rom> <in.tsv> <out.sfc>
  pipeline.py roundtrip <rom>          번역 없이 추출->삽입이 원본과 동일한지 검증

구조 (뱅크 0x04):
  포인터 테이블 0x040000..0x040C00 (u16, 뱅크 상대)
  텍스트 영역   0x040C00..0x050000, 런은 0xFF 로 구분
  포인터가 런 중간을 가리키기도 하므로, 런을 '진입점' 단위 세그먼트로 쪼개
  세그먼트별로 번역하고 삽입 시 각 진입점의 새 주소로 모든 포인터를 갱신한다.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dump import load_tbl, decode

BANK = 0x040000
TBL  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "darkhalf.tbl")

def layout(rom):
    """(포인터맵, 텍스트영역, 런목록) 반환"""
    first = rom[BANK] | (rom[BANK+1] << 8)
    n = first // 2
    ptrs = {BANK + 2*i: BANK + (rom[BANK+2*i] | (rom[BANK+2*i+1] << 8)) for i in range(n)}
    lo, hi = BANK + first, BANK + 0x10000
    runs = []; s = lo
    for i in range(lo, hi):
        if rom[i] == 0xFF:
            runs.append((s, i - s)); s = i + 1
    return ptrs, (lo, hi), runs

def segments(rom):
    """런을 진입점 단위 세그먼트로 분해"""
    ptrs, (lo, hi), runs = layout(rom)
    by_target = {}
    for p, t in ptrs.items(): by_target.setdefault(t, []).append(p)
    out = []
    for ridx, (ra, rl) in enumerate(runs):
        eps = sorted(t for t in by_target if ra <= t < ra + rl)
        bounds = ([ra] if (not eps or eps[0] != ra) else []) + eps + [ra + rl]
        bounds = sorted(set(bounds))
        for k in range(len(bounds) - 1):
            a, b = bounds[k], bounds[k+1]
            out.append({"run": ridx, "addr": a, "len": b - a,
                        "ptrs": sorted(by_target.get(a, []))})
        if rl == 0:
            out.append({"run": ridx, "addr": ra, "len": 0, "ptrs": sorted(by_target.get(ra, []))})
    return out, runs, ptrs, (lo, hi)

def cmd_export(rom_path, out):
    rom = open(rom_path, 'rb').read()
    t = load_tbl(TBL)
    try:
        from kanji import KANJI
    except Exception:
        KANJI = None
    segs, runs, ptrs, _ = segments(rom)
    with open(out, 'w', encoding='utf-8') as f:
        f.write("#id\trun\taddr\tlen\tptrs\torig_hex\torig_text\treadable\ttranslation\n")
        for i, s in enumerate(segs):
            raw = rom[s["addr"]:s["addr"]+s["len"]]
            f.write(f"{i}\t{s['run']}\t{s['addr']:#08x}\t{s['len']}\t"
                    f"{','.join(f'{p:#08x}' for p in s['ptrs'])}\t{raw.hex()}\t"
                    f"{decode(raw, t)}\t{decode(raw, t, KANJI)}\t\n")
    print(f"세그먼트 {len(segs)}개 (런 {len(runs)}개, 포인터 {len(ptrs)}개) -> {out}")

def cmd_insert(rom_path, tsv, out):
    rom = bytearray(open(rom_path, 'rb').read())
    segs, runs, ptrs, (lo, hi) = segments(bytes(rom))
    rows = []
    for line in open(tsv, encoding='utf-8'):
        if line.startswith('#'): continue
        c = line.rstrip('\n').split('\t')
        rows.append(c)
    assert len(rows) == len(segs), f"행 수 불일치 {len(rows)} != {len(segs)}"
    import krcodec, json
    t = load_tbl(TBL)
    trs = [c[8] if len(c) > 8 else "" for c in rows]
    todo = [x for x in trs if x.strip()]
    codes, freq, st = krcodec.allocate(todo, t) if todo else ({}, {}, None)
    if st:
        print(f"번역 세그먼트 {len(todo)}개 | 고유 음절 {st['unique']}/{st['capacity']}자")
        print(f"  단일바이트 배정 {st['single_slots']}자가 출현의 "
              f"{st['occ1']/(st['occ1']+st['occ2'])*100:.0f}% 담당 -> 평균 {st['avg_bytes']:.2f} 바이트/음절")
        patch_font(rom, codes)
        json.dump({ch: slot.hex() for ch, slot in codes.items()},
                  open(out + ".codes.json", "w"), ensure_ascii=False, indent=1)
    newbytes = []
    for c, sg in zip(rows, segs):
        tr = c[8] if len(c) > 8 else ""
        newbytes.append(bytes.fromhex(c[5]) if not tr.strip()
                        else krcodec.encode(tr, codes, t))
    INPLACE = os.environ.get("DH_INPLACE") == "1"
    if INPLACE:
        # 제자리 모드: 세그먼트를 원래 길이에 맞춰 채운다. 주소가 하나도 안 바뀌므로
        # 포인터 갱신이 불필요하고, 뱅크 밖/코드에서의 참조도 그대로 유효하다.
        over = []
        for i, (sg, nb) in enumerate(zip(segs, newbytes)):
            cap = sg["len"]
            if len(nb) > cap: over.append((i, len(nb), cap)); continue
            newbytes[i] = nb + bytes([0x20]) * (cap - len(nb))   # 공백으로 패딩
        if over:
            print(f"!! 길이 초과 세그먼트 {len(over)}개 (제자리 모드에서는 삽입 불가)")
            for i, n, c in over[:10]:
                print(f"   #{i}: {n}바이트 필요 / {c}바이트 가능 (초과 {n-c})")
            sys.exit(1)
        for sg, nb in zip(segs, newbytes):
            rom[sg["addr"]:sg["addr"]+len(nb)] = nb
        print(f"제자리 삽입 완료 (주소 변경 없음, 포인터 갱신 불필요)")
        fix_checksum(rom); open(out, 'wb').write(rom)
        print(f"저장: {out}"); return
    # 런 단위로 재조립
    out_buf = bytearray(); newaddr = {}
    by_run = {}
    for i, s in enumerate(segs): by_run.setdefault(s["run"], []).append(i)
    for ridx in range(len(runs)):
        for i in by_run.get(ridx, []):
            newaddr[segs[i]["addr"]] = lo + len(out_buf)
            out_buf += newbytes[i]
        out_buf.append(0xFF)
    size, cap = len(out_buf), hi - lo
    print(f"재조립 {size}바이트 / 용량 {cap}바이트 ({size-cap:+d})")
    if size > cap:
        print(f"!! 용량 초과 {size-cap}바이트. 뱅크 재배치 없이는 삽입 불가."); sys.exit(1)
    rom[lo:lo+size] = out_buf
    for i in range(lo+size, hi): rom[i] = 0xFF
    # 포인터 갱신
    for p, tgt in ptrs.items():
        na = newaddr.get(tgt)
        if na is None: continue
        v = na - BANK
        rom[p] = v & 0xFF; rom[p+1] = v >> 8
    fix_checksum(rom)
    open(out, 'wb').write(rom)
    print(f"저장: {out}")

FONT_BASE = {None: 0x2F0000, 0xF5: 0x2F4000, 0xF6: 0x2F8000, 0xF7: 0x2FC000}

def patch_font(rom, codes):
    """배정된 음절의 글리프를 폰트 영역에 기록"""
    from makefont import encode as enc_glyph
    for ch, slot in codes.items():
        if len(slot) == 1:
            a = FONT_BASE[None] + slot[0]*64
        else:
            base = FONT_BASE.get(slot[0])
            if base is None:
                raise ValueError(f"알 수 없는 뱅크 {slot[0]:#02x} ({ch})")
            a = base + slot[1]*64
        rom[a:a+64] = enc_glyph(ch)

def fix_checksum(rom):
    rom[0xFFDC] = rom[0xFFDD] = 0xFF; rom[0xFFDE] = rom[0xFFDF] = 0x00
    c = (sum(rom[:0x200000]) + 2*sum(rom[0x200000:0x300000])) & 0xFFFF
    comp = c ^ 0xFFFF
    rom[0xFFDC] = comp & 0xFF; rom[0xFFDD] = comp >> 8
    rom[0xFFDE] = c & 0xFF;    rom[0xFFDF] = c >> 8

def cmd_roundtrip(rom_path):
    import tempfile, filecmp
    d = tempfile.mkdtemp()
    tsv = os.path.join(d, "s.tsv"); out = os.path.join(d, "r.sfc")
    cmd_export(rom_path, tsv)
    cmd_insert(rom_path, tsv, out)
    a = open(rom_path, 'rb').read(); b = open(out, 'rb').read()
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    print(f"\n왕복 검증: 차이 {len(diff)}바이트", 
          "-> 완전 일치 (파이프라인 정확)" if not diff else f"-> 첫 차이 {[hex(x) for x in diff[:8]]}")

if __name__ == "__main__":
    c = sys.argv[1]
    if   c == "export":    cmd_export(sys.argv[2], sys.argv[3])
    elif c == "insert":    cmd_insert(sys.argv[2], sys.argv[3], sys.argv[4])
    elif c == "roundtrip": cmd_roundtrip(sys.argv[2])
