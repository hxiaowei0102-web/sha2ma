"""
福彩3D 百十个位各杀两码 — 6个独立高强度算法
每个算法12-18条件分支，覆盖不同特征维度
输入：上期 b, s, g ∈ [0,9]
输出：杀码 ∈ [0,9]
"""

# ============================================================
# 碰撞避免：确保同一位置两个杀码不重复
# ============================================================
def resolve_collision(kill_a, kill_b_raw, b, s, g):
    """如果两个杀码相同，用fallback队列替换kill_b"""
    if kill_a != kill_b_raw:
        return kill_a, kill_b_raw

    fallbacks = [
        (b + s + g + 5) % 10,
        (b * s + g) % 10,
        (b + s * g) % 10,
        (b * g + s) % 10,
        (s * g + b + 3) % 10,
        (kill_a + 5) % 10,
    ]
    for fb in fallbacks:
        if fb != kill_a:
            return kill_a, fb
    # 极端情况：所有fallback都撞了（几乎不可能）
    return kill_a, (kill_a + 7) % 10


def get_all_kills(b, s, g):
    """计算所有6个杀码，带碰撞处理"""
    k_h1 = kill_h1(b, s, g)
    k_h2_raw = kill_h2(b, s, g)
    k_h1, k_h2 = resolve_collision(k_h1, k_h2_raw, b, s, g)

    k_t1 = kill_t1(b, s, g)
    k_t2_raw = kill_t2(b, s, g)
    k_t1, k_t2 = resolve_collision(k_t1, k_t2_raw, b, s, g)

    k_o1 = kill_o1(b, s, g)
    k_o2_raw = kill_o2(b, s, g)
    k_o1, k_o2 = resolve_collision(k_o1, k_o2_raw, b, s, g)

    return {
        'hundreds': [k_h1, k_h2],
        'tens': [k_t1, k_t2],
        'ones': [k_o1, k_o2],
    }


# ============================================================
# H1: 百位杀码1 — 奇偶空间法
# ============================================================
def kill_h1(b, s, g):
    """奇偶模式(8种) × 跨度分级(3档)"""
    odd_b = b % 2
    odd_s = s % 2
    odd_g = g % 2
    span = max(b, s, g) - min(b, s, g)
    ssum = b + s + g

    if odd_b == 0 and odd_s == 0 and odd_g == 0:  # 全偶
        if span >= 6:
            return (ssum + 7) % 10
        elif span >= 4:
            return (b * s + g) % 10
        else:
            return (ssum + 3) % 10

    if odd_b == 0 and odd_s == 0 and odd_g == 1:  # 偶偶奇
        if span >= 7:
            return (b * b + s + g) % 10
        elif span >= 4:
            return (ssum + 5) % 10
        else:
            return (b + s + g * g) % 10

    if odd_b == 0 and odd_s == 1 and odd_g == 0:  # 偶奇偶
        if b > g:
            return (b + s * s + g) % 10
        elif b < g:
            return (b + s * s + g * g) % 10
        else:
            return (ssum + 2) % 10

    if odd_b == 0 and odd_s == 1 and odd_g == 1:  # 偶奇奇
        if span >= 5:
            return (b + s * s + g * g + 1) % 10
        elif b == g:
            return (ssum + 6) % 10
        else:
            return (b + s * s + g) % 10

    if odd_b == 1 and odd_s == 0 and odd_g == 0:  # 奇偶偶
        if span >= 5:
            return (b * b + s + g + 2) % 10
        elif b == s:
            return (ssum + 4) % 10
        else:
            return (b * b + s + g) % 10

    if odd_b == 1 and odd_s == 0 and odd_g == 1:  # 奇偶奇
        if b > s:
            return (b * b + s + g * g) % 10
        elif b < s:
            return (ssum + 8) % 10
        else:
            return (ssum + 1) % 10

    if odd_b == 1 and odd_s == 1 and odd_g == 0:  # 奇奇偶
        if span <= 3:
            return (b * b + s * s + g + 1) % 10
        elif b > g:
            return (b * b + s * s + g) % 10
        else:
            return (ssum + 6) % 10

    # 全奇 (1,1,1)
    if span >= 6:
        return (ssum + 9) % 10
    elif span >= 3:
        return (ssum + 4) % 10
    else:
        return (ssum + 2) % 10


# ============================================================
# H2: 百位杀码2 — 大小振幅法
# ============================================================
def kill_h2(b, s, g):
    """差值绝对值和法 — 穷举4190公式池发现，V4"""
    return (abs(b - g) + abs(s - g) + 6) % 10


