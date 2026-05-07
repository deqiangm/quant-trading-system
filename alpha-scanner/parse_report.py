#!/usr/bin/env python3
import json

with open('reports/alpha_scan_v4_20260506_2123.json') as f:
    data = json.load(f)

# Print summary stats
print('=== SUMMARY ===')
print(f'total_scanned: {data["total_scanned"]}')
print(f'alpha_candidates: {data["alpha_candidates"]}')
print(f'social_posts_fetched: {data["social_posts_fetched"]}')
print(f'tv_tickers_with_data: {data["tv_tickers_with_data"]}')
print(f'insider_filings_found: {data["insider_filings_found"]}')
print(f'insider_signals_count: {data["insider_signals_count"]}')
print(f'llm_sentiment_available: {data["llm_sentiment_available"]}')
print(f'market_state: {data["market_state"]}')
print(f'market_state_cn: {data["market_state_cn"]}')

# Market sentiment
print('\n=== MARKET SENTIMENT ===')
for etf, info in data['market_sentiment'].items():
    print(f'{etf}: trend={info["trend"]} rsi={info["rsi"]} adx={info["adx"]} 5d={info["price_change_5d"]}% vol={info["volatility"]}')

# Mention spikes
print('\n=== MENTION SPIKES ===')
for spike in data['mention_spikes']:
    print(f'{spike["ticker"]}: today={spike["today_mentions"]} avg={spike["avg_mentions"]} ratio={spike["spike_ratio"]}')

# Crash warning
print('\n=== CRASH WARNING ===')
cw = data['crash_warning']
print(f'composite_score: {cw["composite_score"]}')
print(f'warning_level: {cw["warning_level"]}')
print(f'active_layers: {cw["active_layers"]}')
for layer_name, layer_data in cw['layers'].items():
    print(f'  {layer_name}: score={layer_data["score"]} signals={layer_data["signals"]}')
print(f'all_signals: {cw["all_signals"]}')

# Top 12 picks - key fields
print('\n=== TOP 12 PICKS ===')
for i, pick in enumerate(data['top_picks'][:12], 1):
    print(f'{i}. {pick["ticker"]}: fused={pick["fused_score"]:.1f} tech={pick["technical_score"]:.1f} soc={pick["social_signal"]:.1f} tv={pick["tv_score"]:.1f} wsb_mentions={pick["wsb_mentions"]} wsb_sent={pick["wsb_sentiment"]:.3f} div={pick["divergence"]:.1f} div_label={pick["divergence_label"]} tv_cons={pick["tv_consensus"]} cp={pick["cp_signal"]} conviction={pick["social_conviction"]} price={pick["price"]:.2f} 5d={pick["price_change_5d"]}% rsi={pick["rsi"]}')

# Subreddits
print('\n=== SUBREDDITS ===')
for sub, count in data['social_subreddits'].items():
    print(f'r/{sub}: {count}')

# Social subreddits detail
print('\n=== FEATURES ===')
for feat in data.get('features', []):
    print(feat)
