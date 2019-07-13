import asyncio
import logging

logging.basicConfig(format='%(asctime)s : %(levelname)8s : %(name)30s : %(funcName)-20s : %(lineno)4d : %(message)s')

import aiohttp
from prometheus_async import aio

from settings import _speedport, _password
from speedport import Client
from speedport import DslCollector, InterfaceCollector, LteCollector, ModuleCollector, BondingTunnelCollector

async_collectors = []
server_stats_save = aio.web.server_stats


async def server_stats(*args, **kwargs):
    wait = []
    for collector in async_collectors:
        wait.append(asyncio.create_task(collector.collect()))

    await asyncio.wait(wait)

    return await server_stats_save(*args, **kwargs)


aio.web.server_stats = server_stats


async def main():
    async with aiohttp.ClientSession() as session:
        client = Client(_speedport, _password, session)
        await client.login()

        login_task = asyncio.create_task(client.login_loop())

        dsl = DslCollector(client)
        async_collectors.append(dsl)

        lte = LteCollector(client)
        async_collectors.append(lte)

        interface = InterfaceCollector(client)
        async_collectors.append(interface)

        module = ModuleCollector(client)
        async_collectors.append(module)

        bonding_tunnel = BondingTunnelCollector(client)
        async_collectors.append(bonding_tunnel)

        await aio.web.start_http_server(port=9611)
        await login_task


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
