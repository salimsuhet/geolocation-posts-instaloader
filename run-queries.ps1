# run-queries.ps1
# Executa todas as queries do projeto contra o banco gv_instagram_db
# Uso: .\run-queries.ps1
#      .\run-queries.ps1 -Query method_coverage      # roda só uma query
#      .\run-queries.ps1 -Container meu_db_container  # container customizado

param(
    [string]$Query     = "",
    [string]$Container = "gv_instagram_db",
    [string]$Database  = "instagram",
    [string]$User      = "postgres"
)

$QueriesDir = Join-Path $PSScriptRoot "queries"

if (-not (Test-Path $QueriesDir)) {
    Write-Error "Pasta 'queries/' não encontrada em $PSScriptRoot"
    exit 1
}

# Filtra por nome se passado via -Query
if ($Query -ne "") {
    $files = Get-ChildItem "$QueriesDir\*.sql" | Where-Object { $_.BaseName -like "*$Query*" }
} else {
    $files = Get-ChildItem "$QueriesDir\*.sql" | Sort-Object Name
}

if ($files.Count -eq 0) {
    Write-Warning "Nenhum arquivo .sql encontrado em $QueriesDir"
    exit 1
}

foreach ($file in $files) {
    $separator = "=" * 60
    Write-Host ""
    Write-Host $separator -ForegroundColor Cyan
    Write-Host "  $($file.Name)" -ForegroundColor Yellow
    Write-Host $separator -ForegroundColor Cyan

    docker cp $file.FullName "${Container}:/tmp/$($file.Name)" | Out-Null
    docker exec -it $Container psql -U $User -d $Database -f "/tmp/$($file.Name)"
}

Write-Host ""
Write-Host "Concluído." -ForegroundColor Green
