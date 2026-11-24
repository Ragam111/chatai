@echo off
REM เปิดเซิร์ฟเวอร์ chatai + บอท Discord บน Windows (ต้องมี Python และ Ollama)
cd /d "%~dp0..\.."
if not exist "%~dp0discord-bot.env.bat" (
  echo ไม่พบ deploy\windows\discord-bot.env.bat — คัดลอกจาก discord-bot.env.example แล้วเติมค่าก่อน
  pause & exit /b 1
)
call "%~dp0discord-bot.env.bat"
start "chatai-server" /min python server.py
timeout /t 3 /nobreak >nul
:loop
python -m bots.discord_poll_bridge
echo บอทหยุดทำงาน จะเปิดใหม่ใน 10 วินาที (กด Ctrl+C เพื่อออก)
timeout /t 10 /nobreak >nul
goto loop
