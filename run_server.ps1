# Supervisor loop for the Invoice Generator dev server.
# Runs independently of any Claude Code session - keeps restarting Django's
# runserver if it ever exits or crashes, and logs to server_supervisor.log.

Set-Location "C:\Users\Prakash\invoice-maker"
$logFile = "C:\Users\Prakash\invoice-maker\server_supervisor.log"
$outLog = "C:\Users\Prakash\invoice-maker\server_stdout.log"
$errLog = "C:\Users\Prakash\invoice-maker\server_stderr.log"

while ($true) {
    Add-Content -Path $logFile -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - starting server"
    $proc = Start-Process -FilePath ".\venv\Scripts\python.exe" `
        -ArgumentList "manage.py", "runserver", "0.0.0.0:8000" `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -NoNewWindow -PassThru -Wait
    Add-Content -Path $logFile -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - server exited (code $($proc.ExitCode)), restarting in 3s"
    Start-Sleep -Seconds 3
}
