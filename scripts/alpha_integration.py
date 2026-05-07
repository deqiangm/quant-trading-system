#!/usr/bin/env python3
"""
Alpha Scanner 集成模块
提供与 alpha-stock-finder 系统的数据共享机制
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import glob

class AlphaScannerIntegration:
    """
    Alpha Scanner 集成类
    
    提供以下功能:
    1. 读取 Alpha Scanner 的扫描结果
    2. 获取推荐的交易标的
    3. 将信号转换为回测参数
    """
    
    def __init__(self, 
                 alpha_scanner_path='/home/deqiangm/.hermes/cron/alpha-stock-finder',
                 quant_system_path='/home/deqiangm/.hermes/cron/quant-trading-system'):
        """
        初始化集成模块
        
        Args:
            alpha_scanner_path: Alpha Scanner 项目路径
            quant_system_path: 量化交易系统路径
        """
        self.alpha_scanner_path = Path(alpha_scanner_path)
        self.quant_system_path = Path(quant_system_path)
        self.reports_dir = self.alpha_scanner_path / 'reports'
        self.shared_data_dir = self.quant_system_path / 'data' / 'alpha_signals'
        
        # 创建共享数据目录
        self.shared_data_dir.mkdir(parents=True, exist_ok=True)
    
    def get_latest_report(self):
        """
        获取最新的 Alpha Scanner 报告
        
        Returns:
            dict: 报告数据
        """
        # 查找最新的 JSON 报告
        json_files = list(self.reports_dir.glob('alpha_scan_*.json'))
        
        if not json_files:
            return None
        
        # 按修改时间排序，获取最新的
        latest_file = max(json_files, key=os.path.getmtime)
        
        with open(latest_file, 'r') as f:
            return json.load(f)
    
    def get_alpha_candidates(self, min_score=50, max_count=10):
        """
        获取 Alpha 候选股票列表
        
        Args:
            min_score: 最低评分阈值
            max_count: 最大返回数量
        
        Returns:
            list: 候选股票列表
        """
        report = self.get_latest_report()
        
        if not report:
            return []
        
        # 筛选高分候选
        candidates = []
        for pick in report.get('top_picks', []):
            if pick.get('score', 0) >= min_score:
                candidates.append({
                    'ticker': pick['ticker'],
                    'price': pick['price'],
                    'score': pick['score'],
                    'signals': pick.get('signals', []),
                    'rsi': pick.get('rsi'),
                    'macd_hist': pick.get('macd_hist'),
                    'price_change_5d': pick.get('price_change_5d'),
                    'price_change_20d': pick.get('price_change_20d'),
                    'volume_ratio': pick.get('volume_ratio'),
                    'market_cap': pick.get('market_cap'),
                    'pe_ratio': pick.get('pe_ratio'),
                })
        
        # 按评分排序，取前 N 个
        candidates.sort(key=lambda x: x['score'], reverse=True)
        return candidates[:max_count]
    
    def get_market_sentiment(self):
        """
        获取市场整体情绪
        
        Returns:
            dict: 市场情绪数据
        """
        report = self.get_latest_report()
        
        if not report:
            return None
        
        return report.get('market_sentiment', {})
    
    def suggest_strategy(self, ticker_data):
        """
        根据股票信号建议策略
        
        Args:
            ticker_data: 股票数据 (来自 alpha_candidates)
        
        Returns:
            dict: 策略建议
        """
        signals = ticker_data.get('signals', [])
        rsi = ticker_data.get('rsi', 50)
        macd_hist = ticker_data.get('macd_hist', 0)
        
        recommendations = {
            'primary_strategy': None,
            'secondary_strategy': None,
            'risk_level': 'medium',
            'position_size': 0.95,
            'reasons': []
        }
        
        # 根据 RSI 判断
        if rsi < 30:
            recommendations['primary_strategy'] = 'RSI'
            recommendations['reasons'].append('RSI超卖反弹机会')
        elif rsi > 70:
            recommendations['risk_level'] = 'high'
            recommendations['position_size'] = 0.80
            recommendations['reasons'].append('RSI超买，注意回调风险')
        
        # 根据 MACD 判断
        if macd_hist > 0:
            recommendations['primary_strategy'] = 'MACD'
            recommendations['reasons'].append('MACD多头排列')
        
        # 根据价格动量判断
        price_change_20d = ticker_data.get('price_change_20d', 0)
        if price_change_20d > 20:
            recommendations['primary_strategy'] = 'EnhancedSMA'
            recommendations['reasons'].append('强势趋势，适合均线跟踪')
        
        # 默认策略
        if not recommendations['primary_strategy']:
            recommendations['primary_strategy'] = 'SMA'
            recommendations['reasons'].append('默认均线交叉策略')
        
        return recommendations
    
    def generate_backtest_config(self, min_score=50, max_tickers=5):
        """
        生成回测配置
        
        Args:
            min_score: 最低评分阈值
            max_tickers: 最大标的数量
        
        Returns:
            dict: 回测配置
        """
        candidates = self.get_alpha_candidates(min_score=min_score, max_count=max_tickers)
        sentiment = self.get_market_sentiment()
        
        config = {
            'generated_at': datetime.now().isoformat(),
            'source_report': 'alpha_scanner',
            'market_sentiment': sentiment,
            'backtests': []
        }
        
        for candidate in candidates:
            strategy_suggestion = self.suggest_strategy(candidate)
            
            config['backtests'].append({
                'ticker': candidate['ticker'],
                'strategy': strategy_suggestion['primary_strategy'],
                'secondary_strategy': strategy_suggestion['secondary_strategy'],
                'risk_level': strategy_suggestion['risk_level'],
                'position_size': strategy_suggestion['position_size'],
                'reasons': strategy_suggestion['reasons'],
                'alpha_score': candidate['score'],
                'alpha_signals': candidate['signals'],
            })
        
        return config
    
    def save_shared_signals(self, config=None):
        """
        保存共享信号数据
        
        Args:
            config: 配置数据 (可选，默认自动生成)
        
        Returns:
            str: 保存的文件路径
        """
        if config is None:
            config = self.generate_backtest_config()
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'alpha_signals_{timestamp}.json'
        filepath = self.shared_data_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        return str(filepath)
    
    def load_shared_signals(self, filepath=None):
        """
        加载共享信号数据
        
        Args:
            filepath: 文件路径 (可选，默认加载最新的)
        
        Returns:
            dict: 信号数据
        """
        if filepath is None:
            # 加载最新的
            files = list(self.shared_data_dir.glob('alpha_signals_*.json'))
            if not files:
                return None
            filepath = max(files, key=os.path.getmtime)
        
        with open(filepath, 'r') as f:
            return json.load(f)


def main():
    """测试集成功能"""
    print("\n" + "="*60)
    print("Alpha Scanner 集成测试")
    print("="*60)
    
    integration = AlphaScannerIntegration()
    
    # 获取最新报告
    report = integration.get_latest_report()
    if report:
        print(f"\n最新报告时间: {report.get('timestamp', 'N/A')}")
        print(f"扫描股票数: {report.get('total_scanned', 0)}")
        print(f"Alpha候选数: {report.get('alpha_candidates', 0)}")
    
    # 获取候选
    print("\n--- Alpha 候选股票 (score >= 80) ---")
    candidates = integration.get_alpha_candidates(min_score=80, max_count=5)
    for c in candidates:
        print(f"  {c['ticker']}: 评分 {c['score']}, RSI {c['rsi']:.1f}, 5日涨幅 {c['price_change_5d']:.1f}%")
    
    # 获取市场情绪
    print("\n--- 市场情绪 ---")
    sentiment = integration.get_market_sentiment()
    if sentiment:
        for symbol, data in sentiment.items():
            print(f"  {symbol}: {data.get('trend', 'N/A')}, RSI {data.get('rsi', 'N/A'):.1f}")
    
    # 生成回测配置
    print("\n--- 生成回测配置 ---")
    config = integration.generate_backtest_config(min_score=80, max_tickers=3)
    for bt in config['backtests']:
        print(f"  {bt['ticker']}: 策略={bt['strategy']}, 风险={bt['risk_level']}")
        print(f"    原因: {', '.join(bt['reasons'])}")
    
    # 保存共享信号
    filepath = integration.save_shared_signals(config)
    print(f"\n共享信号已保存: {filepath}")
    
    print("\n" + "="*60)
    print("集成测试完成 ✓")
    print("="*60)


if __name__ == '__main__':
    main()
