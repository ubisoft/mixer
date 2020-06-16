# Mixer

**Disclaimer**: This project is in experimental state and actively developped. Do not use it to edit your production assets without a backup or you might break them.

## Introduction

Mixer is a Blender addon developped at Ubisoft Animation Studio for Real Time Collaboration in 3D edition. It allows multiple Blender users to work on the same scene at the same time. Thanks to a broadcasting server that is independent from Blender, it is also possible to implement a connection for other 3D editing softwares.

## Usage

You can download the addon from the release page and install it into Blender.

We didn't write extensive documentation for the user interface because it is still a work in progress and might be changed often. If will be done when the addon become more stable.

From the Mixer panel in the 3D viewport you can enter an IP address, a port and connect to a server. If you enter `localhost` and no Mixer server is already running on your computer, then the addon will start one in the background when you click `Connect`.

Then you can test locally between two Blender instances, or you can open the port on your router and give you external IP address to someone so he can join your session. 

If you are on the Ubisoft network you don't need any router configuration but beware that the VPN apply some rules and you might not be able to reach the IP of someone else behind the VPN. A configuration that should work is to start the server on a workstation from a Ubisoft site, and to have all participants connect to it.

A Mixer broadcaster hosts rooms that are created by users. By default there is no room and someone needs to create one. The creator of the room will upload its current scene to the server, and this scene will be transfered to people that connect to the room. When all users leave a room its content is destroyed, so someone needs to save the scene before everyone leave if you want to keep it.

## Developer environment

### Python Virtual Environment

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
.venv\Scripts\activate.bat
```

Then install development packages with pip:
```bash
pip install -r requirements-dev.txt
```

### Visual Studio Code

We recommand Visual Studio Code, with Python and Blender VSCode extensions.

If you have a python file open in VSCode, it should automatically detect the virtual env, activate it when prompted. Note that VSCode never detect your python unless you open a Python file. When your python is detected, you should see it in your status bar and any new terminal open should have the virtual env activated ("(.venv)" should appear on the prompt line).

The file `.vscode/settings.shared.json` gives an exemple of settings to fill your own `.vscode/settings.json`. The important parts are `editor`, `python` and `blender` settings.

Similarly you can copy `.vscode/launch.shared.json` and `.vscode/tasks.shared.json` for exemples of debug configurations and tasks to run from VSCode.

#### VSCode "configuration"

To prevent VSCode from breaking on generator related exceptions, modify your local installation of `pydevd_frame.py` like stated in https://github.com/fabioz/ptvsd/commit/b297bc027f504cf8679090079aebff6028dfec02.

### Running code quality tools manually

With the above setup, all the code you type should be formatted on save and you should have flake8 warning messages.

If you want to format manually the codebase, run `black .` in the terminal.

If you want to check flake warnings, run `flake8` in the terminal. Note that the flake8 plugins `flake8-black` and `pep8-naming` are installed in the virtual env so you will be notified if black would reformat a file and if you violate PEP8 naming conventions.

You need to have the virtual env activated for these commands to work.

### CI/CD

The CI/CD script `.gitlab-ci.yml` has a codequality stage that run flake8 on the codebase. Go to the pipeline pages of the project to check if your commits meet the quality check.

## Unit tests

### Fonctionnement en bref

- La classe `BlenderTestCase` lance deux Blender (un sender et un receiver) qui exécutent `python_server.py`.
- `python_server.py` enregistre un opérateur qui gère une boucle asyncio.
- La boucle exécute un serveur qui reçoit du source python, le compile et l'exécute. Blender n'est pa bloqué entre deux exécutions et on voit le déroulement du test
- le test (voir `test_test.py`) envoie du code source au Blender 'sender'. D'abord une commande de connection et join room, puis les fonctions du test à proprement parler.
- pour l'instant la conclusion est décidée manuellement
  - pour un succès, quitter un Blender
  - pour un échec, utilisezr le panneau 3D nommé TEST et cliquer sur Fail

Limites : je n'ai pas géré la comparaison automatique de fichiers. Ca ne marche pas tout seul parce que les fichiers qui ne sont pas identiques en binaire.

Evolution possible : on devrait pouvoir utiliser plusieurs sender et receiver pour faire des tests de charge

### Activer les tests

Command palette : **Python: Configure Tests**, choisir **unittest**, pattern : **test\_\***

Definir la variables d'environnement MIXER_BLENDER_EXE_PATH

Détails dans https://code.visualstudio.com/docs/python/testing#_enable-a-test-framework

### Ecrire un test

Voir `tests\test_test.py`

### Debugger les tests

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

- mettre un breakpoint dans le code de mixer avec une des deux méthodes suivantes :
  - ajouter un appel au builtin `breakpoint()` dans le code. Attention le breakpoint ouvrira le fichier qui est dans %ADDPATA% (vois ci dessous) et ne sera pas editable dans VSCode
  - Ouvrir le fichier de code situé dans `%APPDATA%Blender Foundation\Blender\2.82\scripts\addons\mixer` et y mettre un breakpoint avec VSCode
- démarrer l'exécution du test unitaire : Blender se bloque en attendant l'attachement
- attacher le debugger : l'exécution continue jusqu'au breakpoint

### CI/CD on unit tests

For a first simple setup, we rely on an interactive gitlab runner setup. Issues related to service-based runners are described below.

The scripts are located in a new `gitlab` folder

#### Interactive runner

Documentation:

- Installation : https://docs.gitlab.com/runner/install/windows.html
- Runner commands : https://docs.gitlab.com/runner/commands/

Installation steps: 
1. Install a gitlab runner in a folder of your choice. For this tutorial we'll use `d:\gitlab_runner`.
2. Run a terminal as administrator, create folder `d:\gitlab_runner\working_dir` and place yourself into it in your terminal
3. Register a runner with `gitlab-runner-windows-amd64.exe register`. Use `https://gitlab-ncsa.ubisoft.org/` as URL, `3doSyUPxsy5hL-svi_Qu` as token, `blender` as tags, `shell` as executor. The token can be found in Settings -> CI/CD page of this repository. This step should create a file `config.toml` in `d:\gitlab_runner\working_dir`.
4. Edit `d:\gitlab_runner\working_dir` and add an entry `cache_dir = "D:/gitlab_runner/cache"` in the `[[runners]]` section, after the `shell` entry.

