"""三相配电最优分配求解器（纯标准库实现，便于独立测试）。

问题：每台设备不可拆分，只能接入其允许集合中的一个相位；
所有设备均须接入且各相负载不超过对应容量。
目标：最小化「三相负载最大值与最小值之差」；
差值相同时，取按设备编号排序后的相位序列字典序最小的方案。

求解方式：按设备编号排序后做深度优先搜索，相位按 A/B/C 顺序展开，
因此完整方案按相位序列的字典序依次产生；仅在差值严格更小时更新最优解，
即可保证同差值下保留字典序最小方案。同时使用容量约束与下界剪枝加速。
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Iterable, Optional

PHASES: tuple[str, str, str] = ("A", "B", "C")


@dataclass(frozen=True)
class Device:
    """待分配设备。"""

    code: str  # 设备唯一编号
    power: int  # 正整数功率
    allowed: tuple[str, ...]  # 可接入相位集合（PHASES 的非空子集）


@dataclass(frozen=True)
class SolveResult:
    """求解结果。feasible 为 False 时其余字段为 None。"""

    feasible: bool
    assignment: Optional[dict[str, str]]  # 设备编号 -> 相位
    loads: Optional[dict[str, int]]  # 相位 -> 负载
    imbalance: Optional[int]  # 最大相负载 - 最小相负载


def solve(devices: Iterable[Device], capacities: dict[str, int]) -> SolveResult:
    """求解最优分配方案。

    :param devices: 设备集合（编号唯一、功率为正整数、允许相位非空）。
    :param capacities: 各相容量，形如 {"A": int, "B": int, "C": int}。
    :return: SolveResult；无可行分配时 feasible=False。
    """
    ordered = sorted(devices, key=lambda d: d.code)
    n = len(ordered)
    powers = [d.power for d in ordered]
    # 每个设备的可接入相位按 A/B/C 固定顺序排列，保证 DFS 按字典序枚举方案
    allowed = [tuple(p for p in PHASES if p in d.allowed) for d in ordered]
    caps = {p: capacities[p] for p in PHASES}

    # suffix_addable[i][p]：第 i..n-1 台设备中可接入相位 p 的功率和（剪枝用）
    suffix_addable = [{p: 0 for p in PHASES} for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        prev, cur = suffix_addable[i + 1], suffix_addable[i]
        for p in PHASES:
            cur[p] = prev[p] + (powers[i] if p in allowed[i] else 0)

    # suffix_total[i]：第 i..n-1 台设备的功率总和
    suffix_total = [0] * (n + 1)
    for i in range(n - 1, -1, -1):
        suffix_total[i] = suffix_total[i + 1] + powers[i]

    loads = {p: 0 for p in PHASES}
    current: list[Optional[str]] = [None] * n
    best_imbalance: Optional[int] = None
    best_assignment: Optional[list[str]] = None

    def dfs(i: int, used: int) -> None:
        nonlocal best_imbalance, best_assignment
        if best_imbalance == 0:
            return  # 已达成理论最优（差值为 0），无需继续搜索
        if i == n:
            values = loads.values()
            imbalance = max(values) - min(values)
            # 仅严格更优才更新：同差值时先枚举到的方案字典序更小
            if best_imbalance is None or imbalance < best_imbalance:
                best_imbalance = imbalance
                best_assignment = current.copy()
            return
        if best_imbalance is not None:
            # 下界剪枝：
            #   最终最大负载 >= max(当前最大负载, 总功率平均值上取整)
            #   最终最小负载 <= min(当前各相负载 + 该相剩余可接入功率)
            remaining = suffix_total[i]
            lb_max = max(max(loads.values()), ceil((used + remaining) / 3))
            ub_min = min(loads[p] + suffix_addable[i][p] for p in PHASES)
            if lb_max - ub_min >= best_imbalance:
                return
        for phase in allowed[i]:
            if loads[phase] + powers[i] <= caps[phase]:
                loads[phase] += powers[i]
                current[i] = phase
                dfs(i + 1, used + powers[i])
                loads[phase] -= powers[i]
                current[i] = None

    dfs(0, 0)

    if best_assignment is None:
        return SolveResult(feasible=False, assignment=None, loads=None, imbalance=None)

    final_loads = {p: 0 for p in PHASES}
    for idx, phase in enumerate(best_assignment):
        final_loads[phase] += powers[idx]
    assignment = {ordered[i].code: best_assignment[i] for i in range(n)}
    return SolveResult(
        feasible=True,
        assignment=assignment,
        loads=final_loads,
        imbalance=best_imbalance,
    )
