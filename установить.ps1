<#
    Установка навыка сложного монтажа на Windows.
    Запуск:  powershell -ExecutionPolicy Bypass -File .\установить.ps1
#>

$ProgressPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

$root   = Split-Path -Parent $MyInvocation.MyCommand.Definition
$claude = Join-Path $env:USERPROFILE '.claude'
$skills = Join-Path $claude 'skills'
$models = Join-Path $claude 'models'
$tools  = Join-Path $claude 'tools'
# Своя рабочая папка вместо $env:TEMP: при кириллице в имени пользователя
# TEMP подставляется коротким именем вида C:\Users\75BD~1, которого может не быть.
$work   = Join-Path $claude 'tmp'
$missing = New-Object System.Collections.ArrayList

function Note($text) { Write-Host "  $text" }
function Ok($text)   { Write-Host "  [ok] $text" -ForegroundColor Green }
function Bad($text)  { Write-Host "  [--] $text" -ForegroundColor Yellow }
function Head($text) { Write-Host ""; Write-Host "== $text ==" -ForegroundColor Cyan }

# python.exe и python3.exe в WindowsApps — заглушки, открывающие Microsoft Store.
# Get-Command их находит, но запустить нельзя, поэтому считаем, что команды нет.
function Have($cmd) {
    $c = Get-Command $cmd -ErrorAction SilentlyContinue
    if (-not $c) { return $false }
    if ($c.Source -and $c.Source -like '*\WindowsApps\*' -and $c.Source -like '*python*') { return $false }
    return $true
}

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

function Show-Tail($file, $count) {
    if (Test-Path $file) {
        Get-Content $file -Tail $count -ErrorAction SilentlyContinue |
            ForEach-Object { Note "     | $_" }
    }
}

New-Item -ItemType Directory -Force -Path $work | Out-Null

