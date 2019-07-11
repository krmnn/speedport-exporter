import asyncio
import hashlib
import random
import re
import subprocess
import time
from http.cookies import SimpleCookie

import aiohttp
import dirtyjson as json
from prometheus_async import aio
from prometheus_client import Counter, Gauge, Info, Summary

from settings import _speedport, _password

info = Info('speedport_exporter', 'Version information about the speedport exporter')
info.info({
    'version': subprocess.run(['git', 'describe', '--always'], capture_output=True).stdout.decode().strip()
})


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

    @aio.count_exceptions(LOGIN_EXCEPTIONS)
    @aio.time(LOGIN_TIME)
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
    METRICS_NAMESPACE = 'speedport'
    METRICS_SUBSYSTEM = ''

    _collect_duration = Summary(
        namespace=METRICS_NAMESPACE,
        name='collection_duration',
        unit='seconds',
        documentation='Duration to collect dsl metrics',
        labelnames=['subsystem'],
    )
    _collect_exceptions = Counter(
        namespace=METRICS_NAMESPACE,
        name='collection_exceptions',
        documentation='Exceptions occuring durring the collection',
        labelnames=['subsystem'],
    )

    def __init__(self, client: SpeedportClient):
        self._client = client

    async def collect(self):
        return await aio.time(
            self._collect_duration.labels(self.METRICS_SUBSYSTEM),
            aio.count_exceptions(
                self._collect_exceptions.labels(self.METRICS_SUBSYSTEM),
                self._collect()
            )
        )

    # noinspection PyMethodMayBeStatic
    async def _collect(self):
        return []


class SpeedportDslCollector(SpeedportCollector):
    METRICS_SUBSYSTEM = 'dsl'

    def __init__(self, client: SpeedportClient):
        super(SpeedportDslCollector, self).__init__(client)

        self._connection_info = Info(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='connection',
            documentation='Connection information',
        )

        self._actual_data_rate = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='actual_data_rate',
            unit='kbps',
            documentation='Actual data rate',
            labelnames=['direction']
        )
        self._attainable_data_rate = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='attainable_data_rate',
            unit='kbps',
            documentation='Attainable data rate',
            labelnames=['direction']
        )
        self._snr = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='snr',
            documentation='SNR Margin',
            labelnames=['direction']
        )
        self._signal = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='signal',
            documentation='Signal level',
            labelnames=['direction']
        )
        self._line = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='line',
            documentation='Line Attenuation',
            labelnames=['direction']
        )
        self._fec_size = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='fec_size',
            documentation='FEC Size',
            labelnames=['direction']
        )
        self._codeword = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='codeword_size',
            documentation='Codeword size',
            labelnames=['direction']
        )
        self._interleave = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='interleave',
            documentation='Interleave delay',
            labelnames=['direction']
        )
        self._crc_error_count = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='crc_error_count',
            documentation='CRC (Cyclic Redundancy Check) error count',
            labelnames=['direction']
        )
        self._hec_error_count = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='hec_error_count',
            documentation='HEC (Header Error Correction) error count',
            labelnames=['direction']
        )
        self._fec_error_count = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='fec_error_count',
            documentation='FEC (Forward Error Correction) error count',
            labelnames=['direction']
        )

    async def _collect(self):
        data = await self._client.fetch_data('dsl')
        connection = data['Connection']
        line = data['Line']

        self._connection_info.info(connection)

        self._actual_data_rate.labels('upload').set(line['uactual'])
        self._actual_data_rate.labels('download').set(line['dactual'])

        self._attainable_data_rate.labels('upload').set(line['uattainable'])
        self._attainable_data_rate.labels('download').set(line['dattainable'])

        self._snr.labels('upload').set(line['uSNR'])
        self._snr.labels('download').set(line['dSNR'])

        self._signal.labels('upload').set(line['uSignal'])
        self._signal.labels('download').set(line['dSignal'])

        self._line.labels('upload').set(line['uLine'])
        self._line.labels('download').set(line['dLine'])

        self._fec_size.labels('upload').set(line['uFEC_size'])
        self._fec_size.labels('download').set(line['dFEC_size'])

        self._codeword.labels('upload').set(line['uCodeword'])
        self._codeword.labels('download').set(line['dCodeword'])

        self._interleave.labels('upload').set(line['uInterleave'])
        self._interleave.labels('download').set(line['dInterleave'])

        self._crc_error_count.labels('upload').set(line['uCRC'])
        self._crc_error_count.labels('download').set(line['dCRC'])

        self._hec_error_count.labels('upload').set(line['uHEC'])
        self._hec_error_count.labels('downloads').set(line['dHEC'])

        self._fec_error_count.labels('upload').set(line['uFEC'])
        self._fec_error_count.labels('download').set(line['dFEC'])


class SpeedportLteCollector(SpeedportCollector):
    METRICS_SUBSYSTEM = 'lte'

    def __init__(self, client: SpeedportClient):
        super().__init__(client)

        self._device_info = Info(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='device',
            documentation='LTE Device Information'
        )
        self._connection_info = Info(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='connection',
            documentation='LTE Cell Information'
        )

        self._rsrp = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='rsrp',
            documentation='LTE RSRP'
        )
        self._rsrq = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='rsrq',
            documentation='LTE RSRQ'
        )

    async def _collect(self):
        data = await self._client.fetch_data('lteinfo')

        self._device_info.info({
            'imei': data['imei'],
            'imsi': data['imsi'],
            'device_status': data['device_status'],
            'card_status': data['card_status'],
            'antenna_mode': data['antenna_mode'],
        })

        self._connection_info.info({
            'phycellid': data['phycellid'],
            'cellid': data['cellid'],
            'tac': data['tac'],
            'service_status': data['service_status'],
            'eps': data['eps']
        })

        self._rsrp.set(data['rsrp'])
        self._rsrq.set(data['rsrq'])


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

        await aio.web.start_http_server(port=9611)
        await login_task


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
