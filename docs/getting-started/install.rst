Installation
============


.. _download:

Download
--------

Download the latest Mixer zip file from the `releases page <https://gitlab.com/ubisoft-animation-studio/mixer/-/releases>`_,
Choose the zip file listed in the **Other** section of the release you want to install.

 
.. image:: /img/download.png
   :align: center


.. _installing:

Install
-------

Install Mixer addon from the Blender Preferences panel and enable it.

.. image:: /img/install.png
   :align: center

After the addon is installed and enabled, a Mixer tab is displayed in the 3D viewport N-Panel.


Now close Blender to save your user preferences with the Mixer installation.

.. _testing:

Testing Mixer Locally
---------------------

The easiest way to test Mixer and find out what it can do for you is by using two Blender instances side by side on the same machine.

Start two Blender instances, lay them side by side and open in each one the Mixer panel in the 3D editor.

On one of the Blender (say the left one), click on the Connect button.

.. image:: /img/connect-localhost.png
   :align: center

If you are using Windows, the firewall will prompt you to allow access for Python.
Make sure to allow access for private networks.

.. image:: /img/firewall.png
   :align: center

This has launched a :term:`Mixer server<server>` in the background.
The Mixer server handles communication between several Mixer addons to synchronize the Blender data.

After the server is started and Blender connected to the server, the panel changes and becomes :

.. image:: /img/create-room-localhost.png
   :align: center

Now click on **Create Room** to create a :term:`room`

.. image:: /img/room-created-localhost.png
   :align: center

On the other Blender (say the right one), click on the Connect button.

.. image:: /img/join-room.png
   :align: center

You should be all setup. Move or create an object in one of the Blender, the change should be replicated to the other Blender.

In case of problems, see the :ref:`troubleshooting<faq-failures>` section.