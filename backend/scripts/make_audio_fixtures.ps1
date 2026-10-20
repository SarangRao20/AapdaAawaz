# Generates the SYNTHETIC audio fixtures in backend/data/audio using the Windows built-in
# speech synthesizer (System.Speech, English voices only). These are robot-voice renderings
# of authored fixture transcripts, NOT recordings of real people or real emergencies.
# Usage (from backend/):  powershell -ExecutionPolicy Bypass -File scripts\make_audio_fixtures.ps1
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech

$root = Split-Path -Parent $PSScriptRoot
$dataset = Get-Content -Raw -Encoding UTF8 (Join-Path $root "data\synthetic_reports.json") | ConvertFrom-Json
$outDir = Join-Path $root "data\audio"
New-Item -ItemType Directory -Force $outDir | Out-Null

$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
foreach ($r in $dataset.reports) {
    if (-not $r.audio_fixture) { continue }
    $path = Join-Path $outDir $r.audio_fixture
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $synth.Rate = 0
    $synth.SetOutputToWaveFile($path, $format)
    $synth.Speak($r.transcript)
    $synth.Dispose()
    Write-Output "wrote $($r.audio_fixture) for $($r.id)"
}
