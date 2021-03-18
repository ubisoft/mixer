Work Together
=====================

    
.. _work-together-page:

After you are connected to a Mixer server, you can create or join a room in order to collaborate with other users. The instructions of this section apply to any type of network connection.

.. _create-room:

Create a room
-------------

.. Warning:: 
    All the other users must use the same version of Blender and Mixer as the room creator.

To create a room after you are connected to a server, type a name in the **Room** text box (``Local`` in the picture below), then click on **Create room**.

.. image:: /img/create-room-localhost.png
   :align: center

.. Note:: 
    Creating a room uploads the the contents of your current Blender data to the server, which can take up to several minutes.

After the data has been uploaded, the Mixer panel lists the room in the **Server Rooms** list and others can join the room.

.. image:: /img/room-created-localhost.png
   :align: center


.. _join-room:

Join a room
------------

Anyone connected to a Mixer server can join a room as long as the user runs the same Blender and Mixer versions than the room creator.

.. image:: /img/join-room.png
   :align: center

.. warning::
    When you join a room, your current Blender data is cleared without notice and replaced by the room contents.

Joining the room will download the room contents and this process may take up to several minutes if the room is large or the network is slow.

.. _work-together:

Work together
-------------

While you are joined to a room, your Blender updates are sent to the other users and your Blender is updated with the changes received from the other users.

The updates are sent and received in real time with a few exceptions. When an object is not in **Object** mode (for instance a Mesh is in **Edit** or **Paint** mode), the updates to this object are not sent to the other users and the updates received from other users are not processed. All the updates will be sent or processed as soon as the object mode changes. There are some other cases when updates may be delayed, that are listed in :ref:`update delays <update-delays>`.

Some items are not synchronized, such as the 3D cursor, the current frame time, as well as other UI-related data.

.. tip::
    Read about the :ref:`caveats <caveats>` and save your work regularly during the session.


Leave a room
------------

When you leave a room by clicking on **Leave Room** in the Mixer panel, your Blender data is no more synchronized with the other room users.

If you want to join the room again later, your local data will be cleared and the room contents will be downloaded again into your Blender instance.

.. warning::
    When the last room users leaves the room, the room is destroyed unless **Keep Open** is checked in the room properties.