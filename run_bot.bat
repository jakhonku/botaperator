@echo off
title Telegram Bot Runner
:loop
echo [%date% %time%] Bot ishga tushmoqda...
call .venv\Scripts\activate
python bot.py
echo [%date% %time%] Bot to'xtadi (crash bo'ldi). 5 soniyadan keyin qayta ishga tushadi...
timeout /t 5
goto loop
