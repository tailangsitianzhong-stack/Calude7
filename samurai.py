"""
175cm 男性サムライ(幕末の甲冑武者写真の装束を再現) — Blender プロシージャル生成スクリプト

使い方:
  Blender GUI : Scripting タブでこのファイルを開いて「Run Script」
  コマンド    : blender --background --python samurai.py
  (pip の bpy モジュールでも python3 samurai.py で動作)

単位はメートル。身長(足裏〜頭頂)= 1.75m。兜の前立てはその上に乗ります。
ポーズは 2 種類:
  fan    … 右手に扇を掲げ、刀は腰に差したまま  → samurai.blend / samurai_preview.png
  katana … 抜刀して両手で中段に構える          → samurai_katana.blend / samurai_katana_preview.png
  anim   … リグ+モーション(袈裟斬り/振り下ろし/横斬り/歩き/走り/しゃがみ/回避)
           → samurai_anim.blend と motions/ フォルダの GIF
GUI では下の POSE を書き換えて実行("anim" も可)。コマンドラインでは
  blender --background --python samurai.py -- katana   (省略時は両方を生成)
"""
import bpy
import bmesh
import math
import os
from mathutils import Vector

HEIGHT = 1.75
OUT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()

# 解剖学的な基準高さ(身長 1.75m 基準、約 7.5 頭身)
H = {
    "top": HEIGHT,          # 頭頂
    "head_c": 1.635,        # 頭部中心
    "chin": 1.52,
    "neck": 1.47,
    "shoulder": 1.43,
    "chest": 1.30,
    "waist": 1.08,
    "hip": 0.96,
    "crotch": 0.83,
    "knee": 0.49,
    "ankle": 0.08,
}


# ---------------------------------------------------------------- utilities
def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.curves,
                 bpy.data.cameras, bpy.data.lights):
        for block in list(coll):
            if block.users == 0:
                coll.remove(block)


def _set(bsdf, names, value):
    for n in names:
        if n in bsdf.inputs:
            bsdf.inputs[n].default_value = value
            return


def _rgba_io(mix):
    a = [i for i in mix.inputs if i.type == "RGBA"]
    return a[0], a[1], [o for o in mix.outputs if o.type == "RGBA"][0]


def material(name, color, metallic=0.0, roughness=0.5, coat=0.0, sheen=0.0,
             bump=None, scale=100.0, strength=0.15, var=0.0, var_scale=8.0):
    """Principled BSDF + 任意でプロシージャルな凹凸(bump)と色ムラ(var)"""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    _set(bsdf, ["Coat Weight", "Clearcoat"], coat)
    _set(bsdf, ["Coat Roughness", "Clearcoat Roughness"], 0.06)
    _set(bsdf, ["Sheen Weight", "Sheen"], sheen)
    mat.diffuse_color = (*color, 1.0)
    if bump or var:
        tc = nodes.new("ShaderNodeTexCoord")
    if var:
        nz = nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = var_scale
        nz.inputs["Detail"].default_value = 6
        links.new(tc.outputs["Object"], nz.inputs["Vector"])
        mix = nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        a, b, out = _rgba_io(mix)
        a.default_value = (*(c * (1 - var) for c in color), 1)
        b.default_value = (*(min(1, c * (1 + var)) for c in color), 1)
        links.new(nz.outputs["Fac"], mix.inputs["Factor"])
        links.new(out, bsdf.inputs["Base Color"])
    if bump:
        if bump == "voronoi":
            tex = nodes.new("ShaderNodeTexVoronoi")
            tex.feature = "SMOOTH_F1" if bump == "x" else "F1"
            out = tex.outputs["Distance"]
        elif bump == "wave":
            tex = nodes.new("ShaderNodeTexWave")
            tex.inputs["Distortion"].default_value = 2.0
            out = tex.outputs["Fac"]
        else:
            tex = nodes.new("ShaderNodeTexNoise")
            tex.inputs["Detail"].default_value = 10
            out = tex.outputs["Fac"]
        tex.inputs["Scale"].default_value = scale
        links.new(tc.outputs["Object"], tex.inputs["Vector"])
        bmp = nodes.new("ShaderNodeBump")
        bmp.inputs["Strength"].default_value = strength
        links.new(out, bmp.inputs["Height"])
        links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def kozane_material(name, c1, c2, lace, width=0.016, row=0.03):
    """小札(こざね)を縅糸で綴じた板:Brick テクスチャで札と紐を表現"""
    mat = material(name, c1, roughness=0.3, coat=0.8)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    tc = nodes.new("ShaderNodeTexCoord")
    mp = nodes.new("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value = (math.radians(90), 0, 0)
    br = nodes.new("ShaderNodeTexBrick")
    br.offset = 0.0
    br.inputs["Color1"].default_value = (*c1, 1)
    br.inputs["Color2"].default_value = (*c2, 1)
    br.inputs["Mortar"].default_value = (*lace, 1)
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Mortar Size"].default_value = 0.0022
    br.inputs["Mortar Smooth"].default_value = 0.3
    br.inputs["Brick Width"].default_value = width
    br.inputs["Row Height"].default_value = row
    links.new(tc.outputs["Object"], mp.inputs["Vector"])
    links.new(mp.outputs["Vector"], br.inputs["Vector"])
    links.new(br.outputs["Color"], bsdf.inputs["Base Color"])
    rr = nodes.new("ShaderNodeMapRange")
    rr.inputs["To Min"].default_value = 0.28
    rr.inputs["To Max"].default_value = 0.85
    links.new(br.outputs["Fac"], rr.inputs["Value"])
    links.new(rr.outputs["Result"], bsdf.inputs["Roughness"])
    bmp = nodes.new("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = 0.35
    bmp.invert = True
    links.new(br.outputs["Fac"], bmp.inputs["Height"])
    links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def collection(name):
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll


def finish(obj, name, mat, coll, smooth=True, parent=None):
    obj.name = name
    obj.data.name = name
    if mat:
        obj.data.materials.clear()
        obj.data.materials.append(mat)
    if smooth and hasattr(obj.data, "polygons"):
        for p in obj.data.polygons:
            p.use_smooth = True
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)
    if parent:
        obj.parent = parent
        obj.matrix_parent_inverse = parent.matrix_world.inverted()
    return obj


def apply_scale(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)


def sphere(name, loc, scale, mat, coll, segs=32):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=segs // 2, location=loc)
    o = bpy.context.active_object
    o.scale = scale
    apply_scale(o)
    return finish(o, name, mat, coll)


def cube(name, loc, size, mat, coll, rot=(0, 0, 0), bevel=0.0, smooth=False):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.scale = size
    apply_scale(o)
    if bevel:
        m = o.modifiers.new("Bevel", "BEVEL")
        m.width = bevel
        m.segments = 2
    return finish(o, name, mat, coll, smooth=smooth)


def cylinder(name, loc, r, depth, mat, coll, rot=(0, 0, 0), verts=32, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth,
                                        location=loc, rotation=rot)
    o = bpy.context.active_object
    o.scale = scale
    apply_scale(o)
    return finish(o, name, mat, coll)


def limb(name, p1, p2, r1, r2, mat, coll, verts=24):
    """p1→p2 を結ぶテーパー付き円柱(腕・脚)"""
    p1, p2 = Vector(p1), Vector(p2)
    d = p2 - p1
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r1, radius2=r2,
                                    depth=d.length, location=(p1 + p2) / 2)
    o = bpy.context.active_object
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = d.normalized().to_track_quat("Z", "Y")
    return finish(o, name, mat, coll)


