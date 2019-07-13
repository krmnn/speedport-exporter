import subprocess

from prometheus_client import Info

from . import client
from . import collectors

info = Info('speedport_exporter', 'Version information about the speedport exporter')
info.info({
    'version': subprocess.run(['git', 'describe', '--always'], capture_output=True).stdout.decode().strip()
})

SpeedportClient = client.SpeedportClient

SpeedportDslCollector = collectors.SpeedportDslCollector
SpeedportLteCollector = collectors.SpeedportLteCollector
SpeedportInterfaceCollector = collectors.SpeedportInterfaceCollector
SpeedportModuleCollector = collectors.SpeedportModuleCollector
