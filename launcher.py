"""The packaged app starts localhost, opens the browser, and stays in this terminal."""
import multiprocessing
import os
import socket
import threading
import time
import urllib.request
import webbrowser
from runtime import HOME, VERSION


def main():
    multiprocessing.freeze_support()
    import uvicorn
    from app import app
    port=int(os.environ.get('SIDEA_PORT','8000'))
    while port<8100:
        try:
            with socket.socket() as test:test.bind(('127.0.0.1',port))
            break
        except OSError:port+=1
    url=f'http://127.0.0.1:{port}'
    print(f'\nSide A {VERSION}\nOpen {url}\nWorkspace: {HOME}\nKeep this window open. Ctrl+C stops the app.\n',flush=True)
    if not os.environ.get('SIDEA_NO_BROWSER'):
        def open_when_ready():
            for _ in range(100):
                try:
                    with urllib.request.urlopen(url+'/api/health',timeout=1):pass
                    webbrowser.open(url);return
                except Exception:time.sleep(.2)
        threading.Thread(target=open_when_ready,daemon=True).start()
    uvicorn.run(app,host='127.0.0.1',port=port)


if __name__=='__main__':main()
