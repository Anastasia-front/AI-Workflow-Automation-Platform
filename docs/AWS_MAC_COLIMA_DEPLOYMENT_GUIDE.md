# AI Automation Platform -- AWS Deployment Guide (Mac + Colima)

## Goal

This document describes the exact deployment flow used in this project.

**Environment**

- Local machine: macOS (Apple Silicon ARM64)
- Docker: Colima
- Terraform: Infrastructure already applied
- AWS Region: `eu-central-1`
- EC2: Ubuntu 22.04
- ECR repository:
  `ACCOUNT_ID.dkr.ecr.eu-central-1.amazonaws.com/ai-platform-backend`
- Public URL: `http://ec2-x-7xx-xxx-xx.eu-central-1.compute.amazonaws.com/docs`

---

# 1. Prerequisites

Install:

```bash
brew install awscli terraform
brew install colima docker
```

Start Docker:

```bash
colima start
docker ps
```

---

# 2. Configure AWS CLI

```bash
aws configure
```

Example:

```text
AWS Access Key ID:
AWS Secret Access Key:
Region: eu-central-1
Output: json
```

Verify:

```bash
aws sts get-caller-identity
```

---

# 3. Verify Terraform

```bash
terraform fmt
terraform validate
terraform plan
terraform apply
```

Verify outputs:

```bash
terraform output
```

Expected:

- EC2 IP
- ECR repository
- RDS endpoint
- S3 bucket

---

# 4. Login to ECR from the Mac

```bash
aws ecr get-login-password --region eu-central-1 \
| docker login \
--username AWS \
--password-stdin \
ACCOUNT_ID.dkr.ecr.eu-central-1.amazonaws.com
```

---

# 5. Build AMD64 image on Apple Silicon

EC2 is x86_64.

Build **linux/amd64** image:

```bash
docker build \
    --platform linux/amd64 \
    -t ai-platform-backend:latest .
```

Verify architecture:

```bash
docker image inspect ai-platform-backend \
--format '{{.Architecture}}'
```

Expected:

    amd64

---

# 6. Tag image

```bash
docker tag ai-platform-backend:latest \
ACCOUNT_ID.dkr.ecr.eu-central-1.amazonaws.com/ai-platform-backend:latest
```

---

# 7. Push image

```bash
docker push \
ACCOUNT_ID.dkr.ecr.eu-central-1.amazonaws.com/ai-platform-backend:latest
```

No EC2 is required for building or pushing.

---

# 8. SSH to EC2

Example alias:

```bash
alias ai-platform='ssh -i ~/ssh-keys/ai-platform-key.pem ubuntu@ec2-x-7xx-xxx-xx.eu-central-1.compute.amazonaws.com'
```

Connect:

```bash
ai-platform
```

---

# 9. Clone project (first deployment only)

```bash
cd ~

git clone https://github.com/Anastasia-front/ai-automation-platform.git

cd ai-automation-platform
```

---

# 10. Install Docker on EC2

```bash
sudo apt update

sudo apt install -y docker.io awscli

sudo systemctl enable docker
sudo systemctl start docker

sudo usermod -aG docker ubuntu

newgrp docker
```

Verify:

```bash
docker --version
aws sts get-caller-identity
```

---

# 11. Download environment variables from SSM

```bash
aws ssm get-parameters-by-path \
--path /ai-platform \
--with-decryption \
--recursive \
--region eu-central-1 \
--query "Parameters[*].[Name,Value]" \
--output text \
| awk -F'\t' '{split($1,a,"/"); print a[length(a)]"="$2}' \
> .env
```

---

# 12. Login to ECR on EC2

```bash
aws ecr get-login-password --region eu-central-1 \
| docker login \
--username AWS \
--password-stdin \
ACCOUNT_ID.dkr.ecr.eu-central-1.amazonaws.com
```

---

# 13. Pull latest image

```bash
docker pull \
ACCOUNT_ID.dkr.ecr.eu-central-1.amazonaws.com/ai-platform-backend:latest
```

---

# 14. Run Alembic migrations

```bash
docker run --rm \
--env-file .env \
ACCOUNT_ID.dkr.ecr.eu-central-1.amazonaws.com/ai-platform-backend:latest \
alembic upgrade head
```

---

# 15. Start backend

```bash
docker stop ai-platform-backend || true

docker rm ai-platform-backend || true

docker run -d \
--name ai-platform-backend \
--restart unless-stopped \
-p 80:8000 \
--env-file .env \
ACCOUNT_ID.dkr.ecr.eu-central-1.amazonaws.com/ai-platform-backend:latest
```

---

# 16. Verify

Container:

```bash
docker ps
```

Logs:

```bash
docker logs -f ai-platform-backend
```

Health endpoint:

```bash
curl http://localhost/health
```

From Mac:

```bash
curl http://ec2-x-7xx-xxx-xx.eu-central-1.compute.amazonaws.com/health
```

Expected:

```json
{ "status": "ok", "database": "connected" }
```

Swagger:

    http://ec2-x-7xx-xxx-xx.eu-central-1.compute.amazonaws.com/docs

---

# Normal deployment after code changes

On Mac:

```bash
docker build --platform linux/amd64 -t ai-platform-backend:latest .

docker tag ai-platform-backend:latest \
ACCOUNT_ID.dkr.ecr.eu-central-1.amazonaws.com/ai-platform-backend:latest

docker push \
ACCOUNT_ID.dkr.ecr.eu-central-1.amazonaws.com/ai-platform-backend:latest
```

On EC2:

```bash
aws ecr get-login-password --region eu-central-1 \
| docker login --username AWS --password-stdin \
ACCOUNT_ID.dkr.ecr.eu-central-1.amazonaws.com

docker pull \
ACCOUNT_ID.dkr.ecr.eu-central-1.amazonaws.com/ai-platform-backend:latest

docker stop ai-platform-backend || true
docker rm ai-platform-backend || true

docker run -d \
--name ai-platform-backend \
--restart unless-stopped \
-p 80:8000 \
--env-file .env \
ACCOUNT_ID.dkr.ecr.eu-central-1.amazonaws.com/ai-platform-backend:latest
```

Open:

    http://ec2-x-7xx-xxx-xx.eu-central-1.compute.amazonaws.com/docs
