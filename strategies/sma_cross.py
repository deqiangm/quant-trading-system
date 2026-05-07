#!/usr/bin/env python3
"""
SMA均线交叉策略
Backtrader实现版本
"""

import backtrader as bt
from datetime import datetime

class SmaCross(bt.Strategy):
    """
    简单移动平均线交叉策略
    
    买入信号: 快速均线(10日)上穿慢速均线(20日)
    卖出信号: 快速均线(10日)下穿慢速均线(20日)
    """
    
    params = (
        ('fast_period', 10),
        ('slow_period', 20),
        ('printlog', True),
    )
    
    def __init__(self):
        # 计算移动平均线
        self.fast_sma = bt.indicators.SMA(self.data.close, period=self.params.fast_period)
        self.slow_sma = bt.indicators.SMA(self.data.close, period=self.params.slow_period)
        
        # 交叉信号
        self.crossover = bt.indicators.CrossOver(self.fast_sma, self.slow_sma)
        
        # 订单跟踪
        self.order = None
        self.buyprice = None
        self.buycomm = None
    
    def notify_order(self, order):
        """订单状态通知"""
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status in [order.Completed]:
            if order.isbuy():
                if self.params.printlog:
                    self.log(f'买入执行, 价格: {order.executed.price:.2f}, '
                            f'成本: {order.executed.value:.2f}, '
                            f'手续费: {order.executed.comm:.2f}')
                self.buyprice = order.executed.price
                self.buycomm = order.executed.comm
            else:
                if self.params.printlog:
                    self.log(f'卖出执行, 价格: {order.executed.price:.2f}, '
                            f'成本: {order.executed.value:.2f}, '
                            f'手续费: {order.executed.comm:.2f}')
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            if self.params.printlog:
                self.log('订单取消/保证金不足/拒绝')
        
        self.order = None
    
    def notify_trade(self, trade):
        """交易通知"""
        if not trade.isclosed:
            return
        
        if self.params.printlog:
            self.log(f'交易盈亏, 毛利: {trade.pnl:.2f}, 净利: {trade.pnlcomm:.2f}')
    
    def next(self):
        """策略主逻辑"""
        if self.order:
            return
        
        if not self.position:
            # 无持仓，检查买入信号
            if self.crossover > 0:
                self.log(f'买入信号, 收盘价: {self.data.close[0]:.2f}')
                # 使用95%资金买入
                self.order = self.buy(size=self.broker.getcash() * 0.95 / self.data.close[0])
        else:
            # 有持仓，检查卖出信号
            if self.crossover < 0:
                self.log(f'卖出信号, 收盘价: {self.data.close[0]:.2f}')
                self.order = self.sell(size=self.position.size)
    
    def log(self, txt, dt=None):
        """日志输出"""
        if self.params.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'[{dt.isoformat()}] {txt}')
    
    def stop(self):
        """策略结束"""
        if self.params.printlog:
            self.log(f'策略结束 - 最终资产: {self.broker.getvalue():.2f}', dt=self.datas[0].datetime.date(0))


class RSIStrategy(bt.Strategy):
    """
    RSI策略示例
    
    买入: RSI < 30 (超卖)
    卖出: RSI > 70 (超买)
    """
    
    params = (
        ('rsi_period', 14),
        ('rsi_lower', 30),
        ('rsi_upper', 70),
        ('printlog', True),
    )
    
    def __init__(self):
        self.rsi = bt.indicators.RSI(self.data.close, period=self.params.rsi_period)
        self.order = None
    
    def next(self):
        if self.order:
            return
        
        if not self.position:
            if self.rsi < self.params.rsi_lower:
                self.order = self.buy(size=self.broker.getcash() * 0.95 / self.data.close[0])
        else:
            if self.rsi > self.params.rsi_upper:
                self.order = self.sell(size=self.position.size)
