On a LAN
========

This section describes how to use Mixer on a LAN.

 check the "keep open" checkbox so the room will remain open even if it has no users.

.. _host-a-server:

Host a Server
-------------

Open the Mixer panel in the 3D editor, then click on the **Connect** button.

.. image:: /img/connect-localhost.png
   :align: center

If you are using Windows and starting a server for the first time,
the firewall will prompt you to allow access for Python like in the image below.
    
.. important::
    Make sure to allow access for private networks.

.. image:: /img/firewall.png
   :align: center


Your machine is now hosting a :term:`Mixer server<server>` and the panel changes to :

.. image:: /img/create-room-localhost.png
   :align: center


Now click on **Create Room** to create a :term:`room`

.. image:: /img/room-created-localhost.png
   :align: center

The server is now ready.

Find out the :ref:`IP address <ip-address>` of your machine and communicate it to the other
participants.


.. _connect:

Connect to a Server
-------------------

Start Blender and open the Mixer panel in the 3D editor.

In the **Host** text box, replace ``localhost`` by the IP address of the machine that hosts the server,
then click on the **Connect** button.

.. image:: /img/connect-ip.png
   :align: center

The panel now lists the room created on the server. Click on **Join Room**. 

.. image:: /img/join-room.png
   :align: center

You are ready to collaborate with your colleagues or friends.
