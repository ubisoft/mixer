Frequently asked questions
==========================

.. _faq:

General
-------

Can I control access to the server or a room?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

No. Anyone who knows the address a Mixer server and has network access to the server can join a room an collaborate.

Can I control access to parts os a scene?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

No. All room users can edit all the Blender data without restriction.
If two users edit simultaneously the very same elements data corruption will occur.


.. _saves-not-identical:

Will files saved by all participants contain the same data?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Not exactly. Here is a non limiting list of situations that will cause Blender files saved by participants to differ:

- Creating or updating data that is not synchronized: see the list of :ref:`synchronized data <synchronized>`
- Simultaneous modifications of the same data by several users. 
- Usage of media files: file paths will be different unless shared folders with the same base folder are used.
- Extreme network latency

How does Mixer handle simultaneous and conflicting modifications?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Mixer handles these simultaneous and conflicting modifications:

- simultaneously creating objects with the same name
- renaming datablocks with different names
- linking different objects to the same collection

The following conflicting modifications are not handled, and in these cases, the participants will end up with 
different attribute values:

- setting an attribute with different values.
- adding or removing array elements, like in object modifier or grease pencil layers


How many users can collaborate in a session?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

There is no hardcoded or configurable limit to the number of users that can collaborate.
The limit will come from the response times that depend on the number of users, scene complexity and network performance.


Can I have a server running without executing Blender?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Yes. See :doc:`/advanced/standalone-server`. 

Why is room join sometimes so long?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The server room records all modifications performed by all participants and does not store the current Blender state.
A new user who joins the room receives all the modifications since the room creation.

.. _faq-network:

Networking
----------

Why does Connect fail with a timeout error?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The machine with the address listed in the **Host** text box cannot be reached for one of the following reasons:

* the address is misspelled
* the machine is not up or the server is not started
* the machine cannot be reached because of a network configuration error. See the documentations for connecting in a :ref:`LAN <lan>` or over the :ref:`Internet <Internet>`.

How can I fix a Hamachi connection failure?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
The Hamachi setup may have configured your Hamachi network in public mode instead of private.
An Hamachi community discussion explains how to `change to private network <https://community.logmein.com/t5/LogMeIn-Hamachi-Discussions/Changing-to-a-private-network/m-p/196116/highlight/true#M16898>`_.


.. _ip-address:

How do I find the IP address my machine?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The procedure depends on the operating system.

On Windows you can open a command prompt, then execute the ``IPCONFIG`` command.
The IP addresses of your machine are listed in the lines labeled ``IPv4 Address``

.. _faq-failures:

Failures and errors
-------------------

Why is the "Join Room" button grayed out?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The **Join Room** button may be grayed out because your Blender version and/or Mixer version does not match the Blender and Mixer version of the user who created the room.
By default, all users must use the exact same version of Blender and Mixer.

Why does my update fail to appear on other participant Blender?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Check the following :

- are you and the other participants actually connected to the server? When you are connected, the Mixer panel should display the **Disconnect** button in blue.
- are you attempting to synchronize data that is not or partially supported? See the list of :ref:`synchronized data <synchronized>` and their restrictions.

If you think you have found a bug, please :doc:`report an issue <issue>`.

Other users seem not to have the same scene content than I do
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

During a session it may appear that one or more participants mention they don't see the same things as you do.
This usually appends because of one of these reasons:

- a participant used a feature of Blender that is not yet covered by Mixer. See :ref:`Features <synchronized>`
- a participant called an undo action. See :ref:`Caveats - Undo / Redo <caveats>`
- or there is a bug that went through our quality check process. Please repport it using these guidelines: :doc:`Report an issue <issue>`.

..
    TODO
    Blender has crashed. What happened?
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
