"""业务逻辑层：路由只做参数校验，具体数据获取和加工写在这里。"""

from app.services import lottery_service

__all__ = ["lottery_service"]
