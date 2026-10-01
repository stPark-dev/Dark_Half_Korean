#!/usr/bin/env python3
"""배포용 BPS 패치를 만든다.

python3 darkhalf-kr/mkpatch.py "Dark Half (Japan).sfc" "dist/Dark Half KR.bps" [--dev]

  1. 원본 롬 MD5 확인 (다른 판이면 멈춘다)
  2. 작업 트리가 커밋된 상태인지 확인 (--dev 면 경고만)
  3. 번역 검사(trcheck) -> 통합 빌드 -> 삽입 역검증(verify_insert)
  4. BPS 생성 -> 원본에 다시 적용해 빌드 결과와 바이트로 같은지 확인
"""
import hashlib, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bps

ORIG_MD5 = "55108013f875db3b39da04b8f58489ab"   # Dark Half (Japan), 3MB HiROM
HERE = os.path.dirname(os.path.abspath(__file__))
TSV = os.path.join(HERE, "script_main.tsv")


def run(args, need):
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True)
    if r.returncode != 0 or need not in r.stdout:
        print(r.stdout[-1500:] + r.stderr[-1500:])
        raise SystemExit(f"!! {os.path.basename(args[0])} 실패")
    return r.stdout


def main(src_path, out_path, dev=False):
    src = open(src_path, "rb").read()
    md5 = hashlib.md5(src).hexdigest()
    if md5 != ORIG_MD5:
        raise SystemExit(f"!! 원본 롬 MD5 {md5} — 기대 {ORIG_MD5} (Dark Half (Japan))")

    git = lambda *a: subprocess.run(["git", "-C", HERE] + list(a),
                                    capture_output=True, text=True).stdout.strip()
    commit = git("rev-parse", "--short", "HEAD") or "?"
    dirty = git("status", "--porcelain", "--", ".")
    if dirty:
        msg = f"작업 트리에 커밋되지 않은 변경이 있다 — 패치를 커밋으로 추적할 수 없다\n{dirty}"
        if not dev: raise SystemExit("!! " + msg)
        print("경고: " + msg); commit += "-dirty"

    run([os.path.join(HERE, "trcheck.py"), TSV], "검사 통과")
    with tempfile.TemporaryDirectory() as d:
        kr_path = os.path.join(d, "kr.sfc")
        run([os.path.join(HERE, "build.py"), src_path, TSV, kr_path], "->")
        run([os.path.join(HERE, "verify_insert.py"), src_path, kr_path, TSV], "전부 통과")
        kr = open(kr_path, "rb").read()

    patch = bps.encode(src, kr)
    if bps.apply(patch, src) != kr:
        raise SystemExit("!! 패치 왕복 불일치")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    open(out_path, "wb").write(patch)
    print(f"패치  {out_path}  ({len(patch):,}바이트, 커밋 {commit})")
    print(f"원본  MD5 {md5}  CRC32 {patch[-12:-8][::-1].hex()}  ({len(src):,}바이트)")
    print(f"결과  MD5 {hashlib.md5(kr).hexdigest()}  ({len(kr):,}바이트)")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    main(a[0], a[1], dev="--dev" in sys.argv)
