Key Features
============

.. _features:

Overview
--------

Mixer synchronizes in real time the modifications done to the scene and the objects it contains.

During a collaboration session, Mixer display the position of other participants and highlights their selections.

.. image:: /img/select.png
   :align: center

While an object is not in Object mode (in Edit, Sculpt, Paint, ...) the local modifications to this object are
not sent in real time to the other participants and the other participants modifications are not applied immediately.
Pending local or remote modifications are applied when the object mode changes.

Some items are excluded from synchronization, mainly the current frame time, as well as UI-related data
like object modes and active list items.

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
Action          |Y|                 
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
Mesh            |P|                 except split normals, see [Edit]_
Metaball        |Y|                 See [Edit]_, [Convert]_
Movie clip      |Y|                 See [Media]_
Node group      |Y|                 Not extensively tested
Object          |P|                 Except motion paths, particles and physics. See [Convert]_ 
Paint curve     |N|
Particles       |N|
Shape key       |Y|
Scene           |Y|                 
Sound           |Y|                 See [Media]_
Text            |N|
Texture         |Y|
Volume          |N|
VSE             |P|                 Except meta strips. Not extensively tested
Workspace       |N|
World           |Y|
==============  ==================  ==============================================


.. [Image]
    Generated images and UDIMs are not synchronized. Image files are synchronized.

.. [Convert]
    The result of object conversion (**Object**/**Convert to** menu) is not synchronized.

.. [Edit]
    While an object is not in Object mode (in Edit, Sculpt, Paint, ...) the local modifications to this object are
    not sent to the other participants and the other participants modifications are not applied. Pending modifications
    are applied when the mode changes.

.. [Library]
    The following are not synchronized:

    * the results of **make local** and **reload**
    * library overrides

.. [Media] 
    Media files are synchronized. The result of **reload** or media path modification are not synchronized.
    
.. [GreasePencil]
    * the mask layer is not correctly synchronized
    * area fill is sometimes not correct
