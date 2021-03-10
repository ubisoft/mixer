Starting a Standalone Server
============================

The Mixer server is usually started by the addon when the user clicks on the **Connect** button.
This ties the server to a machine with Blender installed and requires that Blender remains up on the machine that
started the server.

Using a standalone server allows you to run a server on a machine without Blender running or even installed.
The server machine may use a different operating system than the clients.

.. warning::
    Make sure to use the same Mixer version on the server and on the clients.

    This has only been tested with Python 3.7.4


To start a standalone server:

* download the Mixer zip file as described in the :ref:`download section <download>`
* unpack the zip file
* start a command prompt
* change directory to the directory that contains the ``mixer`` directory
* execute the command to start a server::

    python.exe -m mixer.broadcaster.apps.server --log-level INFO

:ref:`Find the IP address <ip-address>` of the machine that executes the server and communicate it to all the participants.

On all the participating Blender, follow the :ref:`connection instructions <next-users>`

.. warning::
    When all participants leave the room, the room is destroyed unless **Keep Open** is checked in the room properties.
