@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo DAR BAIXA MANUAL EM UM EXAME
echo (use quando o laudo foi entregue por outro canal, exame cancelado etc.)
echo.
set CODIGO=
set /p CODIGO=Codigo do exame (ex. 0RC-04950):
if "%CODIGO%"=="" (
    echo Nenhum codigo informado. Nada foi registrado.
    pause
    exit /b
)
set MOTIVO=
set /p MOTIVO=Motivo (opcional):
echo %CODIGO%: %MOTIVO% (baixa registrada em %DATE%)>> baixas.txt
echo.
echo Baixa registrada: %CODIGO%
echo Para desfazer, apague a linha correspondente no arquivo baixas.txt
pause
