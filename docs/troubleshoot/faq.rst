Frequently asked questions
==========================

General
-------

Why is Mixer still in a 0. version ?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Mixer is still in development and using it may cause data loss. 

..
    TODO
    Will files saved by all participants contain the same data ?
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

    No

..
    TODO
    How does Mixer handle conflicting modifications ?
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

    Mixer currently handles only a few types of conflicting modifications, mainly

    * renaming datablocks with different names
    * linking 


How many users can collaborate in a session ?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

There is no hardcoded or configurable limit to the number of users that can collaborate.
The limit will come from the response times that depend on the number of user and scene complexity.


Can I start a standalone server without executing Blender ?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Yes. See :doc:`/advanced/standalone-server`. 

Why is room join sometimes so long ?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The server room records all modifications performed by all participants and does not store the current Blender state.
A new user who joins the room receives all the modifications since the room creation.

Networking
----------

Why does Connect fail with a timeout error ?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The machine with the address listed in the **Host** text box cannot be reached for one of the following reasons:

* the address is misspelled
* the machine is not up or the server is not started
* the machine cannot be reached because of a network configuration error

.. _ip-address:

How do I find the IP address my machine ?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The procedure depends on the operating system.

On Windows you can open a command prompt, then execute the ``IPCONFIG`` command.
The IP addresses of your machine are listed in the lines labeled ``IPv4 Address``


.. _faq-failures:

Failures and errors
-------------------


Why is the "Join Room" button grayed out ?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The **Join Room** button may be grayed out because your Blender version and/or Mixer version does not match
the Blender and Mixer version of the user who created the room.
By default, all users must use the exact same version of Blender and Mixer.

..
    TODO
    Blender has crashed. What happened ?
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