# ── 1. Навык ────────────────────────────────────────────────────────────────
Head 'Навык'
$src = Join-Path $root 'skills\reels-motion'
if (-not (Test-Path $src)) {
    Bad "не нашёл папку skills\reels-motion рядом со скриптом"
    Note "скрипт лежит в: $root"
    Note "запускайте установить.ps1 из той папки комплекта, где видно папку skills"
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
$winget = [bool](Get-Command 'winget' -ErrorAction SilentlyContinue)
if (-not $winget) {
    Bad "нет winget — поставьте «Установщик приложений» из Microsoft Store"
    Note "без него программы придётся ставить вручную"
}

function Try-Winget($wingetId, $cmd, $human) {
    if (-not $winget) { return $false }
    Note "ставлю $human через winget ..."
    $log = Join-Path $work "winget-$cmd.log"
    try {
        winget install --id $wingetId -e --accept-source-agreements --accept-package-agreements 2>&1 |
            Out-File -FilePath $log -Encoding UTF8
    } catch {
        $_.Exception.Message | Out-File -FilePath $log -Encoding UTF8
    }
    Refresh-Path
    if (Have $cmd) { return $true }
    Note "winget не справился, вот его ответ:"
    Show-Tail $log 4
    return $false
}

# Распаковывает архив в $tools\<name> и добавляет в PATH папку, где лежит $exeName.
function Install-Zip($url, $name, $exeName) {
    $zip = Join-Path $work "$name.zip"
    $dir = Join-Path $tools $name
    if (Test-Path $zip) { Remove-Item $zip -Force }
    Invoke-WebRequest $url -OutFile $zip
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    Expand-Archive -LiteralPath $zip -DestinationPath $dir -Force
    Remove-Item $zip -Force
    $exe = Get-ChildItem -LiteralPath $dir -Filter $exeName -Recurse | Select-Object -First 1
    if (-not $exe) { throw "в архиве нет $exeName" }
    Add-UserPath $exe.Directory.FullName
    return $exe.Directory.FullName
}

function Install-NodeDirect {
    $base = 'https://nodejs.org/dist/latest-v22.x/'
    $sums = (Invoke-WebRequest ($base + 'SHASUMS256.txt') -UseBasicParsing).Content
    $m = [regex]::Match($sums, 'node-v[\d.]+-win-x64\.zip')
    if (-not $m.Success) { throw 'не нашёл node-*-win-x64.zip в списке версий' }
    Note "скачиваю $($m.Value) ..."
    return (Install-Zip ($base + $m.Value) 'node' 'node.exe')
}

function Install-FfmpegDirect {
    Note 'скачиваю ffmpeg-release-essentials.zip ...'
    return (Install-Zip 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' 'ffmpeg' 'ffmpeg.exe')
}

function Install-PythonDirect {
    # У 3.12 свежие выпуски идут только исходниками, установщика для Windows нет.
    foreach ($v in @('3.13.9', '3.13.8', '3.12.10')) {
        $url = "https://www.python.org/ftp/python/$v/python-$v-amd64.exe"
        try { $head = Invoke-WebRequest $url -Method Head -UseBasicParsing } catch { continue }
        if ($head.StatusCode -ne 200) { continue }
        $exe = Join-Path $work "python-$v-amd64.exe"
        Note "скачиваю Python $v ..."
        Invoke-WebRequest $url -OutFile $exe
        Note 'ставлю, окна не будет — это тихая установка ...'
        Start-Process -FilePath $exe -Wait -ArgumentList @(
            '/quiet', 'InstallAllUsers=0', 'PrependPath=1', 'Include_pip=1', 'Include_launcher=1'
        )
        Remove-Item $exe -Force -ErrorAction SilentlyContinue
        Refresh-Path
        return $v
    }
    throw 'не нашёл установщик Python на python.org'
}

# winget на многих машинах отсутствует или молча отказывает, поэтому за ним
# идёт запасной путь — прямая загрузка с сайта проекта.
function Ensure-Tool($cmd, $wingetId, $human, $fallback) {
    if (Have $cmd) { Ok $human; return }
    if (Try-Winget $wingetId $cmd $human) { Ok $human; return }
    try {
        $where = & $fallback
        Refresh-Path
        if (Have $cmd) {
            Ok "$human (скачан напрямую)"
            if ($where) { Note $where }
            return
        }
        Bad "$human — файлы легли, но команда не отвечает в этом окне"
        [void]$missing.Add("$human -> закройте окно, откройте PowerShell заново и запустите скрипт ещё раз")
    } catch {
        Bad "$human — не встал: $($_.Exception.Message)"
        [void]$missing.Add("$human -> winget install --id $wingetId -e")
    }
}

Ensure-Tool 'node'   'OpenJS.NodeJS.LTS'  'Node.js' ${function:Install-NodeDirect}
Ensure-Tool 'ffmpeg' 'Gyan.FFmpeg'        'ffmpeg'  ${function:Install-FfmpegDirect}
Ensure-Tool 'python' 'Python.Python.3.13' 'Python'  ${function:Install-PythonDirect}

# ── 3. Библиотеки Python ────────────────────────────────────────────────────
Head 'Библиотеки Python'
if (Have 'python') {
    $pipLog = Join-Path $work 'pip.log'
    $pipOk = $false
    foreach ($extra in @('--user', '')) {
        $cmdArgs = @('-m', 'pip', 'install', '--quiet', '--upgrade')
        if ($extra) { $cmdArgs += $extra }
        $cmdArgs += @('pillow', 'fonttools', 'brotli')
        & python $cmdArgs 2>&1 | Out-File -FilePath $pipLog -Append -Encoding UTF8
        & python -c "import PIL, fontTools, brotli" 2>$null
        if ($LASTEXITCODE -eq 0) { $pipOk = $true; break }
    }
    if ($pipOk) {
        Ok 'Pillow, fontTools, brotli'
    } else {
        Bad 'Pillow не встал, вот что ответил pip:'
        Show-Tail $pipLog 6
        [void]$missing.Add('Pillow -> python -m pip install --user pillow fonttools brotli')
    }

    # Навык вызывает `python3`, которого на Windows нет. Кладём переходник,
    # чтобы команды из SKILL.md работали как написано.
    $py3 = Get-Command 'python3' -ErrorAction SilentlyContinue
    $isStub = $py3 -and ($py3.Source -like '*\WindowsApps\*')
    if ((-not $py3) -or $isStub) {
        try {
            $bin = Join-Path $tools 'bin'
            New-Item -ItemType Directory -Force -Path $bin | Out-Null
            Set-Content -Path (Join-Path $bin 'python3.cmd') -Value "@echo off`r`npython %*" -Encoding ASCII
            Add-UserPath $bin
            Ok 'переходник python3 -> python'
        } catch {
            Bad "переходник python3 не создался: $($_.Exception.Message)"
            [void]$missing.Add('python3 -> в командах навыка пишите python вместо python3')
        }
    } else {
        Ok 'python3'
    }
} else {
    Bad 'без Python библиотеки не поставить'
    [void]$missing.Add('Pillow -> сначала Python, потом python -m pip install --user pillow fonttools brotli')
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

        $zip = Join-Path $work 'whisper-bin-x64.zip'
        $dir = Join-Path $tools 'whisper'
        Note "скачиваю $($rel.tag_name) ..."
        if (Test-Path $zip) { Remove-Item $zip -Force }
        Invoke-WebRequest $asset.browser_download_url -OutFile $zip
        if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        Expand-Archive -LiteralPath $zip -DestinationPath $dir -Force
        Remove-Item $zip -Force

        $exe = Get-ChildItem -LiteralPath $dir -Filter 'whisper-cli.exe' -Recurse |
               Select-Object -First 1
        if (-not $exe) { throw 'в архиве нет whisper-cli.exe' }
        Add-UserPath $exe.Directory.FullName
        Ok "whisper-cli"
        Note $exe.Directory.FullName
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
    Note $model
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

# ── Проверка ────────────────────────────────────────────────────────────────
Head 'Проверка'
foreach ($pair in @(@('node','--version'), @('ffmpeg','-version'), @('python','--version'))) {
    $c = $pair[0]
    if (Have $c) {
        $out = (& $c $pair[1] 2>$null | Select-Object -First 1)
        Ok "$c — $out"
    } else {
        Bad "$c — не отвечает"
    }
}
# whisper-cli печатает справку в stderr, поэтому просто показываем, где он лежит
$wc = Get-Command 'whisper-cli' -ErrorAction SilentlyContinue
if ($wc) { Ok "whisper-cli — $($wc.Source)" } else { Bad 'whisper-cli — не отвечает' }
if (Test-Path $model) { Ok "модель — $([math]::Round((Get-Item $model).Length/1MB)) МБ" }
else { Bad 'модель ggml-small.bin — нет' }

# ── Итог ────────────────────────────────────────────────────────────────────
if ($missing.Count -gt 0) {
    Head 'Не хватает'
    foreach ($m in $missing) { Note $m }
    Note ''
    Note 'Закройте это окно, откройте PowerShell заново и запустите скрипт ещё раз —'
    Note 'часть программ появляется в PATH только в новом окне.'
    Note 'Не помогло — скажите Claude: «проверь, что нужно для навыка reels-motion, и установи»'
} else {
    Head 'Всё на месте'
    Note 'Программы, навык и модель установлены.'
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
