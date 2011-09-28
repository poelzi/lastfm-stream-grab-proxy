lastfm-stream-grab-proxy
========================

lastfm-stream-grab-proxy is a simple HTTP proxy that captures streamed music from the last.fm music service.

How to use
----------

At the command line run:

> python lastfm-stream-grab-proxy.py

If you have the necessary python modules installed, a message will be displayed indicating that the proxy is ready.

Direct your web browser to use *localhost* port *8123*, and any mp3s streamed from last.fm will be saved to the current directory.

You may wish to use the included proxy auto-configure script - *proxy.pac* - to only use this proxy for last.fm services. If your web browser supports this then you can provide it the path to proxy.pac to do so.

Bugs
----

This program has not been extensively tested. There is very little sanity checking. Anything could happen; use at your own risk!

Filenames are constructed from artist and song names, and files will not be written if the constructed filenames are invalid.

This is not a high performance proxy so it is likely that you will want to switch it off when not streaming music, or use the included proxy auto-configure file to only use this proxy when talking to last.fm servers.
