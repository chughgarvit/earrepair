# Speaks every line of tools/clips.tsv with the Windows Indian-English voices.
#   powershell -ExecutionPolicy Bypass -File tools\make_audio.ps1
# Raw clips go to tools\audio_raw. Then run: python tools\finish_audio.py
# Assistant = Heera, task = Ravi: two voices, so "your task" never sounds like the assistant.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $PSScriptRoot 'audio_raw'
New-Item -ItemType Directory -Force $out | Out-Null

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.DataReader, Windows.Storage.Streams, ContentType = WindowsRuntime]

$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [type]$type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
    $task.Wait() | Out-Null
    $task.Result
}

$all = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices
$voices = @{
    assistant = $all | Where-Object { $_.DisplayName -like '*Heera*' } | Select-Object -First 1
    task      = $all | Where-Object { $_.DisplayName -like '*Ravi*' } | Select-Object -First 1
}
foreach ($k in $voices.Keys) { if (-not $voices[$k]) { throw "Voice for '$k' is not installed" } }

$synth = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
$n = 0
foreach ($line in Get-Content (Join-Path $PSScriptRoot 'clips.tsv') -Encoding UTF8) {
    $id, $voice, $text = $line -split "`t"
    $synth.Voice = $voices[$voice]
    $stream = Await ($synth.SynthesizeTextToStreamAsync($text)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
    $reader = New-Object Windows.Storage.Streams.DataReader($stream.GetInputStreamAt(0))
    $size = [uint32]$stream.Size
    $null = Await ($reader.LoadAsync($size)) ([uint32])
    $bytes = New-Object byte[] $size
    $reader.ReadBytes($bytes)
    [System.IO.File]::WriteAllBytes((Join-Path $out "$id.wav"), $bytes)
    $reader.Dispose(); $stream.Dispose()
    $n++
}
"$n clips written to $out"
