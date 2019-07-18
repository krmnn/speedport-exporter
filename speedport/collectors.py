import logging
import re

from prometheus_client import Summary, Counter, Info, Gauge

from .client import Client


class BaseCollector:
    METRICS_NAMESPACE = 'speedport'
    METRICS_SUBSYSTEM = ''
    ENDPOINT = ''

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

    def __init__(self, client: Client):
        self._client = client

        if not self.ENDPOINT:
            self.ENDPOINT = self.METRICS_SUBSYSTEM

        self.logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

    async def collect(self):
        try:
            with self._collect_exceptions.labels(self.METRICS_SUBSYSTEM).count_exceptions():
                with self._collect_duration.labels(self.METRICS_SUBSYSTEM).time():
                    raw = await self._client.fetch_data(self.ENDPOINT)
                    data = self._process_data(raw)
                    self._collect_time.labels(self.METRICS_SUBSYSTEM).set_to_current_time()
                    return data
        except Exception as e:
            self.logger.error("Error while collecting %s", self.ENDPOINT, exc_info=True)

    def _process_data(self, data):
        raise NotImplementedError('Subclasses have to implement _process_Data')


class DslCollector(BaseCollector):
    METRICS_SUBSYSTEM = 'dsl'

    def __init__(self, client: Client):
        super().__init__(client)

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

    def _process_data(self, data):
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


class LteCollector(BaseCollector):
    METRICS_SUBSYSTEM = 'lte'
    ENDPOINT = 'lteinfo'

    def __init__(self, client: Client):
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
    def _process_data(self, data):
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


class InterfaceCollector(BaseCollector):
    METRICS_SUBSYSTEM = 'interface'
    ENDPOINT = 'interfaces'

    def __init__(self, client: Client):
        super().__init__(client)

        self._info = Info(
            namespace=self.METRICS_NAMESPACE,
            name=self.METRICS_SUBSYSTEM,
            labelnames=['interface'],
            documentation='Information about the physical interfaces',
        )
        self._up = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            labelnames=['interface'],
            name='up',
            documentation='The status of the interface',
        )
        self._rx_speed = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            labelnames=['interface'],
            name='receive_speed',
            unit='kbps',
            documentation='Receiving speed of the interface (if applicable else -1)',
        )
        self._tx_speed = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            labelnames=['interface'],
            name='transmit_speed',
            unit='kbps',
            documentation='Transmit speed of the interface (if applicable else -1)'
        )
        self._mtu = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            labelnames=['interface'],
            name='mtu',
            unit='bytes',
            documentation='The mtu of the interface',
        )
        self._tx_packets = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            labelnames=['interface'],
            name='transmit_packets',
            unit='total',
            documentation='Transmitted packets on this interface'
        )
        self._rx_packets = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            labelnames=['interface'],
            name='receive_packets',
            unit='total',
            documentation='Received packets on this interface'
        )
        self._tx_errors = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            labelnames=['interface'],
            name='transmit_errs',
            unit='total',
            documentation='Error count on transmitting'
        )
        self._rx_errors = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            labelnames=['interface'],
            name='receive_errs',
            unit='total',
            documentation='Error count on receiving'
        )
        self._collisions = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            labelnames=['interface'],
            name='collisions',
            documentation='Collision count on interface'
        )

    def _process_data(self, data):
        interfaces = data['line_status']

        for interface in interfaces:
            name = interface['interface']
            del interface['interface']

            self._up.labels(name).set(interface['status'] == 'Up')
            del interface['status']

            if interface['media'] == 'WLAN':
                re_res = re.search(r'([0-9]+)Mbps', interface['speed'])
                if re_res:
                    speed = int(re_res.group(1)) * 1000
                    self._rx_speed.labels(name).set(speed)
                    self._tx_speed.labels(name).set(speed)

                    del interface['speed']
            elif interface['media'] == 'DSL':
                re_res = re.search(r'DownStream:([0-9]+)kbps UpStream:([0-9]+)kbps', interface['speed'])
                if re_res:
                    self._rx_speed.labels(name).set(re_res.group(1))
                    self._tx_speed.labels(name).set(re_res.group(2))
                    del interface['speed']
            else:
                self._rx_speed.labels(name).set(-1)
                self._tx_speed.labels(name).set(-1)

            self._mtu.labels(name).set(interface['MTU'])
            del interface['MTU']

            self._tx_packets.labels(name).set(interface['tx_packets'])
            del interface['tx_packets']
            self._rx_packets.labels(name).set(interface['rx_packets'])
            del interface['rx_packets']

            self._tx_errors.labels(name).set(interface['tx_errors'])
            del interface['tx_errors']
            self._rx_errors.labels(name).set(interface['rx_errors'])
            del interface['rx_errors']

            self._collisions.labels(name).set(interface['collisions'])
            del interface['collisions']

            self._info.labels(name).info(interface)


