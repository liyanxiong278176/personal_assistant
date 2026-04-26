# Travel Assistant - Cloud Deployment Guide

This guide covers deploying the Travel Assistant to Alibaba Cloud or Tencent Cloud student servers.

## Prerequisites

### Server Requirements
- **Minimum**: 2 CPU cores, 2GB RAM (student server specs)
- **OS**: Ubuntu 20.04+, Debian 10+, or CentOS 7+
- **Storage**: 20GB free disk space

### Local Requirements
- SSH client installed
- SSH key pair for server access
- Git (for cloning repository)

### API Keys Required
1. **DashScope API Key** (Tongyi Qianwen LLM)
   - Get from: https://dashscope.console.aliyun.com/apiKey
   - Purpose: AI chat and itinerary generation

2. **QWeather API Key** (Weather data)
   - Get from: https://dev.qweather.com/docs/api/
   - Purpose: Real-time weather information

3. **高德地图 API Key** (Maps and POI)
   - Get from: https://console.amap.com/dev/key/app
   - Purpose: Location search, geocoding, route planning

## Deployment Steps

### Step 1: Prepare Server

1. **Create ECS Instance** (Alibaba Cloud)
   - Go to ECS Console -> Instances -> Create Instance
   - Select: 2 vCPU, 2GB RAM (student tier)
   - OS: Ubuntu 22.04 64-bit
   - Network: VPC with public IP

2. **Configure Security Group** (Firewall)
   ```
   Inbound Rules:
   - Port 80  (HTTP)   - Allow 0.0.0.0/0
   - Port 443 (HTTPS)  - Allow 0.0.0.0/0 (for future SSL)
   - Port 22  (SSH)    - Allow your IP only
   ```

### Step 2: Configure Environment

1. Copy the example environment file:
   ```bash
   cp .env.production.example .env.production
   ```

2. Edit `.env.production` with your values:
   ```bash
   # Server Configuration
   SERVER_HOST=your.server.ip.address
   SSH_USER=root
   SSH_KEY_PATH=~/.ssh/your-key.pem

   # Database
   POSTGRES_PASSWORD=secure_random_password

   # API Keys
   DASHSCOPE_API_KEY=sk-xxxxx
   QWEATHER_API_KEY=xxxxx
   AMAP_API_KEY=xxxxx

   # Application
   WORKERS=2
   LOG_LEVEL=info
   NEXT_PUBLIC_API_URL=http://your.server.ip.address
   ```

### Step 3: Deploy

Run the deployment script:
```bash
chmod +x deployment/deploy.sh
./deployment/deploy.sh production
```

The script will:
- Check SSH connectivity
- Install Docker if needed
- Copy files to server
- Start all containers
- Verify deployment health

### Step 4: Verify

1. Check application status:
   ```bash
   ssh -i ~/.ssh/your-key.pem root@your.server.ip "docker compose -f /opt/travel-assistant/docker-compose.yml ps"
   ```

2. Test the application:
   - Open browser: http://your.server.ip.address
   - Send a chat message
   - Verify streaming response works

3. View logs if needed:
   ```bash
   ssh -i ~/.ssh/your-key.pem root@your.server.ip "docker compose -f /opt/travel-assistant/docker-compose.yml logs -f"
   ```

## Troubleshooting

### Issue: SSH Connection Refused
- **Check**: Security group allows port 22 from your IP
- **Check**: Server is running (ECS Console)
- **Check**: SSH key path is correct
- **Fix**: Add your IP to security group inbound rule

### Issue: Containers Not Starting
- **Check logs**: `docker compose logs`
- **Common cause**: Missing environment variables
- **Fix**: Verify .env file has all required API keys

### Issue: WebSocket Connection Fails
- **Symptom**: Chat connects but no streaming
- **Cause**: Nginx WebSocket headers missing
- **Fix**: Verify nginx.conf has proxy_set_header Upgrade headers
- **Check**: Security group allows port 80

### Issue: Database Connection Failed
- **Check**: PostgreSQL container is healthy
- **Fix**: Verify DATABASE_URL format in .env
- **Fix**: Check postgres container logs: `docker compose logs postgres`

### Issue: Out of Memory
- **Symptom**: Containers restart repeatedly
- **Cause**: 2 workers on 2GB may be tight
- **Fix**: Reduce WORKERS to 1 in .env
- **Fix**: Add swap space on server

## Post-Deployment

### Database Backups
Manual backup (run periodically):
```bash
ssh root@server "docker exec travel-postgres pg_dump -U postgres travel_assistant > backup.sql"
```

### Monitoring
Basic health check:
```bash
curl http://your.server.ip.address/health
```

### SSL/HTTPS (Future)
When you acquire a domain:
1. Update NEXT_PUBLIC_API_URL to use https://
2. Add Certbot for Let's Encrypt
3. Update nginx.conf to listen on 443
4. Add SSL certificate configuration

## Rollback

If deployment fails:
```bash
ssh -i ~/.ssh/your-key.pem root@server "cd /opt/travel-assistant && docker compose down"
```

To redeploy previous version:
```bash
./deployment/deploy.sh production
```

---
*Last updated: 2026-03-31*
