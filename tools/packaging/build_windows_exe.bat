@echo off
setlocal
cd /d "%~dp0..\.."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-packaging.txt
python -m PyInstaller tools\packaging\runtime.spec
echo Built: dist\bacnet-commissioning.exe
endlocal
