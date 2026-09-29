@echo off
rem Karakuri - build the text module (core/text) and its QA tests (tests/text).
rem
rem Uses the compiler that ships inside .NET Framework itself, so there is no SDK
rem install, no NuGet restore and no network access involved. The UI Automation
rem assemblies are resolved from the Global Assembly Cache.

setlocal
set "ROOT=%~dp0.."
set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" set "CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"
if not exist "%CSC%" (
  echo ERROR: csc.exe not found under %WINDIR%\Microsoft.NET
  exit /b 2
)

set "UIACLIENT="
for /d %%D in ("%WINDIR%\assembly\GAC_MSIL\UIAutomationClient\*") do set "UIACLIENT=%%~fD\UIAutomationClient.dll"
if not defined UIACLIENT for /d %%D in ("%WINDIR%\Microsoft.NET\assembly\GAC_MSIL\UIAutomationClient\*") do set "UIACLIENT=%%~fD\UIAutomationClient.dll"
set "UIATYPES="
for /d %%D in ("%WINDIR%\assembly\GAC_MSIL\UIAutomationTypes\*") do set "UIATYPES=%%~fD\UIAutomationTypes.dll"
if not defined UIATYPES for /d %%D in ("%WINDIR%\Microsoft.NET\assembly\GAC_MSIL\UIAutomationTypes\*") do set "UIATYPES=%%~fD\UIAutomationTypes.dll"
if not defined UIACLIENT (
  echo ERROR: UIAutomationClient.dll not found in the GAC
  exit /b 2
)
if not defined UIATYPES (
  echo ERROR: UIAutomationTypes.dll not found in the GAC
  exit /b 2
)

if not exist "%ROOT%\bin" mkdir "%ROOT%\bin"

echo [1/2] core\text -^> bin\karakuri-text.dll
"%CSC%" /nologo /target:library /codepage:65001 /optimize+ ^
  /out:"%ROOT%\bin\karakuri-text.dll" ^
  /r:"%UIACLIENT%" /r:"%UIATYPES%" /r:System.dll /r:System.Core.dll ^
  "%ROOT%\core\text\*.cs"
if errorlevel 1 exit /b 1

echo [2/2] tests\text -^> bin\karakuri-text-tests.exe
"%CSC%" /nologo /target:exe /codepage:65001 /optimize+ ^
  /out:"%ROOT%\bin\karakuri-text-tests.exe" ^
  /r:"%ROOT%\bin\karakuri-text.dll" ^
  /r:"%UIACLIENT%" /r:"%UIATYPES%" ^
  /r:System.dll /r:System.Core.dll /r:System.Web.Extensions.dll ^
  /r:System.Windows.Forms.dll /r:System.Drawing.dll ^
  "%ROOT%\tests\text\*.cs"
if errorlevel 1 exit /b 1

echo Build OK: %ROOT%\bin
exit /b 0
