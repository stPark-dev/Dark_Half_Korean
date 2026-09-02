-- Mesen2 Lua: VRAM/CGRAM 덤프
-- 사용법: 아이템 메뉴를 연 상태에서 D 키를 누르면 파일로 저장된다.
-- 저장 위치: 이 스크립트와 같은 폴더 (vram.bin, cgram.bin)

local OUTDIR = "/home/stpark/다운로드/hanguel/darkhalf-kr/"
local done = 0

-- Mesen2 버전에 따라 memType 이름이 다를 수 있어 후보를 순회한다
local function pickType(names)
  for _, n in ipairs(names) do
    if emu.memType[n] ~= nil then return emu.memType[n], n end
  end
  return nil, nil
end

local VRAM,  vramName  = pickType({"snesVideoRam", "videoRam", "vram"})
local CGRAM, cgramName = pickType({"snesCgRam", "cgRam", "cgram"})

local function dump(memType, size, path, label)
  if memType == nil then emu.log("!! " .. label .. " 타입 없음"); return end
  local f, err = io.open(path, "wb")
  if not f then emu.log("!! 파일 열기 실패: " .. tostring(err)); return end
  local chunk = {}
  for i = 0, size - 1 do
    chunk[#chunk + 1] = string.char(emu.read(i, memType))
    if #chunk >= 4096 then f:write(table.concat(chunk)); chunk = {} end
  end
  if #chunk > 0 then f:write(table.concat(chunk)) end
  f:close()
  emu.log(label .. " " .. size .. "바이트 저장 -> " .. path)
end

local function onFrame()
  if emu.isKeyPressed("D") and done == 0 then
    done = 1
    emu.log("=== 덤프 시작 (memType: " .. tostring(vramName) .. ") ===")
    dump(VRAM,  0x10000, OUTDIR .. "vram.bin",  "VRAM")
    dump(CGRAM, 0x200,   OUTDIR .. "cgram.bin", "CGRAM")
    emu.log("=== 완료. R 키로 다시 덤프 가능 ===")
  elseif emu.isKeyPressed("R") then
    done = 0
  end
end

emu.addEventCallback(onFrame, emu.eventType.endFrame)
emu.log("VRAM 덤프 스크립트 로드됨. 아이템 메뉴를 연 뒤 D 키를 누르세요.")
