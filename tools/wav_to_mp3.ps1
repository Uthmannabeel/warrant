# Transcode WAV -> MP3 using the OS Media Foundation encoder (no ffmpeg, fully offline).
param(
  [string]$Wav = "C:\Users\Nabeel Uthman\Downloads\_warrant-narration.wav",
  [string]$OutDir = "C:\Users\Nabeel Uthman\Downloads",
  [string]$OutName = "Warrant-Narration.mp3"
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null

# Helpers to await WinRT async from Windows PowerShell 5.1
$asTaskOp = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
  $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
$asTaskActProg = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
  $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncActionWithProgress`1' })[0]
function AwaitOp($op, $type) {
  $t = $asTaskOp.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result
}
function AwaitActProg($op, $ptype) {
  $t = $asTaskActProg.MakeGenericMethod($ptype).Invoke($null, @($op)); $t.Wait(-1) | Out-Null
}

[Windows.Storage.StorageFile,        Windows.Storage, ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.StorageFolder,      Windows.Storage, ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Transcoding.MediaTranscoder, Windows.Media, ContentType=WindowsRuntime] | Out-Null
[Windows.Media.MediaProperties.MediaEncodingProfile, Windows.Media, ContentType=WindowsRuntime] | Out-Null
[Windows.Media.MediaProperties.AudioEncodingQuality, Windows.Media, ContentType=WindowsRuntime] | Out-Null

$src    = AwaitOp ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Wav)) ([Windows.Storage.StorageFile])
$folder = AwaitOp ([Windows.Storage.StorageFolder]::GetFolderFromPathAsync($OutDir)) ([Windows.Storage.StorageFolder])
$dst    = AwaitOp ($folder.CreateFileAsync($OutName, [Windows.Storage.CreationCollisionOption]::ReplaceExisting)) ([Windows.Storage.StorageFile])

$profile = [Windows.Media.MediaProperties.MediaEncodingProfile]::CreateMp3([Windows.Media.MediaProperties.AudioEncodingQuality]::High)
$tr = New-Object Windows.Media.Transcoding.MediaTranscoder
$prep = AwaitOp ($tr.PrepareFileTranscodeAsync($src, $dst, $profile)) ([Windows.Media.Transcoding.PrepareTranscodeResult])
if (-not $prep.CanTranscode) { throw "CanTranscode = false ($($prep.FailureReason))" }
AwaitActProg ($prep.TranscodeAsync()) ([double])
Write-Output ("MP3 written: " + (Join-Path $OutDir $OutName))
