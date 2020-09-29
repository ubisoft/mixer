# Hosting a Mixer server

## With a VPN

The simplest way of hosting a server is probably to use a VPN solution like https://www.zerotier.com/ (open source, with a free tier).

## With port forwarding

Alternatively, you can configure NAT rules on your router for port forwarding. 
Default port of Mixer is 12800, so a basic rule would be to forward 12800 on your router to 12800 on the computer hosting the server. 

Once this is done find your router public IP address with http://whatismyip.host/ and share it with other participants. They can connect to your server by replacing `localhost` with this IP in the panel. 

You also need to ensure you have no firewall blocking incoming connections.