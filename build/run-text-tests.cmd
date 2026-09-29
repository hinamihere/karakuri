@echo off
rem Karakuri - build and run the KARA-7 text module QA tests.
rem Exit code 0 means every case passed; see tests\text\test-results.txt.

setlocal
set "ROOT=%~dp0.."

call "%~dp0build-text.cmd"
if errorlevel 1 exit /b 1

echo.
"%ROOT%\bin\karakuri-text-tests.exe" "%ROOT%"
exit /b %ERRORLEVEL%
