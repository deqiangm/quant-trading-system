#!/usr/bin/env python3
"""
Alpha Stock Finder 报告摘要生成器
生成易于阅读的HTML报告并通过Telegram发送摘要
"""

import json
import os
from datetime import datetime
from pathlib import Path

REPORT_DIR = "/home/deqiangm/.hermes/cron/alpha-stock-finder/reports"
HTML_DIR = "/home/deqiangm/.hermes/cron/alpha-stock-finder/html_reports"
os.makedirs(HTML_DIR, exist_ok=True)

def generate_html_report(json_file):
    """生成HTML报告"""
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    timestamp = data.get('timestamp', 'Unknown')
    market_sentiment = data.get('market_sentiment', {})
    top_picks = data.get('top_picks', [])
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Alpha Stock Report - {timestamp}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        h1 {{
            text-align: center;
            color: #00ff88;
            text-shadow: 0 0 10px rgba(0,255,136,0.5);
        }}
        .timestamp {{
            text-align: center;
            color: #888;
            margin-bottom: 30px;
        }}
        .market-sentiment {{
            display: flex;
            justify-content: center;
            gap: 20px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }}
        .etf-card {{
            background: rgba(255,255,255,0.1);
            padding: 15px 25px;
            border-radius: 10px;
            text-align: center;
        }}
        .etf-card.bullish {{ border-left: 4px solid #00ff88; }}
        .etf-card.bearish {{ border-left: 4px solid #ff4444; }}
        .etf-card.neutral {{ border-left: 4px solid #ffaa00; }}
        .stock-card {{
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 15px;
            transition: transform 0.2s;
        }}
        .stock-card:hover {{
            transform: translateX(5px);
            background: rgba(255,255,255,0.08);
        }}
        .stock-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }}
        .ticker {{
            font-size: 24px;
            font-weight: bold;
            color: #00ff88;
        }}
        .score {{
            background: linear-gradient(135deg, #00ff88, #00cc6a);
            color: #000;
            padding: 5px 15px;
            border-radius: 20px;
            font-weight: bold;
        }}
        .metrics {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
            gap: 10px;
            margin: 10px 0;
        }}
        .metric {{
            text-align: center;
        }}
        .metric-value {{
            font-size: 18px;
            font-weight: bold;
        }}
        .metric-value.positive {{ color: #00ff88; }}
        .metric-value.negative {{ color: #ff4444; }}
        .metric-label {{
            font-size: 12px;
            color: #888;
        }}
        .signals {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }}
        .signal {{
            background: rgba(0,255,136,0.2);
            color: #00ff88;
            padding: 4px 10px;
            border-radius: 15px;
            font-size: 12px;
        }}
        .summary {{
            background: rgba(0,255,136,0.1);
            border: 1px solid rgba(0,255,136,0.3);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 30px;
            text-align: center;
        }}
        .summary-value {{
            font-size: 48px;
            font-weight: bold;
            color: #00ff88;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📈 Alpha Stock Report</h1>
        <p class="timestamp">Generated: {timestamp}</p>
        
        <div class="summary">
            <div class="summary-value">{len(top_picks)}</div>
            <div>Alpha Candidates Found</div>
        </div>
        
        <div class="market-sentiment">
"""
    
    # 添加市场情绪
    for etf, info in market_sentiment.items():
        trend_class = info.get('trend', 'neutral')
        html += f"""
            <div class="etf-card {trend_class}">
                <div style="font-weight:bold;">{etf}</div>
                <div>RSI: {info.get('rsi', 'N/A')}</div>
                <div>5D: {info.get('price_change_5d', 0)}%</div>
            </div>
"""
    
    html += """
        </div>
        
        <h2>🔥 Top Picks</h2>
"""
    
    # 添加股票卡片
    for i, stock in enumerate(top_picks, 1):
        price_change_class = 'positive' if stock.get('price_change_5d', 0) > 0 else 'negative'
        html += f"""
        <div class="stock-card">
            <div class="stock-header">
                <span class="ticker">{i}. {stock['ticker']}</span>
                <span class="score">Score: {stock.get('fused_score', stock.get('score', 'N/A'))}</span>
            </div>
            <div class="metrics">
                <div class="metric">
                    <div class="metric-value">${stock.get('price', 0):.2f}</div>
                    <div class="metric-label">Price</div>
                </div>
                <div class="metric">
                    <div class="metric-value {price_change_class}">{stock.get('price_change_1d', 0):+.1f}%</div>
                    <div class="metric-label">1D Change</div>
                </div>
                <div class="metric">
                    <div class="metric-value {price_change_class}">{stock.get('price_change_5d', 0):+.1f}%</div>
                    <div class="metric-label">5D Change</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{stock.get('volume_ratio', 0):.1f}x</div>
                    <div class="metric-label">Volume</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{stock.get('rsi', 0):.0f}</div>
                    <div class="metric-label">RSI</div>
                </div>
            </div>
            <div class="signals">
"""
        for signal in stock.get('signals', [])[:5]:
            html += f'                <span class="signal">{signal}</span>\n'
        
        html += """
            </div>
        </div>
"""
    
    html += """
    </div>
</body>
</html>
"""
    
    html_file = os.path.join(HTML_DIR, f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.html")
    with open(html_file, 'w') as f:
        f.write(html)
    
    return html_file

def generate_telegram_summary(json_file):
    """生成Telegram摘要消息"""
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    # 去重
    seen = set()
    unique_picks = []
    for s in data.get('top_picks', []):
        if s['ticker'] not in seen:
            seen.add(s['ticker'])
            unique_picks.append(s)
    top_picks = unique_picks[:20]
    market = data.get('market_sentiment', {})
    
    # 太平洋时区时间
    from datetime import timezone
    import pytz
    pst = pytz.timezone('America/Los_Angeles')
    now_pst = datetime.now(pst)
    time_str = now_pst.strftime('%Y-%m-%d %I:%M:%S %p PST')
    
    # Markdown格式报告
    msg = f"""# 📈 Alpha Stock Scanner Report

**扫描时间:** {time_str}

---

## 📊 Market Sentiment

| ETF | Trend | RSI | 5D Change |
|-----|-------|-----|-----------|
"""
    
    # 市场情绪
    for etf, info in market.items():
        trend_emoji = "🟢" if info['trend'] == 'bullish' else ("🔴" if info['trend'] == 'bearish' else "🟡")
        msg += f"| {etf} | {trend_emoji} | {info['rsi']} | {info['price_change_5d']:+.1f}% |\n"
    
    msg += "\n---\n\n## 🔥 Top 20 Alpha Picks\n\n"
    
    # 股票表格
    msg += "| # | Ticker | Score | Price | 5D | 20D | Vol | RSI | Signals |\n"
    msg += "|---|--------|-------|-------|-----|-----|-----|-----|----------|\n"
    
    for i, stock in enumerate(top_picks, 1):
        signals = ' · '.join(stock['signals'][:2])
        score = stock.get('fused_score', stock.get('score', 0))
        msg += f"| {i} | **{stock['ticker']}** | {score} | ${stock['price']:.2f} | {stock['price_change_5d']:+.1f}% | {stock.get('price_change_20d', 0):+.1f}% | {stock['volume_ratio']:.1f}x | {stock['rsi']:.0f} | {signals} |\n"
    
    msg += f"""
---

**报告生成完成:** {time_str}
"""
    
    return msg

if __name__ == "__main__":
    # 找到最新的报告
    reports = sorted(Path(REPORT_DIR).glob("alpha_scan_*.json"), reverse=True)
    if reports:
        latest = reports[0]
        print(f"Processing: {latest}")
        
        # 生成HTML报告
        html_file = generate_html_report(latest)
        print(f"HTML Report: {html_file}")
        
        # 生成Telegram摘要
        telegram_msg = generate_telegram_summary(latest)
        print("\n" + "="*50)
        print("Telegram Summary:")
        print("="*50)
        print(telegram_msg)
        
        # 保存摘要到文件
        summary_file = latest.with_suffix('.summary')
        with open(summary_file, 'w') as f:
            f.write(telegram_msg)
        print(f"\nSummary saved: {summary_file}")
