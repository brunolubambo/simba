# Remove a tarefa SIMBA e o atalho da pasta Inicializar. Pode rodar de novo.
$ErrorActionPreference = "Stop"
$TaskName = "SIMBA"
$failed = $false

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "Tarefa: não havia SIMBA no Agendador."
} else {
    $blob = @($task.Actions | ForEach-Object { "$($_.Execute) $($_.Arguments)" }) -join " "
    if ($blob -notlike "*simba_desktop.py*") {
        Write-Host "Tarefa SIMBA existe, mas não executa simba_desktop.py. Não removi."
        $failed = $true
    } else {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Tarefa SIMBA removida."
    }
}

$startup = [Environment]::GetFolderPath("Startup")
$lnk = Join-Path $startup "SIMBA.lnk"
if (-not (Test-Path -LiteralPath $lnk)) {
    Write-Host "Atalho: não havia SIMBA.lnk na pasta Inicializar."
} else {
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($lnk)
    $points = "$($sc.TargetPath) $($sc.Arguments)"
    if ($points -notlike "*simba_desktop.py*") {
        Write-Host "Atalho SIMBA.lnk existe, mas não aponta para simba_desktop.py. Não removi."
        $failed = $true
    } else {
        Remove-Item -LiteralPath $lnk -Force
        Write-Host "Atalho removido: $lnk"
    }
}

if ($failed) { exit 1 }
exit 0
