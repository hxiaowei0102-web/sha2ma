"""
云端全自动更新脚本 — 多数据源 + CSV追加 + 预测生成
GitHub Actions 定时运行
"""
import csv, json, os, sys
from datetime import datetime, timezone, timedelta
from collections import Counter
from urllib.request import urlopen, Request
from urllib.error import URLError
import time

# ============ 配置 ============
CSV_PATH = 'data/fc3d-history.csv'
PREDICT_OUT = 'static/predict.json'
BACKTEST_OUT = 'static/backtest.json'

# 北京时间
BJT = timezone(timedelta(hours=8))

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
    """追加新数据到CSV（去重）"""
    existing = load_existing_issues()
    added = 0
    with open(CSV_PATH, 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        for issue, b, s, g in new_draws:
            if issue not in existing:
                writer.writerow([issue, b, s, g])
                added += 1
                print(f"  新增: {issue} = {b}{s}{g}")
    return added

# ============ 算法(精简自backtest.py) ============
def resolve(k1, k2, pb, ps, pg):
    if k1 != k2: return k2
    for fb in [(pb+ps+pg+5)%10, (pb*ps+pg)%10, (pb+ps*pg)%10]:
        if fb != k1: return fb
    return (k1+5)%10

# V3配置: T2+O2频率切换
def get_kill_v3(pb, ps, pg, freq_t, freq_o):
    from algorithms import kill_h1, kill_h2, kill_t1, kill_o1
    
    def t2_cur(b,s,g):
        d_bs=abs(b-s); d_sg=abs(s-g)
        if d_bs<d_sg: return (b*s+g*g+1)%10
        if d_bs>d_sg: return (s*g+b*b+1)%10
        return (b+s+g+6)%10
    
    def o2_cur(b,s,g):
        p=(b==g or s==g); sp=max(b,s,g)-min(b,s,g)
        if b==s==g: return (b+5)%10
        if p:
            if sp>=7: return (b*s+g+7)%10
            if sp>=5: return (b*s+g+5)%10
            return (b+s+g+3)%10
        return (b*g+s*s+2)%10
    
    sp = max(pb,ps,pg)-min(pb,ps,pg)
    kh1=kill_h1(pb,ps,pg); kh2=resolve(kh1,kill_h2(pb,ps,pg),pb,ps,pg)
    
    kt1=kill_t1(pb,ps,pg)
    kt2r=get_freq_hot(freq_t) if sp>=6 and freq_t and len(freq_t)>0 else t2_cur(pb,ps,pg)
    kt2=resolve(kt1,kt2r,pb,ps,pg)
    
    ko1=kill_o1(pb,ps,pg)
    ko2r=get_freq_hot(freq_o) if sp>=5 and freq_o and len(freq_o)>0 else o2_cur(pb,ps,pg)
    ko2=resolve(ko1,ko2r,pb,ps,pg)
    
    return [kh1,kh2], [kt1,kt2], [ko1,ko2]

def get_freq_hot(freq):
    return freq.most_common(1)[0][0] if freq else 0

def get_freq_window(data, idx, slide):
    freq = Counter()
    for j in range(max(0, idx-slide), idx):
        freq[data[j]] += 1
    return freq

# ============ 回测+预测 ============
def generate_outputs():
    """生成predict.json和backtest.json"""
    issues, h, t, o = [], [], [], []
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            issues.append(row['issue'])
            h.append(int(row['hundreds']))
            t.append(int(row['tens']))
            o.append(int(row['ones']))
    
    N = len(issues)
    if N < 2:
        print("  数据不足，跳过预测")
        return
    
    # 最新一期的预测
    latest_b, latest_s, latest_g = h[-1], t[-1], o[-1]
    freq_t = get_freq_window(t, N, 30)
    freq_o = get_freq_window(o, N, 50)
    kills_h, kills_t, kills_o = get_kill_v3(latest_b, latest_s, latest_g, freq_t, freq_o)
    
    next_issue = str(int(issues[-1]) + 1)
    if next_issue[4:] == '359':  # 跨年
        next_issue = str(int(issues[-1][:4]) + 1) + '001'
    
    predict = {
        'next_issue': next_issue,
        'last_issue': issues[-1],
        'last_draw': f"{latest_b}{latest_s}{latest_g}",
        'kills': {'h': kills_h, 't': kills_t, 'o': kills_o},
        'updated': datetime.now(BJT).strftime('%Y-%m-%d %H:%M'),
    }
    
    # 100期回测
    backtest = []
    nh = nt = no = na = 0
    for i in range(max(1, N-100), N):
        pb, ps, pg = h[i-1], t[i-1], o[i-1]
        ft = get_freq_window(t, i-1, 30)
        fo = get_freq_window(o, i-1, 50)
        kh, kt, ko = get_kill_v3(pb, ps, pg, ft, fo)
        
        h_hit = (kh[0]!=h[i] and kh[1]!=h[i])
        t_hit = (kt[0]!=t[i] and kt[1]!=t[i])
        o_hit = (ko[0]!=o[i] and ko[1]!=o[i])
        all_hit = h_hit and t_hit and o_hit
        
        if h_hit: nh += 1
        if t_hit: nt += 1
        if o_hit: no += 1
        if all_hit: na += 1
        
        backtest.append({
            'issue': issues[i],
            'draw': f"{h[i]}{t[i]}{o[i]}",
            'kh': kh, 'kt': kt, 'ko': ko,
            'hh': h_hit, 'th': t_hit, 'oh': o_hit, 'ah': all_hit,
        })
    
    backtest.reverse()
    total = len(backtest)
    
    backtest_data = {
        'summary': {
            'h': round(nh/total*100, 1) if total else 0,
            't': round(nt/total*100, 1) if total else 0,
            'o': round(no/total*100, 1) if total else 0,
            'all': round(na/total*100, 1) if total else 0,
            'total': total,
        },
        'data': backtest,
    }
    
    with open(PREDICT_OUT, 'w', encoding='utf-8') as f:
        json.dump(predict, f, ensure_ascii=False)
    with open(BACKTEST_OUT, 'w', encoding='utf-8') as f:
        json.dump(backtest_data, f, ensure_ascii=False)
    
    print(f"  预测: {next_issue} → 百{kills_h} 十{kills_t} 个{kills_o}")
    print(f"  回测: {total}期 全中{backtest_data['summary']['all']}%")

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
        return
    
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
