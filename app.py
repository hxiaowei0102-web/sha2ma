"""
福彩3D 百十个位各杀两码系统 — Flask 后端 (V3)
"""
import os
from flask import Flask, jsonify, send_from_directory, request
from backtest import load_data, run_backtest, predict_next, MODEL_CONFIG

app = Flask(__name__, static_folder='static', static_url_path='')

CSV_PATH = os.path.join(os.path.dirname(__file__), 'data', 'fc3d-history.csv')


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/api/config')
def api_config():
    """返回模型配置"""
    return jsonify({
        'model': 'V3',
        'config': MODEL_CONFIG,
    })


@app.route('/api/predict')
def api_predict():
    """下期预测"""
    try:
        pred = predict_next(CSV_PATH)
        return jsonify(pred)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/backtest')
def api_backtest():
    """回测（支持?window=N）"""
    try:
        window_str = request.args.get('window', '100')
        try:
            window = int(window_str)
            if window < 10 or window > 500:
                return jsonify({'error': 'window参数需在10-500之间'}), 400
        except ValueError:
            return jsonify({'error': 'window参数必须为整数'}), 400
        bt = run_backtest(CSV_PATH, n_periods=window)
        return jsonify(bt)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/fullstats')
def api_fullstats():
    """全量统计"""
    try:
        bt = run_backtest(CSV_PATH, full=True)
        return jsonify({
            'summary': bt['summary'],
            'total_periods': bt['summary']['total_periods'],
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("=" * 60)
    print("  福彩3D 百十个位各杀两码系统 (V3)")
    print("  启动中...")
    print("=" * 60)

    try:
        issues, h, t, o = load_data(CSV_PATH)
        print(f"  数据加载: {len(issues)} 期 ({issues[0]} ~ {issues[-1]})")
    except Exception as e:
        print(f"  [错误] 数据加载失败: {e}")
        import sys; sys.exit(1)

    bt100 = run_backtest(CSV_PATH, n_periods=100)
    s = bt100['summary']
    print(f"  100期: 百{s['hundreds_hit_rate']}% 十{s['tens_hit_rate']}% 个{s['ones_hit_rate']}% 全{s['all_hit_rate']}%")

    try:
        bt_all = run_backtest(CSV_PATH, full=True)
        sf = bt_all['summary']
        print(f"  全量: 百{sf['hundreds_hit_rate']}% 十{sf['tens_hit_rate']}% 个{sf['ones_hit_rate']}% 全{sf['all_hit_rate']}%")
    except Exception as e:
        print(f"  全量回测失败: {e}")

    print(f"\n  http://localhost:5000")
    print("=" * 60)

    app.run(host='0.0.0.0', port=5000, debug=False)
