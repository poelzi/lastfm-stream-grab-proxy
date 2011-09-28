function FindProxyForURL(url, host)
{
    if (shExpMatch(host, "*.last.fm"))
    {
        return "PROXY localhost:8123; DIRECT";
    }
}