def lofted(name, rings, mat, coll, verts=32, cap_top=True, cap_bottom=True):
    """rings: [(z, rx, ry, cx, cy), ...] の楕円断面をつないだメッシュ"""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    loops = []
    for z, rx, ry, *c in rings:
        cx, cy = (c + [0, 0])[:2]
        loop = [bm.verts.new((cx + rx * math.cos(2 * math.pi * i / verts),
                              cy + ry * math.sin(2 * math.pi * i / verts), z))
                for i in range(verts)]
        loops.append(loop)
    for a, b in zip(loops, loops[1:]):
        for i in range(verts):
            j = (i + 1) % verts
            bm.faces.new((a[i], a[j], b[j], b[i]))
    if cap_bottom:
        bm.faces.new(list(reversed(loops[0])))
    if cap_top:
        bm.faces.new(loops[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    return finish(o, name, mat, coll)


def subsurf(obj, level=2):
    m = obj.modifiers.new("Subsurf", "SUBSURF")
    m.levels = level
    m.render_levels = level
    return obj


# ---------------------------------------------------------------- materials
M = {}


def checker_material(name, c1, c2, scale=40.0):
    mat = material(name, c1, roughness=0.85)
    nt = mat.node_tree
    chk = nt.nodes.new("ShaderNodeTexChecker")
    chk.inputs["Color1"].default_value = (*c1, 1)
    chk.inputs["Color2"].default_value = (*c2, 1)
    chk.inputs["Scale"].default_value = scale
    nt.links.new(chk.outputs["Color"], nt.nodes["Principled BSDF"].inputs["Base Color"])
    return mat


def build_materials():
    # 写真(幕末期の甲冑武者)の配色に合わせる
    M["skin"] = material("Skin", (0.62, 0.45, 0.34), roughness=0.5, bump="noise", scale=300, strength=0.05, var=0.08)
    M["hair"] = material("Hair", (0.02, 0.02, 0.02), roughness=0.4)
    M["eye"] = material("Eye", (0.03, 0.02, 0.015), roughness=0.05, coat=1.0)
    M["under"] = material("Under_Kimono", (0.025, 0.025, 0.03), roughness=0.9, sheen=0.4,
                          bump="wave", scale=900, strength=0.12, var=0.15)
    M["jinbaori"] = material("Jinbaori_Wool", (0.13, 0.075, 0.045), roughness=0.85, sheen=0.6,
                             bump="noise", scale=600, strength=0.15, var=0.18, var_scale=4)
    M["trim"] = material("Trim_Cream", (0.72, 0.62, 0.44), roughness=0.7, sheen=0.4,
                         bump="wave", scale=900, strength=0.1, var=0.1)
    M["lacquer_bk"] = material("Lacquer_Black", (0.018, 0.016, 0.014), roughness=0.35, coat=1.0,
                               bump="noise", scale=40, strength=0.03, var=0.2)
    M["lacquer_br"] = material("Lacquer_Brown", (0.07, 0.04, 0.025), roughness=0.35, coat=1.0,
                               bump="noise", scale=40, strength=0.03, var=0.25)
    M["lace"] = material("Odoshi_Dark", (0.035, 0.035, 0.05), roughness=0.85, sheen=0.3,
                         bump="wave", scale=600, strength=0.2)
    M["kusari"] = material("Kusari_Mail", (0.06, 0.06, 0.065), metallic=0.85, roughness=0.45,
                           bump="voronoi", scale=260, strength=0.8, var=0.3, var_scale=30)
    M["cord"] = material("Cord_Silk", (0.78, 0.70, 0.52), roughness=0.55, sheen=0.6,
                         bump="wave", scale=500, strength=0.4)
    M["brass"] = material("Brass_Pale", (0.80, 0.70, 0.48), metallic=0.85, roughness=0.32,
                          bump="noise", scale=200, strength=0.04, var=0.15)
    M["gold"] = material("Gold", (0.9, 0.7, 0.3), metallic=1.0, roughness=0.3)
    M["tsuka"] = material("Tsuka_Ito", (0.04, 0.035, 0.03), roughness=0.8, bump="wave", scale=300, strength=0.5)
    M["saya"] = material("Saya", (0.03, 0.025, 0.02), roughness=0.25, coat=1.0, bump="noise", scale=60, strength=0.02)
    M["sandal"] = material("Waraji_Straw", (0.55, 0.47, 0.30), roughness=0.95, bump="wave", scale=250, strength=0.6, var=0.2, var_scale=60)
    M["tabi"] = material("Tabi_Dark", (0.04, 0.04, 0.045), roughness=0.9, sheen=0.3, bump="noise", scale=500, strength=0.1)
    M["paper"] = material("Fan_Paper", (0.90, 0.88, 0.82), roughness=0.75, bump="noise", scale=150, strength=0.08, var=0.05)
    M["obi"] = checker_material("Obi_Check", (0.30, 0.24, 0.17), (0.12, 0.09, 0.07), 60)
    M["kozane_bk"] = kozane_material("Kozane_Black", (0.02, 0.018, 0.016), (0.03, 0.025, 0.02), (0.04, 0.04, 0.06))
    M["kozane_br"] = kozane_material("Kozane_Brown", (0.075, 0.045, 0.028), (0.06, 0.035, 0.022), (0.04, 0.04, 0.06))
    M["ground"] = material("Ground", (0.30, 0.28, 0.25), roughness=0.9, bump="noise", scale=6, strength=0.3, var=0.25, var_scale=2)
    M["backdrop"] = material("Backdrop", (0.42, 0.38, 0.33), roughness=0.95, var=0.35, var_scale=0.8)


def curve(name, pts, radius, mat, coll, smooth=True):
    cd = bpy.data.curves.new(name, "CURVE")
    cd.dimensions = "3D"
    cd.bevel_depth = radius
    cd.bevel_resolution = 3
    cd.use_fill_caps = True
    sp = cd.splines.new("NURBS" if smooth else "POLY")
    sp.points.add(len(pts) - 1)
    for p, co in zip(sp.points, pts):
        p.co = (*co, 1)
    if smooth:
        sp.use_endpoint_u = True
        sp.order_u = min(4, len(pts))
    cd.materials.append(mat)
    o = bpy.data.objects.new(name, cd)
    coll.objects.link(o)
    return o


def mesh_from(name, verts, faces, mat, coll, thickness=0.0, smooth=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    if thickness:
        s = o.modifiers.new("Solidify", "SOLIDIFY")
        s.thickness = thickness
        s.offset = 0
    return finish(o, name, mat, coll, smooth=smooth)


# ---------------------------------------------------------------- body
POSE = "fan"  # GUI 実行時のポーズ: "fan" または "katana"

# 中段の構え:柄頭を臍の前、切先を相手の喉へ向ける
SWORD_DIR = Vector((0.0, -0.86, 0.51)).normalized()
GRIP = Vector((0.0, -0.27, 1.00))          # 左手(柄頭側)の握り位置
ARMS = {
    # 扇を掲げる右腕 / 下ろした左腕
    "fan": dict(R=((-0.20, 0.0, 1.42), (-0.37, -0.10, 1.25), (-0.52, -0.24, 1.23)),
                L=((0.20, 0.0, 1.42), (0.27, 0.0, 1.14), (0.27, -0.07, 0.93))),
    # 両手で柄を握る(右手が鍔側、左手が柄頭側)
    "katana": dict(R=((-0.20, 0.0, 1.42), (-0.21, -0.17, 1.17), tuple(GRIP + SWORD_DIR * 0.15 + Vector((-0.045, 0.045, -0.01)))),
                   L=((0.20, 0.0, 1.42), (0.20, -0.09, 1.11), tuple(GRIP + SWORD_DIR * 0.03 + Vector((0.045, 0.05, -0.02))))),
}


def set_pose(pose):
    global POSE, R_SH, R_EL, R_WR, L_SH, L_EL, L_WR
    POSE = pose
    (R_SH, R_EL, R_WR), (L_SH, L_EL, L_WR) = ARMS[pose]["R"], ARMS[pose]["L"]


set_pose(POSE if POSE in ARMS else "katana")


def build_body(coll):
    head = sphere("Head", (0, 0, H["head_c"]), (0.078, 0.095, 0.115), M["skin"], coll)
    sphere("Jaw", (0, -0.015, H["chin"] + 0.04), (0.060, 0.07, 0.05), M["skin"], coll)
    for s in (-1, 1):
        side = "L" if s > 0 else "R"
        sphere(f"Ear.{side}", (s * 0.078, 0.0, H["head_c"]), (0.012, 0.022, 0.032), M["skin"], coll, segs=16)
        sphere(f"Eye.{side}", (s * 0.032, -0.082, H["head_c"] + 0.012), (0.012, 0.006, 0.007), M["eye"], coll, segs=16)
        cube(f"Brow.{side}", (s * 0.033, -0.086, H["head_c"] + 0.032), (0.03, 0.006, 0.006),
             M["hair"], coll, rot=(0, s * 0.15, 0))
    sphere("Hair_Back", (0, 0.02, H["head_c"] + 0.01), (0.082, 0.085, 0.105), M["hair"], coll)
    cylinder("Chonmage", (0, -0.01, H["top"] - 0.012), 0.012, 0.09, M["hair"], coll, rot=(math.radians(90), 0, 0))
    limb("Neck", (0, 0.005, H["neck"] - 0.04), (0, 0.005, H["chin"] + 0.02), 0.058, 0.052, M["skin"], coll)

    torso = lofted("Torso_Under", [
        (H["crotch"] + 0.02, 0.15, 0.10), (H["hip"], 0.175, 0.115), (H["waist"], 0.155, 0.105),
        (H["chest"], 0.18, 0.12), (H["shoulder"] - 0.02, 0.19, 0.105),
        (H["shoulder"] + 0.02, 0.12, 0.08), (H["neck"] - 0.01, 0.065, 0.06),
    ], M["under"], coll)
    subsurf(torso, 1)

    # 腕:全体を鎖籠手(くさりごて)で覆い、要所に漆の板(筏金)
    for side, (sh, el, wr) in (("R", (R_SH, R_EL, R_WR)), ("L", (L_SH, L_EL, L_WR))):
        sphere(f"Shoulder.{side}", sh, (0.065, 0.065, 0.065), M["kusari"], coll)
        limb(f"UpperArm.{side}", sh, el, 0.062, 0.050, M["kusari"], coll)
        sphere(f"Elbow.{side}", el, (0.052, 0.052, 0.052), M["lacquer_br"], coll)
        limb(f"Forearm.{side}", el, wr, 0.050, 0.040, M["kusari"], coll)
        a, b, c = Vector(sh), Vector(el), Vector(wr)
        for t in (0.35, 0.7):
            p = a.lerp(b, t)
            limb(f"Ikada_Upper.{side}.{t}", p - (b - a) * 0.06, p + (b - a) * 0.06, 0.066, 0.064, M["lacquer_br"], coll, verts=12)
        limb(f"Ikada_Fore.{side}", b.lerp(c, 0.2), b.lerp(c, 0.85), 0.054, 0.045, M["lacquer_bk"], coll, verts=8)
        d = (c - b).normalized()
        if POSE == "katana":
            # 柄を握る:手のひらを柄へ向け、親指は切先側に回す
            g = GRIP + SWORD_DIR * (0.15 if side == "R" else 0.03)
            hand(side, c - d * 0.01, d, coll, curl=88, palm_to=g, thumb_dir=SWORD_DIR)
        else:
            hand(side, c - d * 0.01, d, coll, curl=85 if side == "R" else 22,
                 roll=0 if side == "R" else -90, thumb=-1 if side == "R" else 1)

    # 脚:裁着袴(たっつけばかま)+脛当+足袋・草鞋、やや開いた立ち姿
    for s, side in ((-1, "R"), (1, "L")):
        hp = (s * 0.10, 0.0, H["crotch"] + 0.05)
        kn = (s * 0.15, -0.02, H["knee"])
        an = (s * 0.18, 0.01, H["ankle"] + 0.02)
        limb(f"Thigh.{side}", hp, kn, 0.095, 0.068, M["under"], coll)
        sphere(f"Knee.{side}", kn, (0.06, 0.06, 0.06), M["under"], coll)
        limb(f"Shin.{side}", kn, an, 0.062, 0.042, M["under"], coll)
        limb(f"Suneate.{side}", (kn[0], kn[1] - 0.005, kn[2] - 0.02), (an[0], an[1] - 0.005, an[2] + 0.06),
             0.066, 0.048, M["lacquer_bk"], coll, verts=10)
        for k in (-1, 0, 1):
            ang = math.radians(-90 + k * 35)
            off = Vector((math.cos(ang), math.sin(ang), 0))
            limb(f"Suneate_Splint.{side}.{k}", Vector(kn) + off * 0.066 + Vector((0, 0, -0.04)),
                 Vector(an) + off * 0.050 + Vector((0, 0, 0.08)), 0.008, 0.008, M["lacquer_br"], coll, verts=6)
        cube(f"Tateage.{side}", (kn[0], kn[1] - 0.07, kn[2] + 0.01), (0.10, 0.015, 0.09),
             M["lacquer_br"], coll, bevel=0.006)
        rz = s * math.radians(-12)
        fwd = Vector((math.sin(-rz), -math.cos(-rz), 0))  # つま先方向(やや外向き)
        ax, ay = an[0], an[1]
        fp = []
        fp.append(sphere(f"FootPart.{side}.ankle", (ax, ay, 0.085), (0.046, 0.05, 0.05), M["tabi"], coll))
        fp.append(sphere(f"FootPart.{side}.heel", (ax, ay + 0.035, 0.040), (0.040, 0.045, 0.040), M["tabi"], coll))
        mid = Vector((ax, ay, 0.0)) + fwd * 0.07
        fp.append(cube(f"FootPart.{side}.arch", (mid.x, mid.y, 0.04), (0.085, 0.15, 0.06), M["tabi"], coll,
                       rot=(math.radians(-8), 0, rz), bevel=0.02))
        toe = Vector((ax, ay, 0.0)) + fwd * 0.17
        fp.append(sphere(f"FootPart.{side}.toes", (toe.x, toe.y, 0.025), (0.045, 0.04, 0.024), M["tabi"], coll))
        organic(f"Tabi.{side}", [o.name for o in fp], M["tabi"], coll, voxel=0.005)
        limb(f"Kyahan.{side}", (ax, ay, 0.24), (ax, ay, 0.07), 0.052, 0.047, M["under"], coll)
        sole = Vector((ax, ay, 0.0)) + fwd * 0.075
        cube(f"Waraji.{side}", (sole.x, sole.y, 0.008), (0.10, 0.27, 0.014), M["sandal"], coll,
             rot=(0, 0, rz), bevel=0.005, smooth=True)
        for t in (0.0, 0.09):
            q = Vector((ax, ay, 0.0)) + fwd * t
            cube(f"Waraji_Strap.{side}.{t}", (q.x, q.y, 0.045 if t == 0 else 0.04), (0.10, 0.012, 0.012),
                 M["sandal"], coll, rot=(math.radians(-20 if t else 0), 0, rz), bevel=0.004, smooth=True)
    # 円柱の継ぎ目をなくし、布・鎖の腕脚を一体の有機的な形状に
    for side in ("L", "R"):
        organic(f"Arm_Mail.{side}", [f"Shoulder.{side}", f"UpperArm.{side}", f"Forearm.{side}"], M["kusari"], coll)
        organic(f"Leg.{side}", [f"Thigh.{side}", f"Knee.{side}", f"Shin.{side}"], M["under"], coll)
        organic(f"Hand.{side}", [o.name for o in coll.objects if o.name.startswith(f"HandPart.{side}")],
                M["skin"], coll, voxel=0.0028, smooth=6)
    organic("Head", ["Head", "Jaw", "Neck", "Ear.L", "Ear.R"], M["skin"], coll, voxel=0.004)
    return bpy.data.objects["Head"]


def organic(name, names, mat, coll, voxel=0.006, smooth=10):
    objs = [bpy.data.objects[n] for n in names if n in bpy.data.objects]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    o = bpy.context.active_object
    o.name = name
    o.data.name = name
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    rm = o.modifiers.new("Remesh", "REMESH")
    rm.mode = "VOXEL"
    rm.voxel_size = voxel
    sm = o.modifiers.new("Smooth", "CORRECTIVE_SMOOTH")
    sm.iterations = smooth
    sm.smooth_type = "LENGTH_WEIGHTED"
    sm.use_only_smooth = True
    for m in list(o.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)
    o.data.materials.clear()
    o.data.materials.append(mat)
    for p in o.data.polygons:
        p.use_smooth = True
    return o


def hand(side, wrist, d, coll, curl=30, roll=0.0, thumb=1, palm_to=None, thumb_dir=None):
    """指付きの手。ローカル座標 X=指の並び, Y=指先方向, Z=手の甲"""
    from mathutils import Matrix
    up = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0))
    sx = d.cross(up).normalized()
    nz = sx.cross(d).normalized()
    q = Matrix.Rotation(math.radians(roll), 3, d)
    nz = (q @ nz).normalized()
    sx = d.cross(nz).normalized()
    if palm_to is not None:
        v = Vector(palm_to) - Vector(wrist)
        v = v - d * v.dot(d)
        nz = -v.normalized()
        sx = d.cross(nz).normalized()
    if thumb_dir is not None:
        thumb = 1 if sx.dot(thumb_dir) >= 0 else -1
    basis = Matrix((sx, d, nz)).transposed()

    def W(v):
        return Vector(wrist) + basis @ Vector(v)

    parts = []
    parts.append(sphere(f"HandPart.{side}.palm", (0, 0, 0), (0.042, 0.048, 0.016), M["skin"], coll))
    pm = parts[-1]
    pm.matrix_world = Matrix.Translation(W((0, 0.045, 0))) @ basis.to_4x4()
    fingers = [(-0.027, 0.85, 0.0075), (-0.009, 1.0, 0.0082), (0.009, 1.05, 0.0083), (0.026, 0.95, 0.0080)]
    for k, (x, ln, r) in enumerate(fingers):
        x = x * -thumb
        p = Vector((x, 0.088 - abs(x) * 0.3, 0.0))
        dirv = Vector((x * 0.6, 1, 0)).normalized()
        for j, seg in enumerate((0.044, 0.027, 0.022)):
            ang = math.radians(curl * (j + 1) * 0.7)
            dv = Vector((dirv.x, dirv.y * math.cos(ang), -math.sin(ang))).normalized()
            q2 = p + dv * seg * ln
            parts.append(limb(f"HandPart.{side}.f{k}{j}", W(p), W(q2), r * (1 - 0.1 * j), r * (0.9 - 0.1 * j),
                              M["skin"], coll, verts=12))
            parts.append(sphere(f"HandPart.{side}.k{k}{j}", W(q2), (r * 0.85,) * 3, M["skin"], coll, segs=12))
            p = q2
    t0 = Vector((thumb * 0.035, 0.015, -0.008))
    t1 = t0 + Vector((thumb * 0.03, 0.03, -0.012))
    t2 = t1 + Vector((thumb * 0.008, 0.032, -0.018 - curl * 0.0003))
    parts.append(limb(f"HandPart.{side}.t0", W(t0), W(t1), 0.012, 0.010, M["skin"], coll, verts=12))
    parts.append(limb(f"HandPart.{side}.t1", W(t1), W(t2), 0.0095, 0.008, M["skin"], coll, verts=12))
    parts.append(sphere(f"HandPart.{side}.tk", W(t1), (0.010,) * 3, M["skin"], coll, segs=12))
    parts.append(limb(f"HandPart.{side}.wrist", W((0, -0.03, 0)), W((0, 0.02, 0)), 0.030, 0.034, M["skin"], coll, verts=16))
    # 手甲(てっこう)— 甲を覆う漆の板
    tk = cube(f"Tekko.{side}", (0, 0, 0), (0.07, 0.07, 0.006), M["lacquer_bk"], coll, bevel=0.003)
    tk.matrix_world = Matrix.Translation(W((0, 0.035, 0.019))) @ basis.to_4x4()
    return parts


# ---------------------------------------------------------------- clothing & armor
def open_shell(name, rings, a0, a1, mat, coll, segs=160, thickness=0.008, sub=4):
    """前が開いた筒状の布(陣羽織)。下へいくほど深くなるドレープのひだ付き"""
    dense = []
    for (z0, rx0, ry0), (z1, rx1, ry1) in zip(rings, rings[1:]):
        for k in range(sub):
            t = k / sub
            dense.append((z0 + (z1 - z0) * t, rx0 + (rx1 - rx0) * t, ry0 + (ry1 - ry0) * t))
    dense.append(rings[-1])
    zmin = rings[0][0]
    verts, faces = [], []
    n = segs + 1
    for z, rx, ry in dense:
        w = max(0.0, min(1.0, (1.30 - z) / (1.30 - zmin))) ** 1.3
        for i in range(n):
            a = math.radians(a0 + (a1 - a0) * i / segs)
            edge = min(i, segs - i) / 6.0
            f = (0.045 * math.sin(11 * a + 0.4) + 0.02 * math.sin(23 * a + 1.7)) * w * min(1.0, edge)
            hz_ = z + 0.012 * w * math.sin(7 * a)  # 裾の波打ち
            verts.append((rx * (1 + f) * math.cos(a), ry * (1 + f) * math.sin(a),
                          hz_ if z == zmin else z))
    for r in range(len(dense) - 1):
        for i in range(segs):
            p = r * n + i
            faces.append((p, p + 1, p + 1 + n, p + n))
    o = mesh_from(name, verts, faces, mat, coll, thickness=thickness)
    left = [verts[r * n] for r in range(len(dense))][::sub] + [verts[(len(dense) - 1) * n]]
    right = [verts[r * n + segs] for r in range(len(dense))][::sub] + [verts[(len(dense) - 1) * n + segs]]
    hem = verts[:n:4] + [verts[segs]]
    return o, left, right, hem


def build_armor(coll):
    W = H["waist"]
    # 胴(黒漆、段々の板)
    do = lofted("Do_Cuirass", [
        (W - 0.04, 0.178, 0.125), (H["chest"] - 0.10, 0.185, 0.13),
        (H["chest"], 0.195, 0.138), (H["shoulder"] - 0.05, 0.19, 0.122),
    ], M["lacquer_bk"], coll, cap_top=False, cap_bottom=False)
    do.modifiers.new("Solidify", "SOLIDIFY").thickness = 0.01
    for i in range(8):
        z = W - 0.02 + i * 0.038
        r = 1.0 + 0.04 * math.sin(i / 7 * math.pi)
        lofted(f"Do_Lame.{i}", [(z, 0.19 * r, 0.136 * r), (z + 0.010, 0.19 * r, 0.136 * r)],
               M["lacquer_br"] if i % 2 else M["lace"], coll)
    # 胸板の上縁
    lofted("Do_Munaita", [(H["shoulder"] - 0.07, 0.17, 0.125), (H["shoulder"] - 0.04, 0.16, 0.118)], M["lacquer_br"], coll)

    # 帯(格子柄)+ 結び目
    lofted("Obi", [(W - 0.07, 0.19, 0.138), (W + 0.02, 0.188, 0.136)], M["obi"], coll)
    sphere("Obi_Knot", (-0.04, -0.15, W - 0.03), (0.045, 0.025, 0.035), M["obi"], coll)
    for s in (-1, 1):
        cube(f"Obi_Tail.{s}", (-0.04 + s * 0.03, -0.15, W - 0.11), (0.04, 0.012, 0.14), M["obi"], coll,
             rot=(0, s * 0.25, 0), bevel=0.004)

    # 草摺(暗色の板を縅で連ねる)
    for k in range(7):
        ang = math.radians(-90 + (k - 3) * 30)
        cx, cy = math.cos(ang) * 0.20, math.sin(ang) * 0.15
        for row in range(5):
            z = W - 0.10 - row * 0.055
            r = 1.0 + row * 0.07
            cube(f"Kusazuri.{k}.{row}", (cx * r, cy * r, z), (0.12, 0.012, 0.05),
                 M["kozane_bk"] if row % 2 == 0 else M["kozane_br"], coll,
                 rot=(math.radians(-12 if cy < 0 else 12), 0, ang + math.pi / 2), bevel=0.004)

    # 佩楯(はいだて)— 太腿前の小札の前掛け
    for s, side in ((-1, "R"), (1, "L")):
        base = Vector((s * 0.12, -0.135, 0.70))
        cube(f"Haidate_Cloth.{side}", base + Vector((0, 0.004, 0)), (0.18, 0.012, 0.34), M["under"], coll,
             rot=(math.radians(-8), 0, s * math.radians(8)), bevel=0.004)
        for i in range(4):
            for j in range(7):
                zz = 0.15 - j * 0.045
                p = base + Vector(((i - 1.5) * 0.04, -0.016 + 0.139 * zz, zz))
                cube(f"Haidate_Plate.{side}.{i}.{j}", p, (0.034, 0.008, 0.036),
                     M["lacquer_br"] if (i + j) % 2 else M["kusari"], coll,
                     rot=(math.radians(-8), 0, s * math.radians(8)), bevel=0.003)

    # 小さな袖と喉輪
    for s, side in ((-1, "R"), (1, "L")):
        for row in range(3):
            cube(f"Kosode.{side}.{row}", (s * (0.235 + row * 0.006), 0.0, H["shoulder"] - 0.05 - row * 0.04),
                 (0.012, 0.12, 0.04), M["kozane_bk"] if row % 2 == 0 else M["kozane_br"], coll,
                 rot=(0, s * math.radians(-12), 0), bevel=0.003)
    lofted("Nodowa", [(H["neck"] - 0.04, 0.09, 0.08), (H["neck"] + 0.005, 0.075, 0.068)], M["lacquer_bk"], coll)

    # 陣羽織 — 袖なし、前開き、膝丈、肩が張り出す。縁はクリーム色
    rings = [(0.52, 0.33, 0.27), (0.75, 0.30, 0.245), (0.95, 0.27, 0.215), (1.10, 0.24, 0.185),
             (1.28, 0.25, 0.175), (1.39, 0.30, 0.165), (1.45, 0.25, 0.135), (1.49, 0.12, 0.10)]
    jb, left, right, hem = open_shell("Jinbaori", rings, -55, 235, M["jinbaori"], coll)
    subsurf(jb, 2)
    curve("Jinbaori_Trim_Front.L", left, 0.010, M["trim"], coll)
    curve("Jinbaori_Trim_Front.R", right, 0.010, M["trim"], coll)
    curve("Jinbaori_Trim_Hem", hem, 0.010, M["trim"], coll)
    # 襟の折り返し
    for s, pts in ((1, left), (-1, right)):
        top = pts[-3:]
        lap = [(x - s * 0.015 * 0, y - 0.01, z) for x, y, z in top]
        curve(f"Jinbaori_Eri.{'L' if s > 0 else 'R'}", lap, 0.016, M["jinbaori"], coll)

    # 総角(あげまき)風の飾り紐:兜の緒から胸の結び目へ、房が垂れる
    hz = H["head_c"] + 0.02
    knot_chin = Vector((0, -0.105, H["chin"] - 0.005))
    knot_chest = Vector((0, -0.165, H["chest"] + 0.02))
    for s in (-1, 1):
        curve(f"Shinobi_no_o.{s}", [(s * 0.105, -0.02, hz - 0.06), (s * 0.085, -0.07, H["chin"] + 0.02),
                                    (s * 0.03, -0.10, H["chin"] - 0.01), tuple(knot_chin)], 0.006, M["cord"], coll)
        curve(f"Cord_Down.{s}", [tuple(knot_chin), (s * 0.03, -0.13, H["neck"] - 0.03),
                                 (s * 0.02, -0.16, H["chest"] + 0.08), tuple(knot_chest)], 0.006, M["cord"], coll)
        curve(f"Cord_Loop.{s}", [tuple(knot_chest), (s * 0.08, -0.15, H["chest"] + 0.03),
                                 (s * 0.06, -0.145, H["chest"] - 0.04), (s * 0.02, -0.155, H["chest"] - 0.02)],
              0.006, M["cord"], coll)
        tail = knot_chest + Vector((s * 0.02, -0.005, -0.12))
        curve(f"Cord_Tassel_Line.{s}", [tuple(knot_chest), tuple(knot_chest.lerp(tail, 0.5) + Vector((s * 0.01, 0, 0))), tuple(tail)],
              0.005, M["cord"], coll)
        limb(f"Tassel.{s}", tail, tail + Vector((0, 0, -0.08)), 0.010, 0.022, M["cord"], coll, verts=12)
    sphere("Knot_Chin", knot_chin, (0.022, 0.016, 0.018), M["cord"], coll, segs=12)
    sphere("Knot_Chest", knot_chest, (0.03, 0.018, 0.026), M["cord"], coll, segs=12)


def build_kabuto(coll):
    hz = H["head_c"] + 0.02
    # 鉢
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, location=(0, 0.005, hz))
    hachi = bpy.context.active_object
    hachi.scale = (0.105, 0.12, 0.125)
    apply_scale(hachi)
    bm = bmesh.new()
    bm.from_mesh(hachi.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < -0.01], context="VERTS")
    bm.to_mesh(hachi.data)
    bm.free()
    hachi.modifiers.new("Solidify", "SOLIDIFY").thickness = 0.006
    finish(hachi, "Kabuto_Hachi", M["lacquer_br"], coll)
    for i in range(16):
        a = i * math.pi / 16
        bpy.ops.mesh.primitive_torus_add(major_radius=1.0, minor_radius=0.02,
                                         location=(0, 0.005, hz), rotation=(0, math.pi / 2, a))
        t = bpy.context.active_object
        t.scale = (0.106, 0.121, 0.126)
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        bm = bmesh.new()
        bm.from_mesh(t.data)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < 0.0], context="VERTS")
        bm.to_mesh(t.data)
        bm.free()
        finish(t, f"Kabuto_Suji.{i}", M["lacquer_bk"], coll)
    cylinder("Kabuto_Tehen", (0, 0.005, hz + 0.125), 0.02, 0.01, M["brass"], coll)
    # 眉庇
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=1, depth=0.006, location=(0, -0.01, hz + 0.005))
    mabi = bpy.context.active_object
    mabi.scale = (0.125, 0.145, 1)
    mabi.rotation_euler = (math.radians(-12), 0, 0)
    apply_scale(mabi)
    bm = bmesh.new()
    bm.from_mesh(mabi.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.y > -0.06], context="VERTS")
    bm.to_mesh(mabi.data)
    bm.free()
    finish(mabi, "Kabuto_Mabizashi", M["lacquer_bk"], coll)

    # 錣(暗色・縅糸)
    for row in range(4):
        z = hz - 0.01 - row * 0.032
        r = 1.0 + row * 0.13
        bpy.ops.mesh.primitive_cone_add(vertices=40, radius1=0.125 * r + 0.02, radius2=0.12 * r,
                                        depth=0.034, location=(0, 0.02, z))
        sh = bpy.context.active_object
        sh.scale = (1, 1.08, 1)
        apply_scale(sh)
        bm = bmesh.new()
        bm.from_mesh(sh.data)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.y < -0.06], context="VERTS")
        bm.to_mesh(sh.data)
        bm.free()
        sh.modifiers.new("Solidify", "SOLIDIFY").thickness = 0.005
        finish(sh, f"Kabuto_Shikoro.{row}", M["kozane_bk"] if row % 2 == 0 else M["kozane_br"], coll)
        if row == 0:
            for s in (-1, 1):
                cube(f"Fukigaeshi.{'L' if s > 0 else 'R'}", (s * 0.135, -0.07, z + 0.01),
                     (0.01, 0.07, 0.05), M["lacquer_br"], coll, rot=(0, 0, s * math.radians(-40)), bevel=0.004)

    # 鍬形 — 幅広で平たいクリーム色の板、U字に大きく開く
    horn = [(0.012, 0.00), (0.045, 0.00), (0.085, 0.05), (0.125, 0.12), (0.160, 0.20), (0.185, 0.25),
            (0.165, 0.265), (0.125, 0.235), (0.090, 0.165), (0.055, 0.095), (0.020, 0.050)]
    for s in (-1, 1):
        pts = horn if s > 0 else [(-x, z) for x, z in reversed(horn)]
        verts = [(x, 0.0, z) for x, z in pts]
        o = mesh_from(f"Kuwagata.{'L' if s > 0 else 'R'}", verts, [list(range(len(verts)))],
                      M["brass"], coll, thickness=0.005, smooth=False)
        bv = o.modifiers.new("Bevel", "BEVEL")
        bv.width = 0.002
        bv.segments = 2
        o.location = (0, -0.132, hz + 0.04)
        o.rotation_euler = (math.radians(-15), 0, 0)
    cube("Kuwagata_Dai", (0, -0.128, hz + 0.035), (0.10, 0.012, 0.035), M["lacquer_bk"], coll, bevel=0.006)
    cylinder("Maedate_Mon", (0, -0.14, hz + 0.05), 0.022, 0.008, M["brass"], coll, rot=(math.radians(90), 0, 0))

    build_somen(coll)
    for i in range(3):
        bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=1, depth=0.028,
                                            location=(0, 0.0, H["chin"] - 0.015 - i * 0.026))
        y = bpy.context.active_object
        y.scale = (0.095 + i * 0.01, 0.105 + i * 0.01, 1)
        apply_scale(y)
        bm = bmesh.new()
        bm.from_mesh(y.data)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.y > -0.04], context="VERTS")
        bm.to_mesh(y.data)
        bm.free()
        y.modifiers.new("Solidify", "SOLIDIFY").thickness = 0.004
        finish(y, f"Yodarekake.{i}", M["lacquer_bk"] if i % 2 == 0 else M["lace"], coll)


