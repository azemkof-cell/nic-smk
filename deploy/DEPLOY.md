# Развёртывание на облачном сервере

## Что нужно

1. **VPS** (Ubuntu 22.04/24.04): 2 vCPU, 4 ГБ RAM, 40–80 ГБ SSD. Подойдёт Timeweb, Selectel, Yandex Cloud, Beget, Aeza. Ориентир: 500–1500 ₽/мес.
2. **Домен** (например `smk-vashdomen.ru`) или поддомен. DNS-запись `A` → IP сервера.
3. Доступ по SSH (root или пользователь с sudo).

## Установка

```bash
# 1. Docker
curl -fsSL https://get.docker.com | sh
apt install -y docker-compose-plugin

# 2. Код программы
mkdir -p /opt/smk && cd /opt/smk
# скопировать папку «Программа СМК» на сервер, например через scp:
# scp -r "Программа СМК" root@IP:/opt/smk/

# 3. Домен
cd /opt/smk/deploy
echo "DOMAIN=smk-vashdomen.ru" > .env

# 4. Запуск
docker compose up -d --build
```

Через 1–2 минуты Caddy получит HTTPS-сертификат, программа будет доступна по адресу
`https://smk-vashdomen.ru`.

## Первый вход

На новом сервере база пустая, вход свободный. Сразу:

1. Откройте сайт.
2. «Настройки» → «Доступы» → создайте администратора (ФИО, логин, код).
3. После этого вход станет обязательным.

## Перенос текущих данных

Скопируйте с рабочего компьютера:

- `data/` — база, фото, вложения, локальное хранилище объектов;
- `Документы/` — сформированные протоколы, отчёты, КП.

В docker они лежат в томах `smk-data`, `smk-docs`. Проще всего:

```bash
docker compose down
docker run --rm -v smk-data:/data -v /opt/smk/backup:/backup alpine \
  sh -c "rm -rf /data/* && tar xzf /backup/data.tar.gz -C /data"
docker run --rm -v smk-docs:/docs -v /opt/smk/backup:/backup alpine \
  sh -c "rm -rf /docs/* && tar xzf /backup/docs.tar.gz -C /docs"
docker compose up -d
```

## Резервные копии

В программе: «Настройки» → «Резервные копии».
- копия создаётся вручную кнопкой и автоматически раз в день;
- хранится последние N копий (по умолчанию 14);
- внутри: база, фото, вложения, документы объектов, сформированные документы.

Копии лежат в томе `smk-backups` (`/app/backups`). Чтобы они не пропали вместе с сервером,
раз в сутки отправляйте их во внешнее хранилище. Пример через rclone (Яндекс.Диск):

```bash
apt install -y rclone
rclone config          # настроить remote «yandex»
crontab -e
# каждый день в 03:30
30 3 * * * docker run --rm -v smk-backups:/b rclone/rclone copy /b yandex:smk-backups
```

## Обновление программы

```bash
cd /opt/smk
# заменить файлы новой версией
cd deploy && docker compose up -d --build
```

## Важно

- PDF на сервере делается через **LibreOffice** (в образе уже установлен), Word не нужен.
- Файлы объектов на Яндекс.Диске программа не читает из облака — документы должны быть
  загружены в программу (импорт папки) либо папка должна быть доступна серверу.
- Резервные копии — обязательны: они защищают от сбоя диска и ошибок.
