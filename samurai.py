"""
175cm 男性サムライ — Blender プロシージャル生成スクリプト

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


def build_materials():
    M["skin"] = material("Skin", (0.80, 0.60, 0.47), roughness=0.55)
    M["hair"] = material("Hair", (0.02, 0.02, 0.02), roughness=0.4)
    M["eye"] = material("Eye", (0.03, 0.02, 0.015), roughness=0.1)
    M["kimono"] = material("Kimono_Indigo", (0.04, 0.06, 0.16), roughness=0.85)
    M["hakama"] = material("Hakama_Charcoal", (0.06, 0.06, 0.065), roughness=0.9)
    M["lacquer"] = material("Lacquer_Red", (0.45, 0.03, 0.03), roughness=0.25)
    M["lacquer_bk"] = material("Lacquer_Black", (0.015, 0.015, 0.015), roughness=0.2)
    M["lace"] = material("Odoshi_Lace", (0.55, 0.40, 0.08), roughness=0.7)
    M["gold"] = material("Gold", (1.0, 0.72, 0.25), metallic=1.0, roughness=0.25)
    M["steel"] = material("Steel", (0.80, 0.80, 0.82), metallic=1.0, roughness=0.15)
    M["tsuka"] = material("Tsuka_Ito", (0.03, 0.03, 0.05), roughness=0.8)
    M["saya"] = material("Saya", (0.02, 0.02, 0.02), roughness=0.15)
    M["sandal"] = material("Waraji_Straw", (0.65, 0.55, 0.32), roughness=0.95)
    M["tabi"] = material("Tabi_White", (0.85, 0.85, 0.82), roughness=0.9)
    M["obi"] = material("Obi", (0.35, 0.28, 0.12), roughness=0.8)
    M["ground"] = material("Ground", (0.25, 0.24, 0.22), roughness=0.95)


# ---------------------------------------------------------------- body
def build_body(coll):
    # 頭部
    head = sphere("Head", (0, 0, H["head_c"]), (0.078, 0.095, 0.115), M["skin"], coll)
    sphere("Jaw", (0, -0.015, H["chin"] + 0.04), (0.060, 0.07, 0.05), M["skin"], coll)
    sphere("Nose", (0, -0.093, H["head_c"] - 0.015), (0.012, 0.015, 0.022), M["skin"], coll)
    for s in (-1, 1):
        sphere(f"Ear.{'L' if s > 0 else 'R'}", (s * 0.078, 0.0, H["head_c"]),
               (0.012, 0.022, 0.032), M["skin"], coll, segs=16)
        sphere(f"Eye.{'L' if s > 0 else 'R'}", (s * 0.032, -0.082, H["head_c"] + 0.012),
               (0.012, 0.006, 0.007), M["eye"], coll, segs=16)
        cube(f"Brow.{'L' if s > 0 else 'R'}", (s * 0.033, -0.086, H["head_c"] + 0.032),
             (0.03, 0.006, 0.006), M["hair"], coll, rot=(0, s * 0.15, 0))
    # 髷(ちょんまげ)と頭髪
    sphere("Hair_Back", (0, 0.02, H["head_c"] + 0.01), (0.082, 0.085, 0.105), M["hair"], coll)
    cylinder("Chonmage", (0, -0.01, H["top"] - 0.012), 0.012, 0.09, M["hair"], coll,
             rot=(math.radians(90), 0, 0))
    # 口髭
    cube("Mustache", (0, -0.09, H["head_c"] - 0.05), (0.05, 0.006, 0.008), M["hair"], coll, bevel=0.003)

    # 首
    limb("Neck", (0, 0.005, H["neck"] - 0.04), (0, 0.005, H["chin"] + 0.02), 0.058, 0.052, M["skin"], coll)

    # 胴体(着物で覆われた上半身)
    torso = lofted("Torso_Kimono", [
        (H["crotch"] + 0.02, 0.15, 0.10),
        (H["hip"], 0.175, 0.115),
        (H["waist"], 0.155, 0.105),
        (H["chest"] - 0.08, 0.17, 0.115),
        (H["chest"], 0.18, 0.12),
        (H["shoulder"] - 0.02, 0.19, 0.105),
        (H["shoulder"] + 0.02, 0.12, 0.08),
        (H["neck"] - 0.01, 0.065, 0.06),
    ], M["kimono"], coll)
    subsurf(torso, 1)

    # 腕(肩→肘→手首)
    for s, side in ((-1, "R"), (1, "L")):
        sh = (s * 0.20, 0.0, H["shoulder"] - 0.01)
        el = (s * 0.25, -0.02, 1.13)
        wr = (s * 0.24, -0.12, 0.93)
        sphere(f"Shoulder.{side}", sh, (0.06, 0.06, 0.06), M["kimono"], coll)
        limb(f"UpperArm.{side}", sh, el, 0.058, 0.048, M["kimono"], coll)
        sphere(f"Elbow.{side}", el, (0.048, 0.048, 0.048), M["kimono"], coll)
        limb(f"Forearm.{side}", el, wr, 0.046, 0.034, M["skin"], coll)
        hand = sphere(f"Hand.{side}", (wr[0], wr[1] - 0.04, wr[2] - 0.03),
                      (0.028, 0.05, 0.045), M["skin"], coll)
        # 籠手(こて)
        kote = limb(f"Kote.{side}", el, (wr[0], wr[1] + 0.02, wr[2] + 0.02), 0.052, 0.040,
                    M["lacquer_bk"], coll, verts=12)
        for p in kote.data.polygons:
            p.use_smooth = False

    # 脚(袴の下):股関節→膝→足首
    for s, side in ((-1, "R"), (1, "L")):
        hp = (s * 0.095, 0.0, H["crotch"] + 0.05)
        kn = (s * 0.11, -0.01, H["knee"])
        an = (s * 0.115, 0.01, H["ankle"] + 0.02)
        limb(f"Thigh.{side}", hp, kn, 0.085, 0.058, M["hakama"], coll)
        limb(f"Shin.{side}", kn, an, 0.056, 0.038, M["skin"], coll)
        # 脛当(すねあて)
        limb(f"Suneate.{side}", (kn[0], kn[1] - 0.005, kn[2] - 0.03),
             (an[0], an[1] - 0.005, an[2] + 0.06), 0.062, 0.045, M["lacquer_bk"], coll, verts=10)
        # 足袋+草鞋
        cube(f"Tabi.{side}", (an[0], -0.05, 0.035), (0.085, 0.24, 0.07), M["tabi"], coll, bevel=0.025, smooth=True)
        cube(f"Waraji.{side}", (an[0], -0.05, 0.006), (0.10, 0.26, 0.012), M["sandal"], coll, bevel=0.004)
    return head


# ---------------------------------------------------------------- clothing & armor
def build_armor(coll):
    # 袴(はかま) — 広がった裾のスカート状
    hakama = lofted("Hakama", [
        (0.10, 0.36, 0.26),
        (0.30, 0.31, 0.22),
        (0.60, 0.24, 0.17),
        (H["hip"] - 0.02, 0.185, 0.125),
        (H["waist"] - 0.02, 0.165, 0.112),
    ], M["hakama"], coll, cap_bottom=False)
    sol = hakama.modifiers.new("Solidify", "SOLIDIFY")
    sol.thickness = 0.008
    subsurf(hakama, 1)
    # 袴の股割れ(前の縦プリーツ)
    for i, x in enumerate((-0.09, -0.03, 0.03, 0.09)):
        cube(f"Hakama_Pleat.{i}", (x, -0.17 - abs(x) * 0.3, 0.55), (0.012, 0.012, 0.85),
             M["hakama"], coll, rot=(math.radians(-6), 0, 0))

    # 帯
    lofted("Obi", [(H["waist"] - 0.05, 0.168, 0.116), (H["waist"] + 0.04, 0.162, 0.112)],
           M["obi"], coll)

    # 胴(どう) — 漆塗りの胴鎧
    do = lofted("Do_Cuirass", [
        (H["waist"] - 0.04, 0.178, 0.125),
        (H["chest"] - 0.10, 0.185, 0.13),
        (H["chest"], 0.195, 0.135),
        (H["shoulder"] - 0.06, 0.19, 0.12),
    ], M["lacquer"], coll, cap_top=False, cap_bottom=False)
    do.modifiers.new("Solidify", "SOLIDIFY").thickness = 0.01
    # 胴の段(横の小札ライン)
    for i in range(6):
        z = H["waist"] - 0.02 + i * 0.045
        lofted(f"Do_Lame.{i}", [(z, 0.188, 0.133), (z + 0.008, 0.188, 0.133)],
               M["lace"], coll)

    # 草摺(くさずり) — 腰回りの垂れ板 5 枚 × 4 段
    for k in range(7):
        ang = math.radians(-90 + (k - 3) * 30)
        cx, cy = math.cos(ang) * 0.20, math.sin(ang) * 0.15
        for row in range(4):
            z = H["waist"] - 0.10 - row * 0.065
            r = 1.0 + row * 0.08
            cube(f"Kusazuri.{k}.{row}", (cx * r, cy * r, z), (0.12, 0.012, 0.06),
                 M["lacquer"] if row % 2 == 0 else M["lacquer_bk"], coll,
                 rot=(math.radians(-12 if cy < 0 else 12), 0, ang + math.pi / 2), bevel=0.004)

    # 大袖(おおそで) — 肩の大きな板
    for s, side in ((-1, "R"), (1, "L")):
        for row in range(5):
            z = H["shoulder"] - 0.01 - row * 0.05
            cube(f"Sode.{side}.{row}", (s * (0.26 + row * 0.006), 0.0, z),
                 (0.012, 0.17, 0.052),
                 M["lacquer"] if row % 2 == 0 else M["lacquer_bk"], coll,
                 rot=(0, s * math.radians(-12), 0), bevel=0.004)
        # 肩上(わたがみ)
        cube(f"Watagami.{side}", (s * 0.13, 0.0, H["shoulder"] + 0.01), (0.12, 0.17, 0.025),
             M["lacquer_bk"], coll, rot=(0, s * math.radians(-18), 0), bevel=0.006)

    # 喉輪(のどわ)
    lofted("Nodowa", [(H["neck"] - 0.04, 0.09, 0.08), (H["neck"] + 0.01, 0.075, 0.068)],
           M["lacquer_bk"], coll)


def build_kabuto(coll):
    hz = H["head_c"] + 0.02
    # 鉢(はち)
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
    finish(hachi, "Kabuto_Hachi", M["lacquer_bk"], coll)
    # 筋(すじ)
    for i in range(12):
        a = i * math.pi / 12
        bpy.ops.mesh.primitive_torus_add(major_radius=1.0, minor_radius=0.03,
                                         location=(0, 0.005, hz), rotation=(0, math.pi / 2, a))
        t = bpy.context.active_object
        t.scale = (0.106, 0.121, 0.126)
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        bm = bmesh.new()
        bm.from_mesh(t.data)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < 0.0], context="VERTS")
        bm.to_mesh(t.data)
        bm.free()
        finish(t, f"Kabuto_Suji.{i}", M["gold"], coll)
    # 眉庇(まびさし)
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=1, depth=0.006,
                                        location=(0, -0.01, hz + 0.005))
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

    # 錣(しころ) — 首を守る段々の垂れ
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
        finish(sh, f"Kabuto_Shikoro.{row}", M["lacquer"] if row % 2 == 0 else M["lacquer_bk"], coll)
        # 吹返し(ふきかえし)
        if row == 0:
            for s in (-1, 1):
                cube(f"Fukigaeshi.{'L' if s > 0 else 'R'}", (s * 0.135, -0.07, z + 0.01),
                     (0.01, 0.07, 0.05), M["lacquer"], coll,
                     rot=(0, 0, s * math.radians(-40)), bevel=0.004)

    # 前立て(まえだて) — 鍬形(くわがた)
    for s in (-1, 1):
        bpy.ops.curve.primitive_bezier_curve_add(location=(0, 0, 0))
        crv = bpy.context.active_object
        crv.data.dimensions = "3D"
        crv.data.bevel_depth = 0.006
        crv.data.bevel_resolution = 2
        pts = crv.data.splines[0].bezier_points
        pts[0].co = (s * 0.02, -0.125, hz + 0.04)
        pts[0].handle_left = (s * 0.0, -0.12, hz + 0.0)
        pts[0].handle_right = (s * 0.08, -0.14, hz + 0.08)
        pts[1].co = (s * 0.13, -0.11, hz + 0.32)
        pts[1].handle_left = (s * 0.16, -0.13, hz + 0.20)
        pts[1].handle_right = (s * 0.10, -0.09, hz + 0.40)
        crv.data.materials.append(M["gold"])
        crv.name = f"Kuwagata.{'L' if s > 0 else 'R'}"
        for c in list(crv.users_collection):
            c.objects.unlink(crv)
        coll.objects.link(crv)
    cube("Maedate_Base", (0, -0.125, hz + 0.04), (0.06, 0.012, 0.04), M["gold"], coll, bevel=0.005)

    # 面頬(めんぽお) — 口元を覆う面
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, location=(0, -0.01, H["chin"] + 0.045))
    mp = bpy.context.active_object
    mp.scale = (0.072, 0.09, 0.065)
    apply_scale(mp)
    bm = bmesh.new()
    bm.from_mesh(mp.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.y > -0.02 or v.co.z > 0.04], context="VERTS")
    bm.to_mesh(mp.data)
    bm.free()
    mp.modifiers.new("Solidify", "SOLIDIFY").thickness = 0.005
    finish(mp, "Menpo", M["lacquer"], coll)


def build_katana(coll):
    """左腰に差した打刀(刃長約 70cm)と脇差"""
    def blade_set(prefix, length, tsuka_len, loc, rot):
        root = bpy.data.objects.new(prefix, None)
        coll.objects.link(root)
        root.location = loc
        root.rotation_euler = rot
        parts = [
            cylinder(f"{prefix}_Saya", (0, 0, -length / 2), 0.016, length, M["saya"], coll,
                     verts=16, scale=(1.0, 1.6, 1)),
            cylinder(f"{prefix}_Kojiri", (0, 0, -length - 0.01), 0.017, 0.02, M["gold"], coll,
                     verts=16, scale=(1.0, 1.6, 1)),
            cylinder(f"{prefix}_Tsuba", (0, 0, 0.005), 0.040, 0.008, M["gold"], coll, verts=24),
            cylinder(f"{prefix}_Tsuka", (0, 0, 0.01 + tsuka_len / 2), 0.015, tsuka_len, M["tsuka"], coll,
                     verts=16, scale=(1.0, 1.4, 1)),
            cylinder(f"{prefix}_Kashira", (0, 0, 0.012 + tsuka_len), 0.016, 0.012, M["gold"], coll,
                     verts=16, scale=(1.0, 1.4, 1)),
        ]
        for p in parts:
            p.parent = root
        return root

    # 柄を前、鞘を後ろ下へ向けて帯に差す
    blade_set("Katana", 0.73, 0.25, (0.20, -0.15, H["waist"] - 0.10),
              (math.radians(74), math.radians(-8), math.radians(12)))
    blade_set("Wakizashi", 0.48, 0.17, (0.14, -0.17, H["waist"] - 0.06),
              (math.radians(78), math.radians(-5), math.radians(6)))


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
    cam.location = (1.8, -3.6, 1.25)
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
