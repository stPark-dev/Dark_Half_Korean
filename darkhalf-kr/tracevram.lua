-- Mesen2 Lua: VRAM $4F30~$5C30 (8x8 메뉴 폰트 자리) 에 쓰는 주체를 잡는다.
-- DMA 뿐 아니라 CPU 쓰기도 잡히도록 VRAM 자체에 쓰기 콜백을 건다.
-- 각 쓰기 시점의 CPU PC 를 기록하면, 그 루틴에서 데이터 출처를 역추적할 수 있다.

local LOG = "/home/stpark/다운로드/hanguel/darkhalf-kr/vram_write.txt"
local f = io.open(LOG, "w")
local seen, count = {}, 0

local function onWrite(address, value)
  if count > 400 then return end
  local st = emu.getState()
  local pc, pb
  if st.cpu then pc = st.cpu.pc; pb = st.cpu.k end
  local key = string.format("%02X%04X", pb or 0, pc or 0)
  if not seen[key] then
    seen[key] = true
    count = count + 1
    local line = string.format("VRAM $%04X <= $%02X   PC=$%02X:%04X",
                               address, value, pb or 0, pc or 0)
    emu.log(line); f:write(line .. "\n"); f:flush()
  end
end

local ok, err = pcall(function()
  emu.addMemoryCallback(onWrite, emu.callbackType.write, 0x4F30, 0x5C30,
                        emu.cpuType.snes, emu.memType.snesVideoRam)
end)
if not ok then
  emu.log("!! VRAM 콜백 실패: " .. tostring(err))
  emu.log("   -> Debugger > Memory Tools 에서 VRAM $4F30 에 Write 브레이크포인트를 직접 거세요.")
else
  emu.log("VRAM 쓰기 감시 시작. 게임을 리셋(Emulation > Reset)한 뒤 아이템 메뉴까지 진행하세요.")
  emu.log("기록: " .. LOG)
end
