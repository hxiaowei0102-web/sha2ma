"""
V4性能监控脚本 — 独立运行，检查触发条件
可以通过 cron/GitHub Actions/WorkBuddy automation 调用
"""
import json, os, sys
from datetime import datetime, timezone, timedelta

BJT = timezone(timedelta(hours=8))
MONITOR_FILE = 'static/monitor_history.json'
ALERT_FILE = 'static/TRIGGER_ALERT.json'

def load_history():
    if not os.path.exists(MONITOR_FILE):
        return []
    with open(MONITOR_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def check(latest):
    """检查两个触发条件"""
    rate = latest['rate_100']
    reasons = []
    triggered = False
    
    # 条件1：滚动100期 < 70%
    if rate < 70:
        reasons.append(f"100期全中率 {rate}% < 70% 阈值")
        triggered = True
    
    return triggered, reasons

def check_monthly(history):
    """检查单月下滑 > 8pp"""
    if len(history) < 2:
        return False, ""
    
    latest = history[-1]
    today = datetime.strptime(latest['date'], '%Y-%m-%d')
    
    thirty_ago = None
    for h in reversed(history[:-1]):
        hdate = datetime.strptime(h['date'], '%Y-%m-%d')
        days_diff = (today - hdate).days
        if 25 <= days_diff <= 35:
            thirty_ago = h
            break
    
    if thirty_ago is None and len(history) >= 5:
        thirty_ago = history[max(0, len(history)-6)]
    
    if thirty_ago:
        drop = thirty_ago['rate_100'] - latest['rate_100']
        if drop > 8:
            return True, f"单月下滑 {drop:.1f}pp (从{thirty_ago['rate_100']}%→{latest['rate_100']}%, {thirty_ago['date']}→{latest['date']})"
    
    return False, ""

def main():
    history = load_history()
    
    if not history:
        print("📊 无监控历史数据")
        return 0
    
    latest = history[-1]
    
    print(f"=== V4 性能监控 ===")
    print(f"  时间: {datetime.now(BJT).strftime('%Y-%m-%d %H:%M')}")
    print(f"  最新: {latest['next_issue']}期 → 100期全中率 {latest['rate_100']}%")
    print(f"  历史: {len(history)}条记录 ({history[0]['date']}~{latest['date']})")
    print()
    
    # 趋势：最近5条
    if len(history) >= 5:
        recent = history[-5:]
        rates = [h['rate_100'] for h in recent]
        trend = "↑上升" if rates[-1] > rates[0] else ("↓下降" if rates[-1] < rates[0] else "→平稳")
        print(f"  近5期趋势: {trend} ({'→'.join(str(r) for r in rates)})")
    
    # 条件检查
    alert = False
    alert_reasons = []
    
    # 条件1
    t1, r1 = check(latest)
    if t1:
        alert = True
        alert_reasons.extend(r1)
    
    # 条件2
    t2, r2 = check_monthly(history)
    if t2:
        alert = True
        alert_reasons.append(r2)
    
    if alert:
        print(f"\n  ⚠️ 触发升级条件！")
        for r in alert_reasons:
            print(f"     {r}")
        # 写触发标记
        with open(ALERT_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'triggered': True,
                'reasons': alert_reasons,
                'date': latest['date'],
                'time': latest['time'],
                'rate_100': latest['rate_100'],
            }, f, ensure_ascii=False, indent=2)
        return 1
    else:
        print(f"\n  ✅ 正常：100期 {latest['rate_100']}% ≥ 70%, 月度下滑未触发")
        
        # 预警区（70~74%）
        if latest['rate_100'] < 74:
            print(f"  ⚡ 接近阈值（距70%仅差{latest['rate_100']-70:.1f}pp）")
        
        # 清除旧触发标记
        if os.path.exists(ALERT_FILE):
            os.remove(ALERT_FILE)
        return 0

if __name__ == '__main__':
    sys.exit(main())
