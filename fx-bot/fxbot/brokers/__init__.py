"""ブローカーアダプタ。"""

from .base import Broker, BrokerError
from .paper import PaperBroker

__all__ = ["Broker", "BrokerError", "PaperBroker", "build_broker"]


def build_broker(name: str, params: dict | None = None) -> Broker:
    """設定ファイルの名前からブローカーを組み立てる。

    重い/任意依存のアダプタは、選ばれたときだけ import する。
    """
    params = dict(params or {})
    name = name.lower()

    if name == "paper":
        return PaperBroker(**params)
    if name == "oanda":
        from .oanda import OandaBroker, OandaConfig

        return OandaBroker(OandaConfig(**params))
    if name in ("sbi", "sbi_web"):
        from .sbi_web import SbiWebBroker, SbiWebConfig

        return SbiWebBroker(SbiWebConfig(**params))
    raise KeyError(f"未知のブローカー '{name}'。利用可能: paper, oanda, sbi_web")
