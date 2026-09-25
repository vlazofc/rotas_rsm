$ErrorActionPreference = 'Stop'

$desktop = [Environment]::GetFolderPath('Desktop')
$md = Join-Path $desktop 'Relatorio-Geral-Adimax-Log-2026-09-18.md'
$html = Join-Path $desktop 'Relatorio-Geral-Adimax-Log-2026-09-18.html'
$pdf = Join-Path $desktop 'Relatorio-Geral-Adimax-Log-2026-09-18.pdf'
$chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'

$css = @'
@page { size: A4; margin: 17mm 15mm; }
* { box-sizing: border-box; }
body { font-family: "Segoe UI", Arial, sans-serif; color: #172033; font-size: 10.5pt; line-height: 1.5; margin: 0; }
body::before { content: "RELATÓRIO ADIMAX LOG"; display: block; background: #ffb21a; color: #111827; border-radius: 10px; padding: 16px 20px; font-size: 15pt; font-weight: 800; letter-spacing: .06em; margin-bottom: 18px; }
h1 { font-size: 25pt; line-height: 1.1; margin: 0 0 12px; color: #101827; }
h2 { font-size: 16pt; color: #ad6200; margin: 24px 0 9px; padding-bottom: 5px; border-bottom: 2px solid #ffd98c; page-break-after: avoid; }
h3 { font-size: 12.5pt; color: #25334d; margin: 17px 0 6px; page-break-after: avoid; }
p { margin: 7px 0 9px; }
ul, ol { margin: 6px 0 10px 22px; padding: 0; }
li { margin: 3px 0; }
table { width: 100%; border-collapse: collapse; margin: 10px 0 15px; font-size: 9pt; }
tr { page-break-inside: avoid; }
th { background: #202a3c; color: white; text-align: left; }
th, td { border: 1px solid #cfd5df; padding: 6px 7px; vertical-align: top; }
tr:nth-child(even) td { background: #f7f8fa; }
blockquote { margin: 12px 0; padding: 9px 12px; background: #fff8e8; border-left: 4px solid #ffae00; }
code { background: #eef1f5; border-radius: 3px; padding: 1px 4px; font-size: 9pt; }
'@

$fragment = (ConvertFrom-Markdown -Path $md).Html
$document = '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><style>' + $css + '</style></head><body>' + $fragment + '</body></html>'
Set-Content -LiteralPath $html -Value $document -Encoding utf8
& $chrome --headless --disable-gpu --no-pdf-header-footer --print-to-pdf="$pdf" ([Uri]$html).AbsoluteUri | Out-Null
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pdf)) { throw 'Não foi possível gerar o relatório em PDF.' }
Write-Host "Relatório gerado em $desktop"
