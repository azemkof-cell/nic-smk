# Timeweb Cloud: пошагово

## 1. Сервер

1. Зарегистрируйтесь на timeweb.cloud.
2. «Облачные серверы» → «Создать сервер».
3. Конфигурация:
   - **Ubuntu 24.04**;
   - **2 vCPU, 4 ГБ RAM, 60 ГБ SSD** (минимум); лучше 80 ГБ, если много фото;
   - локация — Москва или Санкт-Петербург;
   - SSH-ключ или пароль root — сохраните.
4. После создания запишите **IP сервера**.

## 2. Домен

1. Купите домен (у Timeweb или reg.ru) — например `smk-vashdomen.ru`.
2. В DNS добавьте запись:
   - тип `A`, имя `@` (или `smk`), значение — IP сервера.
3. Подождите 10–30 минут, пока DNS обновится.

## 3. Развёртывание

Подключитесь по SSH:

```bash
ssh root@IP
```

Установите Docker и запустите программу:

```bash
curl -fsSL https://get.docker.com | sh
apt install -y docker-compose-plugin
mkdir -p /opt/smk && cd /opt/smk
# скопируйте сюда папку программы (scp/rsync) или клонируйте из GitHub:
# git clone https://github.com/ВАШ_АККАУНТ/nic-smk.git .
cd deploy
echo "DOMAIN=smk-vashdomen.ru" > .env
docker compose up -d --build
```

Через 1–2 минуты откройте `https://smk-vashdomen.ru` — сертификат выпустится сам.

## 4. Перенос данных с компьютера

На компьютере (Windows, PowerShell):

```powershell
cd "C:\Users\admin\Yandex.Disk\Программа СМК"
tar -czf data.tar.gz data
tar -czf docs.tar.gz Документы
scp data.tar.gz docs.tar.gz root@IP:/opt/smk/deploy/
```

На сервере:

```bash
cd /opt/smk/deploy
docker compose down
docker run --rm -v smk-data:/data -v /opt/smk/deploy:/backup alpine \
  sh -c "rm -rf /data/* && tar xzf /backup/data.tar.gz -C /data"
docker run --rm -v smk-docs:/docs -v /opt/smk/deploy:/backup alpine \
  sh -c "rm -rf /docs/* && tar xzf /backup/docs.tar.gz -C /docs"
docker compose up -d
```

## 5. После запуска

1. Войдите `admin` / `1234`, смените пин.
2. «Настройки» → «Искусственный интеллект»: вставьте ключи ProxyAPI.
3. «Настройки» → «Резервные копии»: включите авто-копии.
4. Настройте выгрузку копий наружу (rclone на Яндекс.Диск) — см. DEPLOY.md.

## 6. Обновление

```bash
cd /opt/smk
git pull
cd deploy && docker compose up -d --build
```
