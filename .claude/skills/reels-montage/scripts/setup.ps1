# Ставит всё, что нужно навыку монтажа, на Windows. Запускать один раз в PowerShell:
#   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.claude\skills\reels-montage\scripts\setup.ps1"

$ErrorActionPreference = "Continue"

function Say($t) { Write-Host $t }

Say "Проверяю, что уже стоит."

# ── Python ───────────────────────────────────────────────────────────────────
$PY = $null
foreach ($c in @("python", "py", "python3")) {
    $found = Get-Command $c -ErrorAction SilentlyContinue
    if ($found) {
        $v = & $c -c "import sys; print(sys.version_info[0])" 2>$null
        if ($v -eq "3") { $PY = $c; break }
    }
}
if (-not $PY) {
    Say "  Python 3 не найден — ставлю"
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    Say ""
    Say "Python поставлен. ЗАКРОЙ это окно, открой новое и запусти файл ещё раз —"
    Say "иначе система не увидит новую программу."
    exit 0
}
Say "  Python — есть ($PY)"

# ── ffmpeg ───────────────────────────────────────────────────────────────────
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Say "  ffmpeg — есть"
} else {
    Say "  ffmpeg — ставлю"
    winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path", "User")
    if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
        Say "  ffmpeg поставлен, но появится только в новом окне — перезапусти файл после установки."
    }
}

# ── питоновские библиотеки ───────────────────────────────────────────────────
Say "  библиотеки для текста и шрифтов"
& $PY -m pip install --user --quiet --upgrade pillow fonttools brotli

Say "  распознавание речи (faster-whisper)"
& $PY -m pip install --user --quiet --upgrade faster-whisper

# ── модель распознавания ─────────────────────────────────────────────────────
$MODEL = if ($args[0]) { $args[0] } else { "medium" }
Say ""
Say "Скачиваю модель распознавания «$MODEL» — около полутора гигабайт и только один раз."
& $PY -c @"
import sys
try:
    from faster_whisper import WhisperModel
    WhisperModel('$MODEL', device='cpu', compute_type='int8')
    print('  модель готова')
except Exception as e:
    print('  модель не скачалась (%s). Скачается сама при первом монтаже.' % e)
"@

# ── итог ─────────────────────────────────────────────────────────────────────
Say ""
& $PY -c @"
import shutil, importlib
rows = [('ffmpeg', bool(shutil.which('ffmpeg')))]
for mod, name in [('PIL', 'текст на видео'), ('fontTools', 'свои шрифты'),
                  ('faster_whisper', 'распознавание речи')]:
    try:
        importlib.import_module(mod); rows.append((name, True))
    except ImportError:
        rows.append((name, False))
print('Что получилось:')
for name, ok in rows:
    print(('  [v] ' if ok else '  [ ] ') + name)
print('\nВсё готово.' if all(ok for _, ok in rows)
      else '\nЧего-то не хватает — скажи Claude, он доставит.')
"@
