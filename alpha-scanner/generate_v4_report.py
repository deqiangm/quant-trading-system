#!/usr/bin/env python3
"""
Alpha Stock Finder V4 - Social Sentiment Enhanced Report Generator
Generates HTML report with social sentiment fields, divergence analysis,
and tech/social score breakdown.
"""

import json
import os
import glob
from datetime import datetime
from typing import Dict, Optional

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
HTML_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "html_reports")


def _score_class(score: float, high: float = 80, mid: float = 60) -> str:
    return "high" if score >= high else ("medium" if score >= mid else "low")


def _sentiment_emoji(label: str) -> str:
    mapping = {
        "strong_bullish": "🟢🟢",
        "bullish": "🟢",
        "neutral": "⚪",
        "bearish": "🔴",
        "strong_bearish": "🔴🔴",
    }
    return mapping.get(label, "⚪")


def _divergence_style(label: str) -> str:
    styles = {
        "aligned": "color:#34d399;",
        "moderate_divergence": "color:#fbbf24;",
        "high_divergence": "color:#f87171;",
    }
    return styles.get(label, "color:#94a3b8;")


def _cp_signal_style(signal: str) -> str:
    if "call" in signal.lower():
        return "color:#34d399;"
    elif "put" in signal.lower():
        return "color:#f87171;"
    return "color:#94a3b8;"


def _tv_consensus_style(label: str) -> str:
    styles = {
        "strong_buy": "color:#22c55e;font-weight:bold;",
        "buy": "color:#34d399;",
        "neutral": "color:#94a3b8;",
        "sell": "color:#f87171;",
        "strong_sell": "color:#ef4444;font-weight:bold;",
    }
    return styles.get(label, "color:#94a3b8;")


def _insider_signal_style(signal: str) -> str:
    if signal == "bullish":
        return "color:#34d399;font-weight:bold;"
    elif signal == "bearish":
        return "color:#f87171;font-weight:bold;"
    return "color:#94a3b8;"


def _crash_level_style(level: str) -> str:
    """Return CSS style for crash warning level."""
    if 'CRASH' in level:
        return "color:#ef4444;font-weight:bold;font-size:1.2em;"
    elif 'ELEVATED' in level:
        return "color:#f97316;font-weight:bold;"
    elif 'CAUTION' in level:
        return "color:#fbbf24;"
    elif 'WATCH' in level:
        return "color:#38bdf8;"
    return "color:#34d399;"


def _crash_bar_color(score: int) -> str:
    """Return bar color based on crash warning score."""
    if score >= 70:
        return "#ef4444"
    elif score >= 50:
        return "#f97316"
    elif score >= 30:
        return "#fbbf24"
    elif score >= 15:
        return "#38bdf8"
    return "#34d399"


def _crash_warning_stat_card(cw_data: Optional[Dict]) -> str:
    """Generate crash warning stat card HTML."""
    if not cw_data:
        return """<div class="stat-card">
            <div class="stat-value" style="color:#94a3b8;">N/A</div>
            <div class="stat-label">崩盘预警</div>
        </div>"""
    score = cw_data.get('composite_score', 0)
    level = cw_data.get('warning_level', '✅ NORMAL')
    active = cw_data.get('active_layers', 0)
    bar_color = _crash_bar_color(score)
    return f"""<div class="stat-card" style="background:rgba({bar_color.lstrip('#')},0.1);border:1px solid {bar_color}40;">
        <div class="stat-value" style="{_crash_level_style(level)}">{score}</div>
        <div class="stat-label">崩盘预警 ({active}/5层)</div>
        <div style="background:rgba(148,163,184,0.2);border-radius:4px;height:6px;width:100%;margin-top:8px;">
            <div style="background:{bar_color};border-radius:4px;height:6px;width:{score}%;"></div>
        </div>
    </div>"""


