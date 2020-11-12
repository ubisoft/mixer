# Mixer Client-Server Protocol

## Introduction

Mixer is based on message broadcasting: the server broadcasts messages from all clients of a [Room](#room) to other clients of the same room. Messages are also accumulated in a list of the room. When a new client want to join the room, the server starts by sending him all messages from the list before putting him in the room.

This document explain the behavior of the server when he receives Mixer messages types.

## Concepts

### Client

A client is identified by the server with its IP and port, which are concatenated in the form `{IP}:{port}` to create a unique client id.

The server stores attributes for each client, represented as a json object. Some attributes are defined by the server and cannot be changed by the client, the remaining are custom attributes. Any client application can defined new custom client attributes for its own need. We define standard names for some custom attributes to ease communication between clients of separate domains, but all of these are custom and optional. So any client code should assume they can exist or not and provide a default behavior when a custom attribute is not defined for a client.

The name of attributes are defined in the class `ClientAttributes` of [common.py](../mixer/broadcaster/common.py).

Server attributes (always filled by server):
- ID: unique id for the client (string)
- IP: IP of the client (string)
- PORT: port of the client on server side (integer)
- ROOM: current room of the client (string or null)

Note: The ID is stored even if is built from the IP and port. This is to allow future change of the identification strategy. As a consequence, client code should not assume this construction of the ID and should use IP and PORT attributes if they want access to these information.

Standard custom attributes:
- USERNAME: name of the client, non unique (string)
- USERCOLOR: color of the client (list of 3 floats)
- USERSCENES: dictionary of json objects describing client attributes related to each 3D scene, when it makes sense for the client. The key is a scene name, and objects have the following shape:
  - USERSCENES_FRAME: current frame of the client for this scene (integer)
  - USERSCENES_SELECTED_OBJECTS: selected objects of the client for this scene (list of strings)
  - USERSCENES_VIEWS: dictionary of json objects describing client views of this scene. The key is a unique id for the view, and objects have the following shape
    - USERSCENES_VIEWS_EYE: position of the eye (list of 3 floats)
    - USERSCENES_VIEWS_TARGET: position of the target (list of 3 floats)
    - USERSCENES_VIEWS_SCREEN_CORNERS: corners of the view frame (list of 4 list of 3 floats, in the order bottom_left, bottom_right, top_right, top_left)

So a valid example of a client attributes could be:

```json
{
  "id": "124.12.89.1:1234",
  "ip": "124.12.89.1",
  "port": 1234,
  "room": "The Room",
  "user_name": "Me",
  "user_color": [1, 0, 1],
  "user_scenes": [
    {
      "First Scene": {
        "frame": 42,
        "selected_objects": ["Ball", "Cube"],
        "views": {
          "unique_id_1": {
            "eye": [0, 0, 0],
            "target": [0, 0, 10],
            "corners": [
              [-1, -1, 1],
              [1, -1, 1],
              [1, 1, 1],
              [-1, 1, 1],
            ],
            "unique_id_2": {
              "eye": [0, 0, 10],
              "target": [0, 0, 0],
              "corners": [
                [1, -1, 9],
                [-1, -1, 9],
                [-1, 1, 9],
                [1, 1, 9],
            ]
          }
        }
      },
      "Second Scene": {
        "frame": 12,
        "selected_objects": [],
        "views": {}
      }
    }
  ]
}
```

Keep in mind all custom attributes here are optional: one client of a room might not be a 3D application, so it would not send anything related to 3D scenes and views to the servers. Other clients should handle this when they received client updates.

For an example of non standard custom client attributes, search for `blender_windows` in the addon, which is only used accross blender clients.

A known limitation of the way we identify clients is that we have session concept: one user cannot be recognized as the same client accross different connections in time. In the future we might implement this concept if it can be useful.

### Room

A room is identified by a non empty name and regroup clients broadcasting messages to each other.

The server stores attributes for each room, represented as a json object. Some attributes are defined by the server and cannot be changed by clients, the remaining are custom attributes. Any client application can defined new custom room attributes for its own need. We define standard names for some custom attributes to ease communication between clients of separate domains, but all of these are custom and optional. So any client code should assume they can exist or not and provide a default behavior when a custom attribute is not defined for a room.

The name of attributes are defined in the class `RoomAttributes` of [common.py](../mixer/broadcaster/common.py).

Server attributes (always filled by server):
- NAME: unique name of the room (non empty string)
- KEEP_OPEN: indicate if the room should be kept on the server when no more client is inside (boolean)
- COMMAND_COUNT: number of commands stored in the room list (integer)
- BYTE_SIZE: total size in bytes of commands stored in the room list (integer)
- JOINABLE: indicate if the room can be joined by clients (boolean)

Standard custom attributes: None for now.

### Commands / Messages

A command, or message, is some data exchanged between the server and a client. Each command has a byte size (int64), an id (int32), and a message type (int16). For now the id is not used by the protocol. Data of the command is stored after the message type and its size should be the byte size stored as first field of the command.

Commands with type less than `MessageType.COMMAND` are directly allow communication and interaction between clients and server. Other codes are domain specific and broadcasted in the room (Blender domain, VRtist domain, Shot Manager domain, ...).

All codes are defined in [common.py](../mixer/broadcaster/common.py).

A known limitation of this system is that it is hard to keep clients code other than the Blender addon synchronized with server code changes. We plan to address this issue in the near future.


## Mixer Protocol

This section describes the communication protocol between server and clients for each Mixer message type.

Here are rules we want this protocol to respect:
- The server notify all clients of any change about client attributes or rooms attributes
- The clients get notified only if a change occurs
- The clients are responsible to update their own data according to changes: they only receive differentials

**Future work**: Implement unit tests that check rules are respected, and protocol is respected.

### JOIN_ROOM

Data:
- room_name (str)

Protocol:
- Client send `JOIN_ROOM room_name` to Server
- If Client is already joined to a room:
  - Server send `SEND_ERROR` to Client
- ElseIf the room exists
  - Server send `CLEAR_CONTENT` to Client
  - Server send all messages from the room list to Client
  - Server send `JOIN_ROOM room_name` to Client
  - Server broadcasts `CLIENT_UPDATE` to all Clients (only the ROOM attribute)
- Else
  - Server send `JOIN_ROOM room_name` to Client
  - Server send `CONTENT` to Client
  - Server broadcasts `ROOM_UPDATE` to all Clients (all attributes, with JOINABLE set to false)
  - Server broadcasts `CLIENT_UPDATE` to all Clients (only the ROOM attribute)
  - After sending all room content, Client send `CONTENT` to Server
  - Server broadcasts `ROOM_UPDATE` to all Clients (only JOINABLE set to true)

### LEAVE_ROOM

Data:
- room_name (str) (Deprecrated, will be removed)

Protocol:
- Client send `LEAVE_ROOM room_name` to Server
- If the client is not in a room
  - Server send `SEND_ERROR` to Client
- Else
  - Server remove client from room
  - Server broadcasts `CLIENT_UPDATE` to all Clients (only the ROOM attribute)
  - If the room has no more client and KEEP_OPEN is false:
    - Server deletes the room
    - Server broadcasts to all Clients `ROOM_DELETED`

### LIST_ROOMS

Data: None

Protocol:
- Client send `LIST_ROOMS` to Server
- Server send `LIST_ROOMS all_rooms_attributes` to Client, where `all_rooms_attributes` is a json object where keys are room names and values are rooms attributes.

### CONTENT

Data: None

Protocol:
- Occurs after a `JOIN_ROOM` from Client to Server when the room does not exist
- Server send `CONTENT` to Client
- Client send a list of room commands
- Client send `CONTENT` to Server

### CLEAR_CONTENT

Data: None

Protocol:
- Occurs after a `JOIN_ROOM` from Client to Server when the room exists
- Server send `CLEAR_CONTENT` to Client
- Client is supposed to clear its data, but can do what he wants

### DELETE_ROOM

Data:
- room_name (str)

Protocol:
- Client send `DELETE_ROOM` to Server
- If the room does not exist:
  - Server send `SEND_ERROR` to Client
- ElseIf the room is not empty:
  - Server send `SEND_ERROR` to Client
- Else:
  - Server deletes the room
  - Server broadcasts to all Clients `ROOM_DELETED`

### SET_CLIENT_NAME

Deprecated, equivalent to `SET_CLIENT_CUSTOM_ATTRIBUTES` with `USERNAME` custom attribute.

### SEND_ERROR

Data:
- error_message (str)

Protocol:
- Occurs when an operation cannot be performed
- Server send `SEND_ERROR error_message` to Client

### LIST_CLIENTS

Data: None

Protocol:
- Client send `LIST_CLIENTS` to Server
- Server send `LIST_CLIENTS all_clients_attributes` to Client, where `all_clients_attributes` is a json object where keys are client unique ids and values are clients attributes.

### SET_CLIENT_CUSTOM_ATTRIBUTES

Data:
- update_object (json object, with attributes to set)

Protocol:
- Client send `SET_CLIENT_CUSTOM_ATTRIBUTES update_object` to Server
- Server updates Client attributes
- If a change is detected, Server broadcasts `CLIENT_UPDATE` to all Clients (only detected changes)

### SET_ROOM_CUSTOM_ATTRIBUTES


Data:
- room_name (str)
- update_object (json object, with attributes to set)

Protocol:
- Client send `SET_ROOM_CUSTOM_ATTRIBUTES room_name update_object` to Server
- If room does not exist:
  - Server send `SEND_ERROR` to Client
- Else:
  - Server updates room attributes for the specified room
  - If a change is detected, Server broadcasts `ROOM_UPDATE` to all Clients (only detected changes)

### SET_ROOM_KEEP_OPEN

Data:
- room_name (str)
- value (boolean)

Protocol:
- Client send `SET_ROOM_KEEP_OPEN room_name value` to Server
- If room does not exist:
  - Server send `SEND_ERROR` to Client
- Else:
  - Server set value as KEEP_OPEN attribute for the room
  - If a change is detected, Server broadcasts `ROOM_UPDATE` to all Clients (only detected changes)

### CLIENT_ID

Data from Client to Server: None

Data from Server to Client:
- client_id (str)

Protocol:
- Client send `CLIENT_ID` to Server
- Server send `CLIENT_ID client_id` to Client, where `client_id` is the unique id of Client

### CLIENT_UPDATE

Data:
- updates (dict where keys are client unique ids and values are client attributes updates)

Protocol:
- Occurs after some operations produce one or several client updates
- Server broadcasts `CLIENT_UPDATE updates` to all clients

Note: The Server is free to send updates when it wants after the change occured. It allows accumulation of updates before broadcasting, for performance reasons.

### ROOM_UPDATE

Data:
- updates (dict where keys are room names and values are room attributes updates)

Protocol:
- Occurs after some operations produce one or several room updates
- Server broadcasts `ROOM_UPDATE updates` to all clients

Note: The Server is free to send updates when it wants after the change occured. It allows accumulation of updates before broadcasting, for performance reasons.

### ROOM_DELETED

Data:
- room_name (str)

Protocol:
- Occurs after a room has been deleted
- Server broadcasts `ROOM_DELETED room_name` to all clients

### CLIENT_DISCONNECTED

Data:
- client_id (str)

Protocol:
- Occurs after a client has been disconnected
- Server broadcasts `CLIENT_DISCONNECTED client_id` to all clients
