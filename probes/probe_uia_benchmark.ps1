# Karakuri Research Probe: UIA COM, CacheRequest batching, ValuePattern/InvokePattern, IME bypass
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

Write-Output "=== 1. Windows UIA COM Interfaces Verification ==="

# CLSID for CUIAutomation: {ff48dba4-60ef-4201-aa87-54103eef594e}
# CLSID for CUIAutomation8: {e22ad333-b25f-460c-83d0-0581107395c9}
$clsidUia = [System.Guid]::Parse("ff48dba4-60ef-4201-aa87-54103eef594e")
$clsidUia8 = [System.Guid]::Parse("e22ad333-b25f-460c-83d0-0581107395c9")

$typeUia = [System.Type]::GetTypeFromCLSID($clsidUia)
$objUia = [System.Activator]::CreateInstance($typeUia)
Write-Output "CUIAutomation ({ff48dba4-...}) instantiable: $(($objUia -ne $null))"

$typeUia8 = [System.Type]::GetTypeFromCLSID($clsidUia8)
$objUia8 = [System.Activator]::CreateInstance($typeUia8)
Write-Output "CUIAutomation8 ({e22ad333-...}) instantiable: $(($objUia8 -ne $null))"

# Check if IUIAutomation5 interface GUID is available
# IUIAutomation5 IID: {25f700c8-d816-4057-a9dc-3cb0e56778e4}
$iid5 = [System.Guid]::Parse("25f700c8-d816-4057-a9dc-3cb0e56778e4")
$pUnknown = [System.Runtime.InteropServices.Marshal]::GetIUnknownForObject($objUia8)
$pIUIAutomation5 = [System.IntPtr]::Zero
$hr = [System.Runtime.InteropServices.Marshal]::QueryInterface($pUnknown, [ref]$iid5, [ref]$pIUIAutomation5)
[System.Runtime.InteropServices.Marshal]::Release($pUnknown)
if ($hr -eq 0 -and $pIUIAutomation5 -ne [System.IntPtr]::Zero) {
    Write-Output "IUIAutomation5 Interface QueryInterface: SUCCESS (HRESULT 0x0, OS supports IUIAutomation5)"
    [System.Runtime.InteropServices.Marshal]::Release($pIUIAutomation5)
} else {
    Write-Output "IUIAutomation5 Interface QueryInterface: HR=$hr"
}

Write-Output "`n=== 2. Notepad Win32 Edit Control Pattern & IME Probe ==="
$notepadProc = Start-Process notepad -PassThru
Start-Sleep -Milliseconds 1200

