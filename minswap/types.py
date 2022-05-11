from enum import Enum
from dataclasses import dataclass

class NetworkId:
    TESTNET = 0
    MAINNET = 1


@dataclass
class Value:
  unit: str
  quantity: str


@dataclass
class TxIn:
  txHash: str
  index: int