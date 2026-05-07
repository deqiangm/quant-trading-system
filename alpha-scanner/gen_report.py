#!/usr/bin/env python3
import json

with open('reports/alpha_scan_v4_20260506_1448.json', 'r') as f:
    data = json.load(f)

ms = data['market_sentiment']
cw = data['crash_warning']
top12 = data.get('top_picks', [])[:12]

lines = []

lines.append('🔍 Alpha扫描器V4.2 崩盘预警增强版')
lines.append('📅 2026-05-06 14:48 | 扫描完成')
lines.append('━━━━━━━━━━━━━━━━━━━━━━━━')
lines.append('')

# 1. Market state table
lines.append('📊 市场状态')
lines.append('┌──────┬────────┬──────┬──────┬────────┐')
lines.append('│ 指标 │ 趋势   │ RSI  │ ADX  │ 5日涨跌│')
lines.append('├──────┼────────┼──────┼──────┼────────┤')
for sym in ['SPY','QQQ','IWM','DIA']:
    d = ms[sym]
    trend_icon = '🟢多' if d['trend']=='bullish' else ('🔴空' if d['trend']=='bearish' else '🟡震')
    rsi_str = f"{d['rsi']:.1f}"
    adx_str = f"{d['adx']:.1f}"
    chg_str = f"+{d['price_change_5d']:.1f}%" if d['price_change_5d']>=0 else f"{d['price_change_5d']:.1f}%"
    lines.append(f'│ {sym:4} │ {trend_icon}    │ {rsi_str:4} │ {adx_str:4} │ {chg_str:6} │')
lines.append('└──────┴────────┴──────┴──────┴────────┘')
lines.append(f'市场状态: {data.get("market_state_cn","")} ({data.get("market_state","")})')
lines.append('')

# 2. Scan overview
lines.append('📈 扫描概况')
lines.append(f'• 扫描数: {data["total_scanned"]}')
lines.append(f'• Alpha候选: {data["alpha_candidates"]}/{data["total_scanned"]}')
lines.append(f'• 社交帖子: {data["social_posts_fetched"]} (7子版)')
lines.append(f'• TV覆盖: {data["tv_tickers_with_data"]}/{data["total_scanned"]}')
lines.append(f'• 内幕交易: {data["insider_filings_found"]} filings, {data["insider_signals_count"]} 信号匹配')
lines.append(f'• 提及异常: {len(data.get("mention_spikes",[]))} 个')
lines.append(f'• LLM情感: {"✅可用" if data.get("llm_sentiment_available") else "❌不可用"}')
lines.append('')

# 3. Top 12 candidates table
lines.append('🏆 Top 12 Alpha候选股')
lines.append('┌──────┬──────┬──────┬──────┬──────┬──────┬──────────┐')
lines.append('│ 代码 │融合分│技术分│社交分│ TV分 │WSB热 │背离值/标签│')
lines.append('├──────┼──────┼──────┼──────┼──────┼──────┼──────────┤')
for p in top12:
    div_label = p.get('divergence_label','')
    div_val = p.get('divergence',0)
    if div_label == 'aligned':
        div_str = f'{div_val:.0f}/一致'
    elif div_label == 'moderate_divergence':
        div_str = f'{div_val:.0f}/中背离'
    elif div_label == 'high_divergence':
        div_str = f'{div_val:.0f}/高背离'
    else:
        div_str = f'{div_val:.0f}/{div_label}'
    wsb = p.get('wsb_mentions', 0)
    lines.append(f'│ {p["ticker"]:4} │ {p["fused_score"]:4.0f} │ {p["technical_score"]:4.0f} │ {p["social_signal"]:4.0f} │ {p["tv_score"]:4.0f} │ {wsb:4} │ {div_str:8} │')
lines.append('└──────┴──────┴──────┴──────┴──────┴──────┴──────────┘')
lines.append('')

