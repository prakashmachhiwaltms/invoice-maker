# Database Migrations & Automated CI/CD Deployment Guide

This document details the database migration architecture, local development workflow, automated GitHub Actions deployment pipeline, backup policies, and disaster recovery procedures for the Invoice Generator application.

---

## 1. Architecture Overview

* **Application Framework:** Django 6.1 (Python 3)
* **Local Database:** XAMPP MariaDB 10.4 (`127.0.0.1:3307`, Database: `invoice_app`)
* **Production Database:** Docker MySQL 8.4 (`127.0.0.1:3307`, Database: `invoice_app`)
* **Production Host:** Ubuntu VPS (`213.21.243.130`)
* **Production Path:** `/var/www/invoice-maker/`
* **Application Daemon:** Gunicorn via systemd (`invoice-maker.service`)
* **Web Server / SSL:** Nginx HTTPS (`https://invoice.fundtld.info`)
* **CI/CD Orchestration:** GitHub Actions (`.github/workflows/deploy.yml`)

---

## 2. Canonical Migration Baseline

The existing migration history is the canonical baseline and must **never** be deleted, squashed, or reset:
* `accounts`: `0001_initial.py`
* `invoices`: `0001_initial.py`
* `pdf_editor`: `0001_initial` through `0005_pdffield_label_color_pdffield_label_font_and_more`
* `settings_app`: `0001_initial.py`
* Built-in Django migrations (`admin`, `auth`, `contenttypes`, `sessions`)

All future schema changes must be added as forward-moving migrations (e.g. `pdf_editor/migrations/0006_...py`).

---

## 3. Local Developer Workflow

Follow this standard procedure for any database schema modification:

### Step 1: Modify Models
Update the desired model class in `<app>/models.py` (e.g., [`pdf_editor/models.py`](../pdf_editor/models.py)).
> **Rule:** Always provide safe defaults or allow `null=True` on new fields so existing rows are unaffected.

### Step 2: Generate Migration
Run the Django CLI command to create the migration file:
```bash
python manage.py makemigrations
```
Verify the generated file in `<app>/migrations/`.

### Step 3: Inspect Pending Migrations
Review the migration graph and plan:
```bash
python manage.py showmigrations
python manage.py migrate --plan
```

### Step 4: Test Migration Locally
Apply the migration to your local XAMPP MariaDB database:
```bash
python manage.py migrate
```

### Step 5: Test Application
Start the development server and test both the UI and background operations:
```bash
python manage.py runserver
```

### Step 6: Atomic Git Commit
Commit the model code and the generated migration file together:
```bash
git add <app>/models.py <app>/migrations/000X_*.py
git commit -m "Add feature XYZ with database migration"
git push origin main
```
Pushing to the `main` branch automatically triggers the GitHub Actions deployment pipeline.

---

## 4. Production CI/CD Deployment Sequence

The automated pipeline in [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) executes the following strictly ordered stages:

```
[GitHub Push: main]
       │
       ▼
1. Validate & Lint (GitHub Runner)
   ├── Python 3.12 setup
   ├── pip install dependencies
   ├── python manage.py check
   └── python manage.py makemigrations --check --dry-run
       │
       ▼
2. Remote Deployment via SSH (Production Server)
   ├── [Step 1-2] Verify directory /var/www/invoice-maker and .git
   ├── [Step 3]   Pre-migration database backup (/var/backups/invoice-maker/)
   ├── [Step 4-6] git fetch, git checkout main, git pull --ff-only origin main
   ├── [Step 7-8] Activate existing virtual environment (/var/www/invoice-maker/venv)
   ├── [Step 9]   pip install -r requirements.txt & python manage.py check
   ├── [Step 10]  python manage.py showmigrations & migrate --plan
   ├── [Step 11]  python manage.py migrate --noinput
   ├── [Step 12]  python manage.py collectstatic --noinput
   ├── [Step 13]  sudo systemctl restart invoice-maker.service
   ├── [Step 14]  sudo systemctl is-active invoice-maker.service
   └── [Step 15]  Health check: HTTP 200 on https://invoice.fundtld.info/accounts/login/
```

---

## 5. Pre-Migration Backup & Retention Policy

### Backup Script
The pre-migration backup is executed by [`scripts/backup_db.sh`](../scripts/backup_db.sh):
* **Location:** `/var/backups/invoice-maker/` (outside the Git repository).
* **Naming Scheme:** `invoice_app_YYYYMMDD_HHMMSS.sql`
* **Security:** Directory permissions set to `700`, files to `600`.
* **Zero Credential Exposure:** Credentials are read from server-side `/var/www/invoice-maker/.env` and passed via `MYSQL_PWD` (never printed to stdout or process lists).
* **Fail-Safe:** If the dump file is empty or fails, the script exits with code `1`, immediately aborting the deployment before any migrations are run.

### Retention Policy
* **Count:** Keeps the latest **14** migration snapshots.
* Older snapshots are pruned automatically after each successful backup.

---

## 6. Disaster Recovery & Rollback Procedures

### Scenario A: Migration Fails During Deployment
If `python manage.py migrate --noinput` returns an error:
* The deployment script halts immediately (`set -euo pipefail`).
* Static files are not collected and Gunicorn is **not** restarted.
* The pre-migration backup remains intact at `/var/backups/invoice-maker/`.

### Scenario B: Schema Rollback (Reversing a Migration)
If a newly applied migration needs to be reversed cleanly:
```bash
cd /var/www/invoice-maker
source venv/bin/activate
# Rollback target app to previous migration number (e.g. 0005)
python manage.py migrate pdf_editor 0005
sudo systemctl restart invoice-maker.service
```

### Scenario C: Complete Database Restoration (Data Recovery)
If live data was corrupted or accidental loss occurred, restore from the pre-migration snapshot:
```bash
# 1. Stop Gunicorn to prevent concurrent writes
sudo systemctl stop invoice-maker.service

# 2. Identify the target backup file
ls -lt /var/backups/invoice-maker/

# 3. Restore using docker exec (or host mysql)
docker exec -i -e MYSQL_PWD="<PROD_PASSWORD>" vellkoerp-testing-host-mysql-1 \
    mysql -u invoice_user invoice_app < /var/backups/invoice-maker/invoice_app_YYYYMMDD_HHMMSS.sql

# 4. Restart Gunicorn and verify
sudo systemctl start invoice-maker.service
sudo systemctl is-active invoice-maker.service
```

---

## 7. Required GitHub Secrets

Configure these secrets under your GitHub Repository Settings (`Settings` → `Secrets and variables` → `Actions`):

| Secret Name | Description | Example / Note |
| :--- | :--- | :--- |
| `SSH_HOST` | Production server IP or hostname | `213.21.243.130` |
| `SSH_USER` | SSH user authorized to deploy | `root` (or a dedicated deploy user) |
| `SSH_PORT` | SSH port | `22` |
| `SSH_KEY` | Private SSH Key (OpenSSH format) | Dedicated deployment SSH private key |

> **Note on Database Credentials:** The deployment script securely reads `DB_PASSWORD` directly from the server's local `/var/www/invoice-maker/.env`. Therefore, you do **not** need to store database passwords in GitHub repository secrets.

---

## 8. Server Security & Firewall Guidelines

* **MySQL Port 3307:**
  The audit confirmed that Docker exposes MySQL port `3307` on `0.0.0.0:3307`. To protect against external attacks without disturbing co-hosted services (`vellkoerp`):
  * Ensure host firewall (UFW or cloud firewall) blocks external inbound connections to port `3307`.
  * External access must be restricted to localhost (`127.0.0.1`).
