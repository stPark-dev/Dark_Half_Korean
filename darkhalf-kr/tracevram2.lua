-- Mesen2 Lua: VRAM 폰트 자리에 쓰는 주체 추적 (v2)
--
-- v1 실패: addMemoryCallback 은 VRAM 을 대상으로 동작하지 않았다(콜백 미발생).
-- v2: CPU 의 VRAM 접근은 반드시 PPU 레지스터를 거친다는 점을 이용한다.
--     $2115 VMAIN(증가 설정) / $2116-7 VMADD(주소) / $2118-9 VMDATA(데이터)
--     -> VMADD 를 직접 추적하고 VMDATA 쓰기 때 주소를 계산한다.
--     DMA 도 함께 기록해 두 경로를 모두 덮는다.

local LOG  = "/home/stpark/다운로드/hanguel/darkhalf-kr/vram_write2.txt"
local LO, HI = 0x4F30, 0x5C30          -- 8x8 메뉴 폰트가 관측된 VRAM 바이트 범위
local f = io.open(LOG, "w")
local vmain, vaddr = 0x80, 0
local seen, n = {}, 0

local function step()
  local s = vmain & 0x03
  if s == 0 then return 1 elseif s == 1 then return 32 else return 128 end
end

local function note(tag, extra)
  if n > 300 then return end
  local st = emu.getState()
  local pc, pb = 0, 0
  if st.cpu then pc = st.cpu.pc; pb = st.cpu.k end
  local key = tag .. string.format("%02X%04X", pb, pc)
  if seen[key] then return end
  seen[key] = true; n = n + 1
  local line = string.format("%-4s VRAMbyte=$%04X  PC=$%02X:%04X  %s",
                             tag, vaddr * 2, pb, pc, extra or "")
  emu.log(line); f:write(line .. "\n"); f:flush()
end

local function hot() return (vaddr * 2) >= LO and (vaddr * 2) < HI end

emu.addMemoryCallback(function(a, v) vmain = v end, emu.callbackType.write, 0x2115, 0x2115)
emu.addMemoryCallback(function(a, v) vaddr = (vaddr & 0xFF00) | v end,
                      emu.callbackType.write, 0x2116, 0x2116)
emu.addMemoryCallback(function(a, v) vaddr = (vaddr & 0x00FF) | (v << 8) end,
                      emu.callbackType.write, 0x2117, 0x2117)
emu.addMemoryCallback(function(a, v)
  if hot() then note("CPU") end
  if (vmain & 0x80) == 0 then vaddr = (vaddr + step()) & 0xFFFF end
end, emu.callbackType.write, 0x2118, 0x2118)
emu.addMemoryCallback(function(a, v)
  if hot() then note("CPU") end
  if (vmain & 0x80) ~= 0 then vaddr = (vaddr + step()) & 0xFFFF end
end, emu.callbackType.write, 0x2119, 0x2119)

-- DMA 경로도 함께
emu.addMemoryCallback(function(a, v)
  if v == 0 then return end
  for ch = 0, 7 do
    if (v & (1 << ch)) ~= 0 then
      local b = 0x4300 + ch * 0x10
      local bb = emu.read(b + 1, emu.memType.snesMemory, false)
      if bb == 0x18 or bb == 0x19 then
        local lo = emu.read(b+2, emu.memType.snesMemory, false)
        local hi = emu.read(b+3, emu.memType.snesMemory, false)
        local bk = emu.read(b+4, emu.memType.snesMemory, false)
        local sz = (emu.read(b+6, emu.memType.snesMemory, false) << 8)
                 | emu.read(b+5, emu.memType.snesMemory, false)
        if sz == 0 then sz = 0x10000 end
        local mark = hot() and "DMA*" or "DMA"
        if hot() then
          note(mark, string.format("src=$%02X:%04X size=%d", bk, (hi<<8)|lo, sz))
        end
      end
    end
  end
end, emu.callbackType.write, 0x420B, 0x420B)

emu.log(string.format("VRAM $%04X-$%04X 감시 시작. 리셋 후 아이템 메뉴까지 진행하세요.", LO, HI))
emu.log("기록: " .. LOG)
