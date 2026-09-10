#!/usr/bin/env python3
"""몬스터·화자 이름표 (0x04f672 ~ 0x04f8f9) — 구조 해독.

## 한때 「미해결」이라고 적어 뒀던 것

PROGRESS 4.10 은 이 표를 「엔트리가 서로 겹쳐 읽힌다 / 절반만 가능」으로
봤다. 겹친 게 아니라 **읽는 법을 몰랐던 것**이다. 아이템표(4.37)와 같은
조립 언어를 쓴다.

    EE lo hi      ptr 로 꼬리 점프한다. **이 엔트리는 여기서 끝난다**
    F0 C4 lo hi   ptr 의 문자열을 끼워 넣고 계속 읽는다
    EB N          단어표 N 번을 끼워 넣는다
    0xFF          끝

핵심은 **<EE> 도 종료자라는 것**이다. 그래서 엔트리 사이에 0xFF 가 없는
곳이 많고, 0xFF 로만 자르면 여러 엔트리가 하나로 뭉쳐 보인다. 그렇게 뭉친
덩어리를 보고 「겹쳐 읽힌다」고 판단했었다.

제대로 자르면 **107 엔트리**가 나온다 (0xFF 로만 자르면 72개).

    0x04f691  ジャイアント + EE->0x04f68c(バット)   = ジャイアントバット
    0x04f69b  Ｐ           + EE->0x04f68c          = Ｐバット
    0x04f708  F0C4->0x04f701(コボルド) + Ｋ         = コボルドＫ

「F7 비글리프 참조 5개」(4.10)도 오해였다. `f0c401f74b` 를 순차로 훑으면
`f7 4b` 가 F7 이스케이프로 보이는데, 실제로는 `F0 C4` 의 포인터 하이바이트와
그 뒤 글자다. 같은 이유로 「몬스터 이름에 뱅크 이스케이프 14곳」도 0곳이다.

## 이 표는 타일 직접이다 (한글 음절이 전부 단일바이트여야 한다)

원본이 쓰는 2바이트 이스케이프 수를 표별로 세면 갈린다.

    아이템·장비·마법표  0곳    <- 타일 직접(확인됨)
    몬스터·화자 이름표  0곳    <- 여기
    단어표             47곳   <- 대사 렌더러
    메인 대사        3,432곳  <- 대사 렌더러

107개 이름에 한 곳도 없다. 대사 렌더러를 쓴다면 한자가 섞였을 것이다
(단어표는 57엔트리에 47곳을 쓴다). 타일 직접으로 본다.
"""
import sys, os, unicodedata
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LO, HI = 0x04f672, 0x04f8f9
BANK = 0x040000


def bounds(rom, lo=LO, hi=HI):
    """엔트리 경계 [(시작, 끝)]. 0xFF 또는 <EE> lo hi 로 끝난다."""
    out, a = [], lo
    while a < hi:
        s = a
        while a < hi:
            b = rom[a]
            if b == 0xFF: a += 1; break
            if b == 0xEE: a += 3; break
            if b == 0xF0 and rom[a+1] == 0xC4: a += 4; continue
            a += 1
        out.append((s, a))
    return out


def assemble(rom, a, depth=0, words_slots=None):
    """엔트리를 조립기가 보는 대로 편다."""
    out = []
    if depth > 8: return out
    while True:
        b = rom[a]
        if b == 0xFF: return out
        if b == 0xEE:
            return out + assemble(rom, BANK | rom[a+1] | (rom[a+2] << 8),
                                  depth+1, words_slots)
        if b == 0xF0 and rom[a+1] == 0xC4:
            out += assemble(rom, BANK | rom[a+2] | (rom[a+3] << 8),
                            depth+1, words_slots)
            a += 4; continue
        if b == 0xEB and words_slots is not None and rom[a+1] < len(words_slots):
            out += assemble(rom, words_slots[rom[a+1]][0], depth+1, words_slots)
            a += 2; continue
        out.append(b); a += 1


def readable(bs, tbl):
    """조립 결과를 사람이 읽을 문자열로. 0x01/0x02 는 탁점·반탁점 결합이다."""
    o = []
    for b in bs:
        if b in (0x01, 0x02):
            if o: o[-1] = unicodedata.normalize('NFC', o[-1] + ('゙' if b == 0x01 else '゚'))
            continue
        x = tbl.get(bytes([b])) or tbl.get(b) or f'<{b:02x}>'
        o.append(x)
    return ''.join(o)


def entries(rom, tbl, words_slots=None):
    """[(시작, 끝, 원문)] 107개."""
    out = []
    for s, e in bounds(rom):
        bs = assemble(rom, s, words_slots=words_slots)
        if bs: out.append((s, e, readable(bs, tbl)))
    return out


# (원문, 한국어). None 이면 원본 바이트를 그대로 둔다.
#
# 이 표도 타일 직접이라 음절이 전부 단일바이트여야 하고 창 장식 칸(4.38)도
# 피해야 한다. 쓸 수 있는 칸 110 개는 아이템·메뉴·인물 이름이 이미 다 쓰고
# 있어 **새 음절을 하나도 못 넣는다** — 남은 3칸은 「나·을·는」(빈도 311·
# 513·631)이 쥐고 있어 내주면 대사가 무너진다.
#
# 그래서 **이미 단일바이트인 음절로만 지어지는 것만** 옮긴다 (PROGRESS 4.44).
# 박쥐·오크·코볼드·해골·고블린·도마뱀 처럼 낱말이 안 되는 것은 그대로 둔다.
WORDS = [
 ("ようへいＡ",        "무사Ａ"),
 ("ディヴィズウ",       None),
 ("ルキュ",           None),      # <EB> 단어표 참조
 ("ヴェルギル",        None),
 ("アーヴァ",          None),
 ("Ｇバット",          None),      # 박쥐 — 박·쥐 가 없다
 ("ジャイアントバット",   None),
 ("Ｐバット",          None),
 ("ポイズンバット",      None),
 ("Ｖバット",          None),
 ("バンパイアバット",     None),
 ("スライム",          None),      # 점액 — 점·액 이 없다
 ("Ｐスライム",         None),
 ("ポイズンスライム",     None),
 ("Ｇスライム",         None),
 ("ジャイアントスライム",  None),
 ("Ｇオーズ",          None),
 ("グレイオーズ",       None),
 ("オーク",           None),      # 오크 — 크 가 없다
 ("オークＫ",          None),
 ("オークキング",       None),
 ("オークＬ",          None),
 ("オークロード",       None),
 ("コボルド",          None),      # 코볼드 — 볼 이 없다
 ("コボルドＫ",         None),
 ("コボルドキング",      None),
 ("Ｈハウンド",         "Ｈ개"),
 ("ヘルハウンド",       "지옥"),     # + <EE>개
 ("ケルベロス",        None),
 ("Ｗウルフ",          "Ｗ이리"),
 ("ウェアウルフ",       "사람이리"),
 ("Ｗタイガー",         None),      # 호랑이 — 랑 이 없다
 ("ウェアタイガー",      None),
 ("リザード",          None),      # 도마뱀 — 뱀 이 없다
 ("リザードマン",       None),
 ("Ｄニュート",         None),
 ("ドラゴニュート",      None),
 ("Ｄナイト",          "Ｄ기사"),
 ("ドラゴンナイト",      "용기사"),
 ("ガーゴイル",        "가고일"),
 ("Ｇデーモン",         "Ｇ마신"),
 ("グレーターデーモン",   "대마신"),
 ("Ｌデーモン",         "Ｌ"),
 ("レッサーデーモン",     "소마신"),
 ("Ａデーモン",         "Ａ"),
 ("アークデーモン",      "상마신"),
 ("ゾンビ",           "죽은자"),
 ("スケルトン",        None),      # 해골 — 골 이 없다
 ("Ｓナイト",          "Ｓ기사"),
 ("スケルトンナイト",     None),
 ("ゴーレム",          "거상"),
 ("Ｉゴーレム",         "Ｉ"),
 ("アイアンゴーレム",     "강철거상"),
 ("タロス",           None),
 ("Ｍドラゴン",         "Ｍ용"),
 ("マスタードラゴン",     "대용"),
 ("Ｃドラゴン",         "Ｃ"),
 ("カッパードラゴン",     "강철용"),
 ("Ｓドラゴン",         "Ｓ"),
 ("シルバードラゴン",     "은용"),
 ("Ｇドラゴン",         "Ｇ"),
 ("ゴールドドラゴン",     "빛용"),
 ("ゴブリン",          None),      # 고블린 — 블·린 이 없다
 ("Ｈゴブリン",         None),
 ("ホブゴブリン",       None),
 ("Ｇスラッグ",         None),
 ("ジャイアントスラッグ",  None),
 ("Ｐスラッグ",         None),
 ("ポイズンスラッグ",     None),
 ("キマイラ",          None),
 ("Ｓオーガ",          "Ｓ오거"),
 ("ストーンオーガ",      "돌오거"),
 ("Ｆオーガ",          "Ｆ"),
 ("ファイアオーガ",      "불오거"),
 ("バム",             None),
 ("ようへいＢ",        "무사Ｂ"),
 ("ようへいＣ",        "무사Ｃ"),
 ("ようへいＤ",        "무사Ｄ"),
 ("Ｇナイト",          "Ｇ기사"),
 ("ゴールドナイト",      "빛기사"),
 ("Ｓナイト",          "Ｓ기사"),
 ("シルバーナイト",      "은기사"),
 ("メイド",           None),      # 하녀 — 녀 가 없다
 ("おんな",           None),      # 여자 — 여 가 없다
 ("ソルジャー",        "검사"),
 ("まどうし",          "마도사"),
 ("とうぞく",          None),      # 도적 — 적 이 없다
 ("しんぷ",           "사제"),
 ("おとこ",           "장정"),
 ("じいさん",          "어르신"),
 ("こども",           "아이"),
 ("ばあさん",          "노모"),
 ("ＸＸＸ",           None),
 ("ルキュのすうはいしゃ",  "<EB><00>의 신도"),
 ("おやかた",          "대장"),
 ("カイオス",          None),
 ("ようへいＥ",        "무사Ｅ"),
 ("ようへいＦ",        "무사Ｆ"),
 ("レイ",             "레이"),
 ("ホセ",             "호세"),
 ("ようへいＧ",        "무사Ｇ"),
 ("ようへいＨ",        "무사Ｈ"),
 ("カレン",           None),
 ("しかばね",          "주검"),
 ("ようへいＩ",        "무사Ｉ"),
 ("ファルコ",          None),
 ("ウィンダム",        None),
]


