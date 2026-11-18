# BlackMarket AI - Troubleshooting Guide

This guide helps you resolve common issues when running BlackMarket AI.

## Installation Issues

### Python Version Error

**Problem**: "Python 3.10 or higher is required"

**Solution**:
1. Download Python 3.10+ from https://python.org
2. During installation, check "Add Python to PATH"
3. Restart your terminal after installation

### Virtual Environment Creation Failed

**Problem**: "Failed to create virtual environment"

**Solution**:
```bash
# Windows
python -m ensurepip --upgrade
python -m venv venv

# macOS/Linux
python3 -m pip install --upgrade pip
python3 -m venv venv
```

### Dependency Installation Failed

**Problem**: "Failed to install dependencies"

**Solution**:
1. Update pip: `python -m pip install --upgrade pip`
2. Try installing specific packages:
   ```bash
   pip install numpy pandas scikit-learn
   pip install aiohttp websockets textual
   ```
3. For Windows, try with `--user` flag:
   ```bash
   pip install --user -r requirements.txt
   ```

## Runtime Issues

### Module Import Errors

**Problem**: `ModuleNotFoundError: No module named '...'`

**Solution**:
1. Ensure virtual environment is activated:
   ```bash
   # Windows
   venv\Scripts\activate
   
   # macOS/Linux
   source venv/bin/activate
   ```
2. Check if all dependencies are installed:
   ```bash
   pip list
   ```
3. Reinstall requirements:
   ```bash
   pip install -r requirements.txt
   ```

### Database Issues

**Problem**: `sqlite3.OperationalError: no such table: symbols`

**Solution**:
1. Delete the database file:
   ```bash
   # Windows
   del data\blackmarket.db
   
   # macOS/Linux
   rm data/blackmarket.db
   ```
2. Reinitialize the database:
   ```bash
   python -c "from database.connection import Database; Database('sqlite:///data/blackmarket.db').init_db()"
   ```

**Problem**: Database is locked

**Solution**:
1. Make sure no other instances are running
2. On Windows, try:
   ```powershell
   taskkill /F /IM python.exe
   ```
3. Wait a few seconds and try again

### WebSocket Connection Issues

**Problem**: WebSocket connection fails or keeps reconnecting

**Solution**:
1. Check internet connection
2. Firewall may be blocking connections:
   - Windows: Allow Python through Windows Firewall
   - macOS: Check System Preferences > Security & Privacy > Firewall
3. Try running with debug logging:
   ```env
   LOG_LEVEL=DEBUG
   ```

### Memory Issues

**Problem**: Application crashes with memory error

**Solution**:
1. Reduce concurrent scans in config.py:
   ```python
   MAX_CONCURRENT_SCANS = 4  # Reduce from 8
   ```
2. Close other applications using memory
3. On Windows, check Task Manager for memory usage

## Telegram Issues

### Telegram Not Sending Messages

**Problem**: Telegram notifications not working

**Solution**:
1. Verify bot token and chat ID in `.env` file
2. Test connection:
   ```bash
   # Windows
   python -c "from notifications.telegram_client import TelegramClient; t = TelegramClient('your_token', 'your_chat_id'); t.test_connection()"
   
   # macOS/Linux
   python3 -c "from notifications.telegram_client import TelegramClient; t = TelegramClient('your_token', 'your_chat_id'); t.test_connection()"
   ```
3. Check bot permissions:
   - Open your bot in Telegram
   - Click on the bot name
   - Scroll to "Permissions" and ensure all permissions are enabled

### Rate Limit Errors

**Problem**: "429 Too Many Requests" from Telegram

**Solution**:
1. Telegram allows 30 messages per second
2. The system has built-in deduplication, but if you still get errors:
   - Increase `SIGNAL_DEDUP_WINDOW_SECONDS` in config.py
   - Reduce notification frequency in dashboard

## Performance Issues

### Slow Startup

**Problem**: Application takes a long time to start

**Solution**:
1. Set `SCAN_ALL_ELIGIBLE_SYMBOLS=false` in `.env`
2. Reduce timeframes in `.env`:
   ```
   TIMEFRAMES=1m,5m,15m,1h,4h
   ```
