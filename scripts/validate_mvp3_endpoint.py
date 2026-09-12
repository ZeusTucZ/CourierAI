"""Start the frozen local API for the official HTTP validator, then stop it."""
import socket
import subprocess
import sys
import time
from pathlib import Path


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    with Path('artifacts/endpoint_server.log').open('w') as log:
        server=subprocess.Popen([sys.executable,'-m','uvicorn','scripts.serve_mvp3:app','--host','127.0.0.1','--port',str(port)],stdout=log,stderr=log)
        try:
            for _ in range(100):
                if server.poll() is not None: raise RuntimeError('Local API failed; see endpoint_server.log')
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.1): break
                except OSError: time.sleep(.1)
            else: raise RuntimeError('Local API startup timed out')
            result=subprocess.run([sys.executable,'validate_format.py','--endpoint',f'http://127.0.0.1:{port}/decide'],capture_output=True,text=True)
            Path('artifacts/endpoint_validation.log').write_text(result.stdout+result.stderr)
            print(result.stdout+result.stderr)
            result.check_returncode()
        finally:
            server.terminate()
            try: server.wait(timeout=5)
            except subprocess.TimeoutExpired: server.kill();server.wait()


if __name__=='__main__': main()
