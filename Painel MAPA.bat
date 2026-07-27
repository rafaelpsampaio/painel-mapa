@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo Abrindo o painel no navegador...
echo Deixe esta janela aberta enquanto usa o painel.
echo Feche esta janela para encerrar.
py painel.py
