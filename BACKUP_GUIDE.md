# BlackMarket AI - Backup and Recovery Guide

This guide covers how to back up and recover your BlackMarket AI installation, including data, models, and configuration.

## Automatic Backups

The system automatically creates daily backups of critical data:

### What Gets Backed Up

1. **Database** (`data/backups/blackmarket_YYYYMMDD.db`)
   - All trading data
   - Open positions
   - Trade history
   - Model predictions
   - Strategy metrics

2. **Model Checkpoints** (`models/`)
   - Trained ML models
   - Model registry information
   - Validation results

3. **Configuration** (when changed)
   - `.env` file
   - `config.py` modifications

### Backup Schedule

- **Daily**: Database and models at 00:00 UTC
- **Before major operations**: Full backup when running tests or updates
- **On shutdown**: Automatic state persistence

## Manual Backups

### Quick Backup Script

Create a backup with one command:

```bash
# Windows (PowerShell)
python -c "
import shutil
from datetime import datetime
from pathlib import Path

backup_dir = Path('data/backups')
backup_dir.mkdir(exist_ok=True)

timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
shutil.copy2('data/blackmarket.db', backup_dir / f'blackmarket_{timestamp}.db')
shutil.make_archive(f'backup_{timestamp}', 'zip', 'data')
print(f'Backup created: backup_{timestamp}.zip')
"

# macOS/Linux (Bash)
python3 -c "
import shutil
from datetime import datetime
from pathlib import Path

backup_dir = Path('data/backups')
backup_dir.mkdir(exist_ok=True)

timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
shutil.copy2('data/blackmarket.db', backup_dir / f'blackmarket_{timestamp}.db')
shutil.make_archive(f'backup_{timestamp}', 'zip', 'data')
echo \"Backup created: backup_${timestamp}.zip\"
"
```

### Full Backup Script

For a complete backup including all data:

```bash
#!/bin/bash
# backup_full.sh

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="blackmarket_full_${TIMESTAMP}"

# Create backup directory
mkdir -p "backups/${BACKUP_NAME}"

# Copy all important files
cp -r data "backups/${BACKUP_NAME}/"
cp -r models "backups/${BACKUP_NAME}/"
cp -r logs "backups/${BACKUP_NAME}/"
cp .env "backups/${BACKUP_NAME}/"
cp config.py "backups/${BACKUP_NAME}/"

# Create archive
cd backups
zip -r "${BACKUP_NAME}.zip" "${BACKUP_NAME}/"
cd ..

echo "Full backup created: backups/${BACKUP_NAME}.zip"
echo "Size: $(du -h backups/${BACKUP_NAME}.zip)"
```

### Backup to External Location

```bash
# Backup to USB drive or network location
BACKUP_LOCATION="/Volumes/USB/BlackMarket_Backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "${BACKUP_LOCATION}"
cp "backup_${TIMESTAMP}.zip" "${BACKUP_LOCATION}/"

echo "Backup copied to: ${BACKUP_LOCATION}/backup_${TIMESTAMP}.zip"
```

## Recovery Procedures

### From Latest Automatic Backup

```bash
# Find the latest backup
latest_backup=$(ls -t data/backups/blackmarket_*.db | head -1)

# Restore database
cp "$latest_backup" data/blackmarket.db

echo "Database restored from: $latest_backup"
```

### From Specific Date

```bash
# Restore from specific date
BACKUP_DATE="20240101"
backup_file="data/backups/blackmarket_${BACKUP_DATE}.db"

if [ -f "$backup_file" ]; then
    cp "$backup_file" data/blackmarket.db
    echo "Database restored from: $backup_file"
else
    echo "Backup not found for date: $BACKUP_DATE"
fi
```

### From ZIP Archive

```bash
# Extract and restore from ZIP backup
BACKUP_FILE="backup_20240101_120000.zip"

# Extract to temporary location
unzip "$BACKUP_FILE" -d temp_restore

# Copy database
cp temp_restore/data/blackmarket.db data/blackmarket.db

# Copy models if needed
cp -r temp_restore/models/ models/

# Clean up
rm -rf temp_restore

echo "Restored from: $BACKUP_FILE"
```

