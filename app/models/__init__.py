"""모든 모델을 import해 Base.metadata에 등록한다."""

from app.models import unit  # noqa: F401
from app.models import category  # noqa: F401
from app.models import market  # noqa: F401
from app.models import user  # noqa: F401
from app.models import store  # noqa: F401
from app.models import sale  # noqa: F401
from app.models import order  # noqa: F401
from app.models import notification  # noqa: F401
from app.models import subscription  # noqa: F401
from app.models import notification_log  # noqa: F401
from app.models import favorite  # noqa: F401