def build_somen(coll):
    """総面(そうめん)— 顔全体を覆う黒漆の面。目穴・眉・鼻・頬・歯・植毛の髭"""
    hc = H["head_c"]
    bpy.ops.mesh.primitive_uv_sphere_add(segments=96, ring_count=48, location=(0, -0.004, hc - 0.012))
    m = bpy.context.active_object
    m.scale = (0.089, 0.106, 0.128)
    apply_scale(m)
    bm = bmesh.new()
    bm.from_mesh(m.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.y > 0.025 or v.co.z > 0.062 or v.co.z < -0.135],
                     context="VERTS")
    eye_z = 0.012 + 0.012  # 目の高さ(面の原点からの相対)
    holes = [f for f in bm.faces
             if any(((f.calc_center_median().x - s * 0.032) / 0.014) ** 2 +
                    ((f.calc_center_median().z - eye_z) / 0.0055) ** 2 < 1 and f.calc_center_median().y < -0.06 for s in (-1, 1))]
    mouth = [f for f in bm.faces
             if (f.calc_center_median().x / 0.024) ** 2 + ((f.calc_center_median().z + 0.068) / 0.005) ** 2 < 1 and f.calc_center_median().y < -0.06]
    bmesh.ops.delete(bm, geom=holes + mouth, context="FACES")
    # 面の起伏:頬骨と眉を盛り上げる
    for v in bm.verts:
        x, z = v.co.x, v.co.z
        bump = 0.010 * math.exp(-(((abs(x) - 0.045) / 0.02) ** 2 + ((z + 0.02) / 0.02) ** 2))   # 頬骨
        bump += 0.008 * math.exp(-(((abs(x) - 0.03) / 0.025) ** 2 + ((z - 0.036) / 0.008) ** 2))  # 眉
        bump -= 0.006 * math.exp(-(((abs(x) - 0.032) / 0.02) ** 2 + ((z - eye_z) / 0.012) ** 2))  # 目の窪み
        v.co.y -= bump
    bm.to_mesh(m.data)
    bm.free()
    m.modifiers.new("Solidify", "SOLIDIFY").thickness = 0.005
    subsurf(m, 1)
    for s in (-1, 1):
        sphere(f"Somen_EyeShadow.{s}", (s * 0.032, -0.088, hc + 0.012), (0.018, 0.006, 0.010), M["hair"], coll, segs=16)
    finish(m, "Somen", M["lacquer_bk"], coll)
    base = Vector((0, -0.004, hc - 0.012))

    # 鼻(鷲鼻)
    nose = lofted("Somen_Nose", [
        (hc - 0.045, 0.019, 0.014, 0, -0.112), (hc - 0.030, 0.016, 0.018, 0, -0.122),
        (hc - 0.005, 0.010, 0.012, 0, -0.118), (hc + 0.015, 0.008, 0.008, 0, -0.110)],
        M["lacquer_bk"], coll, verts=16)
    subsurf(nose, 2)
    # 眉(盛り上がった眉骨)
    for s in (-1, 1):
        curve(f"Somen_Brow.{s}", [(s * 0.012, -0.112, hc + 0.035), (s * 0.033, -0.112, hc + 0.042),
                                  (s * 0.058, -0.096, hc + 0.035)], 0.0055, M["lacquer_br"], coll)
    # 歯(口の奥)
    for i in range(-3, 4):
        cube(f"Somen_Tooth.{i}", (i * 0.0062, -0.098, hc - 0.081), (0.0055, 0.004, 0.006),
             material("Teeth_Gilt", (0.75, 0.68, 0.45), metallic=0.6, roughness=0.3), coll, bevel=0.0012, smooth=True)
    cube("Somen_MouthDark", (0, -0.094, hc - 0.081), (0.05, 0.004, 0.012), M["hair"], coll)
    # 植毛の髭(口髭とあご髭)
    hair = material("Mask_Hair", (0.05, 0.045, 0.04), roughness=0.6)
    import random
    rnd = random.Random(7)
    for s in (-1, 1):
        for k in range(14):
            t = k / 13
            x0 = s * (0.006 + 0.024 * t)
            p0 = (x0, -0.117 + 0.01 * t, hc - 0.070 + 0.004 * t)
            p1 = (x0 + s * (0.012 + rnd.uniform(0, 0.006)), p0[1] - 0.004, p0[2] - 0.008)
            p2 = (x0 + s * (0.024 + rnd.uniform(0, 0.01)), p0[1] + 0.006, p0[2] - 0.020 - rnd.uniform(0, 0.01))
            curve(f"Somen_Hige.{s}.{k}", [p0, p1, p2], 0.0013, hair, coll)
    for k in range(18):
        x0 = rnd.uniform(-0.022, 0.022)
        p0 = (x0, -0.108, hc - 0.105)
        curve(f"Somen_AgoHige.{k}", [p0, (x0 * 1.1, -0.112, hc - 0.125), (x0 * 1.2 + rnd.uniform(-0.004, 0.004), -0.106, hc - 0.15)],
              0.0013, hair, coll)


