@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title VF Emissor Web - Servidor para Rede Local e Acesso Online
if not exist "portable\python.exe" (
  echo Extraia a pasta completa do ZIP antes de iniciar o emissor.
  echo Nao execute este arquivo diretamente de dentro do ZIP.
  pause
  exit /b 1
)

echo =====================================================================
echo  VF Emissor Web - Modo Multi-Empresa e Acesso em Rede / Online
echo =====================================================================
echo  * Servidor escutando em todas as interfaces de rede (0.0.0.0:8787)
echo  * Na propria maquina: http://localhost:8787
echo  * Outros computadores na contabilidade: http://IP-DESTA-MAQUINA:8787
echo  * Para acesso online gratuito: Use Cloudflare Tunnel (cloudflared)
echo =====================================================================
echo.

"portable\python.exe" "server.py" --allow-remote --host 0.0.0.0 --port 8787
if errorlevel 1 (
  echo.
  echo Nao foi possivel iniciar o servico. Verifique se a porta 8787 ja esta em uso.
  pause
)
