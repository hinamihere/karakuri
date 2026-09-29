$notepad = Start-Process notepad -PassThru
Start-Sleep -Milliseconds 800

try {
    $clsid = [System.Guid]::Parse("ff48dba4-60ef-4201-aa87-54103eef594e")
    $uia = [System.Activator]::CreateInstance([System.Type]::GetTypeFromCLSID($clsid))
    Write-Output "Native COM CUIAutomation instantiated via CLSID successfully!"
    
    $elem = $uia.ElementFromHandle($notepad.MainWindowHandle)
    Write-Output "ElementFromHandle returned: '$($elem.CurrentName)'"
    Write-Output "CurrentClassName: '$($elem.CurrentClassName)'"
    Write-Output "CurrentControlType: $($elem.CurrentControlType)"
    
    # Find child Edit control
    $cond = $uia.CreatePropertyCondition(30012, "Edit") # UIA_ClassNamePropertyId = 30012
    $edit = $elem.FindFirst(4, $cond) # TreeScope_Descendants = 4
    if ($edit -ne $null) {
        Write-Output "Found child edit: Name='$($edit.CurrentName)' Class='$($edit.CurrentClassName)' ControlType=$($edit.CurrentControlType)"
        
        # Check ValuePattern (UIA_ValuePatternId = 10002)
        $valPatternObj = $edit.GetCurrentPattern(10002)
        Write-Output "GetCurrentPattern(ValuePattern 10002) returned: $(($valPatternObj -ne $null))"
        if ($valPatternObj -ne $null) {
            Write-Output "CurrentValue: '$($valPatternObj.CurrentValue)' IsReadOnly: $($valPatternObj.CurrentIsReadOnly)"
            
            # Test SetValue with Japanese characters
            $testVal = "Karakuri-UTF16-Test-Yayoi-NativeCOM"
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            $valPatternObj.SetValue($testVal)
            $sw.Stop()
            Write-Output "SetValue executed via native UIA COM in: $($sw.ElapsedMilliseconds) ms"
            Write-Output "New CurrentValue: '$($valPatternObj.CurrentValue)'"
        }
        
        # Check BoundingRectangle (UIA_BoundingRectanglePropertyId = 30001)
        $rect = $edit.CurrentBoundingRectangle
        Write-Output "BoundingRectangle: Left=$($rect[0]), Top=$($rect[1]), Width=$($rect[2]), Height=$($rect[3])"
        $centerX = $rect[0] + ($rect[2] / 2)
        $centerY = $rect[1] + ($rect[3] / 2)
        Write-Output "Calculated Center Point for SendInput: ($centerX, $centerY)"
    }
} finally {
    if ($notepad -ne $null -and -not $notepad.HasExited) {
        $notepad.Kill()
    }
}
