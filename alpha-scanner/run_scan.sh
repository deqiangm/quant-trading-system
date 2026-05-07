#!/bin/bash
# Alpha Stock Finder 启动脚本
# 用于 cron job 定时执行

# 激活虚拟环境
source /home/deqiangm/.hermes/hermes-agent/venv/bin/activate

# 设置工作目录
cd /home/deqiangm/.hermes/cron/alpha-stock-finder

# 日志文件
LOG_DIR="/home/deqiangm/.hermes/cron/alpha-stock-finder/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/scan_$(date +%Y%m%d_%H%M%S).log"

# 运行扫描器
echo "========================================" >> "$LOG_FILE"
echo "Alpha Stock Scanner Started: $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

python3 alpha_scanner.py >> "$LOG_FILE" 2>&1

echo "========================================" >> "$LOG_FILE"
echo "Alpha Stock Scanner Completed: $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

# 清理旧日志（保留30天）
find "$LOG_DIR" -name "*.log" -mtime +30 -delete 2>/dev/null

# 清理旧报告（保留30天）
find "/home/deqiangm/.hermes/cron/alpha-stock-finder/reports" -name "*.json" -mtime +30 -delete 2>/dev/null