def _crash_warning_section(cw_data: Optional[Dict]) -> str:
    """Generate crash warning detail section HTML."""
    if not cw_data:
        return """<div class="section" style="border-color:rgba(148,163,184,0.2);">
        <h2 class="section-title">🛡️ 崩盘预警系统 (5-Layer Crash Warning)</h2>
        <p style="color:#94a3b8;">崩盘预警数据不可用 — 可能因数据源限制或分析跳过</p>
        </div>"""

    score = cw_data.get('composite_score', 0)
    level = cw_data.get('warning_level', '✅ NORMAL')
    active_layers = cw_data.get('active_layers', 0)
    layers = cw_data.get('layers', {})
    all_signals = cw_data.get('all_signals', [])
    bar_color = _crash_bar_color(score)

    # Build layer rows
    layer_rows = ""
    layer_weights = {
        'Market Euphoria': (20, '市场狂热', 'Fear&Greed指数 + VIX + VVIX'),
        'Yield Curve Anomaly': (30, '收益率曲线异常', '10Y-3M/2Y利差 + 倒挂→陡峭化'),
        'Credit Risk': (20, '信贷风险', 'HY利差 + MOVE指数'),
        'Systemic Risk': (15, '系统性风险', '板块相关性 + SKEW'),
        'Technical Extremes': (15, '技术极端', 'RSI + 量价背离 + 兴登堡凶兆'),
    }

    for name, (weight, cn_name, desc) in layer_weights.items():
        l = layers.get(name, {})
        l_score = l.get('score', 0)
        l_signals = l.get('signals', [])
        l_bar_color = _crash_bar_color(l_score)
        signals_html = "<br>".join([f"<span style='color:#f87171;font-size:0.85em;'>⚠️ {s}</span>" for s in l_signals[:3]]) if l_signals else "<span style='color:#64748b;font-size:0.85em;'>— 无显著信号</span>"
        layer_rows += f"""
        <tr>
            <td><strong>{cn_name}</strong><br><span style="color:#64748b;font-size:0.8em;">{name}</span></td>
            <td style="text-align:center;"><strong>{weight}%</strong></td>
            <td class="score {_score_class(l_score, 50, 25)}" style="{_crash_level_style(level) if l_score >= 50 else ''}">{l_score}</td>
            <td>
                <div style="background:rgba(148,163,184,0.2);border-radius:4px;height:8px;width:100%;">
                    <div style="background:{l_bar_color};border-radius:4px;height:8px;width:{l_score}%;"></div>
                </div>
            </td>
            <td style="font-size:0.85em;">{desc}</td>
            <td>{signals_html}</td>
        </tr>"""

    # Signals summary
    signals_html = ""
    for sig in all_signals[:10]:
        signals_html += f"<div style='padding:3px 0;color:#fbbf24;font-size:0.9em;'>⚠️ {sig}</div>"

    return f"""
    <div class="section" style="border-color:{bar_color}40;">
        <h2 class="section-title">🛡️ 崩盘预警系统 (5-Layer Crash Warning)</h2>
        <div style="display:flex;align-items:center;gap:20px;margin-bottom:20px;">
            <div style="font-size:2.5em;{_crash_level_style(level)}">{level}</div>
            <div>
                <div style="font-size:1.5em;font-weight:bold;color:{bar_color};">综合评分: {score}/100</div>
                <div style="color:#94a3b8;">活跃层: {active_layers}/5 | 权重: Euphoria(20%) + Yield(30%) + Credit(20%) + Systemic(15%) + Technical(15%)</div>
            </div>
            <div style="flex:1;background:rgba(148,163,184,0.2);border-radius:8px;height:16px;">
                <div style="background:{bar_color};border-radius:8px;height:16px;width:{score}%;transition:width 1s;"></div>
            </div>
        </div>

        {f'<div style="background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:10px;padding:15px;margin-bottom:15px;"><h4 style="color:#f87171;margin-bottom:8px;">⚠️ 关键预警信号</h4>{signals_html}</div>' if all_signals else ''}

        <div class="table-wrapper">
        <table>
            <thead>
                <tr>
                    <th>预警层</th>
                    <th>权重</th>
                    <th>评分</th>
                    <th style="width:120px;">可视化</th>
                    <th>检测指标</th>
                    <th>活跃信号</th>
                </tr>
            </thead>
            <tbody>
                {layer_rows}
            </tbody>
        </table>
        </div>

        <div style="margin-top:15px;padding:12px;background:rgba(0,0,0,0.3);border-radius:8px;">
            <h4 style="color:#c084fc;margin-bottom:6px;">💡 崩盘预警如何影响选股</h4>
            <p style="color:#cbd5e1;font-size:0.9em;line-height:1.6;">
                崩盘预警不作为第5维度加入融合权重，而是作为<strong>宏观叠加层(Macro Overlay)</strong>影响所有候选股：
                <br>• 综合评分 ≥70 (CRASH WARNING): 所有long头寸折扣60%（即分数×0.60）
                <br>• 综合评分 ≥50 (ELEVATED RISK): 折扣80%（分数×0.80）
                <br>• 综合评分 ≥30 (CAUTION): 折扣92%（分数×0.92）
                <br>• 同时降低技术权重（动量失效风险），提升社交权重（情绪先行）
            </p>
        </div>
    </div>"""


