#!/usr/bin/env python3
"""Inspect renderer dependencies; opt-in cache-only setup and a real smoke render."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request

import cloud_drawio as c

PLAYWRIGHT='1.61.1'
VIEWER_URL='https://raw.githubusercontent.com/jgraph/drawio/82af434539c3449d99275b91a91b6b99998a7d58/src/main/webapp/js/viewer-static.min.js'
VIEWER_SHA256='ee0c444be46c95dc1842999f133c92598fe43e7cdf279f7095d0f057c48771b1'


def cache_path():
    return Path(os.environ.get('CLOUD_DRAWIO_CACHE',Path.home()/'.cache/cloud-architecture-drawio'))


def setup(cache):
    npm=shutil.which('npm')
    if not npm:raise ValueError('Node.js and npm are required; install them with your platform package manager')
    cache.mkdir(parents=True,exist_ok=True)
    subprocess.run([npm,'install','--prefix',str(cache),'--no-audit','--no-fund','--ignore-scripts',f'playwright@{PLAYWRIGHT}'],check=True,capture_output=True,text=True,timeout=180)
    subprocess.run([shutil.which('node'),str(cache/'node_modules/playwright/cli.js'),'install','chromium'],check=True,capture_output=True,text=True,timeout=300)
    download_viewer(cache)


def download_viewer(cache):
    # Pin official source and digest; never replace a working cache with an error page.
    with urllib.request.urlopen(VIEWER_URL,timeout=30) as response:data=response.read()
    if hashlib.sha256(data).hexdigest()!=VIEWER_SHA256:raise ValueError('viewer SHA-256 mismatch; existing cached viewer was not replaced')
    c.write_outputs([(cache/'viewer-static.min.js',data)])
    provenance={'url':VIEWER_URL,'sha256':hashlib.sha256(data).hexdigest(),'playwright':PLAYWRIGHT}
    c.write_outputs([(cache/'renderer-provenance.json',(json.dumps(provenance,indent=2)+'\n').encode())])


def inspect(smoke=False,viewer=None):
    found,reason=c.find_renderer(viewer)
    result={'ok':bool(found),'python':sys.version.split()[0],'node':shutil.which('node'),'cache':str(cache_path()),'reason':reason}
    if found:
        path=Path(found[1]);result.update(viewer=str(path),viewer_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    if smoke and found:
        with tempfile.TemporaryDirectory(prefix='cloud-drawio-smoke-') as tmp:
            model=json.loads((c.ROOT/'assets/templates/azure-regional.json').read_text())
            verdict,code=c.check(model,Path(tmp)/'smoke.drawio',viewer=found[1],timeout=120)
            result['smoke']=verdict;result['ok']=code==0
    elif smoke:result['smoke']={'rendered':False,'reason':reason}
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--setup',action='store_true');p.add_argument('--smoke',action='store_true');p.add_argument('--viewer');a=p.parse_args()
    try:
        if a.setup:setup(cache_path())
        result=inspect(a.smoke,a.viewer)
    except (OSError,ValueError,subprocess.SubprocessError) as exc:result={'ok':False,'errors':[str(exc)]}
    c.emit(result,indent=2);sys.exit(0 if result['ok'] else 1)

if __name__=='__main__':main()
