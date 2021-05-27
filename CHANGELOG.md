# 1.1.0 (WIP)

## Documentation

- Fix README.md (thanks @XenioxYT, @b4zz4)
- Explicit warning about undo limitations.

# 1.0.0 (2021-04-21)

## Documentation

- Online user [documentation](https://ubisoft-mixer.readthedocs.io/en/latest/)
- Video [tutorials](https://www.youtube.com/channel/UCVfQBSBBvo8GMndYy2TzQHw)

## Features

- Armatures: synchronization
- Geometry node tres: synchronization
- Synchronization: ignore scene camera
- UI: add a prefix to default room name based on user name
- UI: add the list of users per room
- UI: improved visibility of Connect and Disconnect buttons for existing rooms
- UI: removed unused "Join" progress value
- UI: improve warning feedback when Blender or Mixer versions are not the same as the room ones

## Fixes

- Synchronization: ignore "select" attribute everywhere
- UI: color for other users is now accurate
- Node trees: fix missing connections
- Readme fixes (thanks [bangseongbeom](https://github.com/bangseongbeom))

# 0.22.0 (19-03-2021)

## Features

- UI: simplification of Mixer panel
- UI: property panel for the selected room
- UI: advanced and developer properties moved to add-on preferences
- UI: toggle between Mixer and VRtist panels
- Grease pencil: synchronize effects

## Fixes

- Object modifier: synchronization error on Blender 2.92
- VSE: synchronization error on Blender 2.92
- UI: invalid values for user color
- Synchronization: ignore 3D cursor, viewport transform modes, snapping and render engine

## CI

- Tests: run unit tests against several Blender versions

# 0.21.1 (22-02-2021)

## Fixes

- Addon load failure on Blender 2.92 RC

# 0.21.0 (19-02-2021)

## Features

- Animation data: synchronization of key frames, curves and drivers
- MovieClip: synchronization
- Scene annotations: synchronization
- TextCurve: synchronization (with builtin VectorFont only)
- Texture: synchronization
- UI: simplify the Mixer panel and make selection gizmos settings more accessible
- UI: updates received when not in OBJECT mode are retained until OBJECT mode is entered
- UI: can disable display of peer names on selection boxes in Mixer gizmos preferences

## Fixes

- Material nodes: fix possibly missing nodes and connections
- Lights: after light morphing, new type-specific attributes were not synchronized
- Libraries: synchronization error after using "duplicate linked" on an Object from a library
- Undo: fix some synchronization failures and crashes
- UI: selection box displayed with offset for instances of collections with instance_offset
- UI: room creation failed after loading a new file without disconnecting

## Breaking changes

- require Blender 2.91.0

# 0.20.0 (22-01-2021)

## Features

- Shared folders: contents of shared folders are not synchronized by Mixer, but must be synchronized by a user-provided
  mechanism like a network share or a file synchronization tool.
- Libraries: synchronization, including nested libraries. Overrides, make local, reload, duplicate linked, self linking are not supported.
- Require identical Blender and Mixer versions among all users of a room.

## Fixes

- UI: display user name on a single item when a collection is selected
- Room join: fix impossible join because of incompatible VRtist protocol setting
([#15](https://gitlab.com/ubisoft-animation-studio/mixer/-/issues/15))
- Mesh: fix crash when receiving a mesh in a mixed Linux/windows room
([#17](https://gitlab.com/ubisoft-animation-studio/mixer/-/issues/17))
- Material: fix synchronization failure after removing a shading node
- Material: fix a crash after receiving a Material node_tree update
- LayerCollection: fix synchronization failure
- Logging: cleanup

## Breaking changes

- require Blender 2.83.9

# 0.19.0 (18-12-2020)

## Features

- Shared folders
- Mesh: synchronization of vertex groups and shape keys
- Curves: synchronization of shape keys
- View layers: synchronization
- Custom properties: synchronization

## Fixes

- Object parenting: synchronization of child object location
- Decimate modifier: synchronization of delimit attribute
- Curves: exception when loading empty curve
- Metaballs: error messages
- Material assignment: synchronization with multiple materials
- Logging: more focused messages in warning mode


# 0.18.0 (2020-11-18)

## Features

- UI: remove "experimental synchronization" checkbox. Blender generic synchronization mode is now the default mode.
- UI: move VRtist UI into its own panel.
- UI: simplify Mixer panel.
- Bezier curves: synchronization.
- Node trees: synchronization for objects, world and lights (except nodes groups).
- VRtist: sky synchronization.

## Improvements

- Performance: transfer less mesh data with linked meshes and when modifiers are updated.

## Fixes

- Image: image data is synchronized when source folder does not exist on receiver machine.
- Mesh: new part not linked to collection after separate.
- Mesh: misc synchronization errors (UV map, existing faces).
- Grease pencil: duplicate layers during session.
- Metaball: update fixes
- Synchronization: update datablock reference (e.g. TextureNodeImage.image, ArrayModifier.object_offset, Scene.camera).
- Synchronization: some updates performed in non-object mode were ignored.
- Server: dangling connections

## Other

- Tests: add tests for Mesh synchronization
- Refactoring: bpy_prop_collection synchronization.
- Refactoring: mesh synchronization.
- Logging: remove meaningless ReferenceError messages.
- Logging: add exception type when logging an exception.
- Logging: add information about Blender version, Mixer version and loaded addons.
- Code health: remove stats module


# 0.17.0 (2020-10-15)

## Features

- Object modifiers (except those using Image and Curve)
- GreasePencil modifiers
- Change instances collection
- VRtist: move animations keys times
- VRtist: now receives start/end frame
- VRtist: per keyframe interpolation
- VRtist: baked mesh optimization

## Bugfix

- Fix synchronization problems after renaming
- Fix synchronization problems after simultaneous creation
- Fix create object and edit with object popup breaks synchronization
- Fix synchronization problem after loading an asset with unsupported features, such as armatures
- Fix synchronization problem after creating an object then editing its properties with the properties popup
- Guard against infinite recursion when synchronized data has circular references

## Tests

- Add tests with multiple Blender that perform simultaneous modifications
- Add a server option to simulate network latency

## CI/CD

- Add optional build info to the version tag
- Upgrade Flake and Black

## Documentation

- Update docs/synchronization.md to describe incremental synchronization
- Update docs/hosting.md with instructions about Zerotier

## Refactor

- Split blender_data/proxy.py into multiple files


# 0.16.1 (2020-09-22)

## Bugfix

- VRtist: Don't restore original mesh after baking if the original object was not a mesh

## CI/CD

- Merge gitlab.com CI script into main CI script using `only` and `except` clauses.

# 0.16.0 (2020-09-17)

## Features

- Put back sync of `proxy_storage` and `proxy_dir` fields of SequenceEditor (#146)
- VRtist: Packed frame related diffs for VRtist client

## Bugfix

- Fix mesh being triangulated after leaving edit mode. (#191)
- Fix crash occurring when vertex group data is inconsistent (#121)
- Fix send_base_mesh crash
- Fix random test failure with room not joinable yet
- Disconnects clients properly when server is killed
- VRtist: Fixed synchro stuff

## Documentation

- update release.md (#206)

## CI/CD

- Add optional build info to the version tag
- Upgrade Flake and Black

# 0.15.0 (2020-08-12)

## Features

- Independent time between clients of a same room & Blender - VRtist time sync (#195)

# 0.14.1 (2020-08-07)

## Bugfix

- Handle error with unsynchronized volumes (#200)
- Handle error with unsynchronized packed images (#199)
- Recursion error with unsynchronized shape_keys (#164)
- Logging: format exception traceback (#149)
- Room upload may block (#174)
- Fix failure on Linux related to os.getlogin() (#198)

## Misc:

- Refactoring and documentation for open sourcing (#132)
- Do not run all CICD pipelines on glitlab.com (#192)

# 0.14.0

## Features

- Display percentage of data received when joining a room (#186)

## Optimization

- Server: give more importance to received messages and improve concurrency when a client join a large room (#183)

# 0.13.1 (2020-07-23)

## Bugfix

- Remove type of bl_info because Blender cannot parse it

# 0.13.0 (2020-07-23)

## Optimization

- Client-Server connection stabilization: send less messages for client/room updates, better usage of mutexes, refactor server.py (#162)

## Misc.

- Display version string in Mixer panel titlebar (#154)

# 0.12.0 (2020-07-22)

## Features

- Add preferences UI (#63)

# 0.11.0 (2020-07-17)

## Features

- Display view frustums, names and object selections of other users (#3)
- Image support for Env Texture Node (#128)

## Bugfix

- RuntimeError: Error: Object 'Cylinder' can't be hidden because it is not in View Layer 'View Layer' (#100)
- VSE sync fixes (#133)
- Catch exceptions in write_attribute/save (#134)
- Disable VSE properties that cause hard crash on multi scenes files (#146)
- TypeError: add() takes no arguments (1 given) (#148)
- KeyingSet related error (#152)

# 0.10.1 (2020-07-09)

## Bugfix

- Apply transform (#122)

# 0.10.0 (2020-07-09)

## Features

- Add options to download and upload room contents (#59)

## Documentation

- Move some documentation from the README.md file to dedicated `doc/` folder
- Add synchronization documentation

# 0.9.1 (2020-07-08)

## Documentation

- Add LICENSE file to repository and to output zipped addon

# 0.9.0 (2020-07-07)

## Features

- Overhaul of panels UI (#80)
- Prototyping video sequencer synchronization (#124, #126)

## Bugfix

- Ignore properties from other enabled addons (#107)
- Object UUIDs duplication (#120)
- Partial fix for flickering during collaboration (#127, WIP)

## Documentation

- Cleanup README a bit for Open Sourcing (#129, WIP)

# 0.8.0 (2020-07-02)

## Features

- Shot Manager synchronization with VRtist

## Bugfix

- Grease Pencil Animation issue (#86)
- Minor fixes

# 0.7.0 (2020-07-01)

## Features

- Synchronize World including its node_tree (without image files)

## Bugfix

- Fix broken synchronization after exception
- Fix exception during remove from collection

# 0.6.2 (2020-06-29)

## CI/CD

- Adapt CI/CD scripts to new cloud based gitlab runner (#111)

# 0.6.1 (2020-06-25)

## Bugfix

- Perforce deployment (#110)

# 0.6.0 (2020-06-24)

## Features

- Full synchronization of lights and cameras
- Synchronization of metaballs
- Synchronization of Scene objects: all panels excluding keying sets and and view layers

## Bugfix

- Failure during initial scene transfer

# 0.5.2 (2020-06-24)

## Bugfix

- Fix fatal assertion in decode_mesh
- Fix error when writing to unknown attribute
- Fix uncaught exception

# 0.5.1 (2020-06-17)

## Bugfix

- Fix deploy on perforce

# 0.5.0 (2020-06-17)

## Technical

- Resolve "Add deploy stage and environments handling to CICD" (#94)

# 0.4.0 (2020-06-16)

## Bugfix

- Resolve "Crash in send_animated_camera_data" (#92)

# 0.3.1 (2020-06-16)

## Bugfix

- Resolve "Scene \_\_last_scene_to_be_removed\_\_ is sometimes created" (#89)
- Resolve "Gracefully ignore unknown attributes on receive" (#87)
- Resolve "JSON decode error" (#88)

## Technical

- Resolve "Implement CI/CD for Release" (#48)

# 0.3.0 (2020-06-10)

## Release Highlights

- Implementation of generic data serialization/deserialization (accessible from experimental flag in GUI)
- Animated camera parameters for VRtist
- Better logging

# 0.2.0 (2020-05-13)

## Release Highlights

- Official new name: Mixer
- More visibility synchronization
- Collections and multiple scenes
- Time control from VRtist

## Features

- Time and keyframe control from VRtist (#71)
- Support more object visibility attributes (#54)
- Collections linked to multiple collections (#44)

## Bugfix

- Fix crash during scene switch (#36, #42)
- Undo failures for collection rename and other cases (#45)
- Fix scene rename (#43)

## Technical

- Code formatting, linting and developer environment doc (#66)
- Better python imports (#67)
- Tests in CI/CD (#68)

# 0.1.0alpha (2020-04-03)

## Release Highlights

First _official_ release of dccsync (to be renamed one day) addon for Blender. This addon allows to work collaboratively between multiple Blender and [VRtist](https://gitlab-ncsa.ubisoft.org/motion-pictures/vrtist).

This alpha version offers basic functionnality to start working in collaboration. However it is not safe at all and can break the scene of the first user that connects to a session.

## Features

Here are features supported for the synchronization of data among Blender clients.

- Object sync
  - Transform
  - Parenting
  - Collections
- Mesh sync
  - Geometry
    - vertices, edges, faces
    - bevel, crease, seam, uv
  - Custom Split Normals
  - Shape Keys
  - Vertex Colors
  - Vertex Groups
- Collections
  - Name
  - Objects
  - Parenting
- Scenes
  - However, while it is technically possible to create and sync scenes, many crash of Blender occurs when switching between them. This issue will be resolved in the next release of dccsync.
- Grease Pencil Objects

## Known Bugs/Limitations

These bugs and limitations are known and will be addressed in future releases:

- Collections
  - Linked into multiple collections
- Scenes
  - Changing active scene can lead to crashes
  - Can possibly happen when changing view layers
- Undo might not work in some cases
- Materials
  - Incomplete, only sync a subset of Principled Material Node
  - Textures will be erased on the first client when sync happen between all of them
- Some grease pencil objects will not be fully synced
- Performance: right now meshes can be fully re-synched even when the geometry is not changed (just selecting another shape key trigger the resync). It can be quite expensive for big meshes.
- Working from computers on differents networks has not been tested enough

Things that are not mentionned are not supported at all right know, in particular:

- Modifiers
- Contraints
- Bones
- Animation
- Specific object attributes (lights attributes, cameras attributes)
- World
- Curves (they will be synched but as meshes, not curves)
- etc.

# Reporting issues

If the issue is for sync Blender - Blender, send an email to:

- laurent.noel@ubisoft.com
- philippe.crassous@ubisoft.com

If the issue if for sync Blender - VRtist, send an email to:

- thomas.capelle@ubisoft.com
- sylvain.magdelaine@ubisoft.com
- nicolas.fauvet@ubisoft.com
