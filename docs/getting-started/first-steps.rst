First steps
===========

The easiest way to test Mixer and find out what it can do for you is by using two Blender instances side by side on the same machine.

Start two Blender instances, lay them side by side. In each one, open the Mixer panel in the 3D editor.


.. _first-steps:

Create a Server
----------------------------

On one of the Blender (say the left one), click on the **Connect** button.

.. image:: /img/connect-localhost.png
   :align: center

If you are using Windows, the firewall will likely prompt you to allow access for Python.

.. warning::

    Make sure to check **Private networks** and click on **Allow access**.

.. image:: /img/firewall.png
   :align: center

This has launched a :term:`Mixer server<server>` in the background.
The Mixer server handles communication between several Mixer addons to synchronize the Blender data.

After the server is started and Blender connected to the server, the panel changes.
Now click on **Create Room** to create a :term:`room`

.. image:: /img/create-room-localhost.png
   :align: center

After the room is created, the **Server rooms** section of the Mixer panel displays the room name, which is *Local* in
the picture below.

.. image:: /img/room-created-localhost.png
   :align: center

The server is now ready to accept a connection from a new client.

Connect to a Server
-------------------

On the other Blender (say the right one), open the Mixer panel and click on the **Connect** button.

.. image:: /img/connect-localhost.png
   :align: center

This connects Mixer to the server we have just setup before. The **Server Rooms** section lists the room name.

.. warning::

    Connecting to a room wipes out your current data and replaces it with the data from the Mixer server.

.. image:: /img/join-room.png
   :align: center

At this point, both Blender are connected to the server and their data is synchronized. 

Creating or moving an object in one Blender updates the object in the other Blender.

Read more about Mixer :ref:`features <features>` and try by yourself.
