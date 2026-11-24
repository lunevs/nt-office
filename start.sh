#!/bin/sh
set -eu
python manage.py migrate --noinput
python manage.py bootstrap_admin
python manage.py collectstatic --noinput
# Вебхук, кнопка меню и команды бота; ошибка Telegram не мешает запуску сайта.
python manage.py telegram_setup --if-configured || echo "telegram_setup: не удалось настроить бота"
# Утренняя сводка «Сегодня в офисе» в личные чаты Telegram (8:00 по часовому поясу приложения).
export TELEGRAM_DIGEST_SCHEDULER=1
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers "${WEB_CONCURRENCY:-2}" --timeout 60 --access-logfile - --error-logfile -
