# Mixer

**Disclaimer**: This project is in alpha state and actively developped. Do not use it to edit your production assets without a backup or you might break them. In the code you might see references to VRtist or Shot Manager, which are other technologies/addons that are developped in our studio. Don't pay too much attention to related code since we plan to extract it in some kind of plugin mechanism.

## Introduction

Mixer is a Blender addon developped at Ubisoft Animation Studio for Real Time Collaboration in 3D edition. It allows multiple Blender users to work on the same scene at the same time. Thanks to a broadcasting server that is independent from Blender, it is also possible to implement a connection for other 3D editing softwares.

## Usage

You can download the addon from the release page and install it into Blender.

We didn't write extensive documentation for the user interface because it is still a work in progress and might be changed often. If will be done when the addon become more stable.

From the Mixer panel in the 3D viewport you can enter an IP address, a port and connect to a server. If you enter `localhost` and no Mixer server is already running on your computer, then the addon will start one in the background when you click `Connect`.

Then you can test locally between two Blender instances, or you can open the port on your router and give your external IP address to someone so he can join your session.

If you are on the Ubisoft network you don't need any router configuration but beware that the VPN apply some rules and you might not be able to reach the IP of someone else behind the VPN. A configuration that should work is to start the server on a workstation from a Ubisoft site, and to have all participants connect to it.

A Mixer broadcaster hosts rooms that are created by users. By default there is no room and someone needs to create one. The creator of the room will upload its current scene to the server, and this scene will be transfered to people that connect to the room. When all users leave a room, its content is destroyed, so someone needs to save the scene before everyone leave if you want to keep it. Optionally you can check the "keep open" checkbox so the room will remain open even if it has no users.

# Documentation

More documentation is available in the `doc` directory:

- [Data synchronization](doc/synchronization.md)
- [Developer environment](doc/development.md)
- [Releasing a new version](doc/release.md)
- [Unit testing](doc/unittest.md)
