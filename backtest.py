"""
福彩3D 百十个位各杀两码 — 回测引擎 (双模型支持)
严格滚动窗口验证：第i期预测仅用第i-1期数据
"""

import csv
from collections import Counter
from algorithms import get_all_kills, resolve_collision, kill_h1, kill_h2, kill_t1, kill_t2, kill_o1, kill_o2

# ============ 模型配置 ============
MODEL_CONFIGS = {
    'V3': {
        'name': 'V3 激进冲刺型',
        'desc': 'T2+O2频率,span≥6,slide=30/50',
        'tag': '100期73%',
        'o2_span': 6, 'o2_slide': 50,
        't2_freq': True, 't2_slide': 30,
    },
    'V5': {
        'name': 'V5 长期稳定型',
        'desc': '仅O2频率,span≥5,slide=100',
        'tag': '1000期54%',
        'o2_span': 5, 'o2_slide': 100,
        't2_freq': False, 't2_slide': 0,
    },
}

CURRENT_MODEL = 'V3'  # 默认V3


def get_kills_enhanced(b, s, g, model='V3', freq_t=None, freq_o=None):
    """增强版杀码：根据模型配置决定频率切换策略"""
    kills = get_all_kills(b, s, g)
    cfg = MODEL_CONFIGS.get(model, MODEL_CONFIGS['V3'])
    span = max(b, s, g) - min(b, s, g)
    
    # 十位T2频率
    if cfg['t2_freq'] and span >= cfg.get('t2_span', 6) and freq_t is not None and len(freq_t) > 0:
        hot_t = freq_t.most_common(1)[0][0]
        kt1 = kills['tens'][0]
        kt2 = hot_t
        if kt1 == kt2:
            kt2 = resolve_collision(kt1, kt2, b, s, g)[1]
        kills['tens'] = [kt1, kt2]
    
    # 个位O2频率
    if span >= cfg['o2_span'] and freq_o is not None and len(freq_o) > 0:
        hot_o = freq_o.most_common(1)[0][0]
        ko1 = kills['ones'][0]
        ko2 = hot_o
        if ko1 == ko2:
            ko2 = resolve_collision(ko1, ko2, b, s, g)[1]
        kills['ones'] = [ko1, ko2]
    
    return kills

def get_freq_window(data, idx, slide):
    """精确匹配测试脚本的频率窗口 [idx-slide, idx)"""
    freq = Counter()
    start = max(0, idx - slide)
    for j in range(start, idx):
        freq[data[j]] += 1
    return freq


def load_data(csv_path):
    """读取CSV，返回 (issues, hundreds, tens, ones) 四列表"""
    issues, hundreds, tens, ones = [], [], [], []
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames or 'issue' not in reader.fieldnames:
                raise ValueError(f"CSV缺少必要列(issue/hundreds/tens/ones), 实际列: {reader.fieldnames}")
            for row in reader:
                try:
                    issues.append(row['issue'])
                    hundreds.append(int(row['hundreds']))
                    tens.append(int(row['tens']))
                    ones.append(int(row['ones']))
                except (KeyError, ValueError) as e:
                    continue  # 跳过损坏行
    except FileNotFoundError:
        raise FileNotFoundError(f"数据文件不存在: {csv_path}")
    except Exception as e:
        raise RuntimeError(f"数据加载失败: {e}")
    return issues, hundreds, tens, ones


