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

docker exec $Container psql -U $User -d $Database -c $copySql | Out-File -FilePath $Out -Encoding utf8

Write-Host "Exportado: $Out" -ForegroundColor Green