class ModuleCollector(BaseCollector):
    METRICS_SUBSYSTEM = 'module'

    def __init__(self, client: Client):
        super().__init__(client)

        self._info = Info(
            namespace=self.METRICS_NAMESPACE,
            name=self.METRICS_SUBSYSTEM,
            documentation='Firmware version information'
        )

    def _process_data(self, data):
        self._info.info(data)


class BondingTunnelCollector(BaseCollector):
    METRICS_SUBSYSTEM = 'bonding'
    ENDPOINT = 'bonding_tunnel'

    # noinspection SpellCheckingInspection
    _tcp_ext_names = [
        'SyncookiesSent',
        'SyncookiesRecv',
        'SyncookiesFailed',
        'EmbryonicRsts',
        'PruneCalled',
        'RcvPruned',
        'OfoPruned',
        'OutOfWindowIcmps',
        'LockDroppedIcmps',
        'ArpFilter',
        'TW',
        'TWRecycled',
        'TWKilled',
        'PAWSPassive',
        'PAWSActive',
        'PAWSEstab',
        'DelayedACKs',
        'DelayedACKLocked',
        'DelayedACKLost',
        'ListenOverflows',
        'ListenDrops',
        'TCPPrequeued',
        'TCPDirectCopyFromBacklog',
        'TCPDirectCopyFromPrequeue',
        'TCPPrequeueDropped',
        'TCPHPHits',
        'TCPHPHitsToUser',
        'TCPPureAcks',
        'TCPHPAcks',
        'TCPRenoRecovery',
        'TCPSackRecovery',
        'TCPSACKReneging',
        'TCPFACKReorder',
        'TCPSACKReorder',
        'TCPRenoReorder',
        'TCPTSReorder',
        'TCPFullUndo',
        'TCPPartialUndo',
        'TCPDSACKUndo',
        'TCPLossUndo',
        'TCPLostRetransmit',
        'TCPRenoFailures',
        'TCPSackFailures',
        'TCPLossFailures',
        'TCPFastRetrans',
        'TCPForwardRetrans',
        'TCPSlowStartRetrans',
        'TCPTimeouts',
        'TCPRenoRecoveryFail',
        'TCPSackRecoveryFail',
        'TCPSchedulerFailed',
        'TCPRcvCollapsed',
        'TCPDSACKOldSent',
        'TCPDSACKOfoSent',
        'TCPDSACKRecv',
        'TCPDSACKOfoRecv',
        'TCPAbortOnSyn',
        'TCPAbortOnData',
        'TCPAbortOnClose',
        'TCPAbortOnMemory',
        'TCPAbortOnTimeout',
        'TCPAbortOnLinger',
        'TCPAbortFailed',
        'TCPMemoryPressures',
        'TCPSACKDiscard',
        'TCPDSACKIgnoredOld',
        'TCPDSACKIgnoredNoUndo',
        'TCPSpuriousRTOs',
        'TCPMD5NotFound',
        'TCPMD5Unexpected',
        'TCPSackShifted',
        'TCPSackMerged',
        'TCPSackShiftFallback',
        'TCPBacklogDrop',
        'TCPMinTTLDrop',
        'TCPDeferAcceptDrop',
        'IPReversePathFilter',
        'TCPTimeWaitOverflow',
        'TCPReqQFullDoCookies',
        'TCPReqQFullDrop',
        'TCPRetransFail',
        'TCPRcvCoalesce',
    ]
    # noinspection SpellCheckingInspection
    _ip_ext_names = [
        'InNoRoutes',
        'InTruncatedPkts',
        'InMcastPkts',
        'OutMcastPkts',
        'InBcastPkts',
        'OutBcastPkts',
        'InOctets',
        'OutOctets',
        'InMcastOctets',
        'OutMcastOctets',
        'InBcastOctets',
        'OutBcastOctets',
    ]
    # noinspection SpellCheckingInspection
    _ireg_names = [
        'out_sequence_number',
        'maximum_sequence_number',
        'error_sequence_number',
        'out_interface_index',
        'maximum_interface_index',
        'queue_length',
        'over_count',
        'over_number',
        'blow_count',
        'blow_number',
        'reverse_number',
        'time_out_count',
        'time_out_drop_count',
        'lost_times',
        'same_sequence_number',
        # 'sequence_error_count', # in the table there are 16 fields, but only 15 are contained in the json
    ]

    def __init__(self, client: Client):
        super().__init__(client)

        assert len(self._tcp_ext_names) == len(set(self._tcp_ext_names))

        self._tcp_ext_metrics = {
            name: Gauge(
                namespace=self.METRICS_NAMESPACE,
                subsystem=self.METRICS_SUBSYSTEM,
                name='TcpExt_' + name,
                documentation=name
            )
            for name in self._tcp_ext_names
        }

        self._ip_ext_metrics = {
            name: Gauge(
                namespace=self.METRICS_NAMESPACE,
                subsystem=self.METRICS_SUBSYSTEM,
                name='IpExt_' + name,
                documentation=name
            )
            for name in self._ip_ext_names
        }

        self._ireg_metrics = {
            name: Gauge(
                namespace=self.METRICS_NAMESPACE,
                subsystem=self.METRICS_SUBSYSTEM,
                name='ireg_' + name,
                documentation=name
            )
            for name in self._ireg_names
        }

        self._lte_tunnel = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='lte_tunnel',
            unit='status',
            documentation='The status of the lte tunnel, 1 means up',
        )
        self._dsl_tunnel = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='dsl_tunnel',
            unit='status',
            documentation='The status of the dsl tunnel, 1 means up',
        )
        self._bonding = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='bonding',
            unit='status',
            documentation='The status of bonding, 1 means up',
        )

    def _process_data(self, data):
        tcp_ext = data['TcpExt']
        del data['TcpExt']
        self.__merge_lists(tcp_ext, 'TcpExt', self._tcp_ext_names, self._tcp_ext_metrics)

        ip_ext = data['IpExt']
        del data['IpExt']
        self.__merge_lists(ip_ext, 'IpExt', self._ip_ext_names, self._ip_ext_metrics)

        ireg = data['ireg']
        del data['ireg']
        self.__merge_lists(ireg, 'ireg', self._ireg_names, self._ireg_metrics)

        self._lte_tunnel.set(data['lte_tunnel'] == 'Up')
        self._dsl_tunnel.set(data['dsl_tunnel'] == 'Up')
        self._bonding.set(data['bonding'] == 'Up')

    def __merge_lists(self, data, kind: str, names: list, metrics: dict):
        assert len(names) == len(data), "Length {} != {} of {}".format(len(names), len(data), kind)
        for i, name in enumerate(names):
            try:
                val = data[i][kind]
                if len(val):
                    metrics[name].set(val)
                else:
                    metrics[name].set(0)
            except Exception as e:
                self.logger.error("Error on name %s with value %s", name, data[i][kind], exc_info=True)
                raise e


class PPPoESessionCollector(BaseCollector):
    METRICS_SUBSYSTEM = 'pppoe'
    ENDPOINT = 'session'

    def __init__(self, client: Client):
        super().__init__(client)

        self._session = Info(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='session',
            documentation='Information about PPPoE Session'
        )

        self._mtu = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='mtu',
            documentation='The MTU of the PPPoE'
        )

    def _process_data(self, data):
        mtu = data['MTU']
        del data['MTU']
        if mtu:
            self._mtu.set(mtu)
        else:
            self._mtu.set(-1)

        self._session.info(data)


class CPUMemoryCollector(BaseCollector):
    ENDPOINT = 'memory'

    def __init__(self, client: Client):
        super().__init__(client)

        self._memory_main_available = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem='memory',
            name='main_available',
            unit='bytes',
            documentation='Available Main Memory'
        )

        self._memory_main_used = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem='memory',
            name='main_used',
            unit='percentage',
            documentation='Used Main Memory (%)'
        )
        self._memory_main_free = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem='memory',
            name='main_free',
            unit='percentage',
            documentation='Free Main Memory (%)'
        )

        self._memory_flash_available = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem='memory',
            name='flash_available',
            unit='bytes',
            documentation='Available Flash Memory'
        )

        self._memory_flash_used = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem='memory',
            name='flash_used',
            unit='percentage',
            documentation='Used Flash Memory (%)'
        )
        self._memory_flash_free = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem='memory',
            name='flash_free',
            unit='percentage',
            documentation='Free Flash Memory (%)'
        )

        self._cpu_load = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem='cpu',
            name='load',
            unit='percentage',
            documentation='CPU-Load (%)'
        )

        self._memory_dns_available = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem='memory',
            name='dns_available',
            unit='bytes',
            documentation='Available Dns Memory'
        )

        self._memory_dns_used = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem='memory',
            name='dns_used',
            unit='percentage',
            documentation='Used Dns Memory (%)'
        )
        self._memory_dns_free = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem='memory',
            name='dns_free',
            unit='percentage',
            documentation='Free Dns Memory (%)'
        )

        self._dns_cache_entries = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem='memory',
            name='dns_cache_entries',
            documentation='Number of DNS Cache entries'
        )

    def _process_data(self, data):
        amm = int(data['amm'][:-2])
        self._memory_main_available.set(amm * 1024)
        res = re.search(r'([0-9]+(?:\.[0-9]+)?)% vs ([0-9]+(?:\.[0-9]+)?)%', data['used_free_main'])
        if res:
            used = float(res.group(1))
            free = float(res.group(2))

            self._memory_main_used.set(used / 100)
            self._memory_main_free.set(free / 100)
        else:
            self._memory_main_used.set(-1)
            self._memory_main_free.set(-1)

        afm = int(data['afm'][:-2])
        self._memory_flash_available.set(afm * 1024)
        res = re.search(r'([0-9]+(?:\.[0-9]+)?)% vs ([0-9]+(?:\.[0-9]+)?)%', data['used_free_flash'])
        if res:
            used = float(res.group(1))
            free = float(res.group(2))

            self._memory_flash_used.set(used / 100)
            self._memory_flash_free.set(free / 100)
        else:
            self._memory_flash_used.set(-1)
            self._memory_flash_free.set(-1)

        res = re.search(r'([0-9]+(?:\.[0-9]+)?)%', data['cpu_load'])
        if res:
            cpu_load = float(res.group(1))
            self._cpu_load.set(cpu_load / 100)
        else:
            self._cpu_load.set(-1)

        adcm = int(data['adcm'][:-2])
        self._memory_dns_available.set(adcm * 1024)
        res = re.search(r'([0-9]+(?:\.[0-9]+)?)% vs ([0-9]+(?:\.[0-9]+)?)%', data['used_free_dns'])
        if res:
            used = float(res.group(1))
            free = float(res.group(2))

            self._memory_dns_used.set(used / 100)
            self._memory_dns_free.set(free / 100)
        else:
            self._memory_dns_used.set(-1)
            self._memory_dns_free.set(-1)

        self._dns_cache_entries.set(data['nodce'])


