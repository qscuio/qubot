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

### Docker Postgres 快速检查

```bash
# 1) 查看数据库环境变量
docker exec -it qubot-postgres-1 env | grep POSTGRES

# 2) 列出数据库
docker exec -it qubot-postgres-1 psql -U postgres -c "\l"

# 3) 替换为实际 DB 名称
DB=postgres

# 4) 总量、股票数、日期范围
docker exec -it qubot-postgres-1 psql -U postgres -d $DB -c \
"SELECT COUNT(*) total, COUNT(DISTINCT code) stocks, MIN(date) min_date, MAX(date) max_date FROM stock_history;"

# 5) 最近7天有数据的股票数
docker exec -it qubot-postgres-1 psql -U postgres -d $DB -c \
"SELECT COUNT(DISTINCT code) stocks_7d FROM stock_history WHERE date >= CURRENT_DATE - INTERVAL '7 days';"

# 6) 近30天内满足>=21条记录的股票数
docker exec -it qubot-postgres-1 psql -U postgres -d $DB -c \
"SELECT COUNT(*) codes_ge_21 FROM (
  SELECT code, COUNT(*) cnt
  FROM stock_history
  WHERE date >= CURRENT_DATE - INTERVAL '30 days'
  GROUP BY code
  HAVING COUNT(*) >= 21
) t;"

# 7) 近30天内记录最多的股票样本
docker exec -it qubot-postgres-1 psql -U postgres -d $DB -c \
"SELECT code, COUNT(*) cnt
 FROM stock_history
 WHERE date >= CURRENT_DATE - INTERVAL '30 days'
 GROUP BY code
 ORDER BY cnt DESC
 LIMIT 5;"
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
