"""
斬撃の「溜め」と「鋭い振り」の緩急を強める — Blender 4.x / 5.x 用

使い方:
  1. アニメーション付きのアーマチュアを選択(アクティブ)にする
  2. 下の CONFIG で振りの範囲(STRIKE_START〜STRIKE_END)を指定
  3. Scripting タブで実行(Ctrl+Z で元に戻せます)

やること:
  ① 現在のアクションの全 F カーブについて、補間モード(BEZIER / LINEAR / EXPO …)を集計して表示
  ② 振りの区間を「爆発的な初速 → 急減速」にする
     - 区間内に中間キーが無い場合:開始キーの補間を EXPO(または BACK)、イージングを EASE_OUT に
     - 中間キーがある場合:中間キーを開始側へ寄せて(タイミングの前詰め)区間全体を ease-out にし、
       区間内は LINEAR でつなぐ。刀の軌道(弧)を保ったまま初速だけ上がる
  ③ 溜め:振りの直前の区間を減速して止まる形(QUART / EASE_OUT)にし、構えで一瞬「溜まる」
  ④ 残心:振りの直後の区間を BACK / EASE_OUT にし、わずかに行き過ぎてから収まる

Blender 4.4 以降のアクションはスロット/チャンネルバッグ構造で、5.0 では action.fcurves が
無くなったため、両方の構造から F カーブを集めます。
"""
import math
from collections import Counter

import bpy

# ------------------------------------------------------------------ CONFIG
STRIKE_START = 5          # 振り始めのフレーム(溜めの頂点)
STRIKE_END = 10           # 振り切り(インパクト後)のフレーム
STRIKE_EASE = "EXPO"      # "EXPO"(指数関数的) または "BACK"
STRENGTH = 3.0            # 中間キー前詰めの強さ(1=変化なし、2〜4 が目安。大きいほど初速が鋭い)
ANTICIPATION = True       # 振りの直前を減速させて溜めを作る
FOLLOW_THROUGH = True     # 振りの直後に BACK でわずかな行き過ぎ
BACK_AMOUNT = 1.4         # BACK の行き過ぎ量(Blender の既定は 1.70158)
ONLY_SELECTED_BONES = False   # True なら選択中のポーズボーンの F カーブだけを対象


def action_fcurves(obj):
    """4.x(従来)と 4.4+/5.x(スロット付きアクション)の両方から F カーブを返す"""
    ad = obj.animation_data
    action = ad.action if ad else None
    if action is None:
        return None, []
    if hasattr(action, "fcurves") and len(getattr(action, "fcurves", [])):
        return action, list(action.fcurves)
    curves = []
    slot = getattr(ad, "action_slot", None)
    for layer in getattr(action, "layers", []):
        for strip in layer.strips:
            if slot is not None and hasattr(strip, "channelbag"):
                cb = strip.channelbag(slot)
                if cb:
                    curves.extend(cb.fcurves)
            else:
                for cb in strip.channelbags:
                    curves.extend(cb.fcurves)
    return action, curves


def bone_of(fc):
    p = fc.data_path
    if p.startswith('pose.bones["'):
        return p.split('"')[1]
    return None


def front_load(t, k):
    """区間内の位置 t(0..1)を ease-out の逆関数で前へ寄せる。k が大きいほど初速が鋭い"""
    return 1.0 - (1.0 - t) ** (1.0 / k)


def report_interpolation(curves):
    modes = Counter(kp.interpolation for fc in curves for kp in fc.keyframe_points)
    easing = Counter(kp.easing for fc in curves for kp in fc.keyframe_points)
    print("補間モード:", dict(modes))
    print("イージング:", dict(easing))
    return modes


def apply_snappy_slashing_easing(obj=None, start=STRIKE_START, end=STRIKE_END, ease=STRIKE_EASE,
                                 strength=STRENGTH, anticipation=ANTICIPATION,
                                 follow_through=FOLLOW_THROUGH, verbose=True):
    obj = obj or bpy.context.active_object
    if obj is None or obj.type != "ARMATURE":
        print("エラー: アニメーションが設定されたアーマチュアを選択してください。")
        return 0
    action, curves = action_fcurves(obj)
    if not action or not curves:
        print("エラー: アクティブなアクションに F カーブがありません。")
        return 0
    if ONLY_SELECTED_BONES and bpy.context.mode == "POSE":
        sel = {b.name for b in bpy.context.selected_pose_bones or []}
        curves = [fc for fc in curves if bone_of(fc) in sel]
    if verbose:
        print(f"対象アクション: {action.name}  F カーブ {len(curves)} 本  振り {start}〜{end} フレーム")
        report_interpolation(curves)

    span = float(end - start)
    changed = 0
    for fc in curves:
        kps = fc.keyframe_points
        # --- 中間キーを前詰め(どのチャンネルも同じ写像なので体の各部のタイミングは揃ったまま)
        inner = [kp for kp in kps if start < kp.co.x < end]
        for kp in inner:
            t = (kp.co.x - start) / span
            nx = start + span * front_load(t, strength)
            dx = nx - kp.co.x
            kp.co.x = nx
            kp.handle_left.x += dx
            kp.handle_right.x += dx
        fc.update()  # キーの並びを整える
        for i, kp in enumerate(kps):
            x = kp.co.x
            nxt = kps[i + 1].co.x if i + 1 < len(kps) else None
            if abs(x - start) < 1e-4 and nxt is not None:
                if inner:
                    kp.interpolation = "LINEAR"          # 前詰めしたキーへ一直線に飛び出す
                else:
                    kp.interpolation = ease              # EXPO / BACK
                    kp.easing = "EASE_OUT"               # 初速最大 → 減速
                    if ease == "BACK":
                        kp.back = BACK_AMOUNT
                changed += 1
            elif start < x < end:
                is_last_inner = nxt is not None and nxt >= end - 1e-4
                if is_last_inner:
                    kp.interpolation = "QUART"           # インパクト後は急減速
                    kp.easing = "EASE_OUT"
                else:
                    kp.interpolation = "LINEAR"
                changed += 1
            elif anticipation and nxt is not None and abs(nxt - start) < 1e-4:
                kp.interpolation = "QUART"               # 溜め:構えに向かって減速して止まる
                kp.easing = "EASE_OUT"
                changed += 1
            elif follow_through and abs(x - end) < 1e-4 and nxt is not None:
                kp.interpolation = "BACK"                # 残心:わずかに行き過ぎて収まる
                kp.easing = "EASE_OUT"
                kp.back = BACK_AMOUNT
                changed += 1
        fc.update()
    if verbose:
        print(f"完了: {changed} 個のキーの補間を変更しました。")
        report_interpolation(curves)
    return changed


if __name__ == "__main__":
    apply_snappy_slashing_easing()
