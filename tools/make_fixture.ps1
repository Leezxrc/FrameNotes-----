$ErrorActionPreference = 'Stop'
$testOutput = Join-Path $PSScriptRoot '..\.test-artifacts'
New-Item -ItemType Directory -Path $testOutput -Force | Out-Null
$testOutput = (Resolve-Path -LiteralPath $testOutput).Path
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice = $speaker.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'en-*' } | Select-Object -First 1
if ($voice) { $speaker.SelectVoice($voice.VoiceInfo.Name) }
$speaker.SetOutputToWaveFile((Join-Path $testOutput 'speech.wav'))
$speaker.Speak('Welcome to Video Notes. This application creates subtitles from a local video. You can edit the transcript and save your notes. Thank you for watching.')
$speaker.Dispose()
& ffmpeg -hide_banner -loglevel error -y -f lavfi -i 'color=c=0x162733:s=960x540:r=24' -i (Join-Path $testOutput 'speech.wav') -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest (Join-Path $testOutput 'demo.mp4')
if ($LASTEXITCODE -ne 0) { throw 'FFmpeg fixture generation failed' }
Write-Output (Join-Path $testOutput 'demo.mp4')
