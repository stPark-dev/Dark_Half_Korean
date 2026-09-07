-- Mesen2 Lua: VRAM DMA 전수 기록 (v3) — 메뉴 폰트 출처 추적
--
-- v2 와의 차이: VRAM 목적지로 거르지 않는다.
-- v2 는 VRAM $4000~$63FF 만 봤는데 그 범위는 실패한 추적들에서 나온 추측이었다.
-- PROGRESS 원칙 4(추정 위에 다음 단계를 쌓지 않는다)에 어긋나므로 전부 기록한다.
--
-- 목표: 마법 목록 창을 열 때 어떤 DMA 가 일어나는지 소스 주소와 크기를 잡는다.
--       메인 폰트($EF:xxxx = ROM 0x2F0000)가 아닌 출처가 메뉴 폰트다.
--
-- 주의 (PROGRESS 4.1 의 Mesen2 Lua 주의점)
--   $2116/$2117(VMADD)은 쓰기 전용이라 읽으면 0 이다. 쓰기를 가로채 기억한다.
--   VRAM 자체는 addMemoryCallback 대상이 안 된다.

local LOG = "/home/stpark/다운로드/hanguel/darkhalf-kr/dma_log3.txt"
local f = io.open(LOG, "w")
local seen = {}
local vmadd_lo, vmadd_hi = 0, 0
local count = 0

local function rd(a) return emu.read(a, emu.memType.snesMemory, false) end

local function onVmaddLo(addr, value) vmadd_lo = value end
local function onVmaddHi(addr, value) vmadd_hi = value end

local function onMdmaen(addr, value)
  if value == 0 then return end
  local vbyte = (((vmadd_hi << 8) | vmadd_lo)) * 2   -- VMADD 는 워드 단위
  for ch = 0, 7 do
    if (value & (1 << ch)) ~= 0 then
      local base = 0x4300 + ch * 0x10
      local bbus = rd(base + 1)
      if bbus == 0x18 or bbus == 0x19 then           -- VMDATA = VRAM 전송
        local lo, hi, bank = rd(base + 2), rd(base + 3), rd(base + 4)
        local size = (rd(base + 6) << 8) | rd(base + 5)
        if size == 0 then size = 0x10000 end
        local src = (bank << 16) | (hi << 8) | lo
        local key = string.format("%06X:%04X:%04X", src, size, vbyte)
        if not seen[key] then
          seen[key] = true
          count = count + 1
          -- 메인 폰트 뱅크($EF)인지 표시해 둔다. 그 외가 메뉴 폰트 후보다.
          local tag = (bank == 0xEF) and "MAIN" or "????"
          local line = string.format(
            "f%-7d ch%d src=$%02X:%04X size=%-6d VRAM=$%04X  %s",
            emu.getState()["ppu.frameCount"] or 0, ch, bank, (hi<<8)|lo, size, vbyte, tag)
          emu.log(line); f:write(line .. "\n"); f:flush()
        end
      end
    end
  end
end

emu.addMemoryCallback(onVmaddLo, emu.callbackType.write, 0x2116, 0x2116)
emu.addMemoryCallback(onVmaddHi, emu.callbackType.write, 0x2117, 0x2117)
emu.addMemoryCallback(onMdmaen,  emu.callbackType.write, 0x420B, 0x420B)

emu.log("DMA v3 전수 기록 시작 -> dma_log3.txt")
emu.log("MAIN = 메인 폰트 뱅크($EF). ???? 가 메뉴 폰트 후보입니다.")
