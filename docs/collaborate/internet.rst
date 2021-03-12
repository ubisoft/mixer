On the Internet
===============

.. _vpn:

With a hosted VPN
-----------------

Hamachi
^^^^^^^

TODO

Other VPN software
^^^^^^^^^^^^^^^^^^

Mixer has been reported to work successfully with other VPN software:

* `Zerotier <https://www.zerotier.com/>`__
* `OpenVPN <https://openvpn.net/>`__ and `portmap.io <https://portmap.io/>`__ : some details in `this issue <https://gitlab.com/ubisoft-animation-studio/mixer/-/issues/23>`__

.. _port-forwarding:

With port forwarding
--------------------

Collaborating over the Internet without a VPN may require to setup port forwarding and is more involved.

On the network that hosts the server
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
The user who creates the server must setup port forwarding on his router:

* on the machine that hosts the server:

   * :ref:`setup and start <host-a-server>` a Mixer server. Keep ``localhost`` as the value in the **Host** text box.
   * :ref:`find the IP address<ip-address>` of the machine that hosts the server, say ``192.168.0.10``

* on the router:

   * find the *public* address of the router, say ``10.25.125.142``
   * setup a port forwarding rule to the machine that hosts the server (``192.168.0.10`` in our example),
     and to the Mixer port (``12800`` by default).
   * check or edit the value of the *public* forwarded port:
  
     * If the public forwarded port can be set to ``12800``, use this value.
       This setup creates a forwarding rule from ``10.25.125.142:12800`` to ``192.168.0.10:12800``.
     * If the public forwarded port cannot be set to ``12800``, configure it to a permitted value, say ``9090``.
       This setup creates a forwarding rule from ``10.25.125.142:9090`` to ``192.168.0.10:12800``


On the other users locations
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Start Blender and open the Mixer panel in the 3D editor.

* In the **Host** text box, replace ``localhost`` by  the *public* address of the router on the server location,
  (``10.25.125.142`` in our example).

.. image:: /img/connect-port-forward.png
   :align: center

* *If the public forwarded port is not* ``12800``:
 
   * Open the addon preferences 
  
   .. image:: /img/open-preferences.png
      :align: center

   * in the **Port** box type the public forwarded port number, ``9090`` in our example
  
   .. image:: /img/preferences-port.png
        :align: center

   * close the preferences windows

* in the Mixer panel, click on the **Connect** button.

From now on, any participant can create a room and the others can join the room.