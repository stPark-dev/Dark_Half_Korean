-- Mesen2 Lua: 메뉴 폰트 글리프 조립 버퍼에 쓰는 루틴 (v3)
--
-- 대상 주소를 로그로 확정했다. 추측이 아니다.
--
-- dma_log3.txt 분석 결과
--   WRAM -> VRAM $0000~$1FFF 전송 434건. 그 소스가
--     $7E:2C00xx  246건
--     $7E:2B00xx  178건
--     $7E:27xx      8건
--   전송 크기 8~60바이트로 잘게 쪼개져 있다 = 글리프를 조립해 부분 전송한다.
--
-- v1(tracewram.lua)은 $7E:273B 만 봤다. 그 주소도 위 목록에 있지만 8건뿐이고
-- 본체는 $2B00~$2CFF 다. v1 이 실패한 이유가 이것일 수 있다.
-- v2(tracewram2.lua)가 본 $7E:8100~8600 은 타일맵이었다 (쓰이는 값이
-- 00 01 02 03 / 20 / 23 / 32 같은 타일 인덱스였다).
--
-- 이 스크립트는 조립 버퍼에 쓰는 명령의 PC 를 모은다. 루틴을 알면 원본 폰트가
-- 롬 어디에서 오는지 읽어서 확정할 수 있다.

local LOG = "/home/stpark/다운로드/hanguel/darkhalf-kr/wram_write3.txt"
local LO, HI = 0x7E2B00, 0x7E2CFF
local f = io.open(LOG, "w")
local seen, n = {}, 0

local function onWrite(addr, value)
  local st = emu.getState()
  local pc = st["cpu.pc"] or 0
  local k  = st["cpu.k"]  or 0
  local key = string.format("%02X%04X", k, pc)
  if seen[key] then return end
  seen[key] = true
  n = n + 1
  local line = string.format("PC=$%02X:%04X  ->  WRAM $%06X = %02X  (a=%04X x=%04X y=%04X dbr=%02X)",
    k, pc, addr, value,
    st["cpu.a"] or 0, st["cpu.x"] or 0, st["cpu.y"] or 0, st["cpu.dbr"] or 0)
  emu.log(line); f:write(line .. "\n"); f:flush()
end

emu.addMemoryCallback(onWrite, emu.callbackType.write, LO, HI)
emu.log(string.format("WRAM v3 추적 시작. $%06X~$%06X (글리프 조립 버퍼)", LO, HI))
emu.log("-> wram_write3.txt")