def build_katana(coll):
    """左腰に水平気味に差した打刀・脇差と、右手に掲げた扇"""
    def blade_set(prefix, length, tsuka_len, loc, rot, drawn=False):
        root = bpy.data.objects.new(prefix, None)
        coll.objects.link(root)
        root.location = loc
        root.rotation_euler = rot
        parts = [
            cylinder(f"{prefix}_Saya", (0, 0, -length / 2), 0.016, length, M["saya"], coll, verts=16, scale=(1.0, 1.6, 1)),
            cylinder(f"{prefix}_Kojiri", (0, 0, -length - 0.01), 0.017, 0.02, M["brass"], coll, verts=16, scale=(1.0, 1.6, 1)),
            cylinder(f"{prefix}_Koiguchi", (0, 0, -0.008), 0.0175, 0.016, M["brass"], coll, verts=16, scale=(1.0, 1.6, 1)),
        ]
        if not drawn:
            parts += [
                cylinder(f"{prefix}_Tsuba", (0, 0, 0.005), 0.040, 0.008, M["lacquer_bk"], coll, verts=24),
                cylinder(f"{prefix}_Tsuka", (0, 0, 0.01 + tsuka_len / 2), 0.015, tsuka_len, M["tsuka"], coll, verts=16, scale=(1.0, 1.4, 1)),
                cylinder(f"{prefix}_Kashira", (0, 0, 0.012 + tsuka_len), 0.016, 0.012, M["brass"], coll, verts=16, scale=(1.0, 1.4, 1)),
            ]
        # 柄巻きの菱
        for i in range(0 if drawn else 6):
            parts.append(cube(f"{prefix}_Hishi.{i}", (0, -0.022, 0.03 + i * tsuka_len / 6.5), (0.012, 0.004, 0.012),
                              M["cord"], coll, rot=(0, math.radians(45), 0)))
        for p in parts:
            p.parent = root
        return root

    # 柄は体の前で内向き、鞘は後方へ水平に伸びる
    blade_set("Katana", 0.73, 0.25, (0.21, -0.16, H["waist"] - 0.07),
              (math.radians(84), 0, math.radians(-35)), drawn=(POSE == "katana"))
    blade_set("Wakizashi", 0.48, 0.17, (0.15, -0.18, H["waist"] - 0.02),
              (math.radians(86), 0, math.radians(-45)))

    if POSE == "katana":
        build_drawn_katana(coll)
        return

    # 扇(右手で横へ掲げる)
    dR = (Vector(R_WR) - Vector(R_EL)).normalized()
    pivot = Vector(R_WR) + dR * 0.085 + Vector((0, 0, -0.032))
    verts = [tuple(pivot)]
    n = 14
    for i in range(n + 1):
        a = math.radians(95 + 95 * i / n)
        verts.append(tuple(pivot + Vector((math.cos(a) * 0.30, -0.02 * math.sin(a), math.sin(a) * 0.30))))
    faces = [(0, i, i + 1) for i in range(1, n + 1)]
    mesh_from("Fan", verts, faces, M["paper"], coll, thickness=0.003, smooth=False)
    for i in range(0, n + 1, 2):
        curve(f"Fan_Rib.{i}", [tuple(pivot), verts[i + 1]], 0.0025, M["lacquer_br"], coll, smooth=False)


