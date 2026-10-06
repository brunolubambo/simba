# Cria o início automático do SIMBA para o usuário atual, sem administrador.
# Padrão: tarefa "SIMBA" ao fazer logon. Com -Atalho: atalho na pasta Inicializar.
# Pode rodar de novo: atualiza o que já existir.
param(
    [switch]$Atalho
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Pythonw = Join-Path $Root ".venv\Scripts\pythonw.exe"
$Launcher = Join-Path $Root "simba_desktop.py"
$TaskName = "SIMBA"

if (-not (Test-Path -LiteralPath $Pythonw)) {
    Write-Host "Não encontrei o pythonw do projeto: $Pythonw"
    Write-Host "Crie o .venv e instale as dependências antes."
    exit 1
}
if (-not (Test-Path -LiteralPath $Launcher)) {
    Write-Host "Não encontrei o launcher: $Launcher"
    exit 1
}

function Install-SimbaShortcut {
    $startup = [Environment]::GetFolderPath("Startup")
    $lnk = Join-Path $startup "SIMBA.lnk"
    $existed = Test-Path -LiteralPath $lnk
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($lnk)
    $sc.TargetPath = $Pythonw
    $sc.Arguments = '"' + $Launcher + '" --oculto'
    $sc.WorkingDirectory = $Root
    $sc.WindowStyle = 7
    $sc.Description = "SIMBA"
    $sc.Save()
    if ($existed) {
        Write-Host "Atalho atualizado: $lnk"
    } else {
        Write-Host "Atalho criado: $lnk"
    }
    Write-Host "Ele abre o pythonw com simba_desktop.py --oculto, sem janela de console."
}

if ($Atalho) {
    Install-SimbaShortcut
    Write-Host "Não mexi na tarefa do Agendador. Para usar a tarefa, rode de novo sem -Atalho."
    exit 0
}

$me = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$existed = $null -ne (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)
$action = New-ScheduledTaskAction -Execute $Pythonw -Argument ('"' + $Launcher + '" --oculto') -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $me
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId $me -LogonType Interactive -RunLevel Limited
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "SIMBA no PC: servidor local e bandeja, ao fazer logon. Sem administrador." `
    -Force | Out-Null

if ($existed) {
    Write-Host "Tarefa SIMBA atualizada."
} else {
    Write-Host "Tarefa SIMBA criada."
}
Write-Host "Gatilho: ao fazer logon de $me."
Write-Host "Executa, oculto: $Pythonw `"$Launcher`" --oculto"
Write-Host "Se o processo falhar, o Agendador tenta de novo (3 vezes, 1 minuto)."
Write-Host "Para um atalho na pasta Inicializar, em vez da tarefa: instalar-autostart.ps1 -Atalho"
exit 0
