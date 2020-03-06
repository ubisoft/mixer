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

mat.node_tree.links.new(bsdf.inputs['Base Color'], texImage.outputs['Color']) je l'aurais fait dans l'autre sens...

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