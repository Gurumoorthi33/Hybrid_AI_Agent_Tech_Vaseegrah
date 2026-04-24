#!/bin/bash
# =================================================================
# deploy/aws-setup.sh
# Run this from YOUR LOCAL MACHINE (with AWS CLI configured).
# Creates all AWS resources needed for deployment.
#
# Prerequisites:
#   aws configure      (set your access key, secret, region)
#   chmod +x deploy/aws-setup.sh && ./deploy/aws-setup.sh
# =================================================================
set -euo pipefail

# ── Config — change these ────────────────────────────────────────
APP_NAME="yowhats"
AWS_REGION="ap-south-1"          # Mumbai
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
VPC_ID=""                         # leave blank to use default VPC

echo "AWS Account: $ACCOUNT_ID | Region: $AWS_REGION"

# ── 1. ECR Repository ────────────────────────────────────────────
echo ""
echo "===== Creating ECR repository ====="
ECR_REPO="${APP_NAME}-backend"
aws ecr create-repository \
  --repository-name $ECR_REPO \
  --region $AWS_REGION \
  --image-scanning-configuration scanOnPush=true \
  --encryption-configuration encryptionType=AES256 \
  2>/dev/null || echo "ECR repo already exists"

ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
echo "ECR Registry: ${ECR_REGISTRY}/${ECR_REPO}"

# ── 2. IAM role for EC2 (ECR pull + Secrets Manager read) ────────
echo ""
echo "===== Creating IAM role for EC2 ====="
ROLE_NAME="${APP_NAME}-ec2-role"

# Trust policy — allows EC2 to assume this role
cat > /tmp/ec2-trust.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "ec2.amazonaws.com" },
    "Action": "sts:AssumeRole"
  }]
}
EOF

aws iam create-role \
  --role-name $ROLE_NAME \
  --assume-role-policy-document file:///tmp/ec2-trust.json \
  2>/dev/null || echo "IAM role already exists"

# Permissions: ECR read + Secrets Manager read + CloudWatch logs
cat > /tmp/ec2-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": "arn:aws:secretsmanager:${AWS_REGION}:${ACCOUNT_ID}:secret:${APP_NAME}/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "elasticfilesystem:ClientMount",
        "elasticfilesystem:ClientWrite",
        "elasticfilesystem:ClientRootAccess"
      ],
      "Resource": "*"
    }
  ]
}
EOF

POLICY_ARN="${ACCOUNT_ID}:policy/${APP_NAME}-ec2-policy"
aws iam create-policy \
  --policy-name "${APP_NAME}-ec2-policy" \
  --policy-document file:///tmp/ec2-policy.json \
  2>/dev/null || echo "IAM policy already exists"

aws iam attach-role-policy \
  --role-name $ROLE_NAME \
  --policy-arn "arn:aws:iam::${ACCOUNT_ID}:policy/${APP_NAME}-ec2-policy" \
  2>/dev/null || true

# Create instance profile
aws iam create-instance-profile \
  --instance-profile-name "${APP_NAME}-ec2-profile" \
  2>/dev/null || echo "Instance profile already exists"

aws iam add-role-to-instance-profile \
  --instance-profile-name "${APP_NAME}-ec2-profile" \
  --role-name $ROLE_NAME \
  2>/dev/null || true

echo "IAM role: $ROLE_NAME"

# ── 3. Security Group ────────────────────────────────────────────
echo ""
echo "===== Creating Security Group ====="
SG_NAME="${APP_NAME}-sg"

# Get default VPC if not set
if [ -z "$VPC_ID" ]; then
  VPC_ID=$(aws ec2 describe-vpcs \
    --filters "Name=isDefault,Values=true" \
    --query "Vpcs[0].VpcId" --output text \
    --region $AWS_REGION)
fi
echo "VPC: $VPC_ID"

SG_ID=$(aws ec2 create-security-group \
  --group-name $SG_NAME \
  --description "YoWhats API security group" \
  --vpc-id $VPC_ID \
  --region $AWS_REGION \
  --query GroupId --output text \
  2>/dev/null || \
  aws ec2 describe-security-groups \
    --filters "Name=group-name,Values=$SG_NAME" \
    --query "SecurityGroups[0].GroupId" --output text \
    --region $AWS_REGION)

echo "Security Group ID: $SG_ID"

# Allow inbound rules
RULES=(
  "22 tcp 0.0.0.0/0 SSH"          # Tighten to your IP in production
  "80 tcp 0.0.0.0/0 HTTP"
  "443 tcp 0.0.0.0/0 HTTPS"
)

for RULE in "${RULES[@]}"; do
  read PORT PROTO CIDR DESC <<< $RULE
  aws ec2 authorize-security-group-ingress \
    --group-id $SG_ID \
    --protocol $PROTO \
    --port $PORT \
    --cidr $CIDR \
    --region $AWS_REGION \
    2>/dev/null || echo "Rule port $PORT already exists"
done

# ── 4. EFS for RAG data ──────────────────────────────────────────
echo ""
echo "===== Creating EFS for RAG data ====="
EFS_ID=$(aws efs create-file-system \
  --region $AWS_REGION \
  --encrypted \
  --tags Key=Name,Value="${APP_NAME}-rag-data" \
  --query FileSystemId --output text \
  2>/dev/null || echo "SKIP")

if [ "$EFS_ID" != "SKIP" ]; then
  echo "EFS File System ID: $EFS_ID"
  echo "EFS DNS: ${EFS_ID}.efs.${AWS_REGION}.amazonaws.com"
else
  echo "EFS: check AWS Console for existing file system"
fi

# ── 5. Store secrets in Secrets Manager ─────────────────────────
echo ""
echo "===== Creating Secrets Manager secret ====="
echo "Run this manually with your actual values:"
echo ""
echo "  aws secretsmanager create-secret \\"
echo "    --name ${APP_NAME}/env \\"
echo "    --region $AWS_REGION \\"
echo "    --secret-string '{"
echo "      \"ANTHROPIC_API_KEY\": \"sk-ant-...\","
echo "      \"TAVILY_API_KEY\": \"tvly-dev-...\","
echo "      \"MONGO_URI\": \"mongodb+srv://...\""
echo "    }'"

# ── 6. Summary ───────────────────────────────────────────────────
echo ""
echo "======================================================"
echo "AWS Resources Created:"
echo "  ECR Repo:       ${ECR_REGISTRY}/${ECR_REPO}"
echo "  IAM Role:       ${ROLE_NAME}"
echo "  Security Group: ${SG_ID}"
if [ "$EFS_ID" != "SKIP" ]; then
echo "  EFS:            ${EFS_ID}"
fi
echo ""
echo "Add these to GitHub Secrets:"
echo "  AWS_ACCESS_KEY_ID:     (your key)"
echo "  AWS_SECRET_ACCESS_KEY: (your secret)"
echo "  EC2_HOST:              (your EC2 public IP)"
echo "  EC2_SSH_KEY:           (contents of your .pem key)"
echo "  ECR_REGISTRY:          ${ECR_REGISTRY}"
echo "======================================================"