# 칸이 모자라 **접미어 공유를 그대로 쓰는** 엔트리. 앞머리만 적는다.
# 나머지 <EE> 엔트리는 이름을 통째로 적고 <EE> 를 빈 문자열로 보낸다.
#
# 왜 이렇게 하나 — <EE> 를 한국어 바로 뒤로 당기면 뒤에 남는 칸이 **유령
# 엔트리**가 된다. 이 표에는 포인터 표가 없어(뱅크04 를 훑어도 엔트리 시작을
# 가리키는 워드가 0개다) 게임이 순차로 세는 것으로 봐야 하고, 그러면 4.29 의
# 화면 붕괴와 같은 부류가 된다. 그래서 **<EE> 는 원래 자리(엔트리 끝)에 두고**
# 남는 칸은 한국어와 <EE> 사이에 공백으로 채운다 — 점프가 일어난 뒤라 화면에
# 안 나온다.
JUMP_KEEP = {0x04f71e, 0x04f784, 0x04f78f, 0x04f7b8,
             0x04f7d6, 0x04f7e2, 0x04f7ee, 0x04f83c}
EMPTY = 0x04f677          # 0xFF 하나. <EE> 를 여기로 보내면 빈 문자열이다.


def pairs(rom):
    out = []
    for (s, e), (_, kr) in zip(bounds(rom), WORDS):
        if kr: out.append((e - s, kr))
    return out


def texts():
    return [kr for _, kr in WORDS if kr]


def apply(rom, codes, tbl):
    """제자리 삽입. <EE> 로 끝나는 엔트리는 그 3바이트를 지킨다."""
    import krcodec
    rom = bytearray(rom); over = []
    for (s, e), (_, kr) in zip(bounds(bytes(rom)), WORDS):
        if not kr: continue
        raw = bytes(rom[s:e])
        tail = raw[-3:] if raw[-3:-1] and raw[-3] == 0xEE else None
        cap = (e - s - 3) if tail else (e - s - 1)      # 종료자/꼬리 몫
        b = krcodec.encode(kr, codes, tbl)
        if len(b) > cap: over.append((s, kr, len(b), cap)); continue
        if tail:
            t = tail if s in JUMP_KEEP else bytes([0xEE, EMPTY & 0xFF, (EMPTY >> 8) & 0xFF])
            if s in JUMP_KEEP and len(b) != cap:
                over.append((s, kr, len(b), cap)); continue    # 앞머리는 딱 맞아야 한다
            rom[s:e] = b + bytes([0x20]) * (cap - len(b)) + t
        else:
            rom[s:e] = b + bytes([0x20]) * (cap - len(b)) + bytes([0xFF])
    return bytes(rom), over


def verify(new, orig, codes, tbl):
    import krcodec
    bad = []
    for (s, e), (_, kr) in zip(bounds(orig), WORDS):
        if not kr: continue
        raw = orig[s:e]
        tail = raw[-3:] if raw[-3:-1] and raw[-3] == 0xEE else None
        cap = (e - s - 3) if tail else (e - s - 1)
        want = krcodec.encode(kr, codes, tbl)
        if tail:
            t = tail if s in JUMP_KEEP else bytes([0xEE, EMPTY & 0xFF, (EMPTY >> 8) & 0xFF])
            exp = want + bytes([0x20]) * (cap - len(want)) + t
        else:
            exp = want + bytes([0x20]) * (cap - len(want)) + bytes([0xFF])
        if bytes(new[s:e]) != exp: bad.append((s, kr))
    return bad


if __name__ == "__main__":
    from dump import load_tbl
    import words
    rom = open(sys.argv[1], 'rb').read()
    tbl = load_tbl(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "darkhalf.tbl"))
    ws = words.slots(rom)
    es = entries(rom, tbl, ws)
    print(f"엔트리 {len(es)}개")
    for s, e, ja in es:
        print(f"  {s:#08x}-{e:#08x} ({e-s:2d}B)  {ja}")