def run_backtest(csv_path, n_periods=100, full=False, model='V3'):
    """
    滚动窗口回测
    Args:
        csv_path: CSV文件路径
        n_periods: 回测期数（full=True时忽略）
        full: True=全量回测，False=n_periods期回测
        model: 'V3' 或 'V5'
    """
    issues, hundreds, tens, ones = load_data(csv_path)
    N = len(issues)
    cfg = MODEL_CONFIGS.get(model, MODEL_CONFIGS['V3'])

    if full:
        start_idx = 1  # 从第2期开始（第1期需要第0期做输入，但第0期是第1期之前的数据）
        window_desc = f"全量{N-1}期"
    else:
        start_idx = max(1, N - n_periods)
        window_desc = f"最近{min(n_periods, N-start_idx)}期"

    results = []
    for i in range(start_idx, N):
        # 第i期预测：仅用第i-1期数据
        prev_b, prev_s, prev_g = hundreds[i - 1], tens[i - 1], ones[i - 1]
        actual_h, actual_t, actual_o = hundreds[i], tens[i], ones[i]

        # 计算频率窗口(根据模型配置)
        freq_t = get_freq_window(tens, i - 1, cfg['t2_slide']) if cfg['t2_freq'] else None
        freq_o = get_freq_window(ones, i - 1, cfg['o2_slide'])
        kills = get_kills_enhanced(prev_b, prev_s, prev_g, model, freq_t, freq_o)

        kill_h1, kill_h2 = kills['hundreds']
        kill_t1, kill_t2 = kills['tens']
        kill_o1, kill_o2 = kills['ones']

        h_hit = (kill_h1 != actual_h and kill_h2 != actual_h)
        t_hit = (kill_t1 != actual_t and kill_t2 != actual_t)
        o_hit = (kill_o1 != actual_o and kill_o2 != actual_o)
        all_hit = h_hit and t_hit and o_hit

        results.append({
            'issue': issues[i],
            'draw': [actual_h, actual_t, actual_o],
            'prev_draw': [prev_b, prev_s, prev_g],
            'kill_h': [kill_h1, kill_h2],
            'kill_t': [kill_t1, kill_t2],
            'kill_o': [kill_o1, kill_o2],
            'h_hit': h_hit,
            't_hit': t_hit,
            'o_hit': o_hit,
            'all_hit': all_hit,
        })

    # 统计汇总
    total = len(results)
    if total == 0:
        summary = {
            'hundreds_hit_rate': 0, 'tens_hit_rate': 0, 'ones_hit_rate': 0,
            'all_hit_rate': 0, 'total_periods': 0, 'h_hits': 0,
            't_hits': 0, 'o_hits': 0, 'all_hits': 0, 'window': window_desc
        }
    else:
        h_hits = sum(1 for r in results if r['h_hit'])
        t_hits = sum(1 for r in results if r['t_hit'])
        o_hits = sum(1 for r in results if r['o_hit'])
        all_hits = sum(1 for r in results if r['all_hit'])

        summary = {
            'hundreds_hit_rate': round(h_hits / total * 100, 2),
            'tens_hit_rate': round(t_hits / total * 100, 2),
            'ones_hit_rate': round(o_hits / total * 100, 2),
            'all_hit_rate': round(all_hits / total * 100, 2),
            'total_periods': total,
            'h_hits': h_hits,
            't_hits': t_hits,
            'o_hits': o_hits,
            'all_hits': all_hits,
            'window': window_desc,
        }

    # 翻转结果：最新在前
    results.reverse()

    return {'results': results, 'summary': summary}


def get_next_issue(latest_issue):
    """根据最新期号计算下期期号（处理跨年）"""
    year = int(latest_issue[:4])
    seq = int(latest_issue[4:])
    seq += 1
    # 福彩3D每年约358期
    if seq > 358:
        year += 1
        seq = 1
    return f"{year}{seq:03d}"


def predict_next(csv_path, model='V3'):
    """预测下期杀码"""
    issues, hundreds, tens, ones = load_data(csv_path)
    N = len(issues)
    
    if N == 0:
        raise ValueError("数据集为空，无法预测")
    
    cfg = MODEL_CONFIGS.get(model, MODEL_CONFIGS['V3'])

    latest_issue = issues[-1]
    latest_b, latest_s, latest_g = hundreds[-1], tens[-1], ones[-1]
    next_issue = get_next_issue(latest_issue)
    
    freq_t = get_freq_window(tens, N, cfg['t2_slide']) if cfg['t2_freq'] else None
    freq_o = get_freq_window(ones, N, cfg['o2_slide'])
    kills = get_kills_enhanced(latest_b, latest_s, latest_g, model, freq_t, freq_o)

    return {
        'next_issue': next_issue,
        'last_issue': latest_issue,
        'last_draw': {'hundreds': latest_b, 'tens': latest_s, 'ones': latest_g},
        'predictions': kills,
    }


if __name__ == '__main__':
    csv_path = 'data/fc3d-history.csv'

    # 100期回测
    bt = run_backtest(csv_path, n_periods=100)
    s = bt['summary']
    print(f"=== 100期回测 ===")
    print(f"总期数: {s['total_periods']}")
    print(f"百位命中率: {s['hundreds_hit_rate']}% ({s['h_hits']}/{s['total_periods']})")
    print(f"十位命中率: {s['tens_hit_rate']}% ({s['t_hits']}/{s['total_periods']})")
    print(f"个位命中率: {s['ones_hit_rate']}% ({s['o_hits']}/{s['total_periods']})")
    print(f"★★★ 全命中率: {s['all_hit_rate']}% ({s['all_hits']}/{s['total_periods']}) ★★★")

    # 全量回测
    bt_full = run_backtest(csv_path, full=True)
    sf = bt_full['summary']
    print(f"\n=== 全量回测 ===")
    print(f"总期数: {sf['total_periods']}")
    print(f"百位命中率: {sf['hundreds_hit_rate']}%")
    print(f"十位命中率: {sf['tens_hit_rate']}%")
    print(f"个位命中率: {sf['ones_hit_rate']}%")
    print(f"★★★ 全命中率: {sf['all_hit_rate']}% ★★★")
    print(f"\n(基线: 单位置80%, 全命中51.2%)")

    # 下期预测
    pred = predict_next(csv_path)
    print(f"\n=== 下期预测 ===")
    print(f"预测期号: {pred['next_issue']}")
    print(f"上期({pred['last_issue']}): {pred['last_draw']}")
    print(f"百位杀码: {pred['predictions']['hundreds']}")
    print(f"十位杀码: {pred['predictions']['tens']}")
    print(f"个位杀码: {pred['predictions']['ones']}")