def build_drawn_katana(coll, blade_len=0.70, tsuka_len=0.25, sori=0.017):
    """抜き身の打刀:反りのある鎬造りの刀身(切先付き)+ はばき・鍔・柄"""
    from mathutils import Matrix
    u = SWORD_DIR
    e = Vector((0, 0, -1))
    e = (e - u * e.dot(u)).normalized()           # 刃の向き(下側)
    t = u.cross(e).normalized()                   # 刀身の厚み方向
    base = GRIP - u * 0.03                         # 柄頭
    tsuba = base + u * tsuka_len
    steel = material("Blade_Steel", (0.86, 0.87, 0.9), metallic=1.0, roughness=0.12,
                     bump="noise", scale=2000, strength=0.01)
    hamon = material("Blade_Hamon", (0.95, 0.95, 0.95), metallic=0.85, roughness=0.32,
                     bump="noise", scale=900, strength=0.02)

    # 刀身:断面 = 棟・鎬(左右)・刃 の 4 点を長さ方向に掃引
    N = 90
    verts, faces = [], []
    for i in range(N + 1):
        sp = i / N
        w = 0.031 - 0.009 * sp
        th = 0.0075 - 0.0025 * sp
        if sp > 0.93:                               # 切先(ふくら)
            k = (1 - sp) / 0.07
            w *= math.sqrt(max(k, 0.0))
            th *= max(k, 0.05)
        c = tsuba + u * (0.03 + blade_len * sp) - e * (sori * math.sin(math.pi * sp * 0.85) + sori * 0.4 * sp)
        verts += [tuple(c), tuple(c + e * w * 0.32 - t * th / 2), tuple(c + e * w * 0.97),
                  tuple(c + e * w * 0.32 + t * th / 2), tuple(c + e * w * 0.70 - t * th * 0.28),
                  tuple(c + e * w * 0.70 + t * th * 0.28)]
    S = 6
    for i in range(N):
        a, b = i * S, (i + 1) * S
        # 棟〜鎬(地鉄) / 鎬〜刃文線(地鉄) / 刃文線〜刃(刃文)
        faces += [(a + 0, b + 0, b + 1, a + 1), (a + 3, b + 3, b + 0, a + 0),
                  (a + 1, b + 1, b + 4, a + 4), (a + 5, b + 5, b + 3, a + 3),
                  (a + 4, b + 4, b + 2, a + 2), (a + 2, b + 2, b + 5, a + 5)]
    faces.append((0, 1, 4, 2, 5, 3))
    me = bpy.data.meshes.new("Katana_Blade")
    me.from_pydata(verts, [], faces)
    me.materials.append(steel)
    me.materials.append(hamon)
    for k, poly in enumerate(me.polygons):
        poly.material_index = 1 if (k < N * 6 and k % 6 in (4, 5)) else 0
        poly.use_smooth = False
    me.update()
    blade = bpy.data.objects.new("Katana_Blade", me)
    coll.objects.link(blade)
    bv = blade.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")

    # 刀装具:ローカル Z = 刀の軸
    rot = Matrix((t, e, u)).transposed().to_4x4()

    def part(obj, pos):
        obj.matrix_world = Matrix.Translation(pos) @ rot
        return obj
    part(cylinder("Katana_Habaki", (0, 0, 0), 0.016, 0.03, M["brass"], coll, verts=16, scale=(0.55, 1.15, 1)),
         tsuba + u * 0.017 + e * 0.004)
    part(cylinder("Katana_Seppa", (0, 0, 0), 0.022, 0.004, M["brass"], coll, verts=24, scale=(0.8, 1.2, 1)),
         tsuba + u * 0.001)
    part(cylinder("Katana_Tsuba", (0, 0, 0), 0.040, 0.007, M["lacquer_bk"], coll, verts=32, scale=(0.95, 1.05, 1)),
         tsuba - u * 0.004)
    part(cylinder("Katana_Fuchi", (0, 0, 0), 0.0165, 0.014, M["brass"], coll, verts=16, scale=(1.0, 1.4, 1)),
         tsuba - u * 0.015)
    part(cylinder("Katana_Tsuka", (0, 0, 0), 0.015, tsuka_len - 0.03, M["tsuka"], coll, verts=16, scale=(1.0, 1.4, 1)),
         base + u * (tsuka_len / 2))
    part(cylinder("Katana_Kashira", (0, 0, 0), 0.0165, 0.012, M["brass"], coll, verts=16, scale=(1.0, 1.4, 1)),
         base + u * 0.006)
    for i in range(7):
        for sgn in (-1, 1):
            h = part(cube(f"Katana_Hishi.{i}.{sgn}", (0, 0, 0), (0.011, 0.004, 0.011), M["cord"], coll),
                     base + u * (0.03 + i * 0.03) + t * sgn * 0.0148)
            h.matrix_world = h.matrix_world @ Matrix.Rotation(math.radians(90), 4, "Y") @ Matrix.Rotation(math.radians(45), 4, "X")


# ---------------------------------------------------------------- scene
def build_scene(coll):
    # 撮影スタジオ風の曲面ホリゾント
    prof = [(y, 0.0) for y in (-4.0, -1.0, 0.5, 1.2)]
    for i in range(1, 9):
        a = math.radians(90 * i / 8)
        prof.append((1.2 + math.sin(a) * 0.9, 0.9 - math.cos(a) * 0.9))
    prof.append((2.1, 4.5))
    verts, faces = [], []
    for x in (-5.0, 5.0):
        for y, z in prof:
            verts.append((x, y, z))
    n = len(prof)
    for i in range(n - 1):
        faces.append((i, i + 1, n + i + 1, n + i))
    g = mesh_from("Backdrop", verts, faces, M["backdrop"], coll)
    bpy.ops.mesh.primitive_plane_add(size=2.6, location=(0, -0.2, 0.002))
    finish(bpy.context.active_object, "Floor_Mat", M["ground"], coll, smooth=False)

    # 身長スケール参照(175cm マーカー)— ビューポート専用
    ref = cube("HeightRef_175cm", (0.7, 0.3, HEIGHT / 2), (0.01, 0.01, HEIGHT),
               material("Ref", (0.9, 0.1, 0.1), roughness=0.5), coll)
    ref.hide_render = True

    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 70
    cam = bpy.data.objects.new("Camera", cam_data)
    coll.objects.link(cam)
    if POSE == "katana":   # 刀身が見えるよう斜め前から
        cam.location = (2.7, -3.8, 1.3)
        target = Vector((0.0, -0.25, 1.0))
    else:
        cam.location = (0.75, -4.6, 1.15)
        target = Vector((-0.08, 0, 1.0))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam_data.dof.use_dof = True
    cam_data.dof.focus_distance = (target - cam.location).length - 0.15
    cam_data.dof.aperture_fstop = 5.6
    scene.camera = cam

    def light(name, kind, loc, energy, size=1.0, color=(1, 1, 1), aim=(0, 0, 1.1)):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = energy
        ld.color = color
        if kind == "AREA":
            ld.size = size
        lo = bpy.data.objects.new(name, ld)
        coll.objects.link(lo)
        lo.location = loc
        lo.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    light("Key", "AREA", (-2.4, -2.8, 3.2), 420, 2.5, (1.0, 0.93, 0.82))
    light("Fill", "AREA", (3.0, -2.5, 1.6), 110, 3.5, (0.85, 0.9, 1.0))
    light("Rim", "AREA", (0.8, 2.0, 3.0), 260, 1.2, (1.0, 0.95, 0.9))
    light("Kicker", "AREA", (-1.8, 1.5, 1.5), 90, 1.0)

    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.09, 0.085, 0.08, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.5


