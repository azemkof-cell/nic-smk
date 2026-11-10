param(
  [Parameter(Mandatory=$true)][string]$Docx,
  [Parameter(Mandatory=$true)][string]$Pdf
)
$ErrorActionPreference = "Stop"
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
  $doc = $word.Documents.Open($Docx, $false, $true)
  $doc.SaveAs([ref]$Pdf, [ref]17)
  $doc.Close(0)
} finally {
  $word.Quit()
}
Write-Output "OK"
