# run-export.ps1
# Exporta o resultado de uma query da pasta queries/ para um arquivo .csv local
# Uso: .\run-export.ps1 -Query geo_grid_locations_lista
#      .\run-export.ps1 -Query method_coverage -Out coverage.csv
#      .\run-export.ps1 -Query geo_grid_locations_lista -Container meu_db_container

param(
    [Parameter(Mandatory = $true)][string]$Query,
    [string]$Container = "gv_instagram_db",
    [string]$Database  = "instagram",
    [string]$User      = "postgres",
    [string]$Out       = ""
)

$QueriesDir = Join-Path $PSScriptRoot "queries"
$file = Get-ChildItem "$QueriesDir\*.sql" | Where-Object { $_.BaseName -eq $Query } | Select-Object -First 1

if (-not $file) {
    Write-Error "Query '$Query' não encontrada em $QueriesDir. Rode .\run-queries.ps1 para listar os nomes disponíveis."
    exit 1
}

if ($Out -eq "") {
    $Out = "$Query.csv"
}

# Envolve a query original em COPY ... TO STDOUT — remove o ; final se houver
$innerSql = (Get-Content $file.FullName -Raw).TrimEnd()
if ($innerSql.EndsWith(";")) {
    $innerSql = $innerSql.Substring(0, $innerSql.Length - 1)
}
$copySql = "COPY ($innerSql) TO STDOUT WITH CSV HEADER"

# O psql dentro do container escreve em UTF-8 (server_encoding do banco).
# Sem isso, o PowerShell 5.1 decodifica a saída do processo externo usando
# a code page padrão do console (não UTF-8), corrompendo acentos antes
# mesmo do Out-File reescrever o arquivo.
$previousOutputEncoding = [Console]::OutputEncoding
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
try {
    docker exec $Container psql -U $User -d $Database -c $copySql | Out-File -FilePath $Out -Encoding utf8
} finally {
    [Console]::OutputEncoding = $previousOutputEncoding
}

Write-Host "Exportado: $Out" -ForegroundColor Green
