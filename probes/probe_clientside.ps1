Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName UIAutomationClientSideProviders

$table = [UIAutomationClientsideProviders.UIAutomationClientSideProviders]::ClientSideProviderDescriptionTable
[System.Windows.Automation.ClientSettings]::RegisterClientSideProviders($table)
Write-Output "Client-side providers registered successfully. Table count: $($table.Length)"

$notepadProc = Start-Process notepad -PassThru
Start-Sleep -Milliseconds 800

try {
    $notepadElem = [System.Windows.Automation.AutomationElement]::FromHandle($notepadProc.MainWindowHandle)
    Write-Output "Notepad Root: $($notepadElem.Current.Name)"
    
    $all = $notepadElem.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    Write-Output "Descendants count: $($all.Count)"
    foreach ($el in $all) {
        $pats = $el.GetSupportedPatterns()
        $patNames = ($pats | ForEach-Object { $_.ProgrammaticName }) -join ", "
        Write-Output "  Element: Role=$($el.Current.ControlType.ProgrammaticName) Class='$($el.Current.ClassName)' Name='$($el.Current.Name)' Patterns=[$patNames]"
    }

    $editCond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::Edit
    )
    $editElem = $notepadElem.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $editCond)
    if ($editElem -ne $null) {
        Write-Output "`n*** SUCCESS: Found Edit control with ControlType=Edit! ***"
        $valPattern = $editElem.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
        Write-Output "ValuePattern acquired! IsReadOnly=$($valPattern.Current.IsReadOnly)"
        
        $testText = "機巧デスクトップ_Yayoi_Test_UTF16"
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $valPattern.SetValue($testText)
        $sw.Stop()
        Write-Output "SetValue executed in: $($sw.ElapsedMilliseconds) ms"
        Write-Output "Value after SetValue: '$($valPattern.Current.Value)'"
        
        $rect = $editElem.Current.BoundingRectangle
        Write-Output "BoundingRectangle: Left=$($rect.Left), Top=$($rect.Top), Width=$($rect.Width), Height=$($rect.Height)"
        $cx = $rect.Left + ($rect.Width / 2)
        $cy = $rect.Top + ($rect.Height / 2)
        Write-Output "BoundingRectangle Center for SendInput: ($cx, $cy)"
    }
} finally {
    if ($notepadProc -ne $null -and -not $notepadProc.HasExited) {
        $notepadProc.Kill()
    }
}
