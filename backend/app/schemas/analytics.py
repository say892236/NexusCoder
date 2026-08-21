"""统计分析 API 使用的 schema。"""

from datetime import date

from pydantic import BaseModel, Field


class AnalyticsCardResponse(BaseModel):
    """统计页单个 KPI 卡片数据。"""

    key: str = Field(..., description="Stable key identifier")
    label: str = Field(..., description="Card title")
    value: float = Field(..., description="Numeric value")
    display_value: str = Field(..., description="Pre-formatted display text")
    description: str = Field(..., description="What this metric means")


class SeverityDailyPoint(BaseModel):
    """按严重级别拆分的每日发现数。"""

    date: date
    INFO: int
    WARNING: int
    ERROR: int
    CRITICAL: int
    total: int


class CategoryDailyPoint(BaseModel):
    """按类别拆分的每日发现数。"""

    date: date
    BUG: int
    SECURITY: int
    PERFORMANCE: int
    STYLE: int
    MAINTAINABILITY: int
    DOCUMENTATION: int
    TESTING: int
    total: int


class AnalyticsOverviewResponse(BaseModel):
    """Statistics 标签页的统计载荷。"""

    repository: str
    window_days: int
    cards: list[AnalyticsCardResponse]
    severity_chart: list[SeverityDailyPoint]
    category_chart: list[CategoryDailyPoint]


class DashboardAnalyticsResponse(BaseModel):
    """Dashboard 卡片使用的统计载荷。"""

    repository: str
    window_days: int
    cards: list[AnalyticsCardResponse]


class SidebarAnalyticsResponse(BaseModel):
    """侧边栏卡片使用的统计载荷。"""

    repository: str
    window_days: int
    cards: list[AnalyticsCardResponse]
