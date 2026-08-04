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

# O psql dentro do container escreve em UTF-8 (server_encoding do banco).
# Sem isso, o PowerShell 5.1 decodifica a saída do processo externo usando
# a code page padrão do console (não UTF-8), corrompendo acentos na tela.
$previousOutputEncoding = [Console]::OutputEncoding
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
try {
    foreach ($file in $files) {
        $separator = "=" * 60
        Write-Host ""
        Write-Host $separator -ForegroundColor Cyan
        Write-Host "  $($file.Name)" -ForegroundColor Yellow
        Write-Host $separator -ForegroundColor Cyan

        docker cp $file.FullName "${Container}:/tmp/$($file.Name)" | Out-Null
        docker exec -it $Container psql -U $User -d $Database -f "/tmp/$($file.Name)"
    }
} finally {
    [Console]::OutputEncoding = $previousOutputEncoding
}

Write-Host ""
Write-Host "Concluído." -ForegroundColor Green
