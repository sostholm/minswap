from .constants import (FACTORY_ASSET_NAME,
  FACTORY_POLICY_ID,
  LP_POLICY_ID,
  POOL_ADDRESS,
  POOL_NFT_POLICY_ID
)
from .types import NetworkId, TxIn, Value
from typing import Tuple
from dataclasses import dataclass
from datetime import datetime

# ADA goes first
# If non-ADA, then sort lexicographically
def normalizeAssets(a: str, b: str) -> Tuple[str, str]:
  if a == "lovelace":
    return [a, b]
  
  if b == "lovelace":
    return [b, a]

  if a < b:
    return [a, b]
  else:
    return [b, a]

class InvalidPoolException(Exception):
    pass

class InvalidPoolOutput(Exception):
    pass

class PoolNoneNFTException(Exception):
    pass
#/**
# * Represents state of a pool UTxO. The state could be latest state or a historical state.
# */
class PoolState:
  #/** The transaction hash and output index of the pool UTxO */
    txIn: TxIn
    value: Value
    datumHash: str
    assetA: str
    assetB: str
    block_number: int

    def __init__(self, txIn: TxIn, value: Value, datumHash: str=None, block_number: int=None):
        self.txIn = txIn
        self.value = value
        self.datumHash = datumHash
        self.block_number = block_number
        

        #// validate and memoize assetA and assetB
        relevantAssets = [val for val in value if
            not val.unit.startswith(FACTORY_POLICY_ID) and
            not val.unit.startswith(POOL_NFT_POLICY_ID) and
            not val.unit.startswith(LP_POLICY_ID)
        ]

        if len(relevantAssets) == 2:
            # ADA/A pool
            self.assetA = "lovelace"
            nonADAAssets = [val for val in relevantAssets if val.unit != "lovelace"]
            
            assert len(nonADAAssets) == 1, "pool must have 1 non-ADA asset"
            self.assetB = nonADAAssets[0].unit
        
        elif len(relevantAssets) == 3:
            # A/B pool
            nonADAAssets = [val for val in relevantAssets if val.unit != "lovelace"]

            assert len(nonADAAssets) == 2, "pool must have 2 non-ADA asset"
            self.assetA, self.assetB = normalizeAssets(
                nonADAAssets[0].unit,
                nonADAAssets[1].unit
            )
        
        else:
            raise InvalidPoolException(
                "pool must have 2 or 3 assets except factory, NFT and LP tokens"
            )
    
    @property
    def nft(self) -> str:
        nft = next((val for val in self.value if val.unit.startswith(POOL_NFT_POLICY_ID)), None)
        if not nft:
            PoolNoneNFTException("pool doesn't have NFT")
        return nft.unit

    @property
    def id(self) -> str:
        #a pool's ID is the NFT's asset name
        return self.nft[:len(POOL_NFT_POLICY_ID)]

    @property
    def assetLP(self) -> str: 
        return f'{LP_POLICY_ID}{self.id}'

    @property
    def reserveA(self) -> int:
        value = next((val for val in self.value if val.unit == self.assetA), None)
        return int(value.quantity) if value else 0

    @property
    def reserveB(self) -> int:
        value = next((val for val in self.value if val.unit == self.assetB), None)
        return int(value.quantity) if value else 0

#/**
# * Represents a historical point of a pool.
# */


@dataclass
class PoolHistory:
  txHash: str
  #/** Transaction index within the block */
  txIndex: int
  blockHeight: int
  time: datetime


def checkValidPoolOutput(
  networkId: NetworkId,
  address: str,
  value: Value,
  datumHash: str = None
):
  assert address == POOL_ADDRESS[networkId], f'expect pool address of {POOL_ADDRESS[networkId]}, got ${address}'
  # must have 1 factory token
  found_value = next((val for val in value if val.unit == f'{FACTORY_POLICY_ID}{FACTORY_ASSET_NAME}'), None)
  if found_value and found_value.quantity != "1":
    raise Exception('expect pool to have 1 factory token')
  
  if not datumHash: 
      raise InvalidPoolOutput(f'expect pool to have datum hash, got {datumHash}')


def isValidPoolOutput(
  networkId: NetworkId,
  address: str,
  value: Value,
  datumHash: str = None
) -> bool:
    try:
        checkValidPoolOutput(networkId, address, value, datumHash)
        return True
    except Exception as err:
        return False