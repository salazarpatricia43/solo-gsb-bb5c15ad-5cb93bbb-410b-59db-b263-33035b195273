"""FastAPI 应用入口：临时展位三相配电排布 API。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, status

from . import db
from .schemas import (
    AssignmentItem,
    CalculationDetail,
    CalculationRequest,
    CalculationResult,
    CalculationSummary,
    Loads,
)
from .solver import Device, solve

_MESSAGE_FEASIBLE = "计算成功：已找到三相负载最大值与最小值之差最小的分配方案"
_MESSAGE_INFEASIBLE = "无可行分配：不存在所有设备均接入且各相不超容量的方案"


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 应用启动时自动完成数据库初始化（建目录、建表）
    db.init_db()
    yield


app = FastAPI(
    title="临时展位三相配电排布 API",
    description=(
        "提交最多 12 台设备（唯一编号、正整数功率、非空可接入相位集合）"
        "及 A/B/C 各相容量，求解使三相负载最大值与最小值之差最小的分配方案；"
        "差值相同时取按设备编号排序后相位序列字典序最小的方案。"
        "每次计算的输入、分配结果与各相负载均持久化，可随时查询。"
    ),
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["meta"])
def health() -> dict:
    """健康检查。"""
    return {"status": "ok"}


@app.post(
    "/api/v1/calculations",
    response_model=CalculationResult,
    status_code=status.HTTP_201_CREATED,
    tags=["calculations"],
)
def create_calculation(payload: CalculationRequest) -> CalculationResult:
    """创建一次排布计算：求解最优分配并保存输入、分配与各相负载。

    无可行分配时同样保存记录，返回 ``feasible=false`` 及说明信息。
    """
    devices = [
        Device(code=d.id, power=d.power, allowed=tuple(d.allowed_phases))
        for d in payload.devices
    ]
    capacities = {
        "A": payload.capacities.A,
        "B": payload.capacities.B,
        "C": payload.capacities.C,
    }
    result = solve(devices, capacities)
    calculation_id = db.insert_calculation(payload, result)
    record = db.get_calculation(calculation_id)

    assignments = (
        [
            AssignmentItem(device_id=d["device_id"], phase=d["assigned_phase"])
            for d in record["devices"]
        ]
        if result.feasible
        else []
    )
    return CalculationResult(
        id=record["id"],
        created_at=record["created_at"],
        capacities=Loads(**record["capacities"]),
        feasible=result.feasible,
        imbalance=result.imbalance,
        loads=Loads(**record["loads"]) if result.feasible else None,
        message=_MESSAGE_FEASIBLE if result.feasible else _MESSAGE_INFEASIBLE,
        assignments=assignments,
    )


@app.get(
    "/api/v1/calculations",
    response_model=list[CalculationSummary],
    tags=["calculations"],
)
def list_calculations(
    limit: int = Query(default=100, ge=1, le=500, description="返回条数上限"),
    offset: int = Query(default=0, ge=0, description="偏移量"),
) -> list[CalculationSummary]:
    """查询历史计算记录摘要（按创建时间倒序）。"""
    return [CalculationSummary(**item) for item in db.list_calculations(limit, offset)]


@app.get(
    "/api/v1/calculations/{calculation_id}",
    response_model=CalculationDetail,
    tags=["calculations"],
)
def get_calculation(calculation_id: int) -> CalculationDetail:
    """查询单条计算记录详情：输入设备、分配结果与各相负载。"""
    record = db.get_calculation(calculation_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"计算记录不存在：id={calculation_id}",
        )
    assignments = (
        [
            AssignmentItem(device_id=d["device_id"], phase=d["assigned_phase"])
            for d in record["devices"]
        ]
        if record["feasible"]
        else []
    )
    return CalculationDetail(
        id=record["id"],
        created_at=record["created_at"],
        capacities=Loads(**record["capacities"]),
        feasible=record["feasible"],
        imbalance=record["imbalance"],
        loads=Loads(**record["loads"]) if record["feasible"] else None,
        message=_MESSAGE_FEASIBLE if record["feasible"] else _MESSAGE_INFEASIBLE,
        assignments=assignments,
        devices=record["devices"],
    )
