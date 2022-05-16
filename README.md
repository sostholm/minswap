# Translated to python from JS, source: https://github.com/minswap/blockfrost-adapter/blob/main/README.md?plain=1

Modified to work with Oura and mongoDB
- [x] Get current pair price
- [ ] Get historical pair price


# Minswap Blockfrost Adapter

## Features

- [x] Get current pair price
- [x] Get historical pair price
- [ ] Calculate trade price and price impact
- [ ] Create orders and submit to Blockfrost

## Install

- Pypi: `pip install minswap`

## Examples

### Example 1: Get current price of MIN/ADA pool

```python
from minswap import BlockfrostAdapter, NetworkId

adapter = BlockfrostAdapter(
  projectId="<your_project_id>",
  networkId=NetworkId.MAINNET,
)

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
        print(f'ADA/MIN pool ID: {minAdaPool.id}')
        break

```

### Example 2: Get historical prices of MIN/ADA pool

```python
from minswap import BlockfrostAdapter, NetworkId

adapter = BlockfrostAdapter(
  projectId="<your_project_id>",
  networkId=NetworkId.MAINNET,
)

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
    print(f'{historyPoint.time}: {price0} ADA/MIN, {price1} MIN/ADA`)

```