def generate_v4_report(v4_data: Dict) -> str:
    """Generate V4+ Multi-Dimension Fusion HTML report."""

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    top_picks = v4_data.get("top_picks", [])

    # Build top picks rows
    top_rows = ""
    for i, s in enumerate(top_picks[:12], 1):
        fused = s.get("fused_score", 0)
        tech = s.get("technical_score", 0)
        soc = s.get("social_signal", 0)
        tv_score = s.get("tv_score") or 50
        tv_cons = s.get("tv_consensus") or "unknown"
        ins_sig = s.get("insider_signal") or "unavailable"
        ins_score = s.get("insider_score") or 50
        div_label = s.get("divergence_label") or "N/A"
        div_val = s.get("divergence", 0)
        conviction = s.get("social_conviction") or "N/A"
        cp = s.get("cp_signal") or "N/A"
        wsb = s.get("wsb_mentions", 0)
        wsb_sent = s.get("wsb_sentiment", 0)
        spike = s.get("mention_spike_ratio", 0)

        signals_html = "".join(
            [f'<span class="signal-tag bullish">{sig}</span>' for sig in s.get("signals", [])[:3]]
        )

        top_rows += f"""
        <tr>
            <td><strong>{i}</strong></td>
            <td class="ticker">{s['ticker']}</td>
            <td class="score {_score_class(fused)}">{fused:.1f}</td>
            <td class="score {_score_class(tech, 70, 55)}">{tech:.1f}</td>
            <td class="score {_score_class(soc, 70, 50)}">{soc:.1f}</td>
            <td class="score {_score_class(tv_score, 70, 50)}" style="color:#38bdf8;">{tv_score:.0f}</td>
            <td style="{_tv_consensus_style(tv_cons)}">{tv_cons.replace('_', ' ').title()}</td>
            <td style="{_insider_signal_style(ins_sig)}">{ins_sig[:3].upper() if ins_sig != 'unavailable' else '—'}</td>
            <td>{s.get('ml_score', 0):.1f}%</td>
            <td>${s.get('price', 0):.2f}</td>
            <td style="color: {'#34d399' if s.get('price_change_5d', 0) > 0 else '#f87171'}">{s.get('price_change_5d', 0):+.1f}%</td>
            <td>{s.get('rsi', 0):.1f}</td>
            <td class="social-hot">{wsb}🔥</td>
            <td>{wsb_sent:+.2f}</td>
            <td style="{_cp_signal_style(cp)}">{cp}</td>
            <td style="{_divergence_style(div_label)}">{div_label.replace('_', ' ').title()}</td>
            <td>{_sentiment_emoji(conviction)} {conviction.replace('_', ' ').title()}</td>
            <td>{signals_html}</td>
        </tr>"""

    # Build social heatmap section — tickers with highest social activity
    social_tickers = sorted(top_picks, key=lambda x: x.get("wsb_mentions", 0), reverse=True)[:10]
    social_rows = ""
    for s in social_tickers:
        social_rows += f"""
        <tr>
            <td class="ticker">{s['ticker']}</td>
            <td>{s.get('wsb_mentions', 0)}</td>
            <td>{s.get('wsb_sentiment', 0):+.3f}</td>
            <td>{s.get('mention_spike_ratio', 0):.1f}x</td>
            <td style="{_cp_signal_style(s.get('cp_signal') or '')}">{s.get('cp_signal') or 'N/A'}</td>
            <td>{_sentiment_emoji(s.get('social_conviction') or '')} {(s.get('social_conviction') or 'N/A').replace('_', ' ').title()}</td>
            <td class="score {_score_class(s.get('social_signal', 0), 70, 50)}">{s.get('social_signal', 0):.1f}</td>
            <td class="score {_score_class(s.get('fused_score', 0))}">{s.get('fused_score', 0):.1f}</td>
        </tr>"""

    # Divergence analysis — tech vs social divergence
    div_tickers = sorted(top_picks, key=lambda x: abs(x.get("divergence", 0)), reverse=True)[:10]
    div_rows = ""
    for s in div_tickers:
        div_val = s.get("divergence", 0)
        div_label = s.get("divergence_label") or "N/A"
        bar_width = min(abs(div_val) / 50 * 100, 100)
        bar_color = "#34d399" if div_label == "aligned" else ("#fbbf24" if div_label == "moderate_divergence" else "#f87171")
        div_rows += f"""
        <tr>
            <td class="ticker">{s['ticker']}</td>
            <td class="score {_score_class(s.get('technical_score', 0), 70, 55)}">{s.get('technical_score', 0):.1f}</td>
            <td class="score {_score_class(s.get('social_signal', 0), 70, 50)}">{s.get('social_signal', 0):.1f}</td>
            <td style="{_divergence_style(div_label)}">{div_val:+.1f}</td>
            <td style="{_divergence_style(div_label)}">{div_label.replace('_', ' ').title()}</td>
            <td>
                <div style="background:rgba(148,163,184,0.2);border-radius:4px;height:8px;width:100%;">
                    <div style="background:{bar_color};border-radius:4px;height:8px;width:{bar_width}%;"></div>
                </div>
            </td>
        </tr>"""

    html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Alpha Stock Finder V4 - Social Sentiment Enhanced</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
            color: #e4e4e7;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1600px;
            margin: 0 auto;
        }}
        header {{
            text-align: center;
            padding: 30px 0;
            border-bottom: 2px solid #c084fc;
            margin-bottom: 30px;
        }}
        h1 {{
            font-size: 2.5em;
            background: linear-gradient(90deg, #c084fc, #818cf8, #38bdf8, #34d399);
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
            background: linear-gradient(135deg, #7c3aed, #a855f7);
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9em;
            margin-left: 10px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: rgba(192, 132, 252, 0.1);
            border: 1px solid rgba(192, 132, 252, 0.3);
            border-radius: 15px;
            padding: 18px;
            text-align: center;
            transition: transform 0.3s ease;
        }}
        .stat-card:hover {{
            transform: translateY(-5px);
            border-color: #c084fc;
        }}
        .stat-card.social {{
            background: rgba(52, 211, 153, 0.1);
            border: 1px solid rgba(52, 211, 153, 0.3);
        }}
        .stat-card.social:hover {{
            border-color: #34d399;
        }}
        .stat-value {{
            font-size: 2.2em;
            font-weight: bold;
            color: #c084fc;
        }}
        .stat-card.social .stat-value {{
            color: #34d399;
        }}
        .stat-label {{
            color: #94a3b8;
            margin-top: 5px;
            font-size: 0.9em;
        }}
        .section {{
            background: rgba(30, 41, 59, 0.5);
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 25px;
            border: 1px solid rgba(148, 163, 184, 0.2);
        }}
        .section.social-section {{
            border-color: rgba(52, 211, 153, 0.3);
        }}
        .section.divergence-section {{
            border-color: rgba(251, 191, 36, 0.3);
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
            background: linear-gradient(180deg, #c084fc, #818cf8);
            border-radius: 2px;
        }}
        .social-section .section-title::before {{
            background: linear-gradient(180deg, #34d399, #38bdf8);
        }}
        .divergence-section .section-title::before {{
            background: linear-gradient(180deg, #fbbf24, #f97316);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
            font-size: 0.9em;
        }}
        th, td {{
            padding: 10px 12px;
            text-align: left;
            border-bottom: 1px solid rgba(148, 163, 184, 0.2);
        }}
        th {{
            background: rgba(192, 132, 252, 0.1);
            color: #c084fc;
            font-weight: 600;
            white-space: nowrap;
        }}
        .social-section th {{
            background: rgba(52, 211, 153, 0.1);
            color: #34d399;
        }}
        .divergence-section th {{
            background: rgba(251, 191, 36, 0.1);
            color: #fbbf24;
        }}
        tr:hover {{
            background: rgba(192, 132, 252, 0.05);
        }}
        .social-section tr:hover {{
            background: rgba(52, 211, 153, 0.05);
        }}
        .ticker {{
            font-weight: bold;
            color: #fbbf24;
        }}
        .score {{
            font-weight: bold;
        }}
        .score.high {{
            color: #34d399;
        }}
        .score.medium {{
            color: #fbbf24;
        }}
        .score.low {{
            color: #ef4444;
        }}
        .signal-tag {{
            display: inline-block;
            background: rgba(129, 140, 248, 0.2);
            color: #a5b4fc;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 0.8em;
            margin: 1px;
        }}
        .signal-tag.bullish {{
            background: rgba(16, 185, 129, 0.2);
            color: #34d399;
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
        .market-state.sideways {{
            background: rgba(251, 191, 36, 0.2);
            color: #fbbf24;
            border: 1px solid rgba(251, 191, 36, 0.4);
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
        .market-state.volatile {{
            background: rgba(168, 85, 247, 0.2);
            color: #c084fc;
            border: 1px solid rgba(168, 85, 247, 0.4);
        }}
        .social-hot {{
            color: #f97316;
            font-weight: bold;
        }}
        .fusion-explanation {{
            background: rgba(30, 41, 59, 0.8);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            border-left: 4px solid #c084fc;
        }}
        .fusion-explanation h3 {{
            color: #c084fc;
            margin-bottom: 10px;
        }}
        .fusion-explanation p {{
            color: #cbd5e1;
            line-height: 1.6;
        }}
        .fusion-formula {{
            background: rgba(0,0,0,0.3);
            padding: 10px 15px;
            border-radius: 8px;
            margin: 10px 0;
            font-family: 'Courier New', monospace;
            color: #a5b4fc;
        }}
        .legend {{
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
            margin: 10px 0;
            font-size: 0.85em;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 5px;
        }}
        .legend-dot {{
            width: 10px;
            height: 10px;
            border-radius: 50%;
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
            color: #34d399;
        }}
        .live-indicator::before {{
            content: '';
            width: 8px;
            height: 8px;
            background: #34d399;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }}
        .table-wrapper {{
            overflow-x: auto;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
    <h1>Alpha Stock Finder<span class="version-badge">V4.2</span></h1>
    <p class="subtitle">Crash Warning Enhanced - 崩盘预警增强版智能选股系统</p>
            <p class="live-indicator">实时分析 | {timestamp}</p>
        </header>

        <!-- Market State & Overview -->
        <div class="section">
            <div class="market-state {v4_data.get('market_state', 'sideways')}">
                <span>📊</span>
                <span>市场状态: {v4_data.get('market_state_cn', '震荡市')}</span>
            </div>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">{v4_data.get('total_scanned', 0)}</div>
                    <div class="stat-label">扫描股票数</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{v4_data.get('alpha_candidates', 0)}</div>
                    <div class="stat-label">Alpha候选股</div>
                </div>
                            <div class="stat-card social">
                                <div class="stat-value">{v4_data.get('social_posts_fetched', 0)}</div>
                                <div class="stat-label">Reddit帖子采集</div>
                            </div>
                            <div class="stat-card social">
                                <div class="stat-value">{sum(s.get('wsb_mentions', 0) for s in top_picks)}</div>
                                <div class="stat-label">WSB提及总数</div>
                            </div>
                            <div class="stat-card">
                                <div class="stat-value">{v4_data.get('tv_tickers_with_data', 0)}</div>
                                <div class="stat-label">TV数据覆盖</div>
                            </div>
                            <div class="stat-card">
                                <div class="stat-value">{v4_data.get('insider_signals_count', 0)}</div>
                                <div class="stat-label">内幕信号</div>
                            </div>
        <div class="stat-card social">
            <div class="stat-value">{'✅' if v4_data.get('llm_sentiment_available') else '❌'}</div>
            <div class="stat-label">LLM情感</div>
        </div>
        {_crash_warning_stat_card(v4_data.get('crash_warning'))}
    </div>
</div>

                    <!-- Fusion Score Explanation -->
                    <div class="fusion-explanation">
                        <h3>⚡ V4+ Multi-Dimension Fusion Score</h3>
                        <p>4维度融合评分 = 技术分析 + 社交情绪 + TradingView共识 + SEC内幕交易：</p>
                        <div class="fusion-formula">
                            Fused = w_tech × tech + w_social × social + w_tv × tv + w_insider × insider<br>
                            基础权重: tech=0.45, social=0.30, tv=0.15, insider=0.10<br>
                            权重根据市场状态、社交提及量、TV数据可用性、内幕信号强度动态调整
                        </div>
            <div class="legend">
                <div class="legend-item"><div class="legend-dot" style="background:#34d399;"></div> Aligned: 技术与社交同向</div>
                <div class="legend-item"><div class="legend-dot" style="background:#fbbf24;"></div> Moderate Divergence: 轻度背离</div>
                <div class="legend-item"><div class="legend-dot" style="background:#f87171;"></div> High Divergence: 严重背离(警惕)</div>
            </div>
        </div>

        <!-- Top 15 Alpha Candidates (V4 Enhanced) -->
        <div class="section">
            <h2 class="section-title">🏆 Top 15 Alpha候选股 - Tech × Social Fusion</h2>
            <div class="table-wrapper">
            <table>
                <thead>
                    <tr>
                                <th>#</th>
                                <th>代码</th>
                                <th>融合分</th>
                                <th>技术分</th>
                                <th>社交分</th>
                                <th>TV分</th>
                                <th>TV共识</th>
                                <th>内幕</th>
                                <th>ML%</th>
                                <th>价格</th>
                                <th>5日涨幅</th>
                                <th>RSI</th>
                                <th>WSB热度</th>
                                <th>情绪值</th>
                                <th>C/P信号</th>
                                <th>背离</th>
                                <th>社交信心</th>
                                <th>关键信号</th>
                    </tr>
                </thead>
                <tbody>
                    {top_rows}
                </tbody>
            </table>
            </div>
        </div>

        <!-- Social Heatmap -->
        <div class="section social-section">
            <h2 class="section-title">🔥 社交热度排行 (Reddit WSB + StockTwits)</h2>
            <div class="table-wrapper">
            <table>
                <thead>
                    <tr>
                        <th>代码</th>
                        <th>WSB提及</th>
                        <th>情绪值</th>
                        <th>提及倍数</th>
                        <th>C/P信号</th>
                        <th>社交信心</th>
                        <th>社交分</th>
                        <th>融合分</th>
                    </tr>
                </thead>
                <tbody>
                    {social_rows}
                </tbody>
            </table>
            </div>
        </div>

        <!-- Divergence Analysis -->
        <div class="section divergence-section">
            <h2 class="section-title">⚡ 技术vs社交 背离分析</h2>
            <p style="color:#94a3b8;margin-bottom:15px;">
                背离度 = |技术分 - 社交分|。高背离意味着技术面与社交面方向不一致，需额外关注。
            </p>
            <div class="table-wrapper">
            <table>
                <thead>
                    <tr>
                        <th>代码</th>
                        <th>技术分</th>
                        <th>社交分</th>
                        <th>背离度</th>
                        <th>背离类型</th>
                        <th>可视化</th>
                    </tr>
                </thead>
                <tbody>
                    {div_rows}
                </tbody>
            </table>
            </div>
    </div>

    <!-- Crash Warning System -->
    {_crash_warning_section(v4_data.get('crash_warning'))}

    <!-- Version Feature Comparison -->
                    <div class="section">
                        <h2 class="section-title">📋 版本功能演进</h2>
                        <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:15px;margin-top:15px;">
                            <div style="background:rgba(30,41,59,0.8);border-radius:12px;padding:18px;">
                                <h3 style="color:#94a3b8;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid rgba(148,163,184,0.2);">V1 基础版</h3>
                                <div style="padding:5px 0;color:#cbd5e1;">✓ 基础RSI/MACD</div>
                                <div style="padding:5px 0;color:#cbd5e1;">✓ 简单均线系统</div>
                                <div style="padding:5px 0;color:#cbd5e1;">✓ 成交量分析</div>
                                <div style="padding:5px 0;color:#cbd5e1;">✓ 52周新高检测</div>
                            </div>
                            <div style="background:rgba(30,41,59,0.8);border-radius:12px;padding:18px;">
                                <h3 style="color:#38bdf8;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid rgba(148,163,184,0.2);">V2 增强版</h3>
                                <div style="padding:5px 0;color:#cbd5e1;">✓ 动态阈值系统</div>
                                <div style="padding:5px 0;color:#cbd5e1;">✓ Hurst指数</div>
                                <div style="padding:5px 0;color:#cbd5e1;">✓ 信号质量评分</div>
                                <div style="padding:5px 0;color:#cbd5e1;">✓ 市场状态识别</div>
                                <div style="padding:5px 0;color:#cbd5e1;">✓ 多时间框架</div>
                            </div>
                            <div style="background:rgba(30,41,59,0.8);border-radius:12px;padding:18px;">
                                <h3 style="color:#10b981;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid rgba(148,163,184,0.2);">V3 深度学习版</h3>
                                <div style="padding:5px 0;color:#cbd5e1;">★ 100+技术指标</div>
                                <div style="padding:5px 0;color:#cbd5e1;">★ ML信号评分</div>
                                <div style="padding:5px 0;color:#cbd5e1;">★ 特征工程优化</div>
                                <div style="padding:5px 0;color:#cbd5e1;">★ Ichimoku云图</div>
                                <div style="padding:5px 0;color:#cbd5e1;">★ VWAP支撑</div>
                            </div>
                            <div style="background:rgba(30,41,59,0.8);border-radius:12px;padding:18px;border:1px solid rgba(192,132,252,0.3);">
                                <h3 style="color:#c084fc;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid rgba(148,163,184,0.2);">V4 社交版</h3>
                                <div style="padding:5px 0;color:#34d399;">★ Reddit WSB热度</div>
                                <div style="padding:5px 0;color:#34d399;">★ StockTwits情绪</div>
                                <div style="padding:5px 0;color:#34d399;">★ 期权C/P信号</div>
                                <div style="padding:5px 0;color:#34d399;">★ Tech×Social融合</div>
                                <div style="padding:5px 0;color:#34d399;">★ 背离度分析</div>
                            </div>
    <div style="background:rgba(30,41,59,0.8);border-radius:12px;padding:18px;border:1px solid rgba(251,191,36,0.3);">
        <h3 style="color:#fbbf24;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid rgba(148,163,184,0.2);">V4+ 多维融合版</h3>
        <div style="padding:5px 0;color:#fbbf24;">🔥 TradingView共识</div>
        <div style="padding:5px 0;color:#fbbf24;">🔥 TV基本面评分</div>
        <div style="padding:5px 0;color:#fbbf24;">🔥 LLM情感(DeepSeek)</div>
        <div style="padding:5px 0;color:#fbbf24;">🔥 SEC内幕交易</div>
        <div style="padding:5px 0;color:#fbbf24;">🔥 4维融合评分</div>
    </div>
    <div style="background:rgba(30,41,59,0.8);border-radius:12px;padding:18px;border:1px solid rgba(239,68,68,0.3);">
        <h3 style="color:#f87171;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid rgba(148,163,184,0.2);">V4.2 崩盘预警版</h3>
        <div style="padding:5px 0;color:#f87171;">🛡️ 5层崩盘预警</div>
        <div style="padding:5px 0;color:#f87171;">🛡️ 宏观叠加层折扣</div>
        <div style="padding:5px 0;color:#f87171;">🛡️ 收益率曲线监控</div>
        <div style="padding:5px 0;color:#f87171;">🛡️ 信贷风险检测</div>
        <div style="padding:5px 0;color:#f87171;">🛡️ 系统性风险扫描</div>
    </div>
    </div>
                    </div>

                    <div class="footer">
    <p>Alpha Stock Finder V4.2 | Multi-Dimension Fusion + Crash Warning Overlay</p>
    <p>4维度动态权重融合 + 5层崩盘预警宏观叠加: Tech(45%) + Social(30%) + TV(15%) + Insider(10%) × Crash Discount</p>
                        <p>报告生成时间: {timestamp}</p>
                    </div>
    </div>
</body>
</html>
"""

    return html_content


def save_html_report(html_content: str, filename: str = None) -> str:
    """Save HTML report to disk."""
    if filename is None:
        filename = f"report_v4_{datetime.now().strftime('%Y%m%d_%H%M')}.html"

    os.makedirs(HTML_DIR, exist_ok=True)
    filepath = os.path.join(HTML_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"V4 HTML report saved: {filepath}")
    return filepath


def run():
    """Load latest V4 JSON report and generate HTML."""
    v4_files = sorted(glob.glob(os.path.join(REPORT_DIR, "alpha_scan_v4_*.json")), reverse=True)

    if v4_files:
        with open(v4_files[0], "r") as f:
            v4_data = json.load(f)
        print(f"Loaded V4 report: {v4_files[0]}")
    else:
        print("No V4 JSON report found. Run alpha_scanner_v4.py first.")
        return None

    html_content = generate_v4_report(v4_data)
    filepath = save_html_report(html_content)

    return filepath


if __name__ == "__main__":
    run()