# 4. Paragraph summary - trend analysis
lines.append('📝 趋势点评')
semi_tickers = ['AMD','NVDA','AVGO','INTC','QCOM','TXN','NXPI','MU','AMAT','LRCX','KLAC','MRVL','ON','MCHP','SWKS','ARM','WDC','STX']
semi_in_top = [p for p in top12 if p['ticker'] in semi_tickers]
lines.append(f'• 半导体主导榜单: Top12中有{len(semi_in_top)}只半导体股')
lines.append(f'• WDC(西部数据)以融合分92居首,5日+17.1%,RSI=89.6极度超买')
lines.append(f'• AMD融合分91,WSB提及865次(最高),5日+25.0%动能极强')
lines.append(f'• DIS(迪士尼)融合分91,社交分90最高,非科技股亮点')
lines.append(f'• ARM技术分97全场最高,5日+17.7%突破52周新高')
lines.append(f'• 多股RSI>80(QQQ 81.6/GOOG 84.7/AMZN 82.4/MU 87.2/INTC 86.3),短期超买明显')
lines.append('')

# 5. Crash warning 5-layer table
layers = cw['layers']
lines.append('🚨 崩盘预警5层评分')
lines.append(f'综合: {cw["composite_score"]}/100 | 级别: {cw["warning_level"]} | 活跃层: {cw["active_layers"]}/5')
lines.append('┌──────────────────┬──────┬────────────────────────────────────────────────────┐')
lines.append('│ 层级             │ 评分 │ 关键信号                                          │')
lines.append('├──────────────────┼──────┼────────────────────────────────────────────────────┤')
layer_names = list(layers.keys())
for ln in layer_names:
    ld = layers[ln]
    score = ld['score']
    sigs = ld.get('signals',[])
    if sigs:
        sig_str = sigs[0][:44]
        if len(sigs) > 1:
            sig_str += f' (+{len(sigs)-1})'
    else:
        sig_str = '无异常'
    lines.append(f'│ {ln:16} │ {score:4} │ {sig_str:44} │')
lines.append('└──────────────────┴──────┴────────────────────────────────────────────────────┘')
lines.append('')

# 6. Core risk points
lines.append('⚠️ 核心风险要点')
for s in cw.get('all_signals', []):
    lines.append(f'• {s}')
lines.append('')

# 7. Social signal anomalies
lines.append('📱 社交信号异常')
# WSB extreme heat
wsb_hot = sorted(top12, key=lambda x: x.get('wsb_mentions',0), reverse=True)[:5]
lines.append('WSB极端热度:')
for p in wsb_hot:
    sent = p.get('wsb_sentiment', 0)
    sent_str = '偏多' if sent > 0.1 else ('偏空' if sent < -0.1 else '中性')
    lines.append(f'  • {p["ticker"]}: {p["wsb_mentions"]}次提及 (情感:{sent:.2f} {sent_str})')

# High divergence stocks
high_div = [p for p in top12 if p.get('divergence_label','') in ('high_divergence','moderate_divergence')]
if high_div:
    lines.append('高背离个股:')
    for p in high_div:
        dir_str = '价涨社交弱' if p['technical_score'] > p['social_signal'] else '社交强价弱'
        lines.append(f'  • {p["ticker"]}: 背离={p["divergence"]:.0f} ({p["divergence_label"]}) {dir_str}')
else:
    lines.append('高背离个股: 无明显背离')

# Special attention stocks
lines.append('特殊关注:')
for p in top12:
    if p.get('rsi',0) > 85:
        lines.append(f'  • {p["ticker"]}: RSI={p["rsi"]:.1f} 极度超买⚠️')
    if p.get('cp_signal','') in ('heavy_calls','heavy_puts'):
        cp_cn = '看涨期权集中' if p['cp_signal']=='heavy_calls' else '看跌期权集中'
        lines.append(f'  • {p["ticker"]}: {cp_cn} ({p["cp_signal"]})')
lines.append('')

# 8. Key conclusions
lines.append('🎯 要点总结')
lines.append('1. 市场整体多头强势,4大指数全线看涨,但RSI普遍超买(QQQ 81.6/SPY 75.8)')
lines.append('2. 半导体板块集体爆发,Top12中6只半导体股,AMD/MU/INTC等5日涨幅20%+')
lines.append('3. 崩盘预警12/100(NORMAL),仅技术极端层活跃(35分):SPY RSI超买+量价背离')
lines.append('4. 价量背离信号需警惕:SPY价格上涨但成交量递减(20/50日比=0.66)')
lines.append('5. 收益率曲线倒挂后效应仍在:距上次倒挂607天,处于1-24月危险窗口内')
lines.append('')
lines.append('━━━━━━━━━━━━━━━━━━━━━━━━')
lines.append('📊 V4.2 Alpha Scanner | 数据仅供参考,不构成投资建议')

report_text = '\n'.join(lines)
print(report_text)
