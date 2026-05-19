#!/bin/bash
# =================================================================
# deploy/ec2-bootstrap.sh
# Run this ONCE on a fresh Amazon Linux 2023 EC2 instance.
# Usage:  bash ec2-bootstrap.sh
# =================================================================
set -euo pipefail

DEPLOY_DIR=/home/ec2-user/yowhats
DOMAIN="YOUR_DOMAIN"          # e.g. api.yowhats.com  ← change this
EMAIL="YOUR_EMAIL"             # for Let's Encrypt alerts ← change this
AWS_REGION="ap-south-1"

echo "===== Step 1: System update ====="
sudo dnf update -y

echo "===== Step 2: Install Docker ====="
sudo dnf install -y docker
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker ec2-user

echo "===== Step 3: Install Docker Compose v2 ====="
COMPOSE_VERSION="2.27.0"
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -SL "https://github.com/docker/compose/releases/download/v${COMPOSE_VERSION}/docker-compose-linux-x86_64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
docker compose version

echo "===== Step 4: Install AWS CLI v2 ====="
sudo dnf install -y aws-cli
aws --version

echo "===== Step 5: Install Certbot for SSL ====="
sudo dnf install -y certbot
# We'll get the cert after nginx is up

echo "===== Step 6: Mount EFS for RAG data ====="
sudo dnf install -y amazon-efs-utils
# Replace EFS_DNS with your actual EFS DNS name from AWS Console
EFS_DNS="YOUR_EFS_DNS.efs.${AWS_REGION}.amazonaws.com"
sudo mkdir -p /mnt/efs/rag_data
echo "${EFS_DNS}:/ /mnt/efs efs defaults,_netdev 0 0" | sudo tee -a /etc/fstab
# Only mount if EFS_DNS is set
if [ "$EFS_DNS" != "YOUR_EFS_DNS.efs.${AWS_REGION}.amazonaws.com" ]; then
    sudo mount -a
    sudo mkdir -p /mnt/efs/rag_data
    sudo chown -R 1001:1001 /mnt/efs/rag_data
fi

echo "===== Step 7: Create deploy directory ====="
mkdir -p $DEPLOY_DIR
mkdir -p $DEPLOY_DIR/deploy/nginx/certs

echo "===== Step 8: Pull .env from AWS Secrets Manager ====="
# Store your .env contents as a secret named 'yowhats/env' in Secrets Manager
# aws secretsmanager get-secret-value --secret-id yowhats/env \
#   --query SecretString --output text > $DEPLOY_DIR/.env
echo "⚠  Manually create $DEPLOY_DIR/.env with your secrets, or use Secrets Manager."
cat > $DEPLOY_DIR/.env.template << 'ENV'
OPENAI_API_KEY=sk-proj-...
TAVILY_API_KEY=tvly-dev-...
MONGO_URI=mongodb+srv://...
MONGO_DB_NAME=agenticchatbot
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REFRESH_TOKEN=
GOOGLE_CALENDAR_ID=primary
ENV
echo "⚠  Copy .env.template to .env and fill in values."

echo "===== Step 9: Initial self-signed cert (swap for Let's Encrypt after DNS) ====="
mkdir -p $DEPLOY_DIR/deploy/nginx/certs/live/$DOMAIN
openssl req -x509 -nodes -days 30 -newkey rsa:2048 \
  -keyout $DEPLOY_DIR/deploy/nginx/certs/live/$DOMAIN/privkey.pem \
  -out    $DEPLOY_DIR/deploy/nginx/certs/live/$DOMAIN/fullchain.pem \
  -subj "/CN=$DOMAIN"

echo ""
echo "======================================================"
echo "Bootstrap complete!"
echo ""
echo "NEXT STEPS:"
echo "1. Fill in: $DEPLOY_DIR/.env"
echo "2. Copy your nginx configs:"
echo "   scp -r deploy/ ec2-user@EC2_IP:$DEPLOY_DIR/"
echo "3. Run the app:"
echo "   cd $DEPLOY_DIR"
echo "   docker compose up -d"
echo ""
echo "4. Point your domain DNS A record → $(curl -s https://checkip.amazonaws.com)"
echo "5. Get real SSL cert:"
echo "   sudo certbot certonly --standalone -d $DOMAIN --email $EMAIL --agree-tos"
echo "======================================================"
