import logging

from prometheus_client import Summary, Counter, Info, Gauge

from .client import SpeedportClient

logger = logging.getLogger(__name__)


class SpeedportBaseCollector:
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
        documentation='Exceptions occurring during the collection',
        labelnames=['subsystem'],
    )
    _collect_time = Gauge(
        namespace=METRICS_NAMESPACE,
        name='collect_time',
        unit='seconds',
        documentation='Last successful collect (useful because ignoring exceptions)',
        labelnames=['subsystem']
    )

    def __init__(self, client: SpeedportClient):
        self._client = client

    async def collect(self):
        try:
            with self._collect_exceptions.labels(self.METRICS_SUBSYSTEM).count_exceptions():
                with self._collect_duration.labels(self.METRICS_SUBSYSTEM).time():
                    data = await self._collect()
                    self._collect_time.labels(self.METRICS_SUBSYSTEM).set_to_current_time()
                    return data
        except Exception as e:
            logger.error(e)

    # noinspection PyMethodMayBeStatic
    async def _collect(self):
        return []


class SpeedportDslCollector(SpeedportBaseCollector):
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


class SpeedportLteCollector(SpeedportBaseCollector):
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

    # noinspection SpellCheckingInspection
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
