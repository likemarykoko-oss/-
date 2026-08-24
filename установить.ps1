<#
    Установка навыка сложного монтажа на Windows.
    Запуск:  powershell -ExecutionPolicy Bypass -File .\установить.ps1
#>

$ProgressPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

$root   = Split-Path -Parent $MyInvocation.MyCommand.Definition
$claude = Join-Path $env:USERPROFILE '.claude'
$skills = Join-Path $claude 'skills'
$models = Join-Path $claude 'models'
$tools  = Join-Path $claude 'tools'
$missing = New-Object System.Collections.ArrayList

function Note($text)  { Write-Host "  $text" }
function Ok($text)    { Write-Host "  [ok] $text" -ForegroundColor Green }
function Bad($text)   { Write-Host "  [--] $text" -ForegroundColor Yellow }
function Head($text)  { Write-Host ""; Write-Host "== $text ==" -ForegroundColor Cyan }
function Have($cmd)   { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

function Refresh-Path {
    $m = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $u = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = ($m, $u | Where-Object { $_ }) -join ';'
}

function Add-UserPath($dir) {
    $u = [Environment]::GetEnvironmentVariable('Path', 'User')
    if ($u -and ($u -split ';' | Where-Object { $_.TrimEnd('\') -ieq $dir.TrimEnd('\') })) { return }
    $new = if ($u) { "$u;$dir" } else { $dir }
    [Environment]::SetEnvironmentVariable('Path', $new, 'User')
    Refresh-Path
}

# ── 1. Навык ────────────────────────────────────────────────────────────────
Head 'Навык'
$src = Join-Path $root 'skills\reels-motion'
if (-not (Test-Path $src)) {
    Bad "не нашёл папку skills\reels-motion рядом со скриптом"
    Note "запускайте установить.ps1 из распакованной папки комплекта"
    exit 1
}
try {
    New-Item -ItemType Directory -Force -Path $skills | Out-Null
    $dst = Join-Path $skills 'reels-motion'
    if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
    Copy-Item -Recurse -Force $src $dst
    Ok "reels-motion установлен (вместе с 26 шрифтами)"
    Note $dst
} catch {
    Bad "не удалось скопировать навык: $($_.Exception.Message)"
    exit 1
}

# ── 2. Программы ────────────────────────────────────────────────────────────
Head 'Программы'
$winget = Have 'winget'
if (-not $winget) {
    Bad "нет winget — поставьте «Установщик приложений» из Microsoft Store"
    Note "без него программы придётся ставить вручную"
}

function Ensure-Tool($cmd, $wingetId, $human) {
    if (Have $cmd) { Ok $human; return }
    if (-not $winget) { Bad "$human — нет"; [void]$missing.Add("$human"); return }
    Note "ставлю $human ..."
    winget install --id $wingetId -e --silent --accept-source-agreements --accept-package-agreements | Out-Null
    Refresh-Path
    if (Have $cmd) { Ok $human } else { Bad "$human — не встал, поставьте вручную"; [void]$missing.Add($human) }
}

Ensure-Tool 'node'    'OpenJS.NodeJS.LTS'  'Node.js'
Ensure-Tool 'ffmpeg'  'Gyan.FFmpeg'        'ffmpeg'
Ensure-Tool 'python'  'Python.Python.3.12' 'Python'

# ── 3. Библиотеки Python ────────────────────────────────────────────────────
Head 'Библиотеки Python'
if (Have 'python') {
    python -m pip install --quiet --user --upgrade pillow fonttools brotli 2>&1 | Out-Null
    python -c "import PIL, fontTools, brotli" 2>$null
    if ($LASTEXITCODE -eq 0) { Ok 'Pillow, fontTools, brotli' }
    else { Bad 'Pillow не встал'; [void]$missing.Add('Pillow -> python -m pip install --user pillow fonttools brotli') }
} else {
    Bad 'без Python библиотеки не поставить'
}

# ── 4. Whisper ──────────────────────────────────────────────────────────────
Head 'Whisper (распознавание речи)'
if (Have 'whisper-cli') {
    Ok 'whisper-cli уже стоит'
} else {
    try {
        $api = 'https://api.github.com/repos/ggml-org/whisper.cpp/releases/latest'
        $rel = Invoke-RestMethod $api -Headers @{ 'User-Agent' = 'reels-motion' }
        $asset = $rel.assets | Where-Object { $_.name -eq 'whisper-bin-x64.zip' } | Select-Object -First 1
        if (-not $asset) { throw "в релизе $($rel.tag_name) нет whisper-bin-x64.zip" }

        $zip = Join-Path $env:TEMP 'whisper-bin-x64.zip'
        $dir = Join-Path $tools 'whisper'
        Note "скачиваю $($rel.tag_name) ..."
        Invoke-WebRequest $asset.browser_download_url -OutFile $zip
        if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        Expand-Archive -Path $zip -DestinationPath $dir -Force
        Remove-Item $zip -Force

        $exe = Get-ChildItem -Path $dir -Filter 'whisper-cli.exe' -Recurse | Select-Object -First 1
        if (-not $exe) { throw 'в архиве нет whisper-cli.exe' }
        Add-UserPath $exe.Directory.FullName
        if (Have 'whisper-cli') { Ok 'whisper-cli' } else { Ok "whisper-cli ($($exe.Directory.FullName))" }
    } catch {
        Bad "whisper не встал: $($_.Exception.Message)"
        [void]$missing.Add('whisper -> скачайте whisper-bin-x64.zip со страницы релизов ggml-org/whisper.cpp')
    }
}

# ── 5. Модель распознавания ─────────────────────────────────────────────────
Head 'Модель распознавания'
$model = Join-Path $models 'ggml-small.bin'
if ((Test-Path $model) -and ((Get-Item $model).Length -gt 100MB)) {
    Ok 'ggml-small.bin уже на месте'
} else {
    try {
        New-Item -ItemType Directory -Force -Path $models | Out-Null
        Note 'скачиваю ggml-small.bin, 466 МБ — это долго ...'
        $url = 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin'
        Invoke-WebRequest $url -OutFile $model
        if ((Get-Item $model).Length -lt 100MB) { throw 'файл скачался обрезанным' }
        Ok 'ggml-small.bin'
        Note $model
    } catch {
        Bad "модель не скачалась: $($_.Exception.Message)"
        [void]$missing.Add('модель -> скажите Claude «скачай модель small для whisper»')
    }
}

# ── Итог ────────────────────────────────────────────────────────────────────
if ($missing.Count -gt 0) {
    Head 'Не хватает'
    foreach ($m in $missing) { Note $m }
    Note ''
    Note 'Или скажите Claude: «проверь, что нужно для навыка reels-motion, и установи»'
}

Head 'Последний шаг: плагины'
Note ''
Note '   /plugin marketplace add remotion-dev/claude-code-plugin'
Note '   /plugin install remotion@remotion'
Note '   /plugin install hyperframes@claude-plugins-official'
Note ''
Note 'Потом ПЕРЕЗАПУСТИТЕ Claude Code — иначе плагины и навык не подключатся.'
Note 'Ошибка «Host key verification failed»? Скажите Claude:'
Note '   «настрой git на https для github и повтори установку плагина»'
Note ''
Note 'Дальше читайте КАК-ДАВАТЬ-МАТЕРИАЛЫ.md'