3. Disable unused features:
   ```
   ML_ENABLED=false
   TELEGRAM_ENABLED=false
   ```

### High CPU Usage

**Problem**: CPU usage is very high

**Solution**:
1. Reduce `MAX_CONCURRENT_SCANS`
2. Close unnecessary applications
3. On Windows, check Task Manager for CPU usage

## Dashboard Issues

### Terminal Not Displaying Properly

**Problem**: Dashboard shows garbled text or doesn't update

**Solution**:
1. Use a terminal that supports Unicode:
   - Windows: Windows Terminal (from Microsoft Store)
   - macOS: Terminal.app
   - Linux: GNOME Terminal, Konsole
2. Ensure terminal supports 24-bit color
3. Try running with:
   ```bash
   export TERM=xterm-256color
   ```

### Keyboard Shortcuts Not Working

**Problem**: Dashboard keyboard shortcuts (1-0, q, r) don't work

**Solution**:
1. Ensure terminal is in raw mode
2. Try different terminal emulator
3. Some terminals require special configuration for arrow keys

## Data Issues

### Missing Historical Data

**Problem**: Strategies need more historical data

**Solution**:
1. Run the application for longer periods
2. Manually download historical data (future enhancement)
3. Reduce strategy complexity temporarily

### Stale Signals

**Problem**: Signals are not updating

**Solution**:
1. Check `SIGNAL_STALE_SECONDS` in config.py (default: 30 seconds)
2. Verify WebSocket connections are active
3. Check scanner status in dashboard

## Backup and Recovery

### Corrupted Database

**Problem**: Database file is corrupted

**Solution**:
1. Find the latest backup:
   ```bash
   # Windows
   dir data\backups\blackmarket_*.db /B /O:-D
   
   # macOS/Linux
   ls -t data/backups/blackmarket_*.db | head -1
   ```
2. Restore from backup:
   ```bash
   # Windows
   copy "data\backups\blackmarket_20240101.db" "data\blackmarket.db"
   
   # macOS/Linux
   cp "data/backups/blackmarket_20240101.db" "data/blackmarket.db"
   ```

### Model Issues

**Problem**: ML models not training or promoting

**Solution**:
1. Check if enough predictions exist:
   ```sql
   SELECT COUNT(*) FROM predictions WHERE resolved = 1;
   ```
2. Reduce validation thresholds temporarily:
   ```env
   MIN_VALIDATION_F1=0.45
   MIN_VALIDATION_ACCURACY=0.50
   ```
3. Ensure `AUTO_MODEL_TRAINING=true` in `.env`

## Debug Mode

### Enable Debug Logging

Add to `.env`:
```env
LOG_LEVEL=DEBUG
```

### Specific Component Debugging

Set component-specific logging:
```python
# In main.py before running
import logging
logging.getLogger('market.scanner').setLevel(logging.DEBUG)
logging.getLogger('intelligence.intelligence_core').setLevel(logging.DEBUG)
```

### Database Query Debugging

Add to config.py:
```python
DATABASE_URL = "sqlite:///data/blackmarket.db?echo=true"
```

## Common Error Messages

### "Event bus not initialized"

**Cause**: Trying to use event bus before initialization
**Solution**: Ensure orchestrator is properly initialized before using event bus

### "Rate limit exceeded"

**Cause**: Too many requests to Binance API
**Solution**: The system has built-in rate limiting, but if it still happens:
- Wait for the token bucket to refill
- Check `MAX_WEBSOCKET_CONNECTIONS` setting

### "Position not found"

**Cause**: Trying to close a position that doesn't exist
**Solution**: Check if position_id is valid and position still exists

### "Insufficient balance"

**Cause**: Not enough balance to open position
**Solution**: Check balance in dashboard or use smaller position size

## Getting Help

1. Check the logs in `logs/blackmarket.log`
2. Run with debug logging enabled
3. Check GitHub issues for similar problems
4. Create a new issue with:
   - Operating system and Python version
   - Full error message
   - Steps to reproduce
   - Expected vs actual behavior