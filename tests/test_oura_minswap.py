from minswap import __version__, OuraAdapter, NetworkId
import os
import random
from pymongo import MongoClient

def test_version():
    assert __version__ == '0.1.0'

username = os.environ['username']
password = os.environ['password']

client = MongoClient('mongodb://%s:%s@192.168.1.30' % (username, password))

cardano_trader = client.cardano_trader
all_transactions_collection = cardano_trader.all_transactions
assets_collection = cardano_trader.assets

def mustGetEnv(key: str) -> str:
  val = os.environ.get(key)
  if not val:
    raise Exception(f'{key} not found')
  
  return val

PROJECT_ID = os.environ['PROJECT_ID']
MIN = "29d222ce763455e3d7a09a665ce554f00ac89d2e99a1a83d267170c64d494e"
MIN_ADA_POOL_ID = "6aa2153e1ae896a95539c9d62f76cedcdabdcdf144e564b8955f609d660cf6a2"

adapter = OuraAdapter(
  all_transactions_collection=all_transactions_collection,
  assets_collection=assets_collection,
  projectId=PROJECT_ID
)

def test_getAssetDecimals():
    assert adapter.getAssetDecimals("lovelace") == 6
    assert adapter.getAssetDecimals(MIN) == 6

def test_getPoolPrice():
    pools = adapter.getPools()
    # check random 5 pools
    for i in range(5):
        idx = random.randint(0, len(pools))
        pool = pools[idx]
        priceAB, priceBA = adapter.getPoolPrice(pool)
        # product of 2 prices must be approximately equal to 1
        # abs(priceAB * priceBA - 1) <= epsilon
        assert priceAB * priceBA - 1 <= 1e-6


def test_readme_example_1():
  page = 1
  while True:
      pools = adapter.getPools(page=page)

      if len(pools) == 0:
          # last page
          break

      minAdaPool = next((pool for pool in pools if pool.assetA == "lovelace" and pool.assetB=="29d222ce763455e3d7a09a665ce554f00ac89d2e99a1a83d267170c64d494e"), None)

      if minAdaPool:
          min, ada = adapter.getPoolPrice(pool=minAdaPool)
          print(f'ADA/MIN price: {min}; MIN/ADA price: {ada}')
          # print(f'ADA/MIN pool ID: {minAdaPool.id}')
          break

def test_readme_example_2():
    MIN_ADA_POOL_ID = "6aa2153e1ae896a95539c9d62f76cedcdabdcdf144e564b8955f609d660cf6a2"

    history = adapter.getPoolHistory(id=MIN_ADA_POOL_ID)

    for historyPoint in history:
        pool = adapter.getPoolInTx(txHash=historyPoint.txHash)
        if not pool:
            raise Exception("pool not found")
        
        price0, price1 = adapter.getPoolPrice(
            pool,
            decimalsA=6,
            decimalsB=6,
        )
        print(f'{historyPoint.time}: {price0} ADA/MIN, {price1} MIN/ADA')

def test_getPoolById():
    pool = adapter.getPoolById(id=MIN_ADA_POOL_ID)
    assert pool
    assert pool.assetA == "lovelace"
    assert pool.assetB == MIN


def test_get_prices_of_last_5_states_of_min_ada_pool():
    history = adapter.getPoolHistory(id=MIN_ADA_POOL_ID)
    for h in history[:5]:
        pool = adapter.getPoolInTx(txHash=h.txHash)
        assert pool
        assert pool.txIn.txHash == h.txHash