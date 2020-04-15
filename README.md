# Developer environment

## Python Virtual Environment

After cloning the repository, create a Virtual Environment in the code directory:

```bash
python -m venv .venv
```

Use python 3.7 to match Blender's python version.

Activate the virtual env, on Windows the commands are:

With Git bash:
```bash
source .venv/Scripts/activate
```

With cmd.exe:
```bash
.venv/Scripts/activate.bat
```

Then install development packages with pip:
```bash
pip install -r requirements-dev.txt
```

## Visual Studio Code

We recommand Visual Studio Code, with Python and Blender VSCode extensions.

If you have a python file open in VSCode, it should automatically detect the virtual env, activate it when prompted. Note that VSCode never detect your python unless you open a Python file. When your python is detected, you should see it in your status bar and any new terminal open should have the virtual env activated ("(.venv)" should appear on the prompt line).

### settings.json

Add or replace the following configuration to the project VSCode settings file `.vscode/settings.json`:

```json
{
    [...]
    "editor.formatOnSave": true,
    "python.pythonPath": "${workspaceFolder}/.venv/Scripts/python.exe",
    "python.formatting.provider": "black",
    "python.testing.unittestArgs": [
        "-v",
        "-s",
        "./tests",
        "-p",
        "test_*.py"
    ],
    "python.testing.unittestEnabled": true,
    "python.linting.flake8Enabled": true,
    "python.linting.enabled": true,
    "blender.addon.loadDirectory": "./dccsync",
    [...]
}
```

If you have Gitlab extension setup, you may want to add the following setting:

```json
{
    [...]
    "gitlab.instanceUrl": "https://gitlab-ncsa.ubisoft.org/",
    [...]
}
```

### launch.json

