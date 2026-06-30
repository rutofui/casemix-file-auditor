# Deployment Guide - Casemix File Auditor

## Prerequisites
- Docker & Docker Compose installed
- Nginx installed
- SSL certificate from Let's Encrypt (or other provider)
- Domain DNS pointing to server IP

## Quick Deploy

### 1. Clone & Setup
```bash
git clone https://github.com/rutofui/casemix-file-auditor.git
cd casemix-file-auditor
```

### 2. Build & Run with Docker Compose
```bash
docker-compose up -d
```

The application will run on `localhost:8501`

### 3. Setup SSL Certificate
```bash
sudo certbot certonly --standalone -d casemix.ahmadluthfi.online
```

### 4. Setup Nginx Reverse Proxy
```bash
sudo cp nginx.conf /etc/nginx/sites-available/casemix.ahmadluthfi.online
sudo ln -s /etc/nginx/sites-available/casemix.ahmadluthfi.online /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 5. Verify
Visit: https://casemix.ahmadluthfi.online

## Management

### View logs
```bash
docker-compose logs -f casemix
```

### Stop
```bash
docker-compose down
```

### Restart
```bash
docker-compose restart casemix
```

### Update & Redeploy
```bash
git pull
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## Troubleshooting

### Port 8501 already in use
```bash
docker-compose down
# or kill process: lsof -i :8501 | kill -9 <PID>
```

### SSL certificate not found
Make sure Let's Encrypt certificate exists:
```bash
ls -la /etc/letsencrypt/live/casemix.ahmadluthfi.online/
```

### Application won't start
```bash
docker-compose logs casemix
```
