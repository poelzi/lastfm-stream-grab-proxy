function FindProxyForURL(url, host)
{
    if (shExpMatch(host, "*.last.fm") && shExpMatch(url, "http://*"))
    {
        return "PROXY localhost:8123; DIRECT";
    }

    return "DIRECT";
}
