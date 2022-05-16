from dataclasses import dataclass
from datetime import datetime
from cardano_helpers import Transaction, UTXO, Asset, create_transaction_object, resolve_asset, LOVELACE
from typing import Tuple, List
from .types import TxIn
from .constants import POOL_ADDRESS, POOL_NFT_POLICY_ID, FACTORY_POLICY_ID, LP_POLICY_ID
from .pool import (
  checkValidPoolOutput,
  isValidPoolOutput,
  PoolHistory,
  PoolState,
  InvalidPoolException,
  InvalidPoolOutput
)
from .types import NetworkId, Value
from pymongo.cursor import Cursor
from blockfrost import BlockFrostApi, ApiUrls
import pandas as pd

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


@dataclass
class AssetHelper:
    unit: str
    quantity: int
    output_index: int
    datumHash: str

class OuraAdapter:
    networkId: NetworkId
    all_transactions_collection: Cursor
    assets_collection: Cursor
    api: BlockFrostApi
    min_block: int
    get_pools_index: int = 0
    min_lovelace_locked: int
    pools: List[PoolState] = []

    def __init__(
        self,
        all_transactions_collection: Cursor,
        assets_collection: Cursor,
        projectId: str,
    ):  
        self.all_transactions_collection = all_transactions_collection
        self.assets_collection = assets_collection
        self.networkId = NetworkId.MAINNET
        base_url = ApiUrls.mainnet.value if self.networkId == 1 else ApiUrls.testnet.value
        self.api = BlockFrostApi(
            project_id=projectId,
            base_url=base_url,
        )


    # /**
    # *
    # * @returns The latest pools or empty array if current page is after last page
    # */
    def getPools(self):
        # self.min_block = min_block
        # self.min_lovelace_locked = min_ada_locked * LOVELACE
        new_pool_states = []

        all_transactions = list(self.all_transactions_collection.find(
                {"transaction.outputs.address": POOL_ADDRESS[self.networkId], "context.block_number": {"$gte": self.get_pools_index}}, 
                {"transaction.outputs": True, "transaction.hash": True, "context.block_number": True, "context.tx_idx": True}
        ))
        flattened = []
            
        for transaction in all_transactions:
            for index, utxo in enumerate(transaction['transaction']['outputs']):
                if utxo['address'] == POOL_ADDRESS[self.networkId]:
                    
                    pool_utxos = []

                    for asset in utxo['assets']:
                        asset['unit'] = f'{asset["policy"]}{asset["asset"]}'
                        relevant = False
                        
                        if(
                            not asset['unit'].startswith(FACTORY_POLICY_ID) and
                            not asset['unit'].startswith(POOL_NFT_POLICY_ID) and
                            not asset['unit'].startswith(LP_POLICY_ID)
                        ):
                            relevant = True
                        
                        pool_utxos.append({
                            "block_number": transaction['context']['block_number'], 
                            "output_index": index, 
                            **utxo, 
                            "unit": asset['unit'],
                            "quantity": str(asset["amount"]),
                            "relevant": relevant
                        })
                    pool_utxos.append({
                        "output_index": index, 
                        **utxo, 
                        "unit": 'lovelace',
                        "quantity": str(utxo["amount"]),
                        "relevant": True
                    })
                    

                    relevant = [o for o in pool_utxos if o['relevant'] == True]
                    
                    assetA = None
                    assetB = None

                    if len(relevant) == 3:
                        relevant = [o for o in relevant if o['unit'] != 'lovelace']
                        assetA = relevant[0]
                        assetB = relevant[1]
                    
                    elif len(relevant) == 2:
                        assetA = relevant[1]
                        assetB = relevant[0]
                    
                    else:
                        continue
                    
                    flattened.append(
                        dict(
                            tx_in = transaction['transaction']['hash'],
                            tx_idx = transaction['context']['tx_idx'],
                            value = pool_utxos,
                            combined = assetA['unit'] + assetB['unit'],
                            assetA = assetA,
                            assetB = assetB,
                            block_number = transaction['context']['block_number']
                        )
                    )


        
        df = pd.DataFrame(flattened)
        unique_pools = df['combined'].unique()

        latest_state_pools = []
        for combined in unique_pools:
            max_index = df[df['combined'] == combined].block_number.idxmax()
            latest_state_pools.append(df.iloc[max_index].to_dict())

        for pool in latest_state_pools:

            value = []

            for utxo in pool['value']:
                value.append(AssetHelper(
                    unit=utxo['unit'], 
                    quantity=str(utxo['quantity']), 
                    output_index=utxo['output_index'],
                    datumHash="not_available_in_oura"
                ))

            try:
                if isValidPoolOutput(
                    self.networkId,
                    POOL_ADDRESS[self.networkId],
                    value,
                    datumHash="not_available_in_oura"
                ):
                    try:
                        pool_state = PoolState(
                            txIn=TxIn(pool, index=pool['tx_idx']),
                            value=value,
                            block_number=pool['block_number']
                        )
                        new_pool_states.append(pool_state)
                    except InvalidPoolException as e:
                        print(e)

            except InvalidPoolOutput as e:
                print('Invalid pool output')
        
        #Update min block so we don't have to recalculate the latest state from whole history
        self.get_pools_index = max([pool.block_number for pool in new_pool_states])
        
        #Add new pools
        old_pool_ids = [p.assetA + p.assetB for p in self.pools]
        for pool in new_pool_states:
            if pool.assetA + pool.assetB not in old_pool_ids:
                self.pools.append(pool)

        # Update pools
        for pool in new_pool_states:
            for old_pool in self.pools:
                if (
                    new_pool_states[index].assetA == pool_state.assetA 
                    and new_pool_states[index].assetB == pool_state.assetB
                    and new_pool_states[index].block_number < pool_state.block_number
                    # and new_pool_states[index].reserveA > self.min_lovelace_locked
                ):
                    old_pool[index] = pool
                    break
            

        return self.pools

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
            assetAInfo = resolve_asset(asset, self.assets_collection, self.api)
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