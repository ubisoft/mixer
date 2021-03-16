# Mixer

Mixer is a Blender addon developed at Ubisoft Animation Studio for Real Time Collaboration in 3D edition. It allows multiple Blender users to work on the same scene at the same time.

`#F00` **Disclaimer** `#F00`: This project is in alpha state and actively developed. Do not use it to edit your production assets without a backup or you might break them.

## Features

The synchronization currently supports many Blender data types, with the notable exceptions of armatures, volumes and light probes. Refer to the online documentation for details about [synchronized data](https://mixer-github.readthedocs.io/en/latest/getting-started/features.html#what-is-synchronized)

## Usage

The [online documentation](https://mixer-github.readthedocs.io/en/latest/index.html) describes how to :
- [download and installl](https://mixer-github.readthedocs.io/en/latest/getting-started/install.html)
- perform [local tests](https://mixer-github.readthedocs.io/en/latest/getting-started/first-steps.html)
- get connected on a [LAN](https://mixer-github.readthedocs.io/en/latest/collaborate/lan.html) or through the [Internet](https://mixer-github.readthedocs.io/en/latest/collaborate/internet.html)


Addon updates are announced in the [mixer-addon](https://blender.chat/channel/mixer-addon) Blender Chat channel and as a Gitlab [announcement issue](https://gitlab.com/ubisoft-animation-studio/mixer/-/issues?label_name%5B%5D=Information).


## Key limitations

Using Undo in Object mode may undo other participants work and lead to crashes in some case


## Repositories

The main repository is on Gitlab https://gitlab.com/ubisoft-animation-studio/mixer, please post your issues and merge requests there.

The Github repository at https://github.com/ubisoft/mixer, is a mirror that is part of Ubisoft open source initiative.

## License and copyright

The original code is Copyright (C) 2020 Ubisoft.

All code of the `mixer` package except the `mixer.broadcaster` sub-package is under the GPLv3 license. Code of the `mixer.broadcaster` sub-package is under the MIT license so feel free to extract it and use it directly in other python projects that are under a permissive license.

## Contributing

[Contributing](doc/README.md)

