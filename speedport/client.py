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


class Client:
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

        self.logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

    @aio.count_exceptions(LOGIN_EXCEPTIONS)
    @aio.time(LOGIN_TIME)
    async def login(self):
        async with self._session.get('http://{}/html/login/index.html'.format(self._host)) as resp:
            assert resp.status == 200, "Response status code for fetching index is {}".format(file, resp.status)
            re_res = re.search(r'[0-9a-zA-Z]{64}', await resp.text())
            if re_res:
                challenge = re_res.group(0)

        encrypted_password = hashlib.sha256('{}:{}'.format(challenge, self._password).encode()).hexdigest()

        # noinspection SpellCheckingInspection
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

            assert data['login'] == 'success', "Login wasn't successful: {}".format(data)

        derived_key = hashlib.pbkdf2_hmac(
            'sha1',
            hashlib.sha256(self._password.encode()).hexdigest().encode(),
            challenge[0:16].encode(),
            1000,
            16
        ).hex()

        cookies = SimpleCookie()
        cookies['challengev'] = challenge
        cookies['challengev']['domain'] = self._host

        cookies['derivedk'] = derived_key
        cookies['derivedk']['domain'] = self._host

        self._session.cookie_jar.update_cookies(cookies)

    async def fetch_data(self, file: str):
        with self.FETCH_EXCEPTIONS.labels(file).count_exceptions():
            with self.FETCH_TIME.labels(file).time():
                async with self._session.get('http://{}/data/{}.json'.format(self._host, file)) as resp:
                    assert resp.status == 200, "Response status code for {} is {}".format(file, resp.status)
                    raw = await resp.text()
                    try:
                        return json.loads(raw)
                    except json.error.Error as e:
                        self.logger.error(e)
                        raise

    @aio.count_exceptions(HEARTBEAT_EXCEPTIONS)
    @aio.time(HEARTBEAT_TIME)
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
            assert resp.status == 200, "Response status code for heartbeat is {}".format(resp.status)
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
        # noinspection SpellCheckingInspection
        return {item['varid']: item['varvalue'] for item in data}
