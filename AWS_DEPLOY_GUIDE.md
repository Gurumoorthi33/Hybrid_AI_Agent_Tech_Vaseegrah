# YoWhats Agent — AWS Deployment Guide
## From zero to production on AWS (ap-south-1 Mumbai)

---

## PART 1 — AWS Resources Required

### What you need from AWS

| Service | Purpose | Est. Cost/month |
|---------|---------|----------------|
| **EC2 t3.medium** | Runs Docker containers (backend + nginx) | ~$30 |
| **ECR (Elastic Container Registry)** | Stores your Docker images | ~$1 |
| **EFS (Elastic File System)** | Persistent storage for RAG indexes | ~$5 |
| **ACM or Let's Encrypt** | SSL/TLS certificate for HTTPS | Free |
| **Route 53** (optional) | DNS management for your domain | ~$0.50 |
| **Secrets Manager** | Secure storage for API keys | ~$0.40 |
| **VPC + Security Group** | Network isolation + firewall | Free |

> **MongoDB Atlas** is external (not on AWS) — already configured.
> **Total estimated AWS cost: ~$37/month** for a production setup.

### Minimum EC2 spec
- **Instance type:** t3.medium (2 vCPU, 4GB RAM)
- **OS:** Amazon Linux 2023
- **Storage:** 20 GB gp3 root volume
- **Region:** ap-south-1 (Mumbai) — lowest latency from Tamil Nadu

---

## PART 2 — Before You Start (Prerequisites)

Install these on your local machine:

```bash
# AWS CLI
pip install awscli
aws configure          # enter Access Key, Secret Key, region: ap-south-1

# Docker Desktop
# Download from https://www.docker.com/products/docker-desktop

# Git (already installed on most systems)
git --version
```

You also need:
- An AWS account (free tier works for initial setup)
- A domain name (e.g. api.yowhats.com) pointed to your EC2 IP
- Your project code pushed to a GitHub repository

---

## PART 3 — Step-by-Step Backend Deployment

### STEP 1 — Create AWS resources (run once, locally)

```bash
cd yowhats_agent
chmod +x deploy/aws-setup.sh
./deploy/aws-setup.sh
```

This creates:
- ECR repository to store your Docker image
- IAM role for EC2 (to pull from ECR + read secrets)
- Security Group (ports 22, 80, 443 open)
- EFS file system for RAG data persistence

**Save the output** — you'll need the ECR registry URL and Security Group ID.

---

### STEP 2 — Launch EC2 instance

Go to AWS Console → EC2 → Launch Instance:

```
Name:           yowhats-backend
AMI:            Amazon Linux 2023 (x86_64)
Instance type:  t3.medium
Key pair:       Create new → download yowhats-key.pem
Storage:        20 GB gp3
Security group: Select the yowhats-sg created in Step 1
IAM profile:    yowhats-ec2-profile (created in Step 1)
```

Click **Launch Instance**. Note the **Public IP** address.

---

### STEP 3 — Bootstrap the EC2 instance

```bash
# Copy bootstrap script to EC2
scp -i yowhats-key.pem \
    deploy/ec2-bootstrap.sh \
    ec2-user@YOUR_EC2_IP:/home/ec2-user/

# SSH into EC2
ssh -i yowhats-key.pem ec2-user@YOUR_EC2_IP

# Run bootstrap (takes ~5 minutes)
bash ec2-bootstrap.sh
```

This installs Docker, Docker Compose, AWS CLI, Certbot, and mounts EFS.

---

### STEP 4 — Create your .env file on EC2

```bash
# SSH into EC2
ssh -i yowhats-key.pem ec2-user@YOUR_EC2_IP

# Create the env file
nano /home/ec2-user/yowhats/.env
```

Paste your real secrets:

```env
OPENAI_API_KEY=sk-proj-your-actual-key
TAVILY_API_KEY=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
MONGO_URI=mongodb+srv://<user>:<password>@cluster0.9p8gxt8.mongodb.net/agenticchatbot?appName=Cluster0
MONGO_DB_NAME=agenticchatbot
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-gmail-app-password
SMTP_FROM=VaseegrahVeda <your-email@gmail.com>
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-secret
GOOGLE_REFRESH_TOKEN=your-refresh-token
GOOGLE_CALENDAR_ID=primary
```