# ---------------------------------------------------------------- rig & animation
from mathutils import Matrix, Quaternion, Euler

RIG = None
DEFORM = {  # 変形メッシュ → 影響ボーン
    "Arm_Mail.R": ["chest", "upper_arm.R", "forearm.R"], "Arm_Mail.L": ["chest", "upper_arm.L", "forearm.L"],
    "Hand.R": ["forearm.R", "hand.R"], "Hand.L": ["forearm.L", "hand.L"],
    "Leg.R": ["hips", "thigh.R", "shin.R"], "Leg.L": ["hips", "thigh.L", "shin.L"],
    "Tabi.R": ["shin.R", "foot.R"], "Tabi.L": ["shin.L", "foot.L"],
    "Head": ["neck", "head"],
    "Torso_Under": ["hips", "spine", "chest", "neck", "thigh.L", "thigh.R"],
    "Jinbaori": ["hips", "spine", "chest", "thigh.L", "thigh.R"],
}
RIGID = [  # 名前の先頭 → 追従ボーン(該当なしは最寄りのボーン)
    ("Kusazuri", "hips"), ("Obi", "hips"), ("Katana", "hips"), ("Wakizashi", "hips"),
    ("Do_", "spine"), ("Nodowa", "chest"), ("Cord_", "chest"), ("Knot_Chest", "chest"), ("Tassel", "chest"),
    ("Shinobi_no_o", "head"), ("Knot_Chin", "head"), ("Hair_", "head"), ("Chonmage", "head"),
    ("Eye.", "head"), ("Brow.", "head"),
]
SWORD_PARTS = ("Katana_Blade", "Katana_Habaki", "Katana_Seppa", "Katana_Tsuba", "Katana_Fuchi",
               "Katana_Tsuka", "Katana_Kashira", "Katana_Hishi")


def _sword_frame(u, hint):
    y = Vector(u).normalized()
    e = Vector(hint) - y * Vector(hint).dot(y)
    z = -e.normalized()
    x = y.cross(z).normalized()
    return x, y, z


def build_rig(colls):
    """人型アーマチュア:腕は刀に付けた IK ターゲット、脚は足 IK で制御"""
    global RIG
    arm_data = bpy.data.armatures.new("Samurai_Rig")
    arm = bpy.data.objects.new("Samurai_Rig", arm_data)
    colls[0].objects.link(arm)
    arm.show_in_front = True
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones

    def bone(name, head, tail, parent=None, connect=False, deform=True, roll_to=None):
        b = eb.new(name)
        b.head, b.tail = Vector(head), Vector(tail)
        if parent:
            b.parent = eb[parent]
            b.use_connect = connect
        b.use_deform = deform
        if roll_to is not None:
            b.align_roll(Vector(roll_to))
        return b

    bone("root", (0, 0, 0), (0, 0.3, 0), deform=False)
    bone("hips", (0, 0, 0.93), (0, 0, 1.06), "root")
    bone("spine", (0, 0, 1.06), (0, 0, 1.26), "hips", True)
    bone("chest", (0, 0, 1.26), (0, 0, 1.45), "spine", True)
    bone("neck", (0, 0.005, 1.45), (0, 0.005, 1.53), "chest")
    bone("head", (0, 0.005, 1.53), (0, 0.005, 1.76), "neck", True)
    for side, (sh, el, wr) in (("R", (R_SH, R_EL, R_WR)), ("L", (L_SH, L_EL, L_WR))):
        d = (Vector(wr) - Vector(el)).normalized()
        bone(f"upper_arm.{side}", sh, el, "chest")
        bone(f"forearm.{side}", el, wr, f"upper_arm.{side}", True)
        h = bone(f"hand.{side}", wr, Vector(wr) + d * 0.1, f"forearm.{side}", True)
        s = -1 if side == "R" else 1
        hp = (s * 0.10, 0.0, H["crotch"] + 0.05)
        kn = (s * 0.15, -0.02, H["knee"])
        an = (s * 0.18, 0.01, H["ankle"] + 0.02)
        bone(f"thigh.{side}", hp, kn, "hips")
        bone(f"shin.{side}", kn, an, f"thigh.{side}", True)
        bone(f"foot.{side}", an, (an[0] + s * 0.03, -0.14, 0.03), f"shin.{side}", True)
    u = SWORD_DIR
    x, y, z = _sword_frame(u, (0, 0, -1))
    base = GRIP - u * 0.03
    bone("sword", base, base + u * 0.25, "root", deform=False, roll_to=z)
    for side in ("R", "L"):
        h, f = eb[f"hand.{side}"], eb[f"foot.{side}"]
        ik = bone(f"ik_hand.{side}", h.head, h.tail, "sword", deform=False)
        ik.roll = h.roll
        ik = bone(f"ik_foot.{side}", f.head, f.tail, "root", deform=False)
        ik.roll = f.roll
        hp_ = eb[f"thigh.{side}"].head
        # 膝の向き:股関節の真正面・膝の高さに置く(外側に置くとガニ股になる)
        bone(f"pole_knee.{side}", Vector((hp_.x, -1.0, H["knee"])), Vector((hp_.x, -1.1, H["knee"])), "hips", deform=False)
    bpy.ops.object.mode_set(mode="OBJECT")

    for side in ("R", "L"):
        pb = arm.pose.bones
        c = pb[f"forearm.{side}"].constraints.new("IK")
        c.target, c.subtarget, c.chain_count = arm, f"ik_hand.{side}", 2
        c = pb[f"hand.{side}"].constraints.new("COPY_ROTATION")
        c.target, c.subtarget = arm, f"ik_hand.{side}"
        c = pb[f"shin.{side}"].constraints.new("IK")
        c.target, c.subtarget, c.chain_count = arm, f"ik_foot.{side}", 2
        c.pole_target, c.pole_subtarget = arm, f"pole_knee.{side}"
        c = pb[f"foot.{side}"].constraints.new("COPY_ROTATION")
        c.target, c.subtarget = arm, f"ik_foot.{side}"
    # ポール角の較正:深く膝を曲げた姿勢で、膝が股関節と足首を結ぶ線の真上(正面)に来る角度を選ぶ
    RIG = arm
    pose_rig(arm, hips=(0, 0, -0.30), foot_L=(-0.08, 0, 0), foot_R=(0.08, 0, 0))
    for side in ("L", "R"):
        c = pb[f"shin.{side}"].constraints["IK"]
        best = None
        for deg in range(-180, 180, 5):
            c.pole_angle = math.radians(deg)
            bpy.context.view_layer.update()
            hip, knee, ank = pb[f"thigh.{side}"].head, pb[f"shin.{side}"].head, pb[f"foot.{side}"].head
            mid = (hip + ank) / 2
            err = abs(knee.x - mid.x) + (10 if knee.y > mid.y else 0)
            if best is None or err < best[0]:
                best = (err, deg)
        c.pole_angle = math.radians(best[1])
        print(f"[samurai] pole angle {side} = {best[1]} deg (knee offset {best[0]*100:.1f} cm)")
    pose_rig(arm)
    bpy.context.view_layer.update()

    # カーブ(紐・縁取り)をメッシュ化して変形できるように
    objs = [o for c in colls for o in c.objects]
    curves = [o for o in objs if o.type == "CURVE"]
    if curves:
        bpy.ops.object.select_all(action="DESELECT")
        for o in curves:
            o.select_set(True)
        bpy.context.view_layer.objects.active = curves[0]
        bpy.ops.object.convert(target="MESH")
    bpy.context.view_layer.update()

    bones = {b.name: (b.head_local.copy(), b.tail_local.copy()) for b in arm_data.bones if b.use_deform}

    def seg_dist(p, a, b):
        ab = b - a
        t = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
        return (p - (a + ab * t)).length

    def nearest(p, names=None):
        return min((n for n in bones if names is None or n in names), key=lambda n: seg_dist(p, *bones[n]))

    for o in [o for c in colls for o in c.objects]:
        if o is arm or o.type not in ("MESH", "EMPTY") or o.parent is not None:
            continue
        mw = o.matrix_world.copy()
        key = next((k for k in DEFORM if o.name == k or (k == "Jinbaori" and o.name.startswith(k))), None)
        if key and o.type == "MESH":
            names = DEFORM[key]
            groups = {n: o.vertex_groups.new(name=n) for n in names}
            for v in o.data.vertices:
                p = mw @ v.co
                ws = sorted(((1.0 / (seg_dist(p, *bones[n]) ** 4 + 1e-9), n) for n in names), reverse=True)[:2]
                tot = sum(w for w, _ in ws)
                for w, n in ws:
                    groups[n].add([v.index], w / tot, "REPLACE")
            m = o.modifiers.new("Armature", "ARMATURE")
            m.object = arm
            bpy.context.view_layer.objects.active = o
            bpy.ops.object.modifier_move_to_index(modifier=m.name, index=0)
            o.parent = arm
            o.matrix_world = mw
            continue
        if o.name.startswith(SWORD_PARTS):
            bname = "sword"
        elif o.users_collection[0].name == "Samurai_Kabuto":
            bname = "head"
        else:
            bname = next((b for pre, b in RIGID if o.name.startswith(pre)), None)
            if bname is None:
                if o.type == "MESH" and o.data.vertices:
                    c = sum((mw @ v.co for v in o.data.vertices), Vector()) / len(o.data.vertices)
                else:
                    c = mw.translation
                bname = nearest(c)
        o.parent = arm
        o.parent_type = "BONE"
        o.parent_bone = bname
        bpy.context.view_layer.update()
        o.matrix_world = mw
    return arm


def _fcurves(action):
    for layer in getattr(action, "layers", []):
        for strip in layer.strips:
            for cb in strip.channelbags:
                yield from cb.fcurves


CHUDAN = dict(P=GRIP - SWORD_DIR * 0.03, u=SWORD_DIR, hint=(0, 0, -1))


