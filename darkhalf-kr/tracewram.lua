-- Mesen2 Lua: WRAM $7E:273B (VRAM 폰트로 DMA 되는 원본) 에 쓰는 루틴을 잡는다.
--
-- 앞선 실패 두 가지를 고쳤다:
--   1) PC 가 $00:0000 으로 찍힘  -> getState 구조를 한 번 덤프해 필드명을 확인
--   2) PC 로 중복제거해서 대부분 걸러짐 -> 주소 기준으로 중복제거

local LOG   = "/home/stpark/다운로드/hanguel/darkhalf-kr/wram_write.txt"
local BASE  = 0x7E273B          -- DMA 출처
local SIZE  = 1024
local f = io.open(LOG, "w")
local seen, n, probed = {}, 0, false

local function dumpState()
  if probed then return end
  probed = true
  local st = emu.getState()
  local keys = {}
  for k, _ in pairs(st) do keys[#keys+1] = tostring(k) end
  table.sort(keys)
  local line = "state keys: " .. table.concat(keys, ", ")
  emu.log(line); f:write(line .. "\n")
  for _, sub in ipairs({"cpu", "Cpu", "proc"}) do
    if type(st[sub]) == "table" then
      local kk = {}
      for k, _ in pairs(st[sub]) do kk[#kk+1] = tostring(k) end
      table.sort(kk)
      local l2 = sub .. " keys: " .. table.concat(kk, ", ")
      emu.log(l2); f:write(l2 .. "\n")
    end
  end
  f:flush()
end

local function pcOf()
  local st = emu.getState()
  local c = st.cpu or st.Cpu or st.proc
  if type(c) ~= "table" then return 0, 0 end
  local pc = c.pc or c.PC or c.k_pc or 0
  local pb = c.k or c.K or c.pbr or c.PBR or 0
  return pb, pc
end

local function onWrite(address, value)
  dumpState()
  if n > 250 then return end
  local key = string.format("%06X", address)      -- 주소 기준 중복제거
  if seen[key] then return end
  seen[key] = true; n = n + 1
  local pb, pc = pcOf()
  local line = string.format("WRAM $%06X <= $%02X   PC=$%02X:%04X", address, value, pb, pc)
  emu.log(line); f:write(line .. "\n"); f:flush()
end

local ok1 = pcall(function()
  emu.addMemoryCallback(onWrite, emu.callbackType.write, BASE, BASE + SIZE - 1,
                        emu.cpuType.snes, emu.memType.snesMemory)
end)
local ok2 = false
if not ok1 then
  ok2 = pcall(function()
    emu.addMemoryCallback(onWrite, emu.callbackType.write,
                          BASE & 0x1FFFF, (BASE & 0x1FFFF) + SIZE - 1,
                          emu.cpuType.snes, emu.memType.snesWorkRam)
  end)
end
emu.log(string.format("WRAM $%06X +%d 감시 (%s). 리셋 후 아이템 메뉴까지 진행하세요.",
        BASE, SIZE, ok1 and "snesMemory" or (ok2 and "snesWorkRam" or "등록실패")))
emu.log("기록: " .. LOG)
