# narration.json의 장면별 대본을 Windows 내장 음성(SAPI)으로 WAV 파일로 만든다.
# 사용법: powershell -File tts.ps1 -OutDir <출력 폴더>
param(
  [Parameter(Mandatory = $true)][string]$OutDir
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech

$cfg = Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot "narration.json") | ConvertFrom-Json
New-Item -ItemType Directory -Force $OutDir | Out-Null

$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.SelectVoice($cfg.voice)
$synth.Rate = [int]$cfg.rate
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(
  22050,
  [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
  [System.Speech.AudioFormat.AudioChannel]::Mono)

foreach ($scene in $cfg.scenes) {
  $path = Join-Path $OutDir ($scene.id + ".wav")
  $synth.SetOutputToWaveFile($path, $format)
  $synth.Speak($scene.text)
  $synth.SetOutputToNull()
  Write-Output ("{0} -> {1}" -f $scene.id, $path)
}
$synth.Dispose()