# ============================================================
# T1: 十位杀码1 — 和值跨度增强法 (继承V8a)
# ============================================================
def kill_t1(b, s, g):
    """继承V8a核心结构，扩展子分支"""
    span = max(b, s, g) - min(b, s, g)
    ssum = b + s + g

    # 大跨度分支
    if span >= 7:
        if b >= s and b >= g:
            if ((b + s) * g) % 10 == 0:
                return (ssum + 3) % 10
            return ((b + s) * g) % 10
        elif s > b and s >= g:
            if (b * b + g * g) % 10 == 0:
                return (ssum + 5) % 10
            return (b * b + g * g) % 10
        else:  # g 最大
            if (s * g + b) % 10 == 0:
                return (ssum + 7) % 10
            return (s * g + b) % 10

    # 中跨度分支
    if 4 <= span <= 6:
        if b > s and s > g:
            return (b * b + s + g) % 10
        elif b < s and s < g:
            return (b + s * s + g) % 10
        elif b > g:
            return (b + s * s + g * g) % 10
        else:
            return (b * b + s + g * g) % 10

    # 小跨度分支
    if span <= 2:
        if b == s == g:
            return (ssum + 9) % 10
        elif b == s:
            return (b * s + g + 3) % 10
        elif b == g:
            return (ssum + 2) % 10
        elif s == g:
            return (ssum + 3) % 10
        elif b == 0 or s == 0 or g == 0:
            return (ssum + 5) % 10
        else:
            return (ssum + 1) % 10

    # 默认：和值奇偶（V8a继承，span 3）
    if ssum % 2 == 1:
        if (b * b + s * s) % 10 == 0:
            return (ssum + 2) % 10
        return (b * b + s * s + g) % 10
    return (g * g + b) % 10


# ============================================================
# T2: 十位杀码2 — 平衡法
# ============================================================
def kill_t2(b, s, g):
    """十位减中值法 — 穷举4190公式池发现，V4"""
    return (s - sorted([b, s, g])[1] + 5) % 10


# ============================================================
# O1: 个位杀码1 — 形态学全面检测法
# ============================================================
def kill_o1(b, s, g):
    """特殊形态 × 跨度 × 和值极值"""
    span = max(b, s, g) - min(b, s, g)
    ssum = b + s + g
    has_pair = (b == s) or (b == g) or (s == g)
    has_zero = (b == 0) or (s == 0) or (g == 0)

    # 最特殊形态
    if b == s == g:
        return (b + 5) % 10
    if has_pair and has_zero:
        return (ssum + 8) % 10

    # 有对子不含零
    if has_pair and not has_zero:
        if b == s:
            if span >= 6:
                return (b * s + g + 5) % 10
            return (b * s + g + 2) % 10
        elif b == g:
            if span >= 6:
                return (ssum + 7) % 10
            return (ssum + 4) % 10
        else:  # s == g
            if span >= 6:
                return (ssum + 9) % 10
            return (ssum + 1) % 10

    # 含零无对子
    if has_zero and not has_pair:
        if b == 0:
            if s > g:
                return (s * g + 1) % 10
            return (s + g + 2) % 10
        elif s == 0:
            if b > g:
                return (b * g + 1) % 10
            return (b + g + 2) % 10
        else:  # g == 0
            if b > s:
                return (b * s + 1) % 10
            return (b + s + 2) % 10

    # 跨度特殊值
    if span == 5:
        return (b * b + s * s + g) % 10
    if span == 6:
        return (b * s + s * g + g * b) % 10
    if span == 4:
        return (b * b + s * s + g * g) % 10
    if span == 3:
        return (ssum + 4) % 10

    # 和值极值
    if ssum >= 18:
        return (b * s * g) % 10
    if ssum <= 6:
        return (ssum + 2) % 10

    # 默认三分支（按sum%3）
    if ssum % 3 == 0:
        return (ssum + span + 3) % 10
    elif ssum % 3 == 1:
        return (ssum + span + 1) % 10
    else:
        return (ssum + span + 5) % 10


# ============================================================
# O2: 个位杀码2 — 对子感知增强法
# ============================================================
def kill_o2(b, s, g):
    """线性加权法 — 穷举4190公式池发现，V4"""
    return (3 * b + s + g + 3) % 10


# ============================================================
# 单元测试入口
# ============================================================
if __name__ == '__main__':
    # 快速测试：取几个典型输入
    tests = [
        (0, 7, 3),   # 全小、无对子
        (2, 3, 7),   # 递增
        (5, 5, 5),   # 豹子
        (1, 9, 8),   # 大跨度、两大一小
        (4, 4, 0),   # 有对子含零
        (9, 1, 2),   # 大梯度、一大两小
        (3, 7, 6),   # 中跨度
        (0, 0, 9),   # 有对子
        (5, 3, 1),   # 递减
        (8, 5, 2),   # 跨度6
    ]
    for b, s, g in tests:
        r = get_all_kills(b, s, g)
        print(f"({b},{s},{g}) → H:{r['hundreds']} T:{r['tens']} O:{r['ones']}")
