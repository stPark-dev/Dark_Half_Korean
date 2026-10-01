#!/usr/bin/env python3
"""BPS 패치 생성·적용 테스트.

python3 darkhalf-kr/test_bps.py ["Dark Half (Japan).sfc"]
롬 경로를 주면 실제 빌드 결과로 왕복까지 확인한다.
"""
import os, sys, random, hashlib, tempfile, subprocess, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bps

# 롬 경로는 클래스 정의(skipUnless) 전에 읽어야 한다
ROM = sys.argv.pop(1) if __name__ == "__main__" and len(sys.argv) > 1 else None


class TestBps(unittest.TestCase):
    def roundtrip(self, src, tgt):
        p = bps.encode(src, tgt)
        self.assertTrue(p.startswith(b"BPS1"))
        self.assertEqual(bps.apply(p, src), tgt)
        return p

    def test_identical(self):
        src = bytes(range(256)) * 16
        self.roundtrip(src, src)

    def test_changed_bytes(self):
        rnd = random.Random(1)
        src = bytes(rnd.randrange(256) for _ in range(5000))
        tgt = bytearray(src)
        for i in rnd.sample(range(5000), 300): tgt[i] ^= 0x5A
        self.roundtrip(src, bytes(tgt))

    def test_target_longer_and_shorter(self):
        src = b"abcdefgh" * 100
        self.roundtrip(src, src + b"\xff" * 3000 + b"tail")
        self.roundtrip(src, src[:123])
        self.roundtrip(b"", b"new data")
        self.roundtrip(src, b"")

    def test_runs_are_compact(self):
        # 3MB -> 4MB 확장 구간은 대부분 0xFF 채움이다. 리터럴로 쓰면 1MB가 된다.
        src = b"\x00" * 1000
        tgt = src + b"\xff" * 1_000_000
        p = self.roundtrip(src, tgt)
        self.assertLess(len(p), 200)

    def test_wrong_source_rejected(self):
        src = b"original" * 50
        p = bps.encode(src, b"patched!" * 50)
        with self.assertRaises(bps.BpsError):
            bps.apply(p, b"Original" * 50)

    def test_corrupt_patch_rejected(self):
        src = b"original" * 50
        p = bytearray(bps.encode(src, b"patched!" * 50))
        p[10] ^= 1
        with self.assertRaises(bps.BpsError):
            bps.apply(bytes(p), src)


class TestRealRom(unittest.TestCase):
    """mkpatch 가 만든 패치를 원본에 적용하면 빌드 결과와 바이트로 같다."""

    @unittest.skipUnless(ROM, "원본 롬 경로가 없다")
    def test_mkpatch_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "kr.bps")
            r = subprocess.run([sys.executable, "darkhalf-kr/mkpatch.py", ROM, out, "--dev"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            src = open(ROM, "rb").read()
            tgt = bps.apply(open(out, "rb").read(), src)
            self.assertEqual(len(tgt), 4 * 1024 * 1024)
            self.assertIn(hashlib.md5(tgt).hexdigest(), r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
