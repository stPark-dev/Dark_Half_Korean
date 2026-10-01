#!/usr/bin/env python3
"""BPS 패치 생성·적용 (byuu 의 BPS1 형식).

배포는 롬이 아니라 패치다. Flips·beat·RomPatcher.js 등 흔한 도구가 BPS 를
읽는다. 원본·결과·패치 자체의 CRC32 가 들어 있어 틀린 롬에 적용하면
도구가 거부한다.

  BPS1 | 원본 크기 | 결과 크기 | 메타 크기(0) | 동작... | crc(원본) crc(결과) crc(패치)
  동작 = varint((길이-1) << 2 | 종류)
    0 SourceRead  같은 위치의 원본을 복사
    1 TargetRead  뒤따르는 리터럴
    3 TargetCopy  이미 쓴 결과를 복사 (같은 바이트 반복 구간에 쓴다)
"""
import zlib


class BpsError(ValueError):
    pass


def _num(n):
    out = bytearray()
    while True:
        x = n & 0x7F; n >>= 7
        if n == 0:
            out.append(0x80 | x); return bytes(out)
        out.append(x); n -= 1


def _read_num(p, i):
    data, shift = 0, 1
    while True:
        if i >= len(p): raise BpsError("패치가 잘렸다")
        x = p[i]; i += 1
        data += (x & 0x7F) * shift
        if x & 0x80: return data, i
        shift <<= 7; data += shift


def _crc(b):
    return zlib.crc32(b).to_bytes(4, "little")


RUN = 16      # 같은 바이트가 이만큼 이어지면 TargetCopy 로 쓴다


def encode(source, target):
    out = bytearray(b"BPS1" + _num(len(source)) + _num(len(target)) + _num(0))
    lit = bytearray()
    tro = 0                          # TargetCopy 상대 위치 기준
    i, n = 0, len(target)

    def flush():
        if lit:
            out.extend(_num(((len(lit) - 1) << 2) | 1)); out.extend(lit); lit.clear()

    while i < n:
        j = i
        while j < n and j < len(source) and target[j] == source[j]: j += 1
        if j - i >= 4 or (j > i and j == n):
            flush(); out.extend(_num(((j - i - 1) << 2) | 0)); i = j; continue
        j = i + 1
        while j < n and target[j] == target[i]: j += 1
        if j - i >= RUN and not (i < len(source) and target[i] == source[i]):
            # 첫 바이트는 리터럴, 나머지는 그 바이트부터 겹쳐 복사한다
            lit.append(target[i]); flush()
            d = i - tro
            out.extend(_num(((j - i - 2) << 2) | 3))
            out.extend(_num((abs(d) << 1) | (1 if d < 0 else 0)))
            tro = i + (j - i - 1)
            i = j; continue
        lit.append(target[i]); i += 1
    flush()
    out += _crc(source) + _crc(target)
    out += _crc(bytes(out))
    return bytes(out)


def apply(patch, source):
    if len(patch) < 16 or patch[:4] != b"BPS1": raise BpsError("BPS 패치가 아니다")
    if _crc(patch[:-4]) != patch[-4:]: raise BpsError("패치 파일이 손상됐다")
    if _crc(source) != patch[-12:-8]: raise BpsError("원본 롬이 다르다 (CRC32 불일치)")
    i = 4
    ss, i = _read_num(patch, i); ts, i = _read_num(patch, i); ms, i = _read_num(patch, i)
    if ss != len(source): raise BpsError("원본 롬 크기가 다르다")
    i += ms
    out = bytearray(); sro = tro = 0
    end = len(patch) - 12
    while i < end:
        d, i = _read_num(patch, i)
        kind, length = d & 3, (d >> 2) + 1
        if kind == 0:
            out += source[len(out):len(out) + length]
        elif kind == 1:
            out += patch[i:i + length]; i += length
        else:
            r, i = _read_num(patch, i)
            r = -(r >> 1) if r & 1 else r >> 1
            if kind == 2:
                sro += r; out += source[sro:sro + length]; sro += length
            else:
                tro += r
                for _ in range(length): out.append(out[tro]); tro += 1
    if len(out) != ts: raise BpsError("결과 크기가 다르다")
    if _crc(bytes(out)) != patch[-8:-4]: raise BpsError("결과 CRC32 불일치")
    return bytes(out)
