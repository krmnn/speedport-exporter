import asyncio
import hashlib
import logging
import random
import re
import time
from http.cookies import SimpleCookie

import aiohttp
import dirtyjson as json
from prometheus_async import aio
from prometheus_client import Summary, Counter

logging.basicConfig(level=logging.DEBUG)

_speedport = 'speedport.ip'
_password = 'KeAm9pcJ5XBb'


class SpeedportClient:
    # region metric definitions
    METRICS_NAMESPACE = 'speedport_client'
    LOGIN_TIME = Summary(
        namespace=METRICS_NAMESPACE,
        name='login_processing',
        unit='seconds',
        documentation='Time spent to login method'
    )
    LOGIN_EXCEPTIONS = Counter(
        namespace=METRICS_NAMESPACE,
        name='login_exceptions',
        documentation='Exceptions in the login method'
    )
    FETCH_TIME = Summary(
        namespace=METRICS_NAMESPACE,
        name='fetching_processing',
        unit='seconds',
        documentation='Time spent on fetch_data method',
        labelnames=['file']
    )
    FETCH_EXCEPTIONS = Counter(
        namespace=METRICS_NAMESPACE,
        name='fetching_exceptions',
        documentation='Exceptions in the fetch_data method',
        labelnames=['file']
    )
    HEARTBEAT_TIME = Summary(
        namespace=METRICS_NAMESPACE,
        name='heartbeat_processing',
        unit='seconds',
        documentation='Time spent on heartbeat method'
    )
    HEARTBEAT_EXCEPTIONS = Counter(
        namespace=METRICS_NAMESPACE,
        name='heartbeat_exceptions',
        documentation='Exceptions in the heartbeat method'
    )

    # endregion

    def __init__(self, host, password, session: aiohttp.ClientSession):
        self._host = host
        self._password = password
        self._session = session

    @aio.time(LOGIN_TIME)
    @aio.count_exceptions(LOGIN_EXCEPTIONS)
    async def login(self):
        async with self._session.get('http://{}/html/login/index.html'.format(self._host)) as resp:
            assert resp.status == 200
            re_res = re.search(r'[0-9a-zA-Z]{64}', await resp.text())
            if re_res:
                challenge = re_res.group(0)

        encrypted_password = hashlib.sha256('{}:{}'.format(challenge, self._password).encode()).hexdigest()

        request_data = {
            'password': encrypted_password,
            'csrf_token': 'nulltoken',
            'showpw': '0',
            'challengev': challenge,
        }

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': 'http://{}/html/login/index.html'.format(self._host),
        }

        async with self._session.post(
                'http://{}/data/Login.json'.format(self._host),
                data=request_data,
                headers=headers
        ) as resp:
            content = await resp.read()
            parsed = json.loads(content)
            data = self.parse_typed_dict(parsed)

            assert data['login'] == 'success'
            print(data)

        derivedk = hashlib.pbkdf2_hmac(
            'sha1',
            hashlib.sha256(self._password.encode()).hexdigest().encode(),
            self._password[0:16].encode(),
            1000,
            16
        ).hex()

        cookies = SimpleCookie()
        cookies['challengev'] = challenge
        cookies['challengev']['domain'] = self._host

        cookies['derivedk'] = derivedk
        cookies['derivedk']['domain'] = self._host

        self._session.cookie_jar.update_cookies(cookies)

    async def fetch_data(self, file: str):
        with self.FETCH_EXCEPTIONS.labels(file).count_exceptions():
            with self.FETCH_TIME.labels(file).time():
                async with self._session.get('http://{}/data/{}.json'.format(self._host, file)) as resp:
                    assert resp.status == 200

                    return json.loads(await resp.text())

    @aio.time(HEARTBEAT_TIME)
    @aio.count_exceptions(HEARTBEAT_EXCEPTIONS)
    async def heartbeat(self) -> bool:
        # We shouldn't have caching issues, but maybe the speedport interprets the params
        params = {
            '_time': int(time.time()),
            '_rand': random.randint(1, 1000)
        }
        async with self._session.get(
                'http://{}/data/heartbeat.json'.format(self._host),
                params=params
        ) as resp:
            assert resp.status == 200
            raw_data = json.loads(await resp.text())
            data = self.parse_typed_dict(raw_data)
            return data['loginstate'] == '1'

    async def login_loop(self, delay: float = 5):
        while True:
            authorized = await self.heartbeat()
            if not authorized:
                await self.login()
            await asyncio.sleep(delay)

    @staticmethod
    def parse_typed_dict(data):
        return {item['varid']: item['varvalue'] for item in data}


class SpeedportCollector:
    def __init__(self, client: SpeedportClient):
        self._client = client


async def main():
    session = aiohttp.ClientSession()
    client = SpeedportClient(_speedport, _password, session)
    login_task = asyncio.create_task(client.login_loop())

    await aio.web.start_http_server(port=9999)
    await login_task


loop = asyncio.get_event_loop()
loop.set_debug(True)
loop.run_until_complete(main())
