# Деплой nginx

## Применение конфига на сервере (Ubuntu)

1. Скопировать конфиг (с хоста, где лежит репозиторий):
   ```bash
   sudo cp /путь/к/репо/deploy/nginx-vitrinarent.conf /etc/nginx/sites-available/vitrinarent
   ```

2. Убедиться, что сайт включён:
   ```bash
   sudo ln -sf /etc/nginx/sites-available/vitrinarent /etc/nginx/sites-enabled/
   ```

3. Проверить конфиг и перезагрузить nginx:
   ```bash
   sudo nginx -t && sudo systemctl reload nginx
   ```

## Ошибка 413 Request Entity Too Large

В конфиге уже задано `client_max_body_size 50M`. Если 413 остаётся после обновления конфига:

- Убедитесь, что на сервере отредактирован **именно тот файл**, откуда nginx подключает сайт:
  ```bash
  grep -r "server_name.*витрина" /etc/nginx/
  ```
- Либо задайте лимит глобально в `/etc/nginx/nginx.conf` внутри блока `http { ... }`:
  ```nginx
  http {
      client_max_body_size 50M;
      # ... остальное
  }
  ```
  Затем: `sudo nginx -t && sudo systemctl reload nginx`.