try {
    $notepadElem = [System.Windows.Automation.AutomationElement]::FromHandle($notepadProc.MainWindowHandle)
    Write-Output "Notepad Window Name: '$($notepadElem.Current.Name)' Class: '$($notepadElem.Current.ClassName)'"
    
    # Enumerate all elements inside Notepad
    $elements = $notepadElem.FindAll([System.Windows.Automation.TreeScope]::Subtree, [System.Windows.Automation.Condition]::TrueCondition)
    Write-Output "Total subtree elements in Notepad: $($elements.Count)"
    
    foreach ($el in $elements) {
        $patterns = $el.GetSupportedPatterns()
        $patternNames = ($patterns | ForEach-Object { $_.ProgrammaticName }) -join ", "
        Write-Output "  - Element: Role=$($el.Current.ControlType.ProgrammaticName) Class='$($el.Current.ClassName)' Name='$($el.Current.Name)' Patterns=[$patternNames]"
    }
    
    # Target Edit control
    $editElem = $notepadElem.FindFirst(
        [System.Windows.Automation.TreeScope]::Descendants,
        (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ClassNameProperty, "Edit"))
    )
    
    if ($editElem -ne $null) {
        Write-Output "`nFound Win32 'Edit' control! Testing ValuePattern..."
        $patterns = $editElem.GetSupportedPatterns()
        $patternNames = ($patterns | ForEach-Object { $_.ProgrammaticName }) -join ", "
        Write-Output "Edit Control Supported Patterns: [$patternNames]"
        
        $objPattern = $null
        if ($editElem.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$objPattern)) {
            $valPattern = [System.Windows.Automation.ValuePattern]$objPattern
            Write-Output "ValuePattern available: True. IsReadOnly: $($valPattern.Current.IsReadOnly)"
            
            $testString = "Karakuri-UTF16-Test-Yayoi"
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            $valPattern.SetValue($testString)
            $sw.Stop()
            Write-Output "ValuePattern.SetValue executed in: $($sw.ElapsedMilliseconds) ms"
            Write-Output "Read-back Value: '$($valPattern.Current.Value)'"
            
            # Check BoundingRectangle
            $rect = $editElem.Current.BoundingRectangle
            Write-Output "BoundingRectangle: Left=$($rect.Left), Top=$($rect.Top), Width=$($rect.Width), Height=$($rect.Height)"
            $centerX = $rect.Left + ($rect.Width / 2)
            $centerY = $rect.Top + ($rect.Height / 2)
            Write-Output "Calculated Center for SendInput fallback: ($centerX, $centerY)"
        } else {
            Write-Output "ValuePattern NOT available on Edit control"
        }
    }
    
    Write-Output "`n=== 3. Benchmark: CacheRequest Batching vs Per-Property COM Queries ==="
    # Benchmark on Notepad's subtree (or all elements found)
    $allElements = $notepadElem.FindAll([System.Windows.Automation.TreeScope]::Subtree, [System.Windows.Automation.Condition]::TrueCondition)
    $count = $allElements.Count
    $iterations = 50
    Write-Output "Benchmarking $count elements over $iterations iterations..."
    
    # Method A: Un-cached per-property queries (N calls per property per element)
    $swA = [System.Diagnostics.Stopwatch]::StartNew()
    for ($i = 0; $i -lt $iterations; $i++) {
        foreach ($el in $allElements) {
            $n = $el.Current.Name
            $a = $el.Current.AutomationId
            $c = $el.Current.ControlType
            $b = $el.Current.BoundingRectangle
            $e = $el.Current.IsEnabled
            $cl = $el.Current.ClassName
        }
    }
    $swA.Stop()
    $timeUncached = $swA.ElapsedMilliseconds
    $totalPropReads = $count * 6 * $iterations
    Write-Output "Uncached ($totalPropReads property accesses across $iterations iterations): ${timeUncached} ms"
    Write-Output "Average time per property access: $([math]::Round($timeUncached / $totalPropReads, 4)) ms"
    
    # Method B: Batched CacheRequest
    $cacheReq = New-Object System.Windows.Automation.CacheRequest
    $cacheReq.Add([System.Windows.Automation.AutomationElement]::NameProperty)
    $cacheReq.Add([System.Windows.Automation.AutomationElement]::AutomationIdProperty)
    $cacheReq.Add([System.Windows.Automation.AutomationElement]::ControlTypeProperty)
    $cacheReq.Add([System.Windows.Automation.AutomationElement]::BoundingRectangleProperty)
    $cacheReq.Add([System.Windows.Automation.AutomationElement]::IsEnabledProperty)
    $cacheReq.Add([System.Windows.Automation.AutomationElement]::ClassNameProperty)
    $cacheReq.TreeScope = [System.Windows.Automation.TreeScope]::Subtree
    
    $swB = [System.Diagnostics.Stopwatch]::StartNew()
    for ($i = 0; $i -lt $iterations; $i++) {
        $cachedNotepad = $notepadElem.GetUpdatedCache($cacheReq)
        # Note: GetUpdatedCache with Subtree caches the whole subtree in a single COM call!
        $n = $cachedNotepad.Cached.Name
        $a = $cachedNotepad.Cached.AutomationId
        $c = $cachedNotepad.Cached.ControlType
        $b = $cachedNotepad.Cached.BoundingRectangle
        $e = $cachedNotepad.Cached.IsEnabled
        $cl = $cachedNotepad.Cached.ClassName
    }
    $swB.Stop()
    $timeCached = $swB.ElapsedMilliseconds
    Write-Output "Cached ($iterations GetUpdatedCache calls): ${timeCached} ms"
    if ($timeCached -gt 0) {
        Write-Output "Speedup factor: $([math]::Round($timeUncached / $timeCached, 2))x"
    }

} finally {
    if ($notepadProc -ne $null -and -not $notepadProc.HasExited) {
        $notepadProc.Kill()
    }
}

Write-Output "`n=== Probe Finished ==="