def pose_rig(arm, hips=(0, 0, 0), hips_rot=(0, 0, 0), spine=(0, 0, 0), chest=(0, 0, 0), neck=(0, 0, 0),
             sword=None, foot_L=(0, 0, 0), foot_R=(0, 0, 0), sword_follow=True):
    """アーマチュア空間の角度(度)/オフセット(m)でポーズを設定。各回転は親に対する相対"""
    pb = arm.pose.bones
    for b in pb:
        b.rotation_mode = "QUATERNION"
        b.location = (0, 0, 0)
        b.rotation_quaternion = (1, 0, 0, 0)

    def rel(name, deg):
        R = Euler([math.radians(a) for a in deg]).to_quaternion()
        Mr = arm.data.bones[name].matrix_local.to_quaternion()
        pb[name].rotation_quaternion = Mr.inverted() @ R @ Mr

    hb = arm.data.bones["hips"]
    R = Euler([math.radians(a) for a in hips_rot]).to_matrix().to_4x4()
    h = hb.head_local
    pb["hips"].matrix = Matrix.Translation(Vector(hips) + h) @ R @ Matrix.Translation(-h) @ hb.matrix_local
    rel("spine", spine)
    rel("chest", chest)
    rel("neck", neck)
    for side, off in (("L", foot_L), ("R", foot_R)):
        fb = arm.data.bones[f"ik_foot.{side}"]
        pb[f"ik_foot.{side}"].matrix = Matrix.Translation(Vector(off)) @ fb.matrix_local
    s = dict(CHUDAN, **(sword or {}))
    x, y, z = _sword_frame(s["u"], s["hint"])
    P = Vector(s["P"]) + (Vector(hips) if sword_follow else Vector())
    M = Matrix((x, y, z)).transposed().to_4x4()
    M.translation = P
    pb["sword"].matrix = M


_PREVQ = {}


def key_rig(arm, frame, **pose):
    pose_rig(arm, **pose)
    # クォータニオンの符号反転を防ぎ、補間で刀が一回転しないようにする
    for b in arm.pose.bones:
        q = b.rotation_quaternion
        prev = _PREVQ.get(b.name)
        if prev is not None and prev.dot(q) < 0:
            b.rotation_quaternion = -q
        _PREVQ[b.name] = b.rotation_quaternion.copy()
    for name in ("hips", "spine", "chest", "neck", "sword", "ik_foot.L", "ik_foot.R", "pole_knee.L", "pole_knee.R"):
        b = arm.pose.bones[name]
        b.keyframe_insert("location", frame=frame)
        b.keyframe_insert("rotation_quaternion", frame=frame)


def new_action(arm, name, keys, cyclic=False, smooth=False):
    _PREVQ.clear()
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    arm.animation_data_create()
    arm.animation_data.action = act
    for f, pose in keys:
        key_rig(arm, f, **pose)
    if cyclic:
        for fc in _fcurves(act):
            fc.modifiers.new("CYCLES")
    if smooth:
        for fc in _fcurves(act):
            for kp in fc.keyframe_points:
                kp.interpolation = "BEZIER"
                kp.handle_left_type = kp.handle_right_type = "AUTO"
            fc.update()
    act.frame_range = (keys[0][0], keys[-1][0])
    return act


def S(P, u, hint):
    return dict(P=Vector(P), u=Vector(u), hint=Vector(hint))


def build_actions(arm):
    C = CHUDAN
    P0 = Vector(C["P"])
    acts = []
    # 斬撃は「溜め(0-9) → 一気に振り抜く(9-15) → 行き過ぎ(18) → 残心(24) → 戻り(36)」
    # --- 袈裟斬り(右上から左下への斜め斬り)
    acts.append(new_action(arm, "Slash_Diagonal", [
        (0, dict()),
        (6, dict(sword=S((-0.20, -0.08, 1.50), (-0.40, 0.45, 0.80), (0.5, -0.7, -0.3)),
                 hips=(0, 0.04, -0.02), hips_rot=(0, 0, -14), chest=(0, 0, -26), spine=(-6, -4, -8), neck=(0, 0, 10))),
        (9, dict(sword=S((-0.24, -0.04, 1.52), (-0.42, 0.62, 0.66), (0.5, -0.7, -0.3)),
                 hips=(0, 0.05, -0.03), hips_rot=(0, 0, -17), chest=(0, 0, -34), spine=(-7, -5, -10), neck=(0, 0, 14))),
        (11, dict(sword=S((-0.14, -0.30, 1.44), (-0.05, -0.45, 0.89), (0.6, -0.6, -0.4)),
                  hips=(0, -0.02, -0.05), hips_rot=(0, 0, -6), chest=(4, 0, -10), spine=(2, 0, -4), foot_R=(0, -0.12, 0.06))),
        (13, dict(sword=S((-0.02, -0.44, 1.20), (0.45, -0.82, 0.35), (0.6, -0.1, -0.8)),
                  hips=(0, -0.09, -0.09), hips_rot=(0, 0, 10), chest=(10, 0, 16), spine=(10, 0, 4), foot_R=(0, -0.24, 0))),
        (15, dict(sword=S((0.16, -0.34, 0.98), (0.75, -0.40, -0.52), (0.2, 0.4, -0.9)),
                  hips=(0, -0.10, -0.11), hips_rot=(0, 0, 20), chest=(14, 0, 32), spine=(12, 0, 8), foot_R=(0, -0.24, 0))),
        (18, dict(sword=S((0.22, -0.20, 0.90), (0.60, -0.05, -0.80), (0.1, 0.6, -0.8)),
                  hips=(0, -0.10, -0.12), hips_rot=(0, 0, 24), chest=(16, 0, 40), spine=(13, 0, 10), foot_R=(0, -0.24, 0))),
        (24, dict(sword=S((0.16, -0.28, 0.98), (0.70, -0.45, -0.55), (0.2, 0.4, -0.9)),
                  hips=(0, -0.09, -0.10), hips_rot=(0, 0, 16), chest=(10, 0, 26), spine=(9, 0, 6), foot_R=(0, -0.24, 0))),
        (36, dict()),
    ], smooth=True))
    # --- 振り下ろし(上段からの真っ向斬り)
    acts.append(new_action(arm, "Slash_Overhead", [
        (0, dict()),
        (6, dict(sword=S((0, -0.12, 1.55), (0, 0.25, 0.97), (0, -1, 0)), hips=(0, 0.02, 0.01), spine=(-8, 0, 0),
                 neck=(-5, 0, 0), foot_R=(0, -0.06, 0.04))),
        (9, dict(sword=S((0, -0.06, 1.60), (0, 0.58, 0.81), (0, -1, 0)), hips=(0, 0.03, 0.02), spine=(-11, 0, 0),
                 chest=(-4, 0, 0), neck=(-6, 0, 0), foot_R=(0, -0.10, 0.06))),
        (11, dict(sword=S((0, -0.30, 1.52), (0, -0.50, 0.87), (0, -0.8, -0.6)), hips=(0, -0.05, -0.04), spine=(4, 0, 0),
                  foot_R=(0, -0.20, 0.03))),
        (13, dict(sword=S((0, -0.44, 1.08), (0, -0.97, -0.25), (0, 0, -1)), hips=(0, -0.11, -0.13), spine=(18, 0, 0),
                  chest=(5, 0, 0), foot_R=(0, -0.26, 0))),
        (15, dict(sword=S((0, -0.39, 0.92), (0, -0.70, -0.71), (0, 0.3, -1)), hips=(0, -0.12, -0.15), spine=(24, 0, 0),
                  chest=(6, 0, 0), foot_R=(0, -0.26, 0))),
        (18, dict(sword=S((0, -0.35, 0.85), (0, -0.52, -0.85), (0, 0.4, -1)), hips=(0, -0.12, -0.16), spine=(27, 0, 0),
                  chest=(6, 0, 0), foot_R=(0, -0.26, 0))),
        (24, dict(sword=S((0, -0.36, 0.95), (0, -0.75, -0.66), (0, 0.3, -1)), hips=(0, -0.11, -0.13), spine=(20, 0, 0),
                  chest=(4, 0, 0), foot_R=(0, -0.26, 0))),
        (36, dict()),
    ], smooth=True))
    # --- 横薙ぎ(右から左への水平斬り)
    acts.append(new_action(arm, "Slash_Horizontal", [
        (0, dict()),
        (6, dict(sword=S((-0.26, -0.02, 1.20), (-0.65, 0.60, 0.45), (0.4, -0.9, 0)), hips=(0, 0.03, -0.03),
                 hips_rot=(0, 0, -20), chest=(0, 0, -44), spine=(0, 4, -10), neck=(0, 0, 18))),
        (9, dict(sword=S((-0.30, 0.05, 1.18), (-0.55, 0.75, 0.35), (0.4, -0.9, 0)), hips=(0, 0.04, -0.04),
                 hips_rot=(0, 0, -24), chest=(0, 0, -52), spine=(0, 5, -12), neck=(0, 0, 22))),
        (11, dict(sword=S((-0.20, -0.32, 1.14), (-0.85, -0.50, 0.05), (0.3, -1, 0)), hips=(0, -0.03, -0.06),
                  hips_rot=(0, 0, -10), chest=(2, 0, -20), spine=(0, 2, -4), foot_R=(0, -0.10, 0.05))),
        (13, dict(sword=S((0.0, -0.44, 1.12), (-0.10, -1.0, 0.05), (1, 0, 0)), hips=(0, -0.07, -0.08),
                  hips_rot=(0, 0, 5), chest=(4, 0, 4), foot_R=(0, -0.18, 0))),
        (15, dict(sword=S((0.20, -0.30, 1.12), (0.85, -0.50, 0.05), (0.4, 1, 0)), hips=(0, -0.07, -0.09),
                  hips_rot=(0, 0, 18), chest=(4, 0, 34), spine=(0, -2, 8), foot_R=(0, -0.18, 0))),
        (18, dict(sword=S((0.26, -0.12, 1.13), (0.85, 0.45, 0.10), (-0.3, 1, 0)), hips=(0, -0.07, -0.09),
                  hips_rot=(0, 0, 24), chest=(4, 0, 50), spine=(0, -3, 12), foot_R=(0, -0.18, 0))),
        (24, dict(sword=S((0.20, -0.20, 1.10), (0.80, -0.30, 0.10), (0.4, 1, 0)), hips=(0, -0.06, -0.08),
                  hips_rot=(0, 0, 16), chest=(4, 0, 34), spine=(0, -2, 8), foot_R=(0, -0.18, 0))),
        (36, dict()),
    ], smooth=True))

    # --- 歩き / 走り(その場ループ)
    def gait(name, length, step, stride, lift, bob, base_z, lean, sw, narrow):
        keys = []
        for f in range(0, length + 1, step):
            ph = 2 * math.pi * f / length
            fl = (-narrow, -stride * math.cos(ph), lift * max(0.0, -math.sin(ph)))
            fr = (narrow, stride * math.cos(ph), lift * max(0.0, math.sin(ph)))
            hips = (0.02 * math.sin(ph), 0, base_z - bob * math.cos(2 * ph))
            keys.append((f, dict(hips=hips, hips_rot=(0, 0, 6 * math.cos(ph)), spine=(lean, 0, 0),
                                 chest=(0, 0, -5 * math.cos(ph)), neck=(-lean * 0.6, 0, 0),
                                 foot_L=fl, foot_R=fr,
                                 sword=S(P0 + Vector(sw) + Vector((0, 0, 0.012 * math.cos(2 * ph))),
                                         C["u"], C["hint"]))))
        return new_action(arm, name, keys, cyclic=True)
    acts.append(gait("Walk", 32, 4, 0.14, 0.07, 0.015, -0.03, 3, (0, 0, 0), 0.05))
    acts.append(gait("Run", 20, 2, 0.26, 0.15, 0.03, -0.07, 14, (0, -0.06, -0.06), 0.085))

    # --- しゃがみ
    low = dict(hips=(0, 0.07, -0.36), spine=(26, 0, 0), chest=(4, 0, 0), neck=(-22, 0, 0),
               sword=S(P0 + Vector((0, -0.10, -0.20)), (0, -0.62, 0.78), (0, 0, -1)))
    acts.append(new_action(arm, "Crouch", [(0, dict()), (10, low), (30, low), (42, dict())]))

    # --- 回避(右へのサイドステップ)
    acts.append(new_action(arm, "Dodge", [
        (0, dict()),
        (5, dict(hips=(0, 0, -0.08), spine=(6, 0, 0))),
        (9, dict(hips=(-0.25, 0, -0.10), spine=(6, -10, 0), foot_R=(-0.30, 0, 0.12))),
        (13, dict(hips=(-0.45, 0.05, -0.16), hips_rot=(0, -6, 0), spine=(10, -14, 0), neck=(0, 10, 0),
                  foot_R=(-0.55, 0, 0))),
        (17, dict(hips=(-0.48, 0.05, -0.14), hips_rot=(0, -4, 0), spine=(8, -8, 0), neck=(0, 6, 0),
                  foot_R=(-0.55, 0, 0), foot_L=(-0.30, 0, 0.08))),
        (22, dict(hips=(-0.45, 0.03, -0.10), spine=(6, -2, 0), foot_R=(-0.55, 0, 0), foot_L=(-0.38, 0, 0))),
        (30, dict(hips=(-0.45, 0, -0.04), foot_R=(-0.55, 0, 0), foot_L=(-0.38, 0, 0))),
        (36, dict(hips=(-0.22, 0, -0.06), foot_R=(-0.55, 0, 0), foot_L=(-0.10, 0, 0.08))),
        (42, dict(hips=(0, 0, -0.04), foot_R=(-0.20, 0, 0.08), foot_L=(0, 0, 0))),
        (48, dict()),
    ]))
    # --- ゲーム用:待機・被弾・倒れ
    acts.append(new_action(arm, "Idle", [
        (f, dict(hips=(0, 0, -0.012 - 0.008 * math.cos(2 * math.pi * f / 60)),
                 chest=(-1.5 * math.cos(2 * math.pi * f / 60), 0, 0),
                 sword=S(P0 + Vector((0, 0, 0.008 * math.cos(2 * math.pi * f / 60))), C["u"], C["hint"])))
        for f in range(0, 61, 10)], cyclic=True))
    acts.append(new_action(arm, "Hit", [
        (0, dict()),
        (4, dict(hips=(0, 0.08, -0.03), hips_rot=(-6, 0, 0), spine=(-14, 0, 6), neck=(-10, 0, 0),
                 sword=S(P0 + Vector((0.05, 0.12, 0.10)), (0.1, -0.5, 0.86), (0, 0, -1)), foot_L=(0, 0.04, 0))),
        (10, dict(hips=(0, 0.10, -0.06), spine=(-6, 0, 3), sword=S(P0 + Vector((0.03, 0.10, 0.0)), (0.05, -0.7, 0.7), (0, 0, -1)),
                  foot_L=(0, 0.08, 0), foot_R=(0, 0.04, 0))),
        (20, dict()),
    ]))
    acts.append(new_action(arm, "Death", [
        (0, dict()),
        (6, dict(hips=(0, 0.06, -0.06), spine=(-10, 0, 0), neck=(-12, 0, 0),
                 sword=S(P0 + Vector((0.05, 0.12, 0.05)), (0.2, -0.4, 0.9), (0, 0, -1)))),
        (18, dict(hips=(0, -0.05, -0.45), spine=(24, 0, -6), neck=(15, 0, 0),
                  sword=S((0.25, -0.30, 0.30), (0.5, -0.8, -0.3), (0, 0, -1)), sword_follow=False)),
        (34, dict(hips=(0.05, -0.32, -0.66), hips_rot=(62, 0, 8), spine=(25, 0, -8), neck=(20, 0, 0),
                  sword=S((0.30, -0.45, 0.05), (0.55, -0.83, 0.0), (0, 0, -1)), sword_follow=False)),
        (60, dict(hips=(0.05, -0.34, -0.68), hips_rot=(64, 0, 8), spine=(25, 0, -8), neck=(22, 0, 0),
                  sword=S((0.30, -0.45, 0.03), (0.55, -0.83, 0.0), (0, 0, -1)), sword_follow=False)),
    ]))
    arm.animation_data.action = acts[0]
    scene = bpy.context.scene
    scene.render.fps = 30
    scene.frame_start, scene.frame_end = 0, 44
    pose_rig(arm)
    return acts


