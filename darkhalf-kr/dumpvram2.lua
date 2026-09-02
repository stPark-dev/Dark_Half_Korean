-- Mesen2 Lua: VRAM 자동 덤프 (키 입력 불필요)
--
-- v1 실패: emu.isKeyPressed("D") 가 반응하지 않음(키 이름/포커스 문제).
-- v2: 1초(60프레임)마다 자동으로 덮어쓴다.
--     아이템 메뉴를 연 채 2~3초 기다렸다가 스크립트를 Stop 하면
--     vram.bin 에 그 화면의 VRAM 이 남는다.

local OUT   = "/home/stpark/다운로드/hanguel/darkhalf-kr/vram.bin"
local OUTCG = "/home/stpark/다운로드/hanguel/darkhalf-kr/cgram.bin"
local EVERY = 60
local frame, dumps = 0, 0

local function pick(names)
  for _, n in ipairs(names) do
    if emu.memType[n] ~= nil then return emu.memType[n] end
  end
end
local VRAM  = pick({"snesVideoRam", "videoRam", "vram"})
local CGRAM = pick({"snesCgRam", "cgRam", "cgram"})

local function dump(mt, size, path)
  if mt == nil then return false end
  local f = io.open(path, "wb")
  if not f then return false end
  local buf = {}
  for i = 0, size - 1 do
    buf[#buf+1] = string.char(emu.read(i, mt))
    if #buf >= 4096 then f:write(table.concat(buf)); buf = {} end
  end
  if #buf > 0 then f:write(table.concat(buf)) end
  f:close(); return true
end

emu.addEventCallback(function()
  frame = frame + 1
  if frame % EVERY ~= 0 then return end
  if dump(VRAM, 0x10000, OUT) then
    dump(CGRAM, 0x200, OUTCG)
    dumps = dumps + 1
    emu.log(string.format("덤프 #%d (frame %d) 저장됨", dumps, frame))
  else
    emu.log("!! 덤프 실패 - memType 또는 파일 경로 확인")
  end
end, emu.eventType.endFrame)

emu.log("자동 덤프 시작: 1초마다 vram.bin 덮어씀.")
emu.log("아이템 메뉴를 연 채 2~3초 기다렸다가 Stop 하세요.")
