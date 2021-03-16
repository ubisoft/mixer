# Contributing

## Repositories

The main repository is on Gitlab https://gitlab.com/ubisoft-animation-studio/mixer, please post your issues and merge requests there.

On the Gitlab repository you can see the CI tasks running (linting, unit tests, packing the addon and releases) and you have access to clean releases on the dedicated page https://gitlab.com/ubisoft-animation-studio/mixer/-/releases.

We do our development on both public Gitlab and an internal instance at Ubisoft. Mirroring is used to keep all repositories in sync (commits, tags and branches). We are slowly moving some important issues to the public repository to give more information to the community about our future developments and to open discussions.

We also have a mirror on Github https://github.com/ubisoft/mixer, as part of Ubisoft open source repositories.

## Contributing

You can [report any bug through issues on Gitlab](https://gitlab.com/ubisoft-animation-studio/mixer/-/issues). Please include the version you use in the issue and how to reproduce the bug, if possible. You can join a blender file, or a room file that you can save with the "Download Room" button in advanced room options.

 In the code you might see references to VRtist or Shot Manager, which are other technologies / addons that are developed in our studio. Don't pay too much attention to related code since we plan to extract it in some way, probably with a plugins strategy.

You can [submit a merge requests on Gitlab](https://gitlab.com/ubisoft-animation-studio/mixer/-/merge_requests), but keep in mind that the architecture of the addon is likely to change significantly in the next few months. For bugfixes, simple refactoring, typos, documentation, or things related to the usage of the Blender API you can directly submit the merge request. For features please also open an issue to discuss it, so we can think about how it would fit in the future architecture.

If you have quick questions or want to chat with us, we have a channel on the Blender chat dedicated to this addon: https://blender.chat/channel/mixer-addon

## License and copyright

The original code is Copyright (C) 2020 Ubisoft.

All code of the `mixer` package except the `mixer.broadcaster` sub-package is under the GPLv3 license. Code of the `mixer.broadcaster` sub-package is under the MIT license so feel free to extract it and use it directly in other python projects that are under a permissive license.

## Documentation

More documentation is available in the `doc` directory:

- [Client-Server protocol](protocol.md)
- [Data synchronization](synchronization.md)
- [Developer environment](development.md)
- [Releasing a new version](release.md)
- [Unit testing](unittest.md)
