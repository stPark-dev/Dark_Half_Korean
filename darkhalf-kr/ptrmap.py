#!/usr/bin/env python3
"""포인터 <-> 메시지 매핑 및 런 분류.

리포인팅의 전제는 '모든 포인터가 어디를 가리키는지' 아는 것이다.
추가로 각 텍스트 런이 길이를 바꿔도 되는지 분류한다.

  free        : 진입점 1개. 길이 자유. 번역 시 가장 편한 대상.
  multi       : 진입점 여러 개, 간격 불규칙. 모든 진입점을 함께 리포인팅해야 함.
  fixed-array : 진입점 간격이 전부 동일. 고정폭 레코드 배열이므로 레코드 크기 유지 필수.
"""
import sys, json, collections

BANK04 = 0x040000

def bank04_pointers(rom):
    first = rom[BANK04] | (rom[BANK04+1] << 8)
    n = first // 2
    return {BANK04 + 2*i: BANK04 + (rom[BANK04+2*i] | (rom[BANK04+2*i+1] << 8))
            for i in range(n)}, BANK04 + first

def run_start(rom, a, floor):
    i = a
    while i > floor and rom[i-1] != 0xFF: i -= 1
    return i

def classify(entries):
    if len(entries) == 1: return "free"
    gaps = [entries[i+1]-entries[i] for i in range(len(entries)-1)]
    return "fixed-array" if len(set(gaps)) == 1 else "multi"

def main(rom_path, out_json):
    rom = open(rom_path, 'rb').read()
    ptrs, floor = bank04_pointers(rom)
    by_target = collections.defaultdict(list)
    for p, tgt in ptrs.items(): by_target[tgt].append(p)

    runs = collections.defaultdict(list)
    for tgt in sorted(by_target): runs[run_start(rom, tgt, floor)].append(tgt)

    out = []
    kinds = collections.Counter()
    for rs in sorted(runs):
        eps = sorted(runs[rs])
        end = rom.find(b'\xFF', rs)
        kind = classify(eps)
        kinds[kind] += 1
        out.append({
            "run": rs, "end": end, "len": end-rs, "kind": kind,
            "entries": [{"target": e, "pointers": sorted(by_target[e])} for e in eps],
            "stride": (eps[1]-eps[0]) if kind == "fixed-array" else None,
        })
    json.dump({"bank": BANK04, "pointer_count": len(ptrs), "runs": out},
              open(out_json, 'w'), indent=1)

    print(f"뱅크 0x04 포인터 {len(ptrs)}개 -> 고유 목표 {len(by_target)}개 -> 텍스트 런 {len(runs)}개")
    print("런 분류:", dict(kinds))
    free_bytes = sum(r["len"] for r in out if r["kind"] == "free")
    tot = sum(r["len"] for r in out)
    print(f"길이 자유(free) 런: {kinds['free']}개 / {free_bytes}바이트 "
          f"(전체 {tot}바이트의 {free_bytes/tot*100:.0f}%)")
    for k in ("multi", "fixed-array"):
        rs = [r for r in out if r["kind"] == k]
        if rs:
            print(f"  {k}: {len(rs)}개, {sum(r['len'] for r in rs)}바이트"
                  + (f", stride={sorted(set(r['stride'] for r in rs))}" if k == "fixed-array" else ""))
    print(f"저장: {out_json}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "darkhalf-kr/ptrmap.json")
