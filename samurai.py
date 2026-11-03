"""
175cm 男性サムライ(幕末の甲冑武者写真の装束を再現) — Blender プロシージャル生成スクリプト

使い方:
  Blender GUI : Scripting タブでこのファイルを開いて「Run Script」
  コマンド    : blender --background --python samurai.py
  (pip の bpy モジュールでも python3 samurai.py で動作)

単位はメートル。身長(足裏〜頭頂)= 1.75m。兜の前立てはその上に乗ります。
生成後、samurai.blend と samurai_preview.png を同じフォルダに保存します。
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


def material(name, color, metallic=0.0, roughness=0.5):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    mat.diffuse_color = (*color, 1.0)
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
    M["skin"] = material("Skin", (0.62, 0.45, 0.34), roughness=0.55)
    M["hair"] = material("Hair", (0.02, 0.02, 0.02), roughness=0.4)
    M["eye"] = material("Eye", (0.03, 0.02, 0.015), roughness=0.1)
    M["under"] = material("Under_Kimono", (0.025, 0.025, 0.03), roughness=0.85)
    M["jinbaori"] = material("Jinbaori_Brown", (0.13, 0.075, 0.045), roughness=0.8)
    M["trim"] = material("Trim_Cream", (0.78, 0.68, 0.48), roughness=0.6)
    M["lacquer_bk"] = material("Lacquer_Black", (0.018, 0.016, 0.014), roughness=0.25)
    M["lacquer_br"] = material("Lacquer_Brown", (0.07, 0.04, 0.025), roughness=0.3)
    M["lace"] = material("Odoshi_Dark", (0.035, 0.035, 0.05), roughness=0.8)
    M["kusari"] = material("Kusari_Mail", (0.05, 0.05, 0.055), metallic=0.7, roughness=0.5)
    M["cord"] = material("Cord_Cream", (0.82, 0.74, 0.56), roughness=0.75)
    M["brass"] = material("Brass_Pale", (0.85, 0.76, 0.52), metallic=0.6, roughness=0.35)
    M["gold"] = material("Gold", (0.9, 0.7, 0.3), metallic=1.0, roughness=0.3)
    M["tsuka"] = material("Tsuka_Ito", (0.04, 0.035, 0.03), roughness=0.8)
    M["saya"] = material("Saya", (0.03, 0.025, 0.02), roughness=0.2)
    M["sandal"] = material("Waraji_Straw", (0.55, 0.47, 0.30), roughness=0.95)
    M["tabi"] = material("Tabi_Dark", (0.04, 0.04, 0.045), roughness=0.9)
    M["paper"] = material("Fan_Paper", (0.92, 0.90, 0.85), roughness=0.7)
    M["obi"] = checker_material("Obi_Check", (0.30, 0.24, 0.17), (0.12, 0.09, 0.07), 60)
    M["ground"] = material("Ground", (0.30, 0.28, 0.25), roughness=0.95)


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
R_SH, R_EL, R_WR = (-0.20, 0.0, 1.42), (-0.37, -0.10, 1.25), (-0.52, -0.24, 1.23)  # 扇を掲げる右腕
L_SH, L_EL, L_WR = (0.20, 0.0, 1.42), (0.27, 0.0, 1.14), (0.27, -0.07, 0.93)      # 下ろした左腕


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
        limb(f"Hand.{side}", c, c + d * 0.10, 0.036, 0.028, M["skin"], coll, verts=16)
        limb(f"Tekko.{side}", c - d * 0.005, c + d * 0.06, 0.040, 0.034, M["lacquer_bk"], coll, verts=8)

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
        rz = s * math.radians(-15)
        cube(f"Tabi.{side}", (an[0] + s * 0.02, -0.05, 0.035), (0.085, 0.24, 0.07), M["tabi"], coll,
             rot=(0, 0, rz), bevel=0.025, smooth=True)
        cube(f"Waraji.{side}", (an[0] + s * 0.02, -0.05, 0.006), (0.10, 0.26, 0.012), M["sandal"], coll,
             rot=(0, 0, rz), bevel=0.004)
        for t in (-0.05, 0.05):
            cube(f"Waraji_Strap.{side}.{t}", (an[0] + s * 0.02, -0.05 + t, 0.05), (0.09, 0.012, 0.012),
                 M["sandal"], coll, rot=(0, 0, rz))
    return head


# ---------------------------------------------------------------- clothing & armor
def open_shell(name, rings, a0, a1, mat, coll, segs=40, thickness=0.008):
    """前が開いた筒状の布(陣羽織)。a0→a1 は角度(度)の範囲"""
    verts, faces = [], []
    n = segs + 1
    for z, rx, ry in rings:
        for i in range(n):
            a = math.radians(a0 + (a1 - a0) * i / segs)
            verts.append((rx * math.cos(a), ry * math.sin(a), z))
    for r in range(len(rings) - 1):
        for i in range(segs):
            p = r * n + i
            faces.append((p, p + 1, p + 1 + n, p + n))
    o = mesh_from(name, verts, faces, mat, coll, thickness=thickness)
    left = [verts[r * n] for r in range(len(rings))]
    right = [verts[r * n + segs] for r in range(len(rings))]
    hem = verts[:n]
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
                 M["lacquer_bk"] if row % 2 == 0 else M["lacquer_br"], coll,
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
                 (0.012, 0.12, 0.04), M["lacquer_bk"] if row % 2 == 0 else M["lacquer_br"], coll,
                 rot=(0, s * math.radians(-12), 0), bevel=0.003)
    lofted("Nodowa", [(H["neck"] - 0.04, 0.09, 0.08), (H["neck"] + 0.005, 0.075, 0.068)], M["lacquer_bk"], coll)

    # 陣羽織 — 袖なし、前開き、膝丈、肩が張り出す。縁はクリーム色
    rings = [(0.52, 0.33, 0.27), (0.75, 0.30, 0.245), (0.95, 0.27, 0.215), (1.10, 0.24, 0.185),
             (1.28, 0.25, 0.175), (1.39, 0.30, 0.165), (1.45, 0.25, 0.135), (1.49, 0.12, 0.10)]
    jb, left, right, hem = open_shell("Jinbaori", rings, -55, 235, M["jinbaori"], coll)
    subsurf(jb, 1)
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
        finish(sh, f"Kabuto_Shikoro.{row}", M["lacquer_bk"] if row % 2 == 0 else M["lace"], coll)
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
        o.location = (0, -0.132, hz + 0.04)
        o.rotation_euler = (math.radians(-15), 0, 0)
    cube("Kuwagata_Dai", (0, -0.128, hz + 0.035), (0.10, 0.012, 0.035), M["lacquer_bk"], coll, bevel=0.006)
    cylinder("Maedate_Mon", (0, -0.14, hz + 0.05), 0.022, 0.008, M["brass"], coll, rot=(math.radians(90), 0, 0))

    # 面頬(黒、鼻と髭付き)+ 垂(よだれかけ)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, location=(0, -0.008, H["chin"] + 0.05))
    mp = bpy.context.active_object
    mp.scale = (0.080, 0.096, 0.078)
    apply_scale(mp)
    bm = bmesh.new()
    bm.from_mesh(mp.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.y > -0.025 or v.co.z > 0.045], context="VERTS")
    bm.to_mesh(mp.data)
    bm.free()
    mp.modifiers.new("Solidify", "SOLIDIFY").thickness = 0.006
    finish(mp, "Menpo", M["lacquer_bk"], coll)
    sphere("Menpo_Nose", (0, -0.103, H["head_c"] - 0.022), (0.016, 0.02, 0.026), M["lacquer_bk"], coll, segs=16)
    for s in (-1, 1):
        cube(f"Menpo_Hige.{s}", (s * 0.028, -0.104, H["head_c"] - 0.058), (0.045, 0.008, 0.012),
             M["lacquer_br"], coll, rot=(0, s * math.radians(-18), 0), bevel=0.004)
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


def build_katana(coll):
    """左腰に水平気味に差した打刀・脇差と、右手に掲げた扇"""
    def blade_set(prefix, length, tsuka_len, loc, rot):
        root = bpy.data.objects.new(prefix, None)
        coll.objects.link(root)
        root.location = loc
        root.rotation_euler = rot
        parts = [
            cylinder(f"{prefix}_Saya", (0, 0, -length / 2), 0.016, length, M["saya"], coll, verts=16, scale=(1.0, 1.6, 1)),
            cylinder(f"{prefix}_Kojiri", (0, 0, -length - 0.01), 0.017, 0.02, M["brass"], coll, verts=16, scale=(1.0, 1.6, 1)),
            cylinder(f"{prefix}_Tsuba", (0, 0, 0.005), 0.040, 0.008, M["lacquer_bk"], coll, verts=24),
            cylinder(f"{prefix}_Tsuka", (0, 0, 0.01 + tsuka_len / 2), 0.015, tsuka_len, M["tsuka"], coll, verts=16, scale=(1.0, 1.4, 1)),
            cylinder(f"{prefix}_Kashira", (0, 0, 0.012 + tsuka_len), 0.016, 0.012, M["brass"], coll, verts=16, scale=(1.0, 1.4, 1)),
        ]
        # 柄巻きの菱
        for i in range(6):
            parts.append(cube(f"{prefix}_Hishi.{i}", (0, -0.022, 0.03 + i * tsuka_len / 6.5), (0.012, 0.004, 0.012),
                              M["cord"], coll, rot=(0, math.radians(45), 0)))
        for p in parts:
            p.parent = root
        return root

    # 柄は体の前で内向き、鞘は後方へ水平に伸びる
    blade_set("Katana", 0.73, 0.25, (0.21, -0.16, H["waist"] - 0.07),
              (math.radians(84), 0, math.radians(-35)))
    blade_set("Wakizashi", 0.48, 0.17, (0.15, -0.18, H["waist"] - 0.02),
              (math.radians(86), 0, math.radians(-45)))

    # 扇(右手で横へ掲げる)
    pivot = Vector(R_WR) + (Vector(R_WR) - Vector(R_EL)).normalized() * 0.07
    verts = [tuple(pivot)]
    n = 14
    for i in range(n + 1):
        a = math.radians(95 + 95 * i / n)
        verts.append(tuple(pivot + Vector((math.cos(a) * 0.30, -0.02 * math.sin(a), math.sin(a) * 0.30))))
    faces = [(0, i, i + 1) for i in range(1, n + 1)]
    mesh_from("Fan", verts, faces, M["paper"], coll, thickness=0.003, smooth=False)
    for i in range(0, n + 1, 2):
        curve(f"Fan_Rib.{i}", [tuple(pivot), verts[i + 1]], 0.0025, M["lacquer_br"], coll, smooth=False)


# ---------------------------------------------------------------- scene
def build_scene(coll):
    bpy.ops.mesh.primitive_plane_add(size=8, location=(0, 0, 0))
    finish(bpy.context.active_object, "Ground", M["ground"], coll, smooth=False)

    # 身長スケール参照(175cm マーカー)
    cube("HeightRef_175cm", (0.7, 0.3, HEIGHT / 2), (0.01, 0.01, HEIGHT),
         material("Ref", (0.9, 0.1, 0.1), roughness=0.5), coll)

    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 50
    cam = bpy.data.objects.new("Camera", cam_data)
    coll.objects.link(cam)
    cam.location = (0.9, -3.9, 1.2)
    target = Vector((0, 0, 0.95))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam

    def light(name, kind, loc, energy, size=1.0):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = energy
        if kind == "AREA":
            ld.size = size
        lo = bpy.data.objects.new(name, ld)
        coll.objects.link(lo)
        lo.location = loc
        lo.rotation_euler = (Vector((0, 0, 1.0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    light("Key", "AREA", (2.5, -3.0, 3.5), 250, 2.0)
    light("Fill", "AREA", (-3.0, -2.0, 2.0), 80, 3.0)
    light("Rim", "AREA", (0.0, 3.0, 3.0), 200, 1.5)

    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.05, 0.05, 0.06, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6


def main():
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

    # 身長チェック(足裏〜頭頂: 髪・頭部のみで計測)
    dg = bpy.context.evaluated_depsgraph_get()
    top = max((o.matrix_world @ Vector(v)).z
              for o in c_body.objects if o.type == "MESH"
              for v in o.evaluated_get(dg).bound_box)
    print(f"[samurai] body height = {top * 100:.1f} cm")

    blend = os.path.join(OUT_DIR, "samurai.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    print(f"[samurai] saved {blend}")

    if bpy.app.background:
        scene = bpy.context.scene
        # ヘッドレス環境でも動くよう Cycles(CPU) でプレビュー
        scene.render.engine = "CYCLES"
        scene.cycles.device = "CPU"
        scene.cycles.samples = 64
        scene.cycles.use_denoising = True
        scene.render.resolution_x = 1080
        scene.render.resolution_y = 1350
        scene.render.filepath = os.path.join(OUT_DIR, "samurai_preview.png")
        try:
            bpy.ops.render.render(write_still=True)
            print(f"[samurai] rendered {scene.render.filepath}")
        except Exception as e:  # GPU のない環境では失敗することがある
            print(f"[samurai] render skipped: {e}")


if __name__ == "__main__":
    main()