Then run an interactive : `gitlab-runner-windows-amd64.exe run`. It must run as administrator because the `TSCON` command requires administrator rights to disconnect a session from the remote desktop.

As the runner executes jobs, it will display the jobs status : 
```
D:\gitlab_runner>gitlab-runner-windows-amd64.exe run
Runtime platform                                    arch=amd64 os=windows pid=19628 revision=4c96e5ad version=12.9.0
Starting multi-runner from D:\gitlab_runner\config.toml...  builds=0
Configuration loaded                                builds=0
listen_address not defined, metrics & debug endpoints disabled  builds=0
[session_server].listen_address not defined, session endpoints disabled  builds=0
Checking for jobs... received                       job=11132741 repo_url=https://gitlab-ncsa.ubisoft.org/animation-studio/blender/mixer.git runner=Q-sQ1rhN
Job succeeded                                       duration=5m3.2796891s job=11132741 project=39094 runner=Q-sQ1rhN
Checking for jobs... received                       job=11132866 repo_url=https://gitlab-ncsa.ubisoft.org/animation-studio/blender/mixer.git runner=Q-sQ1rhN
WARNING: Job failed: exit status 1                  duration=5m8.5314355s job=11132866 project=39094 runner=Q-sQ1rhN
WARNING: Failed to process runner                   builds=0 error=exit status 1 executor=shell runner=Q-sQ1rhN
```

The builds for the runner will be put in the current working directory `d:\gitlab_runner\working_dir` where you started the runner.

#### Runner as a Windows service

Using a system service could be difficult because the user profile may not be easy to access and we also need the service to access to the desktop.

Using a service that logons with a user account requires a user account that can logon as a service as described in https://docs.gitlab.com/runner/faq/README.html#the-service-did-not-start-due-to-a-logon-failure-error-when-starting-service.

## How to release a new version ?

The release process of Mixer is handled with CI/CD and based on git tags. Each tag with a name `v{major}.{minor}.{bugfix}` is considered to be a release tag and should trigger the release job of the CI/CD.

You should not add such tag manually, instead run the script:

```bash
python -m extra.prepare_release <major> <minor> <bugfix>
```

For it to succeed:
- You should have commited all your changes
- You should have added a section describing the release and starting with `# <major>.<minor>.<bugfix>` in `CHANGELOG.md`
- The tag `v{major}.{minor}.{bugfix}` should not already exists

If all these requirements are met, then the script will inject the new version number in the addon `bl_info` dictionnary and tag the commit.

You can then push the tag:
```bash
git push # Push the branch
git push --tags # Push the tag
```

Then watch your pipeline on Gitlab and wait for the release notes to appear on the release page.

### What if I did a mistake ?

It may happen. In that case just go to gitlab and remove the tag. It will also remove the release.

In your local repository manually delete the tag.

## Misc

### Guidelines

- Use name_full instead of name for Blender objects (because of external links)

### Blender stuff

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
