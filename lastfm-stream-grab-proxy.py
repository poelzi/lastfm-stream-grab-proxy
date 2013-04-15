#!/usr/bin/python
#
# This is a simple implementation of a http proxy that will save music
# files from the last.fm music service.
# Copyright Alexander Else, 2011.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import SocketServer
import SimpleHTTPServer
import socket
from select import select
import random
import urlparse
import re
from xml.dom.minidom import parseString
from ID3 import ID3
from StringIO import StringIO
import errno
import gzip
import os
import argparse

parser = argparse.ArgumentParser(description='last.fm store proxy.',
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--no-proxy', default=False, action="store_true",
                   help='ignore proxy environment')
parser.add_argument('--debug', default=False, action="store_true",
                   help='print debug output')
parser.add_argument('--output', default=".",
                   help='ignore proxy environment')
parser.add_argument('--format', default="{artist}/{album}/{title}.mp3",
                   help='save files with pattern. Possible arguments: artist, album, title, station')

#parser.add_argument('integers', metavar='N', type=int, nargs='+',
#                   help='an integer for the accumulator')
#parser.add_argument('--sum', dest='accumulate', action='store_const',
#                   const=sum, default=max,
#                   help='sum the integers (default: find the max)')

args = parser.parse_args()

proxy_so = os.environ.get("SOCKS_SERVER", None) or os.environ.get("socks_server", None)
proxy_http = os.environ.get("HTTP_PROXY", None) or os.environ.get("http_proxy", None)
if args.no_proxy == False and (proxy_so or proxy_http):
    try:
        import socks
        print "use proxy: %s" %(proxy_so or proxy_http)
    except ImportError, e:
        print "For proxy support, install python-socksipy"
        os.exit(-1)

def debug(msg):
    if args.debug:
        print "msg"
        
def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else: raise

class TrackInfoCache:
    def __init__(self):
        self._cache = {}

    def get(self, key, default=None):
        if self._cache.has_key(key):
            return self._cache[key]
        else:
            return default

    def set(self, key, data):
        self._cache[key] = data

    def delete(self, key):
        if self._cache.has_key(key): del self._cache[key]

track_info_cache = TrackInfoCache()

class LastFMSupport():
    def __init__(self):
        #self.track_info_cache = TrackInfoCache()
        self.mp3_re = re.compile('[a-z]+([0-9]+)\.last\.fm.*\.mp3$')
        #self.xml_re = re.compile('method=radio.*getPlaylist')
        self.xml_re = re.compile('ws.audioscrobbler.com/radio/xspf.php')
        self.station_re = re.compile('ws.audioscrobbler.com/radio/adjust.php')
        self.station = "Unknown Station"
        
    def update_station(self, url):
        try:
            p = urlparse.urlparse(url)
            station = urlparse.parse_qs(p.query)["url"][0]
            self.station = station.replace("lastfm://", "").replace("/", "-")
            print "listening to station: %s" %self.station
        except Exception as e:
            self.station = "Unknown Station"
            print "error parsing station: %s" %e
        
        
    def get_track_info_from_xml(self, xml):
        metadata = {}
        xml_data = parseString(xml)
        tracks = xml_data.getElementsByTagName('track')
        debug(xml)
        for track in tracks:
            track_info = {}
            try:
                for element in ['location', 'title', 'creator', 'album']:
                    node = track.getElementsByTagName(element)[0]
                    content = node.firstChild.nodeValue
                    track_info[element] = content

                m = re.search('/([a-f\d]+)\.mp3', track_info['location'])
                if m:
                    key = m.groups()[0]
                    metadata[key] = track_info
                else:
                    print 'WARNING: No track location ' % track_info['location']
            except: pass
        # update station title
        try:
            for node in xml_data.childNodes[0].childNodes:
                if node.nodeName == 'title':
                    self.station = node.childNodes[0].wholeText
                    track_info_cache.set("station", self.station)
        except Exception as e:
            print "can't find title: %s" %e
        return metadata

    def update_track_info_from_xml(self, xml):
        metadata = self.get_track_info_from_xml(xml)
        for k, v in metadata.items():
            track_info_cache.set(k, v)

    def update_id3_tag(self, filename, info):
        needs_update = 0
        id3 = ID3(filename)
        for k, v in info.items():
            id3[k] = v
            needs_update = 1
        if needs_update: id3.write()


class ProxyHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):

    def __init__(self, *args):
        self.protocol = 'HTTP/1.0'
        self.rbufsize = 0
        self.lastfm = LastFMSupport()
        self.proxy_re = re.compile(r'(?P<host>[^:/ ]+).?(?P<port>[0-9]*)') # FIXME: ipv6 ip support
        SimpleHTTPServer.SimpleHTTPRequestHandler.__init__(self, *args)

    def _strip_http_headers(self, http_response):
        end_headers = re.search('(\r\n\r\n)', http_response).span()[1]
        stripped = http_response[end_headers:]
        return stripped

    def _needs_decompression(self, http_data):
        needs_decompression = 0
        m = re.search('Content-Encoding: ([^\r\n]+)', http_data)
        if m:
            for encode_method in (m.groups()[0]).split(','):
                if encode_method == 'gzip':
                    needs_decompression = 1
        return needs_decompression

    def _get_socket(self):
        if args.no_proxy == False and (proxy_so or proxy_http):
            sock = socks.socksocket()
            if proxy_so:
                s = self.proxy_re.search(proxy_so)
                sock.setproxy(socks.PROXY_TYPE_SOCKS5,s.group("host"), int(s.group("port")) or 1080)
            elif proxy_http:
                #s = self.proxy_re.search(http)
                s = urlparse.urlparse(proxy_http)
                s = self.proxy_re.search(s.netloc)
                sock.setproxy(socks.PROXY_TYPE_HTTP, s.group("host"), int(s.group("port")) or 8080)   
            return sock
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            return sock
        
        
    def _connect(self, netloc):
        port = 80
        separator = netloc.find(':')
        if separator > 0:
            port = int(netloc[separator+1:])
            netloc = netloc[:separator]

        #sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        #sock = socks.socksocket()
        #sock.setproxy(socks.PROXY_TYPE_SOCKS5,"localhost", 10800)
        sock = self._get_socket()
        try: sock.connect((netloc, port))
        except socket.error:
            return None
        return sock

    def write_mp3(self, content):
        print 'Found mp3 file'
        m = re.search('last\.fm/user/\d+/([^/]+)/', self.path)
        if m:
            song_key = m.groups()[0]
            meta = track_info_cache.get(song_key)
            track_info_cache.delete(song_key)
            station = track_info_cache.get("station", "Unknown Station")
            data = dict(artist="unknown", album="unknown", title="unknown", station=station)
            if meta:
                data.update(meta)
            data["artist"] = data["creator"]
            try:
                debug(data)
                filename = unicode(args.format).format(**data)
            except Exception, e:
                print 'Oh no, could not lookup track info: %s' % e
                filename = 'filerand%d.mp3' % random.randint(1, 1000000)
        
        full_path = os.path.expanduser(os.path.join(args.output, filename))
        mkdir_p(os.path.dirname(full_path))
                
        try:
            f = open(full_path, 'wb')
        except:
            print 'Could not create file %s' % full_path
            full_path = os.path.expanduser(os.path.join(os.path.dirname(full_path), 'filerand%d.mp3' % random.randint(1, 1000000)))
            try:
                f = open(full_path, 'wb')
            except:
                print 'Oh no. Can\'t write to %s either' %s

        if f:
            print 'Writing %d bytes to %s' % (len(content), filename)
            f.write(content)
            f.close()
            try:
                self.lastfm.update_id3_tag(full_path, {'ARTIST': meta['creator'], 'TITLE': meta['title'], 'ALBUM': meta['album']})
            except:
                print 'Could not update ID3 tag'        
        
    def _do_method(self):
        (scheme, netloc, path, params, query, fragment) = urlparse.urlparse(self.path, scheme='http')
        if scheme != 'http' or fragment or netloc == None:
            self.send_error(400, 'Invalid URL %s' % self.path)
            return
        sock = self._connect(netloc)
        if sock is not None:
            if self.headers.has_key('Proxy-Connection'):
                del self.headers['Proxy-Connection']
            self.headers['Connection'] = 'close'

            sock.send("%s %s %s\r\n" % (self.command, self.path, self.request_version))

            for header in self.headers.items():
                sock.send("%s: %s\r\n" % header)
            sock.send("\r\n")

            found_xml = self.lastfm.xml_re.search(self.path)
            found_mp3 = self.lastfm.mp3_re.search(self.path)

            if self.lastfm.station_re.search(self.path):
                self.lastfm.update_station(self.path)
            
            if found_xml or found_mp3:
                content = self._read_write(sock, True)
                if found_xml and content is not None: 
                    print 'Found an xml'
                    self.lastfm.update_track_info_from_xml(content)
                if found_mp3 and content is not None:
                    self.write_mp3(content)
            else:
                self._read_write(sock)
        else:
            self.send_error(404, "Could not connect to host %s:%d" % (netloc, port))

    do_GET  = _do_method
    do_HEAD = _do_method
    do_POST = _do_method

    def _read_write(self, server_sock, save_data=False):
        rlist = [self.connection, server_sock]
        wlist = []
        http_content = ""
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
                                response_code = m.groups()[0]
                                if m:
                                    self.log_request(m.groups()[0])
                                    if response_code[0] != '2':
                                        save_data = False
                                else: self.log_request()
                            if save_data: http_content += data
                            self.connection.send(data)
                        else:
                            server_sock.send(data)
            if idle_count >= max_idle: break

        if save_data and len(http_content):
            needs_decompression = self._needs_decompression(http_content)
            http_content = self._strip_http_headers(http_content)
            if needs_decompression:
                buf = StringIO(http_content)
                http_content = gzip.GzipFile(fileobj=buf).read()
            return http_content
        else: return None


def run_server(addr, port):
    SocketServer.ThreadingTCPServer.allow_reuse_address = True
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
