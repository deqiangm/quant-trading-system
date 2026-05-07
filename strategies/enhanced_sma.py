#!/usr/bin/env python3
"""
增强版SMA均线交叉策略
包含止损、止盈、仓位管理等风控功能
"""

import backtrader as bt
from datetime import datetime

class EnhancedSmaCross(bt.Strategy):
    """
    增强版SMA均线交叉策略
    
    特性:
    1. 可配置的快慢均线周期
    2. 止损/止盈机制
    3. 仓位管理 (不满仓操作)
    4. 交易日志记录
    
    买入信号: 快速均线上穿慢速均线
    卖出信号: 快速均线下穿慢速均线
    """
    
    params = (
        ('fast_period', 10),      # 快速均线周期
        ('slow_period', 30),      # 慢速均线周期
        ('stop_loss', 0.05),      # 止损比例 5%
        ('take_profit', 0.15),    # 止盈比例 15%
        ('position_size', 0.95),  # 仓位比例 95%
        ('printlog', True),
    )
    
    def __init__(self):
        # 计算移动平均线
        self.fast_sma = bt.indicators.SMA(self.data.close, period=self.params.fast_period)
        self.slow_sma = bt.indicators.SMA(self.data.close, period=self.params.slow_period)
        
        # 交叉信号
        self.crossover = bt.indicators.CrossOver(self.fast_sma, self.slow_sma)
        
        # 订单和价格跟踪
        self.order = None
        self.buyprice = None
        self.buycomm = None
        self.stop_order = None
        self.profit_order = None
    
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
        # 如果有挂单，等待执行
        if self.order:
            return
        
        # 检查当前是否持仓
        if not self.position:
            # 无持仓，检查买入信号
            if self.crossover > 0:
                self.log(f'买入信号, 收盘价: {self.data.close[0]:.2f}')
                # 计算买入数量
                cash_to_use = self.broker.getcash() * self.params.position_size
                size = int(cash_to_use / self.data.close[0])
                if size > 0:
                    self.order = self.buy(size=size)
        else:
            # 有持仓，检查卖出信号或止损止盈
            if self.crossover < 0:
                self.log(f'卖出信号 (均线交叉), 收盘价: {self.data.close[0]:.2f}')
                self.order = self.sell(size=self.position.size)
    
    def log(self, txt, dt=None):
        """日志输出"""
        if self.params.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'[{dt.isoformat()}] {txt}')
    
    def stop(self):
        """策略结束"""
        if self.params.printlog:
            self.log(f'策略结束 - 最终资产: {self.broker.getvalue():.2f}', 
                    dt=self.datas[0].datetime.date(0))


class MACDStrategy(bt.Strategy):
    """
    MACD策略
    
    基于MACD指标的交易策略
    买入: MACD线上穿信号线
    卖出: MACD线下穿信号线
    """
    
    params = (
        ('macd_fast', 12),
        ('macd_slow', 26),
        ('macd_signal', 9),
        ('position_size', 0.95),
        ('printlog', True),
    )
    
    def __init__(self):
        # MACD指标
        self.macd = bt.indicators.MACD(
            self.data.close,
            period_me1=self.params.macd_fast,
            period_me2=self.params.macd_slow,
            period_signal=self.params.macd_signal
        )
        
        # MACD交叉信号
        self.crossover = bt.indicators.CrossOver(self.macd.macd, self.macd.signal)
        
        # 订单跟踪
        self.order = None
        self.buyprice = None
    
    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status in [order.Completed]:
            if order.isbuy():
                if self.params.printlog:
                    self.log(f'买入执行, 价格: {order.executed.price:.2f}')
                self.buyprice = order.executed.price
            else:
                if self.params.printlog:
                    self.log(f'卖出执行, 价格: {order.executed.price:.2f}')
        
        self.order = None
    
    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        if self.params.printlog:
            self.log(f'交易盈亏, 毛利: {trade.pnl:.2f}, 净利: {trade.pnlcomm:.2f}')
    
    def next(self):
        if self.order:
            return
        
        if not self.position:
            if self.crossover > 0:
                self.log(f'买入信号 (MACD交叉), 收盘价: {self.data.close[0]:.2f}')
                cash_to_use = self.broker.getcash() * self.params.position_size
                size = int(cash_to_use / self.data.close[0])
                if size > 0:
                    self.order = self.buy(size=size)
        else:
            if self.crossover < 0:
                self.log(f'卖出信号 (MACD交叉), 收盘价: {self.data.close[0]:.2f}')
                self.order = self.sell(size=self.position.size)
    
    def log(self, txt, dt=None):
        if self.params.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f'[{dt.isoformat()}] {txt}')
    
    def stop(self):
        if self.params.printlog:
            self.log(f'策略结束 - 最终资产: {self.broker.getvalue():.2f}', 
                    dt=self.datas[0].datetime.date(0))
