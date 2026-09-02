-- Mesen2 Lua: VRAM DMA 출처 추적 (v2)
--
-- v1 버그: $2116/$2117(VMADD)은 쓰기 전용이라 읽으면 0이 나온다.
--          -> 쓰기를 가로채 마지막 값을 기억해 둔다.
-- 목표: VRAM $4F30~$5C30 (8x8 메뉴 폰트가 올라가는 자리) 로 가는 전송의 출처를 잡는다.

local LOG = "/home/stpark/다운로드/hanguel/darkhalf-kr/dma_log2.txt"
local f = io.open(LOG, "w")
local seen = {}
local vmadd_lo, vmadd_hi = 0, 0        -- $2116, $2117 최근 쓰기값

local function rd(a) return emu.read(a, emu.memType.snesMemory, false) end

local function onVmaddLo(addr, value) vmadd_lo = value end
local function onVmaddHi(addr, value) vmadd_hi = value end

local function onMdmaen(addr, value)
  if value == 0 then return end
  local vword = (vmadd_hi << 8) | vmadd_lo
  local vbyte = vword * 2                       -- VMADD 는 워드 단위
  for ch = 0, 7 do
    if (value & (1 << ch)) ~= 0 then
      local base = 0x4300 + ch * 0x10
      local bbus = rd(base + 1)
      if bbus == 0x18 or bbus == 0x19 then
        local lo, hi, bank = rd(base + 2), rd(base + 3), rd(base + 4)
        local size = (rd(base + 6) << 8) | rd(base + 5)
        if size == 0 then size = 0x10000 end
        -- 관심 구간(8x8 폰트)으로 가는 전송만 표시
        local hot = (vbyte >= 0x4000 and vbyte < 0x6400)
        local key = string.format("%02X%04X:%04X:%04X", bank, (hi<<8)|lo, size, vbyte)
        if not seen[key] then
          seen[key] = true
          local line = string.format("%s ch%d src=$%02X:%04X size=%-5d VRAMbyte=$%04X",
                       hot and "**" or "  ", ch, bank, (hi<<8)|lo, size, vbyte)
          emu.log(line); f:write(line .. "\n"); f:flush()
        end
      end
    end
  end
end

emu.addMemoryCallback(onVmaddLo, emu.callbackType.write, 0x2116, 0x2116)
emu.addMemoryCallback(onVmaddHi, emu.callbackType.write, 0x2117, 0x2117)
emu.addMemoryCallback(onMdmaen,  emu.callbackType.write, 0x420B, 0x420B)
emu.log("DMA v2 추적 시작. ** 표시가 8x8 폰트 구간(VRAM $4000-$63FF) 전송입니다.")
