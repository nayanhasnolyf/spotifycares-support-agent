$done = $false
$iteration = 1

while (-not $done) {
    Write-Host "Batch iteration $iteration..."
    $output = uv run --env-file .env spotify-cares machine-annotate --queue training --provider groq --fallback-provider gemini --limit 5 --retry-unknown-quota 2>&1
    
    $output | Out-Host
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Success! Exit code 0. Assuming all done."
        $done = $true
    } else {
        $outString = $output -join "`n"
        
        if ($outString -match "run locked") {
            Write-Host "FATAL: Lock file detected! Aborting loop to notify agent!"
            exit 1
        }
        
        if ($outString -match "saved.*limit") {
            Write-Host "Daily token limit hit. Purging failure records and sleeping 5 minutes..."
            uv run python clean_jsonl.py
            Get-ChildItem -Recurse -Filter "*budget.jsonl" -ErrorAction SilentlyContinue | Remove-Item -Force
            Start-Sleep -Seconds 310
        } else {
            Write-Host "Cooling down 62s..."
            Start-Sleep -Seconds 62
        }
    }
    $iteration++
}

Write-Host "FINISHED!"
