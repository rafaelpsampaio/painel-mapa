@echo off
rem Instala o Painel MAPA neste computador:
rem  - atalho "Painel MAPA" na area de trabalho (abre sem janela preta)
rem  - opcionalmente, inicia o painel junto com o Windows
chcp 65001 >nul
cd /d "%~dp0"

echo Instalando bibliotecas necessarias (isso pode demorar um pouco)...
py -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo.
    echo ATENCAO: falha ao instalar as bibliotecas necessarias.
    echo Verifique sua conexao com a internet e tente rodar instalar.bat de novo.
    echo.
    pause
    exit /b 1
)

if not exist painel.ico py gerar_icone.py

echo Criando atalho na area de trabalho...
cscript //nologo criar_atalho.vbs

set /p AUTO=Iniciar o painel automaticamente com o Windows? (s/n):
if /i "%AUTO%"=="s" (
    copy /y "%~dp0iniciar_painel.vbs" "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Painel MAPA.vbs" >nul
    echo Configurado: o painel abre sozinho quando o computador ligar.
) else (
    del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Painel MAPA.vbs" 2>nul
    echo Ok, o painel so abre pelo atalho.
)

echo.
echo Instalacao concluida. Duplo clique em "Painel MAPA" na area de trabalho.
pause
