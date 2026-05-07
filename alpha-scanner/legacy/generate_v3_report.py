#!/usr/bin/env python3
"""
Alpha Stock Finder 对比分析报告生成器
生成HTML格式的对比报告，展示V3版本的改进
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional

REPORT_DIR = "/home/deqiangm/.hermes/cron/alpha-stock-finder/reports"
HTML_DIR = "/home/deqiangm/.hermes/cron/alpha-stock-finder/html_reports"

def generate_comparison_report(v3_data: Dict, enhanced_data: Optional[Dict] = None) -> str:
    """生成对比分析HTML报告"""
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Alpha Stock Finder V3 - 对比分析报告</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            color: #e4e4e7;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        header {{
            text-align: center;
            padding: 30px 0;
            border-bottom: 2px solid #38bdf8;
            margin-bottom: 30px;
        }}
        h1 {{
            font-size: 2.5em;
            background: linear-gradient(90deg, #38bdf8, #818cf8, #c084fc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 10px;
        }}
        .subtitle {{
            color: #94a3b8;
            font-size: 1.1em;
        }}
        .version-badge {{
            display: inline-block;
            background: linear-gradient(135deg, #059669, #10b981);
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9em;
            margin-left: 10px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: rgba(56, 189, 248, 0.1);
            border: 1px solid rgba(56, 189, 248, 0.3);
            border-radius: 15px;
            padding: 20px;
            text-align: center;
            transition: transform 0.3s ease;
        }}
        .stat-card:hover {{
            transform: translateY(-5px);
            border-color: #38bdf8;
        }}
        .stat-value {{
            font-size: 2.5em;
            font-weight: bold;
            color: #38bdf8;
        }}
        .stat-label {{
            color: #94a3b8;
            margin-top: 5px;
        }}
        .section {{
            background: rgba(30, 41, 59, 0.5);
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 25px;
            border: 1px solid rgba(148, 163, 184, 0.2);
        }}
        .section-title {{
            font-size: 1.5em;
            margin-bottom: 20px;
            color: #f8fafc;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .section-title::before {{
            content: '';
            width: 4px;
            height: 24px;
            background: linear-gradient(180deg, #38bdf8, #818cf8);
            border-radius: 2px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}
        th, td {{
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid rgba(148, 163, 184, 0.2);
        }}
        th {{
            background: rgba(56, 189, 248, 0.1);
            color: #38bdf8;
            font-weight: 600;
        }}
        tr:hover {{
            background: rgba(56, 189, 248, 0.05);
        }}
        .ticker {{
            font-weight: bold;
            color: #fbbf24;
        }}
        .score {{
            font-weight: bold;
        }}
        .score.high {{
            color: #10b981;
        }}
        .score.medium {{
            color: #f59e0b;
        }}
        .score.low {{
            color: #ef4444;
        }}
        .signal-tag {{
            display: inline-block;
            background: rgba(129, 140, 248, 0.2);
            color: #a5b4fc;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 0.85em;
            margin: 2px;
        }}
        .signal-tag.bullish {{
            background: rgba(16, 185, 129, 0.2);
            color: #34d399;
        }}
        .signal-tag.bearish {{
            background: rgba(239, 68, 68, 0.2);
            color: #f87171;
        }}
        .improvement {{
            display: inline-flex;
            align-items: center;
            gap: 5px;
            color: #10b981;
            font-size: 0.9em;
        }}
        .improvement::before {{
            content: '↑';
        }}
        .market-state {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 10px 20px;
            border-radius: 10px;
            font-size: 1.1em;
            margin-bottom: 20px;
        }}
        .market-state.bull {{
            background: rgba(16, 185, 129, 0.2);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.4);
        }}
        .market-state.bear {{
            background: rgba(239, 68, 68, 0.2);
            color: #f87171;
            border: 1px solid rgba(239, 68, 68, 0.4);
        }}
        .market-state.sideways {{
            background: rgba(251, 191, 36, 0.2);
            color: #fbbf24;
            border: 1px solid rgba(251, 191, 36, 0.4);
        }}
        .market-state.volatile {{
            background: rgba(168, 85, 247, 0.2);
            color: #c084fc;
            border: 1px solid rgba(168, 85, 247, 0.4);
        }}
        .feature-comparison {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
            margin-top: 20px;
        }}
        .feature-col {{
            background: rgba(30, 41, 59, 0.8);
            border-radius: 12px;
            padding: 20px;
        }}
        .feature-col h3 {{
            color: #f8fafc;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(148, 163, 184, 0.2);
        }}
        .feature-col.v1 h3 {{
            color: #94a3b8;
        }}
        .feature-col.v2 h3 {{
            color: #38bdf8;
        }}
        .feature-col.v3 h3 {{
            color: #10b981;
        }}
        .feature-item {{
            padding: 8px 0;
            color: #cbd5e1;
            position: relative;
            padding-left: 20px;
        }}
        .feature-item::before {{
            content: '✓';
            position: absolute;
            left: 0;
            color: #34d399;
        }}
        .feature-item.new::before {{
            content: '★';
            color: #fbbf24;
        }}
        .footer {{
            text-align: center;
            padding: 30px 0;
            color: #64748b;
            border-top: 1px solid rgba(148, 163, 184, 0.2);
            margin-top: 30px;
        }}
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.7; }}
        }}
        .live-indicator {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            color: #10b981;
        }}
        .live-indicator::before {{
            content: '';
            width: 8px;
            height: 8px;
            background: #10b981;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Alpha Stock Finder<span class="version-badge">V3.0</span></h1>
            <p class="subtitle">深度学习增强版 - 智能选股系统对比分析报告</p>
            <p class="live-indicator">实时分析 | {timestamp}</p>
        </header>
        
        <!-- 市场状态 -->
        <div class="section">
            <div class="market-state {v3_data.get('market_state', 'sideways')}">
                <span>📊</span>
                <span>市场状态: {v3_data.get('market_state_cn', '震荡市')}</span>
            </div>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">{v3_data.get('total_scanned', 0)}</div>
                    <div class="stat-label">扫描股票数</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{v3_data.get('alpha_candidates', 0)}</div>
                    <div class="stat-label">Alpha候选股</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{len(v3_data.get('features', []))}</div>
                    <div class="stat-label">新增特征</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">100+</div>
                    <div class="stat-label">技术指标</div>
                </div>
            </div>
        </div>
        
        <!-- 版本功能对比 -->
        <div class="section">
            <h2 class="section-title">版本功能对比</h2>
            <div class="feature-comparison">
                <div class="feature-col v1">
                    <h3>V1 基础版</h3>
                    <div class="feature-item">基础RSI/MACD</div>
                    <div class="feature-item">简单均线系统</div>
                    <div class="feature-item">成交量分析</div>
                    <div class="feature-item">52周新高检测</div>
                    <div class="feature-item">固定阈值系统</div>
                </div>
                <div class="feature-col v2">
                    <h3>V2 增强版</h3>
                    <div class="feature-item">动态阈值系统</div>
                    <div class="feature-item">Hurst指数</div>
                    <div class="feature-item">信号质量评分</div>
                    <div class="feature-item">市场状态识别</div>
                    <div class="feature-item">异常检测</div>
                    <div class="feature-item">多时间框架</div>
                </div>
                <div class="feature-col v3">
                    <h3>V3 深度学习版</h3>
                    <div class="feature-item new">100+技术指标</div>
                    <div class="feature-item new">ML信号评分</div>
                    <div class="feature-item new">特征工程优化</div>
                    <div class="feature-item new">趋势持久性量化</div>
                    <div class="feature-item new">风险调整收益</div>
                    <div class="feature-item new">K线形态识别</div>
                    <div class="feature-item new">Ichimoku云图</div>
                    <div class="feature-item new">VWAP支撑</div>
                </div>
            </div>
        </div>
        
        <!-- Top 10 Alpha候选股 -->
        <div class="section">
            <h2 class="section-title">🏆 Top 10 Alpha候选股</h2>
            <table>
                <thead>
                    <tr>
                        <th>排名</th>
                        <th>股票代码</th>
                        <th>综合得分</th>
                        <th>ML评分</th>
                        <th>价格</th>
                        <th>5日涨幅</th>
                        <th>RSI</th>
                        <th>ADX</th>
                        <th>Hurst</th>
                        <th>关键信号</th>
                    </tr>
                </thead>
                <tbody>
"""
    
    # 添加候选股数据
    for i, stock in enumerate(v3_data.get('top_picks', [])[:10], 1):
        score_class = 'high' if stock['score'] >= 70 else ('medium' if stock['score'] >= 50 else 'low')
        signals_html = ''.join([f'<span class="signal-tag bullish">{s}</span>' for s in stock['signals'][:3]])
        
        html_content += f"""
                    <tr>
                        <td><strong>{i}</strong></td>
                        <td class="ticker">{stock['ticker']}</td>
                        <td class="score {score_class}">{stock['score']:.1f}</td>
                        <td>{stock['ml_score']:.1f}%</td>
                        <td>${stock['price']:.2f}</td>
                        <td style="color: {'#34d399' if stock['price_change_5d'] > 0 else '#f87171'}">{stock['price_change_5d']:+.1f}%</td>
                        <td>{stock['rsi']:.1f}</td>
                        <td>{stock['adx']:.1f}</td>
                        <td>{stock['hurst']:.2f}</td>
                        <td>{signals_html}</td>
                    </tr>
"""
    
    html_content += """
                </tbody>
            </table>
        </div>
        
        <!-- 技术分析详情 -->
        <div class="section">
            <h2 class="section-title">📊 技术分析指标说明</h2>
            <table>
                <thead>
                    <tr>
                        <th>指标类别</th>
                        <th>指标名称</th>
                        <th>说明</th>
                        <th>应用场景</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>趋势指标</td>
                        <td>ADX (平均趋向指数)</td>
                        <td>衡量趋势强度，>25表示趋势明显</td>
                        <td>确认趋势方向和强度</td>
                    </tr>
                    <tr>
                        <td>趋势指标</td>
                        <td>Hurst指数</td>
                        <td>>0.6表示趋势持久性强</td>
                        <td>判断趋势可持续性</td>
                    </tr>
                    <tr>
                        <td>动量指标</td>
                        <td>RSI (相对强弱指数)</td>
                        <td>30以下超卖，70以上超买</td>
                        <td>寻找反转机会</td>
                    </tr>
                    <tr>
                        <td>动量指标</td>
                        <td>MACD (异同移动平均)</td>
                        <td>金叉/死叉信号</td>
                        <td>确认趋势转换</td>
                    </tr>
                    <tr>
                        <td>波动率指标</td>
                        <td>布林带位置</td>
                        <td>价格在带内的位置</td>
                        <td>判断超买超卖</td>
                    </tr>
                    <tr>
                        <td>成交量指标</td>
                        <td>Volume Z-Score</td>
                        <td>成交量偏离度</td>
                        <td>检测异常放量</td>
                    </tr>
                </tbody>
            </table>
        </div>
        
        <div class="footer">
            <p>Alpha Stock Finder V3.0 | 深度学习增强版</p>
            <p>结合传统技术指标与机器学习，实现更准确的选股预测</p>
            <p>报告生成时间: {timestamp}</p>
        </div>
    </div>
</body>
</html>
"""
    
    return html_content


def save_html_report(html_content: str, filename: str = None):
    """保存HTML报告"""
    if filename is None:
        filename = f"alpha_report_v3_{datetime.now().strftime('%Y%m%d_%H%M')}.html"
    
    filepath = os.path.join(HTML_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"HTML报告已保存: {filepath}")
    return filepath


def run_comparison():
    """运行对比分析"""
    # 尝试加载最新的V3报告
    import glob
    
    v3_files = sorted(glob.glob(os.path.join(REPORT_DIR, "alpha_scan_v3_*.json")), reverse=True)
    
    if v3_files:
        with open(v3_files[0], 'r') as f:
            v3_data = json.load(f)
        print(f"加载V3报告: {v3_files[0]}")
    else:
        print("未找到V3报告，请先运行 alpha_scanner_v3.py")
        return None
    
    # 生成HTML报告
    html_content = generate_comparison_report(v3_data)
    filepath = save_html_report(html_content)
    
    return filepath


if __name__ == "__main__":
    run_comparison()
