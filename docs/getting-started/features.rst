Key Features
============

.. _features:

Overview
--------

Mixer synchronizes in real time the modifications done to the scene and the objects it contains. During a collaboration session, Mixer displays the position of other participants and highlights their selections. 

.. image:: /img/select.png
   :align: center

See :ref:`work-together` for more details.

.. _synchronized:

What is synchronized
--------------------

This table described the status of synchronization for the main Blender data types.
The custom properties of all datablocks are also synchronized

.. |Y| replace:: Yes
.. |N| replace:: No
.. |P| replace:: Partial


==============  ==================  ==============================================
Data                  Status          Comments
==============  ==================  ==============================================
Action          |Y|                 See [Delay]_
Armature        |N|
Brush           |N|
Collection      |P|                 Except collection children ordering
Camera          |Y|
Curve           |P|                 Except surface and Bézier curves. See [Edit]_, [Convert]_
Grease pencil   |Y|                 See [GreasePencil]_, [Edit]_, [Convert]_
Image           |P|                 See [Image]_, [Media]_
Keying sets     |N|
Library         |P|                 See [Library]_             
Light           |Y|
Light probe     |N|
Line style      |N|
Mask            |N|
Material        |Y|                 
Mesh            |P|                 except split normals, custom properties, see [Edit]_
Metaball        |Y|                 See [Edit]_, [Convert]_
Movie clip      |Y|                 See [Media]_
Node group      |P|                 Not extensively tested, see [NodeGroups]_
Object          |P|                 Except motion paths, particles and physics. See [Convert]_ 
Paint curve     |N|
Particles       |N|
Shape key       |Y|
Scene           |Y|                 See [Delay]_
Sound           |Y|                 See [Media]_
Text            |N|
Texture         |Y|
Volume          |N|
VSE             |P|                 Except meta strips. Not extensively tested
Workspace       |N|
World           |Y|
==============  ==================  ==============================================

.. [Convert]
    The result of object conversion (**Object**/**Convert to** menu) is not synchronized.

.. _update-delays:

.. [Delay]
    Some updates may be delayed until another modification is detected:

    * scene annotations: try to click around in the background of the 3D viewport
    * animation curves names : try to toggle the curve *Enable* checkbox twice.

.. [Edit]
    While an object is not in Object mode (in Edit, Sculpt, Paint, ...) the local modifications to this object are
    not sent to the other participants and the other participants modifications are not applied. Pending modifications
    are applied when the mode changes.

.. [GreasePencil]
    * the mask layer is not correctly synchronized
    * area fill is sometimes not correct

.. [Image]
    Generated images and UDIMs are not synchronized. Image files are synchronized.

.. [Library]
    Nested libraries will fail when shared folders are not in use. The following are not synchronized:

    * the results of **make local** and **reload**
    * library overrides

.. [Media] 
    Media files are synchronized. The result of **reload** or media path modification are not synchronized.

.. [NodeGroups]

   **Collection** sockets in geometry node groups cause synchronization failures and may crash

.. _caveats:

Caveats
-------

In addition to the limitations listed in the previous section, you should be aware of the following :

* using undo may cause unexpected behavior and cause crashes. Using undo while in **Object** mode may undo other participants changes.
* the files saved by all participants are :ref:`not exactly identical <saves-not-identical>`.
