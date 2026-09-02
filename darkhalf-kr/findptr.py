#!/usr/bin/env python3
"""포인터 테이블 탐색.

메시지 경계를 추측으로 정하면 반드시 틀린다. 포인터 테이블을 찾아
경계를 확정한 뒤, 각 메시지의 마지막 바이트를 보면 종료 코드가 드러난다.

단조 증가하는 u16 런을 찾고, 그 값들이 텍스트 구간을 가리키는지 검증한다.
"""
import sys, struct

def find_u16_tables(rom, lo, hi, min_run=12, min_gap=4, max_gap=800):
    """값이 [lo,hi)이고 단조 증가하는 u16 런"""
    out=[]; n=len(rom); i=0
    while i < n-4:
        vals=[]; p=i
        while p < n-1:
            v=rom[p]|(rom[p+1]<<8)
            if not (lo <= v < hi): break
            if vals:
                g=v-vals[-1]
                if not (min_gap <= g <= max_gap): break
            vals.append(v); p+=2
        if len(vals) >= min_run:
            out.append((i, len(vals), vals[0], vals[-1]))
            i = p
        else:
            i += 2
    return out

if __name__=="__main__":
    rom=open(sys.argv[1],'rb').read()
    # 대사 뱅크 0x042000-0x04F000 을 가리키는 16비트 포인터 (뱅크베이스 0x040000)
    for base,label in ((0x040000,"bank 0x04"),):
        lo,hi=0x2000,0xF000
        tabs=find_u16_tables(rom, lo, hi)
        tabs.sort(key=lambda t:-t[1])
        print(f"[{label}] 후보 테이블 {len(tabs)}개 (상위 10)")
        for off,cnt,v0,vN in tabs[:10]:
            print(f"  테이블 @{off:#08x}  항목 {cnt:4d}  첫값 {v0:#06x}(->{base+v0:#08x})  끝값 {vN:#06x}(->{base+vN:#08x})")
