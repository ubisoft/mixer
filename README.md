# Mixer

**Disclaimer**: This project is in alpha state and actively developed. Do not use it to edit your production assets without a backup or you might break them. In the code you might see references to VRtist or Shot Manager, which are other technologies / addons that are developed in our studio. Don't pay too much attention to related code since we plan to extract it in some way, probably with a plugins strategy.

## Introduction

Mixer is a Blender addon developed at Ubisoft Animation Studio for Real Time Collaboration in 3D edition. It allows multiple Blender users to work on the same scene at the same time. Thanks to a broadcasting server that is independent from Blender, it is also possible to implement a connection for other 3D editing softwares.

## Repositories

The main repository is on Gitlab https://gitlab.com/ubisoft-animation-studio/mixer, please post your issues and merge requests there.

On the Gitlab repository you can see the CI tasks running (linting, unit tests, packing the addon and releases) and you have access to clean releases on the dedicated page https://gitlab.com/ubisoft-animation-studio/mixer/-/releases.

We do our development on both public Gitlab and an internal instance at Ubisoft. Mirroring is used to keep all repositories in sync (commits, tags and branches). We are slowly moving some important issues to the public repository to give more information to the community about our future developments and to open discussions.

We also have a mirror on Github https://github.com/ubisoft/mixer, as part of Ubisoft open source repositories.

## Usage

As a Blender user, you can download the addon from the Gitlab release page https://gitlab.com/ubisoft-animation-studio/mixer/-/releases and install it into Blender. Pick the archive under Assets/Other part of the last release.

We didn't write extensive documentation for the user interface because it is still a work in progress and might change often. We'll write a tutorial with screenshots and make videos once the UI become stable.

From the Mixer panel in the 3D viewport you can enter an IP address, a port and connect to a server. If you enter `localhost` and no Mixer server is already running on your computer, then the addon will start one in the background when you click `Connect`.

Then you can test locally between two Blender instances, or you can open the port on your router and give your external IP address to other people so they can join your session.

If all participants are in the same network everything should work directly. It it is not the case then the user hosting the server needs to setup its router for port forwarding and share its public IP.

A Mixer server hosts rooms that are created by users. By default there is no room and someone connected to the server needs to create one from the panel. The creator of the room will upload its current blender data to the server, and this data will be transfered to people that connect to the room.

When all users leave a room, its content is destroyed, so someone needs to save the file before everyone leave, if you want to keep it. Optionally you can check the "keep open" checkbox so the room will remain open even if it has no users.

As a Developer, you may want to read the [Developer environment](doc/development.md) documentation that details our setup.

## Contributing

You can [report any bug through issues on Gitlab](https://gitlab.com/ubisoft-animation-studio/mixer/-/issues). Please include the version you use in the issue and how to reproduce the bug, if possible. You can join a blender file, or a room file that you can save with the "Download Room" button in advanced room options.

You can [submit a merge requests on Gitlab](https://gitlab.com/ubisoft-animation-studio/mixer/-/merge_requests), but keep in mind that the architecture of the addon is likely to change significantly in the next few months. For bugfixes, simple refactoring, typos, documentation, or things related to the usage of the Blender API you can directly submit the merge request. For features please also open an issue to discuss it, so we can think about how it would fit in the future architecture.

If you have quick questions or want to chat with us, we have a channel on the Blender chat dedicated to this addon: https://blender.chat/channel/mixer-addon

## License and copyright

The original code is Copyright (C) 2020 Ubisoft.

All code of the `mixer` package except the `mixer.broadcaster` sub-package is under the GPLv3 license. Code of the `mixer.broadcaster` sub-package is under the MIT license so feel free to extract it and use it directly in other python projects that are under a permissive license.

## Documentation

More documentation is available in the `doc` directory:

- [Client-Server protocol](doc/protocol.md)
- [Data synchronization](doc/synchronization.md)
- [Developer environment](doc/development.md)
- [Releasing a new version](doc/release.md)
- [Unit testing](doc/unittest.md)
- [Hosting a Mixer server](doc/hosting.md)
