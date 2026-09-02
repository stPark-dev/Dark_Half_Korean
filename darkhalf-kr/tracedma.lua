-- Mesen2 Lua: VRAM 으로 가는 DMA 의 출처를 기록한다.
-- $420B(MDMAEN) 쓰기를 가로채, 활성 채널의 B버스 목적지가 VMDATA($18/$19)인 것만 로그.
-- 압축 폰트가 어느 ROM 주소에서 오는지(또는 WRAM 경유인지) 드러난다.

local LOG = "/home/stpark/다운로드/hanguel/darkhalf-kr/dma_log.txt"
local seen = {}
local f = io.open(LOG, "w")

local function rd(a)          -- CPU 주소 공간 읽기
  return emu.read(a, emu.memType.snesMemory, false)
end

local function onMdmaen(addr, value)
  if value == 0 then return end
  for ch = 0, 7 do
    if (value & (1 << ch)) ~= 0 then
      local base = 0x4300 + ch * 0x10
      local bbus = rd(base + 1)                        -- $43x1 B버스 목적지
      if bbus == 0x18 or bbus == 0x19 then             -- VMDATA = 폰트/타일 전송
        local lo   = rd(base + 2)
        local hi   = rd(base + 3)
        local bank = rd(base + 4)
        local cntL = rd(base + 5)
        local cntH = rd(base + 6)
        local src  = (bank << 16) | (hi << 8) | lo
        local size = (cntH << 8) | cntL
        if size == 0 then size = 0x10000 end
        local vaddr = (rd(0x2117) << 8) | rd(0x2116)   -- VMADD (워드 단위)
        local key = string.format("%06X:%04X:%04X", src, size, vaddr)
        if not seen[key] then
          seen[key] = true
          local line = string.format(
            "ch%d  src=$%02X:%04X  size=%d  VRAM=$%04X(word) -> byte $%04X",
            ch, bank, (hi << 8) | lo, size, vaddr, vaddr * 2)
          emu.log(line)
          f:write(line .. "\n"); f:flush()
        end
      end
    end
  end
end

emu.addMemoryCallback(onMdmaen, emu.callbackType.write, 0x420B, 0x420B)
emu.log("DMA 추적 시작. 아이템 메뉴를 여닫아 보세요. 로그: " .. LOG)
