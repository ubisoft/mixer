Get connected
=============

This section describes how several users can connect to the same Mixer server using a LAN or through the Internet.

.. tip::
    It is recommended that you try Mixer locally before you attempt to connect on a network.

Whatever the network type, one user will have to create a server that the other users can connect to.

.. _lan:

On a LAN
----------

.. _host-a-server:

Host a Server
^^^^^^^^^^^^^^^^^^

Open the Mixer panel in the 3D editor, check that the **Host** text box contains ``localhost`` then click on the **Connect** button.

.. image:: /img/connect-localhost.png
   :align: center
   :alt: Connect to localhost

If you are using Windows and starting a server for the first time,
the firewall will prompt you to allow access for Python like in the image below.
    
.. image:: /img/firewall.png
   :align: center

.. important::
    Make sure to allow access for private networks.

Your machine is now hosting a Mixer server and the panel changes to :

.. image:: /img/create-room-localhost.png
   :align: center

The server is now ready. Find out the :ref:`IP address <ip-address>` of your machine and communicate it to the other participants.


.. _connect:

Connect to a Server
^^^^^^^^^^^^^^^^^^^

Start Blender and open the Mixer panel in the 3D editor.

In the **Host** text box, replace ``localhost`` by the IP address of the machine that hosts the server,, which is ``192.168.0.48`` in the example below, then click on the **Connect** button.

.. image:: /img/connect-ip.png
   :align: center

The panel now lists the room created on the server. Click on **Join Room**. 

.. image:: /img/join-room.png
   :align: center

You are ready to :ref:`collaborate <work-together-page>` with your colleagues or friends.


.. _internet:

On the Internet
-----------------

.. _vpn:

With a hosted VPN
^^^^^^^^^^^^^^^^^^^^

VPN software like Hamachi, Zerotier and others can be used to execute a Mixer session over the Internet. The overall process is as follows:

- all participants:

    - download, install and start the VPN software using the VPN software instructions

- one participant:
  
    - creates a VPN network using the VPN software instructions
    - starts Blender, open the Mixer panel, leaving ``localhost`` in the panel **Host** text box, then click **Connect** to create a server
    - finds the VPN address of his machine and communicate it to others

- the others:

    - connect to the VPN network using the VPN software instructions
    - start Blender, open the Mixer panel and fill the **Host** text box with the VPN address of the server.
  
Hamachi
"""""""

Follow this tutorial to easily install and configure an Hamachi server:

.. raw:: html

   <div style="position: relative; padding-bottom: 45%; height: 0; overflow: hidden; max-width: 80%; border:solid 0.1em; border-color:#4d4d4d; align=center; margin: auto;">
      <iframe width="560" height="315" src="https://www.youtube.com/embed/07ifLm0K0mI" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
   </div>
   <br>
   

If the connection to the server fails, see the :ref:`networking FAQ <faq-network>`.


Other VPN software
""""""""""""""""""""
Mixer has been reported to work successfully with other VPN software:

* `Zerotier <https://www.zerotier.com/>`__
* `OpenVPN <https://openvpn.net/>`__ and `portmap.io <https://portmap.io/>`__ .



.. _port-forwarding:

With port forwarding
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. use addresses from https://tools.ietf.org/html/rfc5737

Collaborating over the Internet without a VPN may require to setup port forwarding and is more involved.

On the network that hosts the server
""""""""""""""""""""""""""""""""""""""""""""""
The user who creates the server must setup a TCP port forwarding rule on his router:

* on the machine that hosts the server:

   * :ref:`setup and start <host-a-server>` a Mixer server. Keep ``localhost`` as the value in the **Host** text box.
   * :ref:`find the IP address<ip-address>` of the machine that hosts the server, say ``192.168.0.10``

* on the router:
  
   * find the *public* IP v4 address of the router using the router administration tool or http://whatismyip.host/.
     You will need to share this address with other participants
     Say you found the public IP v4 address of your router is ``203.0.113.17``
   * setup a TCP port forwarding rule to the machine that hosts the server (``192.168.0.10`` in our example),
     and the TCP port used by Mixer (``12800`` by default).
   * check or edit the value of the *public* forwarded port:
  
     * If the public forwarded port can be set to ``12800``, use this value.
       This setup creates a TCP port forwarding rule from ``203.0.113.17:12800`` to ``192.168.0.10:12800``.
     * If the public forwarded port cannot be set to ``12800``, configure it to a permitted value, say ``9090``.
       This setup creates a TCP port forwarding rule from ``203.0.113.17:9090`` to ``192.168.0.10:12800``


On the other users locations
"""""""""""""""""""""""""""""""""
Start Blender and open the Mixer panel in the 3D editor.

* In the **Host** text box, replace ``localhost`` by  the *public* address of the router on the server location,
  (``203.0.113.17`` in our example).

.. image:: /img/connect-port-forward.png
   :align: center

* *If the public forwarded port is not* ``12800``:
 
   * Open the Mixer preferences using the Mixer panel title bar setings icon
  
   .. image:: /img/open-preferences-internet.png
      :align: center

   * in the **Port** text box type the public forwarded port number, ``9090`` in our example
  
   .. image:: /img/preferences-internet-port.png
        :align: center

   * close the preferences windows

* in the Mixer panel, click on the **Connect** button.

You are ready to :ref:`collaborate <work-together-page>` with your colleagues or friends.
