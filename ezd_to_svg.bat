@echo off
setlocal
title EZD to SVG + DXF
where python >nul 2>nul
if not errorlevel 1 (
    python "%~dp0ezd_to_svg.py" --no-pause %*
) else (
    py -3 "%~dp0ezd_to_svg.py" --no-pause %*
)
echo.
echo Finished. Review messages above before closing.
pause
