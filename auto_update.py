"""
云端全自动更新脚本 — 多数据源 + CSV追加 + 预测生成
GitHub Actions 定时运行
"""
import csv, json, os, sys
from datetime import datetime, timezone, timedelta
from collections import Counter
from urllib.request import urlopen, Request
from urllib.error import URLError

# ============ 配置 ============
CSV_PATH = 'data/fc3d-history.csv'
PREDICT_OUT = 'static/predict.json'

# 北京时间
BJT = timezone(timedelta(hours=8))

# 双模型配置（统一从backtest.py导入）
# MODEL_CONFIGS 在 backtest.py 中定义

# ============ 6层降级数据源 ============
DATA_SOURCES = [
    {
        'name': 'huiniao',
        'type': 'json',
        'url': 'http://api.huiniao.top/interface/home/lotteryHistory?type=fcsd&page=1&limit=5',
        'parser': lambda data: [
            (item['code'], int(item['one']), int(item['two']), int(item['three']))
            for item in data['data']['data']['list']
        ]
    },
    {
        'name': 'apihz',
        'type': 'json',
        'url': 'https://api.apihz.cn/api/kaijiang/fc3d/list.php',
        'parser': lambda data: [
            (item['qihao'], int(item['haoma'][0]), int(item['haoma'][1]), int(item['haoma'][2]))
            for item in data.get('data', [])
        ]
    },
    {
        'name': 'zhcw',
        'type': 'html',
        'url': 'https://www.zhcw.com/kjxx/fc3d/',
        'parser': None  # HTML解析
    },
    {
        'name': '8200',
        'type': 'json',
        'url': 'https://api.8200.cn/hall/fc3d/getFc3dLotteryList',
        'parser': lambda data: [
            (item['lotteryDrawNum'], int(item['lotteryDrawResult'][0]), 
             int(item['lotteryDrawResult'][1]), int(item['lotteryDrawResult'][2]))
            for item in data.get('data', data.get('result', []))
        ]
    },
    {
        'name': '55128',
        'type': 'html',
        'url': 'https://www.55128.cn/kjh/fcsd-history-61.htm',
        'parser': None
    },
    {
        'name': 'cjcp',
        'type': 'html',
        'url': 'https://www.cjcp.com.cn/kaijiang/fc3d/',
        'parser': None
    },
]