To be able to debug the broadcaster from VSCode, you need to run it with a launch configuration. Here is an example of `.vscode/launch.json` that allows to run the broadcaster or the CLI in interactive mode, as well as some other examples you can take inspiration from.

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Run DCC Broadcaster",
      "type": "python",
      "request": "launch",
      "module": "dccsync.broadcaster.dccBroadcaster",
      "args": [
        "--log-level=DEBUG",
        "--log-file=${workspaceFolder}/.vscode/logs/dccBroadcaster.log"
      ],
      "console": "integratedTerminal"
    },
    {
      "name": "Run cli.py (interactive session)",
      "type": "python",
      "request": "launch",
      "module": "dccsync.broadcaster.cli",
      "console": "integratedTerminal"
    },
    {
      "name": "Run cli.py room list",
      "type": "python",
      "request": "launch",
      "module": "dccsync.broadcaster.cli",
      "args": [
        "room",
        "list"
      ],
      "console": "integratedTerminal"
    },
    {
      "name": "Python: Remote Attach",
      "type": "python",
      "request": "attach",
      "port": 5688,
      "host": "localhost",
      "pathMappings": [
        {
          "localRoot": "${workspaceFolder}",
          "remoteRoot": "."
        }
      ]
    }
  ]
}
```

## Running code quality tools manually

With the above setup, all the code you type should be formatted on save and you should have flake8 warning messages.

If you want to format manually the codebase, run `black .` in the terminal.

If you want to check flake warnings, run `flake8` in the terminal. Note that the flake8 plugins `flake8-black` and `pep8-naming` are installed in the virtual env so you will be notified if black would reformat a file and if you violate PEP8 naming conventions.

You need to have the virtual env activated for these commands to work.

## CI/CD

The CI/CD script `.gitlab-ci.yml` has a codequality stage that run flake8 on the codebase. Go to the pipeline pages of the project to check if your commits meet the quality check.

# Unit tests

## Fonctionnement en bref

- La classe `BlenderTestCase` lance deux Blender (un sender et un receiver) qui exécutent `python_server.py`.
- `python_server.py` enregistre un opérateur qui gère une boucle asyncio.
- La boucle exécute un serveur qui reçoit du source python, le compile et l'exécute. Blender n'est pa bloqué entre deux exécutions et on voit le déroulement du test
- le test (voir `test_test.py`) envoie du code source au Blender 'sender'. D'abord une commande de connection et join room, puis les fonctions du test à proprement parler.
- pour l'instant la conclusion est décidée manuellement
  - pour un succès, quitter un Blender
  - pour un échec, utilisezr le panneau 3D nommé TEST et cliquer sur Fail

Limites : je n'ai pas géré la comparaison automatique de fichiers. Ca ne marche pas tout seul parce que les fichiers qui ne sont pas identiques en binaire.

Evolution possible : on devrait pouvoir utiliser plusieurs sender et receiver pour faire des tests de charge

## Activer les tests

Command palette : **Python: Configure Tests**, choisir **unittest**, pattern : **test\_\***

Definir la variables d'environnement DCCSYNC_BLENDER_EXE_PATH

Détails dans https://code.visualstudio.com/docs/python/testing#_enable-a-test-framework

## Ecrire un test

Voir `tests\test_test.py`

## Debugger les tests

To enable justMyCode in the uni tests, see https://github.com/microsoft/vscode-python/issues/7131#issuecomment-525873210

Coté Blender, `python_server.py` autorise la connexion du debugger sur les ports spécifiés dans `BlenderTestCase`. Pour attacher le debugger, il faut ajouter deux configuration de debug, une avec 5688 (sender) et une avec 5689 (receiver):

>

    {
        "name": "Attach to sender (5688)",
        "type": "python",
        "request": "attach",
        "port": 5688,
        "host": "localhost",
        "pathMappings": [
            {
                "localRoot": "${workspaceFolder}",
                "remoteRoot": "."
            }
        ]
    },
        {
        "name": "Attach to senreceiver (5689)",
        "type": "python",
        "request": "attach",
        "port": 5689,
        "host": "localhost",
        "pathMappings": [
            {
                "localRoot": "${workspaceFolder}",
                "remoteRoot": "."
            }
        ]
    },

>

Ensuite:

- mettre un breakpoint dans le code de dccsync avec une des deux méthodes suivantes :
  - ajouter un appel au builtin `breakpoint()` dans le code. Attention le breakpoint ouvrira le fichier qui est dans %ADDPATA% (vois ci dessous) et ne sera pas editable dans VSCode
  - Ouvrir le fichier de code situé dans `%APPDATA%Blender Foundation\Blender\2.82\scripts\addons\dccsync` et y mettre un breakpoint avec VSCode
- démarrer l'exécution du test unitaire : Blender se bloque en attendant l'attachement
- attacher le debugger : l'exécution continue jusqu'au breakpoint

# Misc

## Guidelines

- Use name_full instead of name for Blender objects (because of external links)

## Blender stuff

import bmesh
bm = bmesh.new() bm.free()

obj = bpy.context.selected_objects[0]

bm.from_mesh(obj.data)

bm.verts.ensure_lookup_table()

triangles = bm.calc_loop_triangles()

comparaison de matrices marche pas

l'undo est un hack => graph non updaté sur undo

bmesh supporte pas les custom normals

grease pencil n'est pas un mesh standard

bpy.msgbus.subscribe_rna est appelé dans le viewport pas dans l'inspecteur

replace data of an object pas possible

instance de material par parametre

problème de nommage 2 objets ne peuvent pas avoir le même nom, meme dans des hierarchies différentes
pire, parfois on renomme un objet, l'ui ne refuse pas mais renomme un autre objet, peut-être d'une autre scene

_UL_
property index pour une liste UI

obj.select = True -> étrange, un seul set de seléction ?

intialization des custom properties dans un timer !

pas de callback app start/end => test de l'existence d'une window...

bpy.context.active_object.mode != 'OBJECT' le mode objet est stocké sur l'objet actif !

bpy.ops.object.delete() marche pas

link changement de transform possible en script mais pas en UI

les lights ont des parametres différents en fonciton du render engine:
exemple : light.cycles.cast_shadow vs light.use_shadow

mat.node_tree.links.new(bsdf.inputs['Base Color'], tex_image.outputs['Color']) je l'aurais fait dans l'autre sens...

set parametre sur une multi selection marche à moitié

Si il manque des textures, le .blend ne se charge pas (à vérifier)

un fichier ne peut pas s'appeler null.blend (quelles sont les autres contraintes ?)

normal map Red & Green inverted, quel est le standard ?

pas (toujours) de messages de visibilité des objets / collections

visible_get() vs hide_viewport

bpy.app.handlers.depsgraph_update_pre Débile

les handlers ne sont pas appelés pour les suppression et renommage de collections

update.id.original dans les updates, le .original est le nouveau !

pas d'update (handler) sur les scenes dépendentes

crash quand on lit des infos d'update liés à des collections ajoutées/détruites

hide_viewport sur collection -> reception du message quand hide_viewport=True pas quand hide_viewport=False

collection invisible, pre handler l'update remove from collection n'est pas notifié,
changement de collection d'un object -> pas de notif du tout d'une collection invisible à une collection invisible

material.grease_pencil !!!

stroke.points.add(count) vs stroke.points.pop()

quand on supprime un grease pencil, il en reste une trace dans bpy.data.grease_pencils -> orphan data

recherche dans bpy.data.objects par name, pas par name_full
