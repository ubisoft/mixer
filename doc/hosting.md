# Hosting a Mixer server

The simplest way of hosting a server is probably to use a VPN solution like https://www.zerotier.com/ (open source, with a free tier).

When running a server under Windows 10, pay attention to the Windows firewall popup and take care to enable communication with the `python.exe` provided with Blender.

## Setup with Zerotier

Follow the [Zerotier](https://www.zerotier.com/) documentation to [setup a network](https://zerotier.atlassian.net/wiki/spaces/SD/pages/8454145/Getting+Started+with+ZeroTier)

### On the machine that hosts the server
- start Zerotier and connect to your Zerotier network
- start Blender, open the Mixer tray, leave `host` as `localhost`, leave `port` to the default value (12800), in `Advanced Options` check `Show server console` and click `Connect`. This starts the server with a console.

### On client machines
- start Zerotier and connect to your Zerotier network.
- start Blender, open the Mixer tray, leave `port` to the default value (12800), type in `host` the Zerotier address of the machine that hosts the server, then click `Connect`.

## Setup with port forwarding

Alternatively, you can configure NAT rules on your router for port forwarding. 
Default port of Mixer is 12800, so a basic rule would be to forward 12800 on your router to 12800 on the computer hosting the server. 

Once this is done find your router public IP address with http://whatismyip.host/ and share it with other participants. They can connect to your server by replacing `localhost` with this IP in the panel. 

You also need to ensure you have no firewall blocking incoming connections.