**Important:** Never commit this file to Git. It stays only on the server.

---

### STEP 5 — Configure nginx with your domain

```bash
# On your LOCAL machine, edit the nginx config:
nano deploy/nginx/default.conf
```

Replace these two values:
```
YOUR_DOMAIN  →  api.yowhats.com       (your actual domain)
YOUR_ADMIN_IP → 103.x.x.x            (your office/home IP)
```

Then copy nginx configs to EC2:
```bash
scp -i yowhats-key.pem -r deploy/ ec2-user@YOUR_EC2_IP:/home/ec2-user/yowhats/
```

---

### STEP 6 — Build Docker image locally and push to ECR

```bash
# On your LOCAL machine:

# Login to ECR
aws ecr get-login-password --region ap-south-1 | \
  docker login --username AWS --password-stdin \
  YOUR_ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com

# Build the image
docker build -t yowhats-backend:latest .

# Tag for ECR
docker tag yowhats-backend:latest \
  YOUR_ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com/yowhats-backend:latest

# Push to ECR
docker push \
  YOUR_ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com/yowhats-backend:latest
```

---

### STEP 7 — First deployment on EC2

```bash
# SSH into EC2
ssh -i yowhats-key.pem ec2-user@YOUR_EC2_IP

cd /home/ec2-user/yowhats

# Copy compose files (already done in Step 5, but verify)
ls docker-compose.yml docker-compose.prod.yml

# Set ECR variables
export ECR_REGISTRY="YOUR_ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com"
export ECR_REPO="yowhats-backend"
export IMAGE_TAG="latest"
export AWS_REGION="ap-south-1"

# Login to ECR from EC2
aws ecr get-login-password --region ap-south-1 | \
  docker login --username AWS --password-stdin $ECR_REGISTRY

# Pull and start
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  up -d

# Check logs
docker compose logs -f backend
```

Expected output:
```
✅ KeyManager connected to MongoDB
✅ VectorStore [default] loaded: XXXX docs
🔑 ROOT ADMIN KEY CREATED — save this, it won't be shown again:
   ywk_live_a<64hex>
🚀 YoWhats Agent API v3.1 ready
📊 Dashboard: http://localhost:8000/dashboard
```

**Save the root admin key immediately.**

---

### STEP 8 — Ingest knowledge base (first time only)

```bash
# SSH into EC2
ssh -i yowhats-key.pem ec2-user@YOUR_EC2_IP

# Copy your knowledge file to EFS
mkdir -p /mnt/efs/rag_data/default
cp /path/to/vaseegrah_veda.txt /mnt/efs/rag_data/default/

# Run ingestion inside the container
docker compose exec backend python setup.py
```

---

### STEP 9 — Set up SSL with Let's Encrypt

```bash
# On EC2 (after DNS is pointing to this EC2 IP):
# First, stop nginx temporarily
docker compose stop nginx

# Get SSL certificate
sudo certbot certonly --standalone \
  -d api.yowhats.com \
  --email your@email.com \
  --agree-tos --non-interactive

# Certs are now at /etc/letsencrypt/live/api.yowhats.com/
# Restart with SSL
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  up -d nginx

# Auto-renew every 90 days
echo "0 3 * * * root certbot renew --quiet && docker compose -f /home/ec2-user/yowhats/docker-compose.yml restart nginx" | \
  sudo tee /etc/cron.d/certbot-renew
```

---

### STEP 10 — Point DNS to your EC2

In your domain registrar (GoDaddy / Namecheap / Route 53):

```
Type:  A
Name:  api           (or @ for root domain)
Value: YOUR_EC2_PUBLIC_IP
TTL:   300
```

---

### STEP 11 — Verify everything works

```bash
# Health check
curl https://api.yowhats.com/health

# Expected response:
# {"status":"ok","service":"YoWhats RAG Agent","version":"3.1.0"}

# Test chat endpoint (use a client key)
curl -X POST https://api.yowhats.com/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ywk_live_c..." \
  -d '{"user_id": "test", "message": "What is hair growth oil?"}'

# Dashboard (only accessible from YOUR_ADMIN_IP)
open https://api.yowhats.com/dashboard
```