def assign_action(arm, act):
    arm.animation_data.action = act
    try:
        if not arm.animation_data.action_slot and act.slots:
            arm.animation_data.action_slot = act.slots[0]
    except AttributeError:
        pass
    bpy.context.scene.frame_start, bpy.context.scene.frame_end = map(int, act.frame_range)


def render_motion_previews(arm, acts, out_dir):
    """各モーションを低解像度で書き出し、GIF とコマ割りシートを作る"""
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = 400, 500
    scene.cycles.samples = int(os.environ.get("SAMURAI_ANIM_SAMPLES", 12))
    scene.camera.data.dof.use_dof = False
    frames_dir = os.path.join(out_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    sheet_rows = []
    for act in acts:
        assign_action(arm, act)
        a, b = map(int, act.frame_range)
        step = 2 if act.name in ("Run",) else 3
        files = []
        for f in range(a, b + (0 if "Walk" in act.name or "Run" in act.name else 1), step):
            scene.frame_set(f)
            fp = os.path.join(frames_dir, f"{act.name}_{f:03d}.png")
            scene.render.filepath = fp
            bpy.ops.render.render(write_still=True)
            files.append(fp)
        print(f"[samurai] rendered {len(files)} frames of {act.name}")
        sheet_rows.append((act.name, files))
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("[samurai] PIL not available; frames left in", frames_dir)
        return
    for name, files in sheet_rows:
        ims = [Image.open(f).convert("RGB") for f in files]
        dur = int(1000 / 30 * (2 if name == "Run" else 3))
        ims[0].save(os.path.join(out_dir, f"{name}.gif"), save_all=True, append_images=ims[1:],
                    duration=dur, loop=0)
    cols = 6
    tw, th = 200, 250
    sheet = Image.new("RGB", (cols * tw + 150, len(sheet_rows) * th), (235, 230, 222))
    d = ImageDraw.Draw(sheet)
    for r, (name, files) in enumerate(sheet_rows):
        idx = [round(i * (len(files) - 1) / (cols - 1)) for i in range(cols)]
        for c, i in enumerate(idx):
            sheet.paste(Image.open(files[i]).convert("RGB").resize((tw, th)), (150 + c * tw, r * th))
        d.text((10, r * th + th // 2), name, fill=(40, 30, 20))
    sheet.save(os.path.join(out_dir, "motions_sheet.png"))


def export_glb(arm, path):
    """Web(three.js)用 GLB:プロシージャルノードを外して基本色だけに、重いメッシュは間引く"""
    for mat in bpy.data.materials:
        if not mat.node_tree:
            continue
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        bsdf = nodes.get("Principled BSDF")
        if not bsdf:
            continue
        for inp in ("Base Color", "Roughness", "Normal"):
            for l in list(bsdf.inputs[inp].links):
                links.remove(l)
        for n in [n for n in nodes if n.type not in ("BSDF_PRINCIPLED", "OUTPUT_MATERIAL")]:
            nodes.remove(n)
    objs = [o for o in bpy.data.objects if o is arm or o.parent is arm or (o.parent and o.parent.parent is arm)]
    for o in objs:
        if o.type == "MESH":
            if "Subsurf" in o.modifiers:
                o.modifiers["Subsurf"].levels = 0
            n = len(o.data.polygons)
            if n > 3000:
                d = o.modifiers.new("Decimate", "DECIMATE")
                d.ratio = max(0.08, 3000 / n)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = arm
    pose_rig(arm)
    arm.animation_data.action = None
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=True,
                              export_animations=True, export_animation_mode="ACTIONS",
                              export_force_sampling=True, export_def_bones=False,
                              export_frame_step=1, export_yup=True)
    print(f"[samurai] exported {path}")


def main(pose=None):
    glb = pose == "glb"
    anim = pose in ("anim", "glb")
    if pose:
        set_pose("katana" if anim else pose)
    suffix = "_anim" if anim else ("" if POSE == "fan" else "_" + POSE)
    clear_scene()
    build_materials()
    c_body = collection("Samurai_Body")
    c_armor = collection("Samurai_Armor")
    c_kabuto = collection("Samurai_Kabuto")
    c_weap = collection("Samurai_Katana")
    c_scene = collection("Scene")
    build_body(c_body)
    build_armor(c_armor)
    build_kabuto(c_kabuto)
    build_katana(c_weap)
    build_scene(c_scene)
    if anim:
        arm = build_rig([c_body, c_armor, c_kabuto, c_weap])
        acts = build_actions(arm)
        assign_action(arm, acts[0])
        if glb:
            os.makedirs(os.path.join(OUT_DIR, "game"), exist_ok=True)
            export_glb(arm, os.path.join(OUT_DIR, "game", "samurai.glb"))
            return

    # 身長チェック(足裏〜頭頂: 髪・頭部のみで計測)
    dg = bpy.context.evaluated_depsgraph_get()
    top = max((o.matrix_world @ Vector(v)).z
              for o in c_body.objects if o.type == "MESH"
              for v in o.evaluated_get(dg).bound_box)
    print(f"[samurai] body height = {top * 100:.1f} cm")

    blend = os.path.join(OUT_DIR, f"samurai{suffix}.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    print(f"[samurai] saved {blend}")
    if anim:
        if bpy.app.background and os.environ.get("SAMURAI_NO_RENDER") != "1":
            scene = bpy.context.scene
            scene.render.engine = "CYCLES"
            scene.cycles.device = "CPU"
            scene.cycles.use_denoising = True
            render_motion_previews(arm, acts, os.path.join(OUT_DIR, "motions"))
        return

    if bpy.app.background:
        scene = bpy.context.scene
        # ヘッドレス環境でも動くよう Cycles(CPU) でプレビュー
        scene.render.engine = "CYCLES"
        scene.cycles.device = "CPU"
        scene.cycles.samples = int(os.environ.get("SAMURAI_SAMPLES", 160))
        scene.cycles.max_bounces = 8
        try:
            scene.view_settings.view_transform = "AgX"
            scene.view_settings.look = "AgX - Medium High Contrast"
        except TypeError:
            pass
        scene.cycles.use_denoising = True
        scene.render.resolution_x = 1080
        scene.render.resolution_y = 1350
        scene.render.filepath = os.path.join(OUT_DIR, f"samurai{suffix}_preview.png")
        try:
            bpy.ops.render.render(write_still=True)
            print(f"[samurai] rendered {scene.render.filepath}")
        except Exception as e:  # GPU のない環境では失敗することがある
            print(f"[samurai] render skipped: {e}")


if __name__ == "__main__":
    import sys
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not bpy.app.background:
        main(POSE)                       # GUI: POSE で指定したポーズ("anim" も可)
    else:
        for p in (args or ["fan", "katana", "anim"]):
            main(p)
