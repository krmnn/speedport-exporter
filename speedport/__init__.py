import subprocess

from prometheus_client import Info

from . import client
from . import collectors

info = Info('speedport_exporter', 'Version information about the speedport exporter')
info.info({
    'version': subprocess.run(['git', 'describe', '--always'], capture_output=True).stdout.decode().strip()
})

Client = client.Client

DslCollector = collectors.DslCollector
LteCollector = collectors.LteCollector
InterfaceCollector = collectors.InterfaceCollector
ModuleCollector = collectors.ModuleCollector
BondingTunnelCollector = collectors.BondingTunnelCollector
PPPoESessionCollector = collectors.PPPoESessionCollector
