-- Mesen2 Lua: 메뉴 글리프 조립 버퍼에 쓰는 루틴을 잡는다 (v2)
--
-- v1 과의 차이: 대상 주소를 추측하지 않는다.
-- v1 은 $7E:273B 를 봤는데 그건 실패한 추적들에서 나온 추정이었다.
-- v2 는 dma_log3.txt 로 확정한 버퍼를 본다.
--
-- dma_log3.txt 에서 확정된 사실
--   메인 폰트  src=$EF:xxxx size=64  (172건 전부 64바이트 = 16x16 글리프 1개)
--              -> ROM 0x2F0000 에서 글리프 단위로 직접 DMA. 이미 아는 경로다.
--   메뉴 텍스트 src=$7E:81xx~85xx -> VRAM $F1xx~$F5xx (델타 일정 0x7016)
--              -> WRAM 에서 조립한 뒤 DMA. 그래서 롬 바이트 검색이 실패했다.
--
-- 이 스크립트는 그 WRAM 버퍼에 쓰는 명령의 PC 를 모은다.
-- PC 를 알면 그 루틴을 읽어 원본 폰트가 롬 어디에서 오는지 확정할 수 있다.
--
-- 주의 (PROGRESS 4.1)
--   emu.getState() 는 점 포함 평면 키를 쓴다: st["cpu.pc"], st["cpu.k"]

local LOG  = "/home/stpark/다운로드/hanguel/darkhalf-kr/wram_write2.txt"
local LO   = 0x7E8100          -- dma_log3 이 지목한 버퍼 시작
local HI   = 0x7E8600          -- 끝
local f = io.open(LOG, "w")
local seen, n = {}, 0

local function onWrite(addr, value)
  local st = emu.getState()
  local pc = st["cpu.pc"] or 0
  local k  = st["cpu.k"]  or 0
  -- PC 로 중복제거한다. 같은 루틴이 수천 번 써도 한 줄만 남는다.
  local key = string.format("%02X%04X", k, pc)
  if seen[key] then return end
  seen[key] = true
  n = n + 1
  local line = string.format("PC=$%02X:%04X  ->  WRAM $%06X = %02X", k, pc, addr, value)
  emu.log(line); f:write(line .. "\n"); f:flush()
  if n == 1 then
    -- 필드명이 바뀌었을 때를 대비해 한 번만 상태 키를 남긴다
    local keys = {}
    for kk, _ in pairs(st) do keys[#keys+1] = tostring(kk) end
    table.sort(keys)
    f:write("-- state keys: " .. table.concat(keys, ", ") .. "\n"); f:flush()
  end
end

emu.addMemoryCallback(onWrite, emu.callbackType.write, LO, HI)
emu.log(string.format("WRAM v2 추적 시작. $%06X~$%06X 에 쓰는 PC 를 모읍니다.", LO, HI))
emu.log("-> wram_write2.txt")
