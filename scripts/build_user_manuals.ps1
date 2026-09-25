$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$manualDir = Join-Path $root 'docs\manual'
$chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
if (-not (Test-Path -LiteralPath $chrome)) {
    $chrome = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
}
if (-not (Test-Path -LiteralPath $chrome)) { throw 'Chrome ou Edge não encontrado.' }

$css = @'
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
* { box-sizing: border-box; }
body { font-family: "Segoe UI", Arial, sans-serif; color: #172033; font-size: 10.5pt; line-height: 1.48; margin: 0; }
body::before { content: "ADIMAX LOG"; display: block; color: #111827; background: #ffb21a; border-radius: 10px; padding: 16px 20px; font-size: 14pt; font-weight: 800; letter-spacing: .08em; margin-bottom: 18px; }
h1 { font-size: 27pt; line-height: 1.08; margin: 0 0 8px; color: #101827; page-break-after: avoid; }
h2 { font-size: 17pt; color: #ad6200; margin: 26px 0 10px; padding-bottom: 5px; border-bottom: 2px solid #ffd98c; page-break-after: avoid; }
h3 { font-size: 13pt; color: #25334d; margin: 19px 0 7px; page-break-after: avoid; }
h4 { font-size: 11pt; margin: 15px 0 5px; page-break-after: avoid; }
p { margin: 7px 0 9px; }
ul, ol { margin: 7px 0 11px 22px; padding: 0; }
li { margin: 3px 0; }
blockquote { margin: 14px 0; padding: 10px 13px; background: #fff8e8; border-left: 4px solid #ffae00; color: #4d3b15; }
table { width: 100%; border-collapse: collapse; margin: 10px 0 16px; font-size: 9pt; page-break-inside: auto; }
tr { page-break-inside: avoid; }
th { background: #202a3c; color: white; text-align: left; }
th, td { border: 1px solid #cfd5df; padding: 6px 7px; vertical-align: top; }
tr:nth-child(even) td { background: #f7f8fa; }
code { background: #eef1f5; border-radius: 3px; padding: 1px 4px; font-size: 9pt; }
img { display: block; max-width: 100%; max-height: 170mm; object-fit: contain; margin: 14px auto; border: 1px solid #d7dce4; border-radius: 12px; box-shadow: 0 5px 18px #0002; }
strong { color: #111827; }
@media print { a { color: inherit; text-decoration: none; } h2 { break-before: auto; } }
'@

$files = @(
    @{ Source = 'Manual-do-Usuario-Adimax-Log.md'; Pdf = 'Manual-do-Usuario-Adimax-Log.pdf' },
    @{ Source = 'Manual-do-Motorista-Adimax-Android.md'; Pdf = 'Manual-do-Motorista-Adimax-Android.pdf' }
)

foreach ($item in $files) {
    $source = Join-Path $manualDir $item.Source
    $pdf = Join-Path $manualDir $item.Pdf
    $htmlPath = [IO.Path]::ChangeExtension($pdf, '.html')
    $fragment = (ConvertFrom-Markdown -Path $source).Html
    $baseUri = ([Uri]$manualDir).AbsoluteUri.TrimEnd('/') + '/'
    $html = '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><base href="' + $baseUri + '"><style>' + $css + '</style></head><body>' + $fragment + '</body></html>'
    Set-Content -LiteralPath $htmlPath -Value $html -Encoding utf8
    $uri = ([Uri]$htmlPath).AbsoluteUri
    & $chrome --headless --disable-gpu --no-pdf-header-footer --print-to-pdf="$pdf" $uri | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pdf)) { throw "Falha ao gerar $pdf" }
}

Write-Host 'Manuais gerados com sucesso.'