class BondingTR181Collector(BaseCollector):
    METRICS_SUBSYSTEM = 'bonding'
    ENDPOINT = 'bonding_tr181'

    def __init__(self, client: Client):
        super().__init__(client)

        self._info = Info(
            namespace=self.METRICS_NAMESPACE,
            name=self.METRICS_SUBSYSTEM,
            documentation='General information about the bonding system'
        )
        self._error_info = Info(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='error',
            documentation='Last Error Info'
        )
        self._hello_info = Info(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='hello',
            documentation='Hello Info'
        )

        self._enabled = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='enabled',
            documentation='Bonding enabled'
        )
        self._rttswitch = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='rttswitch',
            documentation='RTTSwitch'
        )
        self._rtt = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='rtt',
            documentation='current rtt'
        )
        self._rttthre = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='rtt_threshold',
            documentation='RTT Threshold'
        )
        self._bwcalcula = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='bandwidth_calculation_interval',
            documentation='Bandwidth Calculation Interval'
        )
        self._bandwidth = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='bandwidth_available',
            documentation='AvailableBW'
        )
        self._hello_interval = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='hello_interval',
            documentation='Hello interval'
        )
        self._idle_hello_interval = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='idle_hello_interval',
            documentation='IdleHelloInterval'
        )
        self._hello_retry_times = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='hello_retry_times',
            documentation='HelloRetryTimes',
        )
        self._idle_hello_traffic_interval = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='idle_hello_traffic_interval',
            documentation='IdleHelloTrafficInterval'
        )

        self._interface_number_of_entries = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='interface_entries',
            documentation='InterfaceNumberOfEntries'
        )

        self._queue_skb_timeout = Gauge(
            namespace=self.METRICS_NAMESPACE,
            subsystem=self.METRICS_SUBSYSTEM,
            name='skb_queue_timeout',
            documentation='QueueSkbTimeOut'
        )

    def _process_data(self, data):
        self._enabled.set(data['enable1'])
        del data['enable1']
        self._rttswitch.set(data['rttswitch'])
        del data['rttswitch']
        self._rtt.set(data['rtt'])
        del data['rtt']
        self._rttthre.set(data['rttthre'])
        del data['rttthre']
        self._bwcalcula.set(data['bwcalcula'])
        del data['bwcalcula']
        self._bandwidth.set(data['bw'])
        del data['bw']
        self._hello_interval.set(data['hellointerval'])
        del data['hellointerval']
        self._idle_hello_interval.set(data['idlehellointerval'])
        del data['idlehellointerval']
        self._hello_retry_times.set(data['helloretrytimes'])
        del data['helloretrytimes']
        self._idle_hello_traffic_interval.set(data['idlehellotrafficinterval'])
        del data['idlehellotrafficinterval']
        self._interface_number_of_entries.set(data['num_entry'])
        del data['num_entry']
        self._queue_skb_timeout.set(data['QueueSkbTimeOut'])
        del data['QueueSkbTimeOut']

        del data['status1']  # collected within BondingTunnelCollector

        self._error_info.info({'last_error_info': data['errorinfo']})
        del data['errorinfo']

        self._hello_info.info({'status': data['hellostatus']})
        del data['hellostatus']

        self._info.info(data)