## Database Recovery

### Corrupted Database Recovery

If the database is corrupted:

1. **Stop the application**
2. **Find the latest good backup**
3. **Restore as shown above**
4. **Verify data integrity**

### Partial Recovery

If only certain tables are corrupted:

```sql
-- Connect to the database
sqlite3 data/blackmarket.db

-- Check table integrity
PRAGMA integrity_check;

-- If specific table is corrupted, drop and recreate
DROP TABLE IF EXISTS positions;
-- The system will recreate tables on next startup

-- Exit
.quit
```

## Model Recovery

### Restore Trained Models

Models are stored in the `models/` directory:

```bash
# List available models
ls -la models/

# Restore from backup
cp -r backups/20240101/models/* models/

# Verify model files
ls models/registry/
```

### Roll Back to Previous Model

If a new model performs poorly:

```python
# In Python console
from learning.trainer import Trainer

trainer = Trainer()
trainer.rollback_model()
```

## Configuration Recovery

### Restore Configuration Files

```bash
# Restore .env file
cp .env.example .env
# Edit with your settings

# Restore config.py (if modified)
cp backups/20240101/config.py config.py
```

## Backup Verification

### Verify Database Backup

```bash
# Check if database can be opened
sqlite3 data/backups/blackmarket_20240101.db "SELECT COUNT(*) FROM symbols;"

# Compare record counts
echo "Original:"
sqlite3 data/blackmarket.db "SELECT COUNT(*) FROM trades;"
echo "Backup:"
sqlite3 data/backups/blackmarket_20240101.db "SELECT COUNT(*) FROM trades;"
```

### Verify Model Backup

```bash
# Check if model files exist
ls -la models/

# Test model loading
python -c "
from learning.predictor import Predictor
p = Predictor()
print('Models loaded successfully')
"
```

## Backup Best Practices

### Frequency Recommendations

- **Daily**: For active trading
- **Weekly**: For development/testing
- **Monthly**: For archival

### Retention Policy

- **Automatic backups**: Keep last 30 days
- **Manual backups**: Keep as long as needed
- **Model checkpoints**: Keep all versions for rollback

### Security Considerations

1. **Encryption**: Backup files contain no sensitive data, but consider encrypting if storing off-site
2. **Access Control**: Ensure backup files have appropriate permissions
3. **Location**: Store at least one backup off-site (cloud, USB drive)

### Backup Checklist

- [ ] Database backed up daily
- [ ] Models saved after training
- [ ] Configuration files included
- [ ] Backups verified regularly
- [ ] Off-site copies maintained
- [ ] Backup process documented

## Disaster Recovery

### Complete System Loss

If you lose the entire system:

1. **Get a new machine** with Python 3.10+
2. **Clone or extract** BlackMarket AI
3. **Run install script**: `./install_unix.sh` or `.\install_windows.ps1`
4. **Restore from latest backup**: Copy from your backup location
5. **Verify everything works**

### Partial Data Loss

If only certain data is lost:

1. **Identify what's missing**
2. **Find the appropriate backup**
3. **Restore only the affected files**
4. **Test functionality**

## Automation

### Cron Job for Linux/macOS

Add to crontab:
```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * /path/to/BlackMarket-AI/backup_daily.sh
```

### Task Scheduler for Windows

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger: Daily at 2:00 AM
4. Action: Start program: `python.exe`
5. Arguments: `-c "import shutil; from datetime import datetime; shutil.copy2('data/blackmarket.db', f'data/backups/blackmarket_{datetime.now().strftime(\"%Y%m%d\")}.db')"`

## Monitoring Backups

### Log Backup Operations

```python
# Add to your backup script
import logging

logging.basicConfig(
    filename='logs/backup.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logging.info("Backup started")
# ... backup code ...
logging.info(f"Backup completed: {backup_file}")
```

### Check Backup Status

```bash
# Check backup directory
ls -la data/backups/

# Count backups
ls data/backups/blackmarket_*.db | wc -l

# Check backup sizes
du -h data/backups/blackmarket_*.db | sort -h
```

Remember: Regular backups are your safety net. Test your recovery process periodically to ensure it works when you need it.