# ============ 数据抓取 ============
def fetch_latest():
    """6层降级：依次尝试，首个成功即返回，不继续"""
    for src in DATA_SOURCES:
        try:
            req = Request(src['url'], headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            ctx = __import__('ssl')._create_unverified_context() if '8200' in src['url'] or '55128' in src['url'] else None
            with urlopen(req, timeout=15, context=ctx) as resp:
                raw = resp.read().decode('utf-8', errors='ignore')
                data = json.loads(raw)
                
                if src['type'] == 'json' and src['parser']:
                    draws = src['parser'](data)
                elif src['type'] == 'html':
                    # HTML解析: 从页面提取期号和号码
                    import re
                    draws = []
                    # 匹配期号-号码模式: 2026200 或 2026200期
                    pattern = re.findall(r'(20\d{5})\D*?(\d)\D+?(\d)\D+?(\d)', raw)
                    for issue, b, s, g in pattern:
                        draws.append((issue, int(b), int(s), int(g)))
                else:
                    draws = []
                
                if draws:
                    print(f"  [{src['name']}] ✓ 获取{len(draws)}条, 最新{draws[0]}")
                    return {src['name']: draws}  # 首个成功即返回
                else:
                    print(f"  [{src['name']}] 无数据, 尝试下一个...")
        except Exception as e:
            print(f"  [{src['name']}] ✗ {str(e)[:60]}")
    
    print(f"  ❌ 所有6个数据源均失败")
    return {}

def merge_results(all_results):
    """多源合并：至少1源确认即可(2+源共识标记为确认)"""
    issue_map = {}
    for src_name, draws in all_results.items():
        for issue, b, s, g in draws:
            if issue not in issue_map:
                issue_map[issue] = Counter()
            issue_map[issue][(b, s, g)] += 1
    
    confirmed = []
    for issue in sorted(issue_map.keys()):
        counter = issue_map[issue]
        nums, count = counter.most_common(1)[0]
        # 至少1源确认即采纳
        confirmed.append((issue, nums[0], nums[1], nums[2]))
    
    confirmed.sort()
    return confirmed

# ============ CSV操作 ============
def load_existing_issues():
    """读取CSV中已有的期号"""
    existing = []
    try:
        with open(CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing.append(row['issue'])
    except FileNotFoundError:
        pass
    return existing

def append_to_csv(new_draws):
    """追加新数据到CSV（去重+校验）"""
    existing = load_existing_issues()
    added = 0
    with open(CSV_PATH, 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        for issue, b, s, g in new_draws:
            # 校验数据合法性
            if issue in existing:
                continue
            if not (issue.startswith('20') and 7 <= len(issue) <= 8):
                print(f"  ⚠ 跳过无效期号: {issue}")
                continue
            if not all(isinstance(x, int) and 0 <= x <= 9 for x in [b, s, g]):
                print(f"  ⚠ 跳过无效号码: {issue}={b}{s}{g}")
                continue
            writer.writerow([issue, b, s, g])
            added += 1
            print(f"  新增: {issue} = {b}{s}{g}")
    return added

# ============ 算法与回测（统一导入） ============
from backtest import run_backtest, predict_next, MODEL_CONFIG

# ============ 回测+预测 ============
def generate_outputs():
    """生成V3预测和100期回测 — 直接复用backtest.py"""
    import csv
    issues = []
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            issues.append(row['issue'])
    
    N = len(issues)
    if N < 2:
        print("  数据不足，跳过预测")
        return
    
    # 预测
    pred = predict_next(CSV_PATH)
    latest = pred['last_draw']
    
    all_predict = {
        'next_issue': pred['next_issue'],
        'last_issue': pred['last_issue'],
        'last_draw': f"{latest['hundreds']}{latest['tens']}{latest['ones']}",
        'updated': datetime.now(BJT).strftime('%Y-%m-%d %H:%M'),
    }
    
    # 100期回测
    bt = run_backtest(CSV_PATH, n_periods=100)
    s = bt['summary']
    
    backtest_data = []
    for r in bt['results']:
        backtest_data.append({
            'issue': r['issue'], 'draw': ''.join(str(d) for d in r['draw']),
            'kh': r['kill_h'], 'kt': r['kill_t'], 'ko': r['kill_o'],
            'hh': r['h_hit'], 'th': r['t_hit'], 'oh': r['o_hit'], 'ah': r['all_hit'],
        })
    
    all_predict['kills'] = {
        'h': pred['predictions']['hundreds'],
        't': pred['predictions']['tens'],
        'o': pred['predictions']['ones'],
    }
    all_predict['summary'] = {
        'h': s['hundreds_hit_rate'],
        't': s['tens_hit_rate'],
        'o': s['ones_hit_rate'],
        'all': s['all_hit_rate'],
        'total': s['total_periods'],
    }
    all_predict['data'] = backtest_data
    
    print(f"  V3 {s['total_periods']}期: 百{s['hundreds_hit_rate']}% 十{s['tens_hit_rate']}% 个{s['ones_hit_rate']}% ★{s['all_hit_rate']}%★")
    
    with open(PREDICT_OUT, 'w', encoding='utf-8') as f:
        json.dump(all_predict, f, ensure_ascii=False)
    
    # 追加监控历史（用于触发条件检测）
    save_monitor_history(all_predict)
    
    print(f"  预测期号: {all_predict['next_issue']}")


def save_monitor_history(all_predict):
    """保存100期全中率到监控历史文件"""
    MONITOR_FILE = 'static/monitor_history.json'
    s = all_predict['summary']
    entry = {
        'date': datetime.now(BJT).strftime('%Y-%m-%d'),
        'time': datetime.now(BJT).strftime('%H:%M'),
        'last_issue': all_predict['last_issue'],
        'next_issue': all_predict['next_issue'],
        'rate_100': s['all'],
        'rate_h': s['h'],
        'rate_t': s['t'],
        'rate_o': s['o'],
    }
    
    history = []
    try:
        if os.path.exists(MONITOR_FILE):
            with open(MONITOR_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
    except:
        pass
    
    # 去重：同一天同一期号只保留最新
    history = [h for h in history if h.get('next_issue') != entry['next_issue']]
    history.append(entry)
    
    # 只保留最近180天
    if len(history) > 180:
        history = history[-180:]
    
    with open(MONITOR_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    
    # 检查触发条件，写警报文件
    check_and_alert(history, entry)
    
    print(f"  监控历史: {len(history)}条, 当前{entry['rate_100']}%")


def check_and_alert(history, entry):
    """云端唯一触发检查：满足条件写TRIGGER_ALERT.json，正常则删除"""
    ALERT_FILE = 'static/TRIGGER_ALERT.json'
    
    if len(history) < 2:
        # 历史不足，清除旧警报
        if os.path.exists(ALERT_FILE):
            os.remove(ALERT_FILE)
        return
    
    latest = history[-1]
    triggered = False
    reasons = []
    
    # 条件1：100期全中率 < 70%
    if latest['rate_100'] < 70:
        reasons.append(f"100期全中率{latest['rate_100']}% < 70%阈值")
        triggered = True
    
    # 条件2：单月下滑 > 8pp
    # 修复：向后找第一个 25~35 天前的记录；找不到则继续找更早的（容忍缺数据）
    from datetime import datetime as dt
    today = dt.strptime(latest['date'], '%Y-%m-%d')
    matched = False
    for h in reversed(history[:-1]):
        hdate = dt.strptime(h['date'], '%Y-%m-%d')
        days_diff = (today - hdate).days
        if 25 <= days_diff <= 35:
            drop = h['rate_100'] - latest['rate_100']
            if drop > 8:
                reasons.append(f"单月下滑{drop:.1f}pp ({h['rate_100']}%→{latest['rate_100']}%, {h['date']}→{latest['date']})")
                triggered = True
            matched = True
            break
        # 超过35天还没找到 → 继续向后找更早的（不break），最多再看10条
    # 若全部记录都太旧(>60天)，也尝试用最近一条可比的
    if not matched:
        for h in reversed(history[:-1]):
            hdate = dt.strptime(h['date'], '%Y-%m-%d')
            days_diff = (today - hdate).days
            if days_diff <= 60:
                drop = h['rate_100'] - latest['rate_100']
                if drop > 8:
                    reasons.append(f"单月下滑{drop:.1f}pp ({h['rate_100']}%→{latest['rate_100']}%, {h['date']}→{latest['date']})")
                    triggered = True
                break
    
    if triggered:
        alert = {
            'triggered': True,
            'reasons': reasons,
            'date': entry['date'],
            'time': entry['time'],
            'rate_100': latest['rate_100'],
        }
        with open(ALERT_FILE, 'w', encoding='utf-8') as f:
            json.dump(alert, f, ensure_ascii=False)
        print(f"\n  ⚠️ 触发升级条件！{' / '.join(reasons)}")
    else:
        # 正常则清除旧警报
        if os.path.exists(ALERT_FILE):
            os.remove(ALERT_FILE)

# ============ 主流程 ============
if __name__ == '__main__':
    print(f"=== FC3D 杀2码 自动更新 ===")
    print(f"  时间(北京): {datetime.now(BJT).strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. 抓取数据(6层降级)
    print(f"\n[1/4] 6层降级抓取...")
    fetched = fetch_latest()
    if not fetched:
        print("  所有源失败, 仅生成预测不更新CSV")
        # 仍然生成预测
        print(f"\n[3/4] 生成预测...")
        generate_outputs()
        print(f"\n[4/4] 完成 ✓")
        sys.exit(0)
    
    # 提取数据
    src_name, draws = list(fetched.items())[0]
    print(f"  使用数据源: {src_name}, {len(draws)}条")
    
    # 2. 追加CSV
    print(f"\n[2/4] 更新CSV...")
    added = append_to_csv(draws)
    print(f"  新增{added}期")
    
    # 3. 生成预测(无论有无新数据都执行)
    print(f"\n[3/4] 生成预测...")
    generate_outputs()
    
    print(f"\n[4/4] 完成 ✓")
