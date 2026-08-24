#!/bin/bash
# Установка навыка сложного монтажа. Копирует навык и проверяет программы.
set -u
cd "$(dirname "$0")"
SKILLS_DIR="$HOME/.claude/skills"
echo "── Навык сложного монтажа ──"; echo
mkdir -p "$SKILLS_DIR"
[ -d "$SKILLS_DIR/reels-motion" ] && rm -rf "$SKILLS_DIR/reels-motion"
cp -R "skills/reels-motion" "$SKILLS_DIR/"
echo "  ✓ reels-motion установлен (вместе с 26 шрифтами)"
echo
echo "── Программы ──"
miss=""
for pair in "ffmpeg:brew install ffmpeg" "node:brew install node" "python3:есть в macOS"; do
  c="${pair%%:*}"; h="${pair#*:}"
  command -v "$c" >/dev/null 2>&1 && echo "  ✓ $c" || { echo "  ✗ $c"; miss="$miss\n     $c → $h"; }
done
python3 -c "import PIL" 2>/dev/null && echo "  ✓ Pillow" || miss="$miss\n     Pillow → pip3 install --user pillow fonttools brotli"
command -v whisper-cli >/dev/null 2>&1 && echo "  ✓ whisper" || miss="$miss\n     whisper → brew install whisper-cpp"
[ -n "$miss" ] && { echo; echo "Не хватает:"; printf "$miss\n"; echo; echo "Или скажите Claude: «проверь, что нужно для навыка reels-motion, и установи»"; }
cat <<'TXT'

── Последний шаг: плагины ──

   /plugin marketplace add remotion-dev/claude-code-plugin
   /plugin install remotion@remotion
   /plugin install hyperframes@claude-plugins-official

Потом ПЕРЕЗАПУСТИТЕ Claude Code.
Ошибка «Host key verification failed»? Скажите Claude:
   «настрой git на https для github и повтори установку плагина»

Дальше читайте КАК-ДАВАТЬ-МАТЕРИАЛЫ.md
TXT
