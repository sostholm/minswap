from dataclasses import dataclass
from datetime import datetime
from blockfrost import BlockFrostApi, ApiUrls
from typing import Tuple
from .types import TxIn
from .constants import POOL_ADDRESS, POOL_NFT_POLICY_ID
from .pool import (
  checkValidPoolOutput,
  isValidPoolOutput,
  PoolHistory,
  PoolState,
  InvalidPoolException,
  InvalidPoolOutput
)
from .types import NetworkId

@dataclass
class BlockfrostAdapterOptions:
  projectId: str
  networkId: NetworkId

@dataclass
class GetPoolsParams:
  page: int

@dataclass
class GetPoolByIdParams:
  id: str

@dataclass
class GetPoolPriceParams:
  pool: PoolState
  decimalsA: int
  decimalsB: int

@dataclass
class GetPoolHistoryParams:
  id: str

@dataclass
class GetPoolInTxParams:
  txHash: str


class BlockfrostAdapter:
    networkId: NetworkId
    api: None

    def __init__(
        self,
        projectId,
        networkId = NetworkId.MAINNET,
    ):  
        base_url = ApiUrls.mainnet.value if networkId == 1 else ApiUrls.testnet.value
        self.networkId = networkId
        self.api = BlockFrostApi(
            project_id=projectId,
            base_url=base_url,
        )

    # /**
    # *
    # * @returns The latest pools or empty array if current page is after last page
    # */
    def getPools(
        self,
        page,
        count = 100,
        order = "asc",
    ):
        utxos = self.api.address_utxos(
            address=POOL_ADDRESS[self.networkId],
            count=count,
            order=order,
            page=page,
        )
        valid_utxos = []
        for utxo in utxos:
            try:
                if isValidPoolOutput(
                    self.networkId,
                    POOL_ADDRESS[self.networkId],
                    utxo.amount,
                    utxo.data_hash
                ):
                    valid_utxos.append(utxo)

            except InvalidPoolOutput as e:
                print('Invalid pool output')

        pool_states = []
        for utxo in utxos:
            try:
                pool_state = PoolState(
                    txIn=TxIn(utxo.tx_hash, index=utxo.output_index),
                    value=utxo.amount,
                    datumHash=utxo.data_hash
                )
                pool_states.append(pool_state)
            except InvalidPoolException as e:
                print(e)
        
        return pool_states

    #/**
#    * Get a specific pool by its ID.
#    * @param {Object} params - The parameters.
#    * @param {string} params.pool - The pool ID. self is the asset name of a pool's NFT and LP tokens. It can also be acquired by calling pool.id.
#    * @returns {PoolState | null} - Returns the pool or null if not found.
#    */
    def getPoolById(
        self,
        id,
    ) -> PoolState: 
        nft = f'{POOL_NFT_POLICY_ID}{id}'
        nftTxs = self.api.asset_transactions(
            nft,
            count=1,
            page=1,
            order="desc"
        )

        if len(nftTxs) == 0:
            return None
        
        return self.getPoolInTx(txHash=nftTxs[0].tx_hash)

    def getPoolHistory(
        self,
        id,
        page = 1,
        count = 100,
        order = "desc",
    ) -> PoolHistory:
    
        nft = f'{POOL_NFT_POLICY_ID}{id}'
        nftTxs = self.api.asset_transactions(
            nft,
            count=count,
            page=page,
            order=order,
        )
        
        nftTxs = [PoolHistory(
            txHash=tx.tx_hash,
            txIndex=tx.tx_index,
            blockHeight=tx.block_height,
            time=datetime.utcfromtimestamp(int(tx.block_time)),
        ) for tx in nftTxs]

        return nftTxs
    #/**
    #* Get pool state in a transaction.
    #* @param {Object} params - The parameters.
    #* @param {string} params.txHash - The transaction hash containing pool output. One of the way to acquire is by calling getPoolHistory.
    #* @returns {PoolState} - Returns the pool state or null if the transaction doesn't contain pool.
    #*/
    def getPoolInTx(
        self,
        txHash,
    ) -> PoolState:
        poolTx = self.api.transaction_utxos(txHash)
        poolUtxo = next((o for o in poolTx.outputs if o.address == POOL_ADDRESS[self.networkId]), None)

        if not poolUtxo:
            return None
        checkValidPoolOutput(
            self.networkId,
            poolUtxo.address,
            poolUtxo.amount,
            poolUtxo.data_hash
        )
        return PoolState(
            txIn = TxIn(txHash, index=poolUtxo.output_index),
            value = poolUtxo.amount,
            datumHash = poolUtxo.data_hash
        )


    def getAssetDecimals(self, asset: str) -> int:
        if asset == "lovelace":
            return 6
        
        try:
            assetAInfo = self.api.asset(asset)
            return assetAInfo.metadata.decimals if assetAInfo.metadata and assetAInfo.metadata.decimals else 0
        except Exception as err:
        # if isinstance(err, BlockfrostServerError) and err.status_code == 404):
            return 0

    #/**
    #* Get pool price.
    #* @param {Object} params - The parameters to calculate pool price.
    #* @param {string} params.pool - The pool we want to get price.
    #* @param {string} [params.decimalsA] - The decimals of assetA in pool, if undefined then query from Blockfrost.
    #* @param {string} [params.decimalsB] - The decimals of assetB in pool, if undefined then query from Blockfrost.
    #* @returns {[string, string]} - Returns a pair of asset A/B price and B/A price, adjusted to decimals.
    #*/
    def getPoolPrice(
      self,
      pool,
      decimalsA=None,
      decimalsB=None,
    ) -> Tuple[int, int]:
      if decimalsA == None:
        decimalsA = self.getAssetDecimals(pool.assetA)
      
      if decimalsB == None:
        decimalsB = self.getAssetDecimals(pool.assetB)
      
      adjustedReserveA = int(pool.reserveA) / 10 ** decimalsA
      adjustedReserveB = int(pool.reserveB) / 10 ** decimalsB
      priceAB = adjustedReserveA / adjustedReserveB
      priceBA = adjustedReserveB / adjustedReserveA
      return [priceAB, priceBA]