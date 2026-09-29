# Свежие статьи

Каждое утро GitHub Actions берёт последние 10 статей из OpenAlex по вашим темам,
Claude пишет к каждой одно предложение по-русски, результат попадает в `data.json`
(его показывает сайт на GitHub Pages) и приходит письмом.

## Настройка (один раз, ~15 минут)

1. Создайте репозиторий на GitHub и загрузите в него все файлы (Add file → Upload files).
2. Ключи и почта: Settings → Secrets and variables → Actions → New repository secret:
   - `OPENALEX_API_KEY` — бесплатно на https://openalex.org/settings/api
   - `ANTHROPIC_API_KEY` — https://console.anthropic.com (платно, но копейки: Haiku, ~20 статей в день)
   - `SMTP_USER` — ваш Gmail, `SMTP_PASS` — пароль приложения (https://myaccount.google.com/apppasswords, нужна 2FA)
   - `MAIL_TO` — куда слать письмо
3. Сайт: Settings → Pages → Source: Deploy from a branch → `main` / `(root)`.
4. Первый запуск: Actions → «Ежедневный дайджест» → Run workflow.
5. На телефоне откройте `https://ВАШ-ЛОГИН.github.io/ИМЯ-РЕПО/`:
   Android — меню Chrome → «Добавить на главный экран»; iPhone — Safari → Поделиться → «На экран Домой».

## Темы

Правьте `scripts/config.json`: `name` — как показывать, `query` — поисковый запрос для OpenAlex
(лучше по-английски). Пустой `query` — просто самые новые статьи вообще.

Время рассылки — 9:00 по Риге (с учётом летнего/зимнего времени): workflow стартует заранее
и ждёт до 9:00, потому что GitHub часто запускает cron с опозданием на несколько часов.
Другое время — поменяйте `09:00` и `Europe/Riga` в `.github/workflows/daily.yml`.
