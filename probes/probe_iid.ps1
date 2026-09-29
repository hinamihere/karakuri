# Karakuri Research Probe: UIA COM, CacheRequest batching, ValuePattern/InvokePattern, IME bypass
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

Write-Output "=== 1. Windows UIA COM Interfaces Verification ==="

$clsidUia8 = [System.Guid]::Parse("e22ad333-b25f-460c-83d0-0581107395c9")
$typeUia8 = [System.Type]::GetTypeFromCLSID($clsidUia8)
$objUia8 = [System.Activator]::CreateInstance($typeUia8)

# IUIAutomation5 IID: {25f700c8-d816-4057-a9dc-3cbdee77e256}
$iid5 = [System.Guid]::Parse("25f700c8-d816-4057-a9dc-3cbdee77e256")
$pUnknown = [System.Runtime.InteropServices.Marshal]::GetIUnknownForObject($objUia8)
$pIUIAutomation5 = [System.IntPtr]::Zero
$hr = [System.Runtime.InteropServices.Marshal]::QueryInterface($pUnknown, [ref]$iid5, [ref]$pIUIAutomation5)
[System.Runtime.InteropServices.Marshal]::Release($pUnknown)

Write-Output ("QueryInterface IUIAutomation5 HRESULT: 0x" + $hr.ToString("X8"))
if ($hr -eq 0) {
    Write-Output "CONFIRMED: IUIAutomation5 is supported by CUIAutomation8 on this system (Windows 10 21H2)."
    [System.Runtime.InteropServices.Marshal]::Release($pIUIAutomation5)
}

# IUIAutomation6 IID: {bae70bfb-70ca-430b-ab77-aa4747994ff3}
$iid6 = [System.Guid]::Parse("bae70bfb-70ca-430b-ab77-aa4747994ff3")
$pUnknown = [System.Runtime.InteropServices.Marshal]::GetIUnknownForObject($objUia8)
$pIUIAutomation6 = [System.IntPtr]::Zero
$hr6 = [System.Runtime.InteropServices.Marshal]::QueryInterface($pUnknown, [ref]$iid6, [ref]$pIUIAutomation6)
[System.Runtime.InteropServices.Marshal]::Release($pUnknown)
Write-Output ("QueryInterface IUIAutomation6 HRESULT: 0x" + $hr6.ToString("X8"))
if ($hr6 -eq 0) {
    Write-Output "CONFIRMED: IUIAutomation6 is also supported by CUIAutomation8 on this system."
    [System.Runtime.InteropServices.Marshal]::Release($pIUIAutomation6)
}

