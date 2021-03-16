# Mixer

Mixer is a Blender addon developed at Ubisoft Animation Studio for Real Time Collaboration in 3D edition. It allows multiple Blender users to work on the same scene at the same time.

**Disclaimer**: This project is in alpha state and actively developed. Do not use it to edit your production assets without a backup or you might break them.

## Features

The synchronization currently supports many Blender data types, with the notable exceptions of armatures, volumes and light probes. Refer to the online documentation for details about [synchronized data](https://mixer-github.readthedocs.io/en/latest/getting-started/features.html#what-is-synchronized)

## Usage

The [online documentation](https://mixer-github.readthedocs.io/en/latest/index.html) describes how to :

- [download and installl](https://mixer-github.readthedocs.io/en/latest/getting-started/install.html)
- perform [local tests](https://mixer-github.readthedocs.io/en/latest/getting-started/first-steps.html)
- get connected on a [LAN](https://mixer-github.readthedocs.io/en/latest/collaborate/lan.html) or through the [Internet](https://mixer-github.readthedocs.io/en/latest/collaborate/internet.html)

Updates are announced in the [mixer-addon](https://blender.chat/channel/mixer-addon) Blender Chat channel and as a Gitlab [announcement issue](https://gitlab.com/ubisoft-animation-studio/mixer/-/issues?label_name%5B%5D=Information).

## Key limitations

Using Undo in Object mode may undo other participants work. It may also lead to a Blender crashes in some cases.

[synchronized data](https://mixer-github.readthedocs.io/en/latest/getting-started/features.html#what-is-synchronized)

## Support

The active support repository is on Gitlab https://gitlab.com/ubisoft-animation-studio/mixer. Please post your issues and merge requests there.

The [Mixer Github repository](https://github.com/ubisoft/mixer) is a mirror that is part of Github [Ubisoft open source](https://github.com/ubisoft) projects group.

## Contributing

See [contributing](doc/README.md)

## License and copyright

The original code is Copyright (C) 2020 Ubisoft.

All code of the `mixer` package is under the GPLv3 license except code of the `mixer.broadcaster` sub-package, chich is under the MIT license.

