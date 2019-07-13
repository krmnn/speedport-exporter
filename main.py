import asyncio

import aiohttp
from prometheus_async import aio

from settings import _speedport, _password
from speedport import SpeedportClient
from speedport import SpeedportDslCollector, SpeedportInterfaceCollector, SpeedportLteCollector, \
    SpeedportModuleCollector

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
        client = SpeedportClient(_speedport, _password, session)
        await client.login()

        login_task = asyncio.create_task(client.login_loop())

        dsl = SpeedportDslCollector(client)
        async_collectors.append(dsl)

        lte = SpeedportLteCollector(client)
        async_collectors.append(lte)

        interface = SpeedportInterfaceCollector(client)
        async_collectors.append(interface)

        module = SpeedportModuleCollector(client)
        async_collectors.append(module)

        await aio.web.start_http_server(port=9611)
        await login_task


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
