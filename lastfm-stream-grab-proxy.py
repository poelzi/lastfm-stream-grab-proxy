#!/usr/bin/python

import SocketServer
import SimpleHTTPServer
import socket
from select import select
from urlparse import urlparse
import re

class ProxyHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    def __init__(self, *args):
        SimpleHTTPServer.SimpleHTTPRequestHandler.__init__(self, *args)
        self.protocol = 'HTTP/1.0'

    def _connect(self, netloc):
        port = 80
        separator = netloc.find(':')
        if separator > 0:
            port = int(netloc[separator+1:])
            netloc = netloc[:separator]

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try: sock.connect((netloc, port))
        except socket.error:
            return None
        return sock

    def _do_method(self):
        (scheme, netloc, path, params, query, fragment) = urlparse(self.path, scheme='http')
        if scheme != 'http' or fragment or netloc == None:
            self.send_error(400, 'Invalid URL %s' % self.path)
            return
        sock = self._connect(netloc)
        if sock is not None:
            self.log_request()
            if self.headers.has_key('Proxy-Connection'):
                del self.headers['Proxy-Connection']
            self.headers['Connection'] = 'close'

            sock.send("%s %s %s\r\n" % (self.command, self.path, self.request_version))
            for header in self.headers.items():
                sock.send("%s: %s\r\n" % header)
            sock.send("\r\n")
            self._read_write(sock)
        else:
            self.send_error(404, "Could not connect to host %s:%d" % (netloc, port))

    do_GET  = _do_method
    do_HEAD = _do_method
    do_POST = _do_method

    def _read_write(self, server_sock):
        rlist = [self.connection, server_sock]
        wlist = []
        max_idle = 10
        idle_count = 0
        seen_http_header = False
        while 1:
            (r, _, x) = select(rlist, wlist, rlist, 1)
            if x: break
            idle_count += 1
            if r:
                for descriptor in r:
                    data = descriptor.recv(8192)
                    if data:
                        idle_count = 0
                        if descriptor is server_sock:
                            # http header is in first server packet
                            if not seen_http_header:
                                seen_http_header = True
                                m = re.match('HTTP/\d\.\d (\d+)', data)
                                if m: self.log_request(m.groups()[0])
                                else: self.log_request()
                            self.connection.send(data)
                        else:
                            server_sock.send(data)
            if idle_count >= max_idle: break

def run_server(addr, port):
    #httpd = SocketServer.ForkingTCPServer((addr, port), ProxyHandler)
    httpd = SocketServer.ThreadingTCPServer((addr, port), ProxyHandler)
    print 'Listening on %s:%d' % (addr, port)
    try: httpd.serve_forever(poll_interval=0.5)
    except:
        print 'Shutting down'
        httpd.shutdown()

if __name__ == "__main__":
    addr = 'localhost'
    port = 8123
    run_server(addr, port)
