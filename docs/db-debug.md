# 数据库调试命令

## Telegram Bot 命令

```
/dbcheck   - 查看 stock_history 状态
/dbsync    - 同步历史数据
/scan      - 扫描启动信号
/history 600519 - 查看单只股票历史
```

## SSH 数据库查询

```bash
# 连接数据库
psql -U postgres -d qubot

# 或 Docker
docker exec -it postgres psql -U postgres -d qubot
```

### SQL 查询

```sql
-- 表和记录概览
SELECT 
    COUNT(*) as total,
    COUNT(DISTINCT code) as stock_count,
    MAX(date) as max_date,
    MIN(date) as min_date
FROM stock_history;

-- 最近7天有数据的股票
SELECT COUNT(DISTINCT code) 
FROM stock_history 
WHERE date >= CURRENT_DATE - INTERVAL '7 days';

-- 查看样本数据
SELECT * FROM stock_history ORDER BY date DESC LIMIT 10;

-- 查看特定股票
SELECT * FROM stock_history WHERE code = '600519' ORDER BY date DESC LIMIT 20;
```

## 日志查看

```bash
# Docker
docker logs -f qubot

# Systemd  
journalctl -u qubot -f

# 文件
tail -f /var/log/qubot.log
```
