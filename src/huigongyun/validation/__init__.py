"""验证层脚手架。

本包包含用于项目级校验的实现与接口导出，例如 `DefaultProjectValidator`，
用于发现缺失字段、重复项、待确认标记与报价缺失等常见问题。

同时提供 ``RiskLevel``、``RiskClassifier`` 和 ``RiskDashboard`` 用于
在现有校验结果上叠加风险分级标签。
"""

from .default import DefaultProjectValidator
from .risk import RiskClassifier, RiskDashboard, RiskLevel

__all__ = ["DefaultProjectValidator", "RiskClassifier", "RiskDashboard", "RiskLevel"]