---

## PART 4 — CI/CD with GitHub Actions (Auto-deploy on git push)

### Set GitHub Secrets

In your GitHub repo → Settings → Secrets → Actions → New secret:

| Secret name | Value |
|-------------|-------|
| `AWS_ACCESS_KEY_ID` | Your AWS access key |
| `AWS_SECRET_ACCESS_KEY` | Your AWS secret key |
| `EC2_HOST` | Your EC2 public IP |
| `EC2_SSH_KEY` | Contents of yowhats-key.pem |

### How it works

Every `git push` to `main`:
1. GitHub Actions builds a new Docker image
2. Pushes it to ECR with git commit SHA as tag
3. SSH into EC2 and does a zero-downtime rolling restart

```bash
git add .
git commit -m "update agent logic"
git push origin main
# → Auto-deploys in ~3 minutes
```

---

## PART 5 — Frontend Deployment

The dashboard (`dashboard.html`) is served by the backend itself at `/dashboard`.
No separate frontend deployment needed.

If you want a separate React/Next.js frontend in the future:

### Option A — S3 + CloudFront (cheapest, ~$1/month)
```bash
# Build your frontend
npm run build

# Create S3 bucket
aws s3 mb s3://yowhats-frontend --region ap-south-1

# Enable static hosting
aws s3 website s3://yowhats-frontend \
  --index-document index.html \
  --error-document index.html

# Upload
aws s3 sync ./dist s3://yowhats-frontend --delete

# Create CloudFront distribution pointing to S3 bucket
# (do this in AWS Console → CloudFront → Create Distribution)
```

### Option B — Serve from same EC2 (current setup)
The dashboard is already live at `https://api.yowhats.com/dashboard`.
Access restricted to your admin IP via nginx.

---

## PART 6 — Monitoring & Maintenance

### View logs
```bash
# All services
docker compose logs -f

# Backend only
docker compose logs -f backend

# Nginx only
docker compose logs -f nginx
```

### Restart a service
```bash
docker compose restart backend
```

### Update to new version (manual)
```bash
cd /home/ec2-user/yowhats
docker compose pull backend
docker compose up -d --no-deps backend
```

### Scale workers (if traffic grows)
Edit `Dockerfile`, change `--workers 2` to `--workers 4`, rebuild and redeploy.

### Add new customer RAG file
```bash
# Via API (from anywhere)
curl -X POST https://api.yowhats.com/client/ingest \
  -H "X-API-Key: ywk_live_c..." \
  -F "file=@/path/to/knowledge.pdf"
```

Uploading the same filename again replaces that customer's stored source file
and rebuilds only that customer's private vector DB:
`data/customers/<client_key_id>/index.bin` and `docs.pkl`.

---

## PART 7 — File Structure Summary

```
yowhats_agent/
├── Dockerfile                    ← Backend container definition
├── .dockerignore                 ← Keeps image lean
├── docker-compose.yml            ← Local dev stack
├── docker-compose.prod.yml       ← Production overrides (ECR image + EFS)
├── .env.example                  ← Template for secrets
│
├── deploy/
│   ├── aws-setup.sh              ← Creates ECR, IAM, SG, EFS on AWS
│   ├── ec2-bootstrap.sh          ← Installs Docker/Certbot on fresh EC2
│   └── nginx/
│       ├── nginx.conf            ← Nginx main config
│       └── default.conf          ← Site config: HTTPS, proxy, dashboard IP lock
│
├── .github/
│   └── workflows/
│       └── deploy.yml            ← CI/CD: push to ECR + deploy to EC2
│
├── server.py                     ← FastAPI app entry point
├── dashboard.html                ← Admin dashboard (served at /dashboard)
└── ... (all other Python files)
```

---

## Quick Reference Commands

```bash
# Start (local)
docker compose up --build -d

# Start (production EC2)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Stop
docker compose down

# View logs
docker compose logs -f

# Run inside container
docker compose exec backend python setup.py

# Rebuild and restart
docker compose up --build -d backend

# Check container status
docker compose ps
```
