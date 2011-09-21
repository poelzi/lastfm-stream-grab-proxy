#!/usr/bin/python

import SocketServer
import SimpleHTTPServer
import urllib

class ProxyHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    def foo(self):
        x = 1

    def do_GET(self):
        self.copyfile(urllib.urlopen(self.path), self.wfile)

def run_server(addr, port):
    httpd = SocketServer.ForkingTCPServer((addr, port), ProxyHandler)
    print 'Listening on %s:%d' % (addr, port)
    httpd.serve_forever()

if __name__ == "__main__":
    addr = 'localhost'
    port = 8123
    run_server(addr, port)
