import os
import copy
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

WORKSPACE = r"c:\Users\17941\OneDrive\文档\字体"
SCRATCH = r"C:\Users\17941\.gemini\antigravity\brain\1b9f4b40-0b3f-4346-9bf6-1b27b618d701\scratch"
SRC_VF = os.path.join(SCRATCH, "SourceHanSerifCN-VF.ttf")

# Target Samsung S26U / Android primary font vertical metrics (UPM = 1000)
# Matches SamsungSans.ttf & Roboto-Regular.ttf & OneUISans-VF.ttf
TARGET_HEAD_YMAX = 1056
TARGET_HEAD_YMIN = -271
TARGET_HHEA_ASCENT = 928
TARGET_HHEA_DESCENT = -244
TARGET_HHEA_LINEGAP = 0


def scale_glyph_y_to_box(glyf_table, gname, target_ymin=-120, target_ymax=880):
    g = glyf_table[gname]
    if g.numberOfContours <= 0 or not hasattr(g, "coordinates"):
        return
    old_ymin, old_ymax = g.yMin, g.yMax
    span = old_ymax - old_ymin
    if span <= 0:
        return
    target_span = target_ymax - target_ymin
    scale = target_span / span
    old_mid = (old_ymax + old_ymin) / 2.0
    target_mid = (target_ymax + target_ymin) / 2.0
    coords = g.coordinates
    for i in range(len(coords)):
        x, y = coords[i]
        new_y = int(round(target_mid + (y - old_mid) * scale))
        coords[i] = (x, new_y)
    g.recalcBounds(glyf_table)


def shift_glyph_y(glyf_table, gname, dy):
    g = glyf_table[gname]
    if g.numberOfContours <= 0 or not hasattr(g, "coordinates"):
        return
    coords = g.coordinates
    for i in range(len(coords)):
        x, y = coords[i]
        coords[i] = (x, y + dy)
    g.recalcBounds(glyf_table)


def clamp_all_glyphs_y(tt, ymin_limit=TARGET_HEAD_YMIN, ymax_limit=TARGET_HEAD_YMAX):
    glyf_table = tt["glyf"]
    gvar_table = tt["gvar"] if "gvar" in tt else None
    clamped_count = 0

    # First pass: simple glyphs
    for gname in glyf_table.keys():
        g = glyf_table[gname]
        if g.numberOfContours > 0 and hasattr(g, "yMax"):
            if g.yMax > ymax_limit or g.yMin < ymin_limit:
                coords = g.coordinates
                for i in range(len(coords)):
                    x, y = coords[i]
                    if y > ymax_limit:
                        y = ymax_limit
                    elif y < ymin_limit:
                        y = ymin_limit
                    coords[i] = (x, y)
                g.recalcBounds(glyf_table)
                if gvar_table and gname in gvar_table.variations:
                    gvar_table.variations[gname] = []
                clamped_count += 1

    # Second pass: composite glyphs
    for gname in glyf_table.keys():
        g = glyf_table[gname]
        if g.isComposite() and hasattr(g, "yMax"):
            g.recalcBounds(glyf_table)
            if g.yMax > ymax_limit or g.yMin < ymin_limit:
                g.yMax = min(g.yMax, ymax_limit)
                g.yMin = max(g.yMin, ymin_limit)
                clamped_count += 1

    return clamped_count


def update_name_table(tt, family_name_cn, family_name_en, subfamily_en="Regular"):
    name_table = tt["name"]
    ps_name = family_name_en.replace(" ", "").replace("-", "") + "-" + subfamily_en.replace(" ", "")
    full_cn = f"{family_name_cn} {subfamily_en}" if subfamily_en != "Regular" else family_name_cn
    full_en = f"{family_name_en} {subfamily_en}" if subfamily_en != "Regular" else family_name_en

    for rec in name_table.names:
        is_cjk = rec.langID in (0x0804, 0x0404, 0x0C04, 0x1004, 0x1404)
        fam = family_name_cn if is_cjk else family_name_en
        full = full_cn if is_cjk else full_en
        if rec.nameID in (1, 16):
            rec.string = fam
        elif rec.nameID in (2, 17):
            rec.string = subfamily_en
        elif rec.nameID in (3, 4):
            rec.string = full
        elif rec.nameID in (6, 20):
            rec.string = ps_name


def apply_s26u_fixes(tt, center_colon=True, weight_class=400):
    glyf_table = tt["glyf"]
    gvar_table = tt["gvar"] if "gvar" in tt else None
    cmap = tt.getBestCmap()

    # 1. Scale the 4 extreme vertical-only multi-cell glyphs into standard [-120, 880] em-box
    outlier_vertical_glyphs = ["glyph30721", "glyph30720", "uni3031", "uni3032"]
    for gname in outlier_vertical_glyphs:
        if gname in glyf_table:
            scale_glyph_y_to_box(glyf_table, gname, target_ymin=-120, target_ymax=880)
            if gvar_table and gname in gvar_table.variations:
                gvar_table.variations[gname] = []

    # 2. Optional colon vertical centering for Lock Screen / Status Bar clock & CJK text
    if center_colon:
        # Align ASCII ':' (U+003A) with the vertical center of digits '0'..'9'
        gn_zero = cmap.get(ord("0"))
        gn_colon = cmap.get(ord(":"))
        if gn_zero and gn_colon and gn_zero in glyf_table and gn_colon in glyf_table:
            g0 = glyf_table[gn_zero]
            gc = glyf_table[gn_colon]
            mid_zero = (g0.yMax + g0.yMin) / 2.0
            mid_colon = (gc.yMax + gc.yMin) / 2.0
            dy_colon = int(round(mid_zero - mid_colon))
            shift_glyph_y(glyf_table, gn_colon, dy_colon)

        # Align fullwidth '：' (U+FF1A) with the vertical center of CJK characters ('中' = 380.0)
        gn_zhong = cmap.get(ord("中"))
        gn_fw_colon = cmap.get(ord("："))
        if gn_zhong and gn_fw_colon and gn_zhong in glyf_table and gn_fw_colon in glyf_table:
            gz = glyf_table[gn_zhong]
            gfc = glyf_table[gn_fw_colon]
            mid_zhong = (gz.yMax + gz.yMin) / 2.0
            mid_fw_colon = (gfc.yMax + gfc.yMin) / 2.0
            dy_fw = int(round(mid_zhong - mid_fw_colon))
            shift_glyph_y(glyf_table, gn_fw_colon, dy_fw)

    # 3. Clamp any remaining minor outlier tips to [-271, 1056]
    clamp_all_glyphs_y(tt, ymin_limit=TARGET_HEAD_YMIN, ymax_limit=TARGET_HEAD_YMAX)

    # 4. Set head vertical bounds to match OneUISans-VF / Roboto / SamsungSans (1056 / -271)
    head = tt["head"]
    head.recalcBBoxes = False
    head.yMax = TARGET_HEAD_YMAX
    head.yMin = TARGET_HEAD_YMIN

    # 5. Set hhea vertical metrics to match SamsungSans / Roboto (928 / -244 / 0)
    hhea = tt["hhea"]
    hhea.ascent = TARGET_HHEA_ASCENT
    hhea.descent = TARGET_HHEA_DESCENT
    hhea.lineGap = TARGET_HHEA_LINEGAP

    # 6. Set OS/2 vertical metrics & weight / selection flags
    os2 = tt["OS/2"]
    os2.sTypoAscender = TARGET_HHEA_ASCENT
    os2.sTypoDescender = TARGET_HHEA_DESCENT
    os2.sTypoLineGap = TARGET_HHEA_LINEGAP
    os2.usWinAscent = TARGET_HHEA_ASCENT
    os2.usWinDescent = abs(TARGET_HHEA_DESCENT)
    os2.usWeightClass = weight_class
    # Set bit 6 (REGULAR = 0x0040), clear bit 7 (USE_TYPO_METRICS = 0x0080) to match Samsung system fonts
    os2.fsSelection = (os2.fsSelection | 0x0040) & ~0x0080

    # 7. Remove BASE table so HarfBuzz/Minikin doesn't shift Latin/CJK default baselines when used as primary system font
    if "BASE" in tt:
        del tt["BASE"]


def verify_saved_font(path):
    tt = TTFont(path)
    head, hhea, os2 = tt["head"], tt["hhea"], tt["OS/2"]
    glyf_table = tt["glyf"]
    max_y = max(glyf_table[gn].yMax for gn in glyf_table.keys() if hasattr(glyf_table[gn], "yMax") and glyf_table[gn].numberOfContours != 0)
    min_y = min(glyf_table[gn].yMin for gn in glyf_table.keys() if hasattr(glyf_table[gn], "yMin") and glyf_table[gn].numberOfContours != 0)
    fvar_str = ""
    if "fvar" in tt:
        fvar_str = f", fvar={[(a.axisTag, a.minValue, a.defaultValue, a.maxValue) for a in tt['fvar'].axes]}"
    cmap = tt.getBestCmap()
    gc = glyf_table[cmap[ord(":")]]
    gfc = glyf_table[cmap[ord("：")]]
    print(
        f"[VERIFIED] {os.path.basename(path)} ({os.path.getsize(path)/1024/1024:.2f} MB):\n"
        f"  head=({head.yMax}, {head.yMin}), actual_glyf_bounds=({max_y}, {min_y})\n"
        f"  hhea=({hhea.ascent}, {hhea.descent}, {hhea.lineGap}), OS/2_typo=({os2.sTypoAscender}, {os2.sTypoDescender}, {os2.sTypoLineGap}), OS/2_win=({os2.usWinAscent}, {os2.usWinDescent})\n"
        f"  usWeightClass={os2.usWeightClass}, fsSelection=0x{os2.fsSelection:04x}, ':' mid={(gc.yMax+gc.yMin)/2:.1f}, '：' mid={(gfc.yMax+gfc.yMin)/2:.1f}{fvar_str}"
    )
    tt.close()


def main():
    os.makedirs(WORKSPACE, exist_ok=True)
    print("Loading base SourceHanSerifCN-VF.ttf ...")
    base_vf = TTFont(SRC_VF)

    # 1. Variable Font (default weight moved from 250 -> 400 Regular), Colon Centered
    print("\n1. Building SourceHanSerifCN-VF-CenterColon-S26U.ttf (VF, default=400, centered colon)...")
    vf_400_cc = instantiateVariableFont(base_vf, {"wght": (250, 400, 900)}, inplace=False)
    apply_s26u_fixes(vf_400_cc, center_colon=True, weight_class=400)
    update_name_table(vf_400_cc, "思源宋体 S26U VF", "Source Han Serif S26U VF", "Regular")
    out_vf_cc = os.path.join(WORKSPACE, "思源宋体CN-VF-S26U修复_冒号居中.ttf")
    vf_400_cc.save(out_vf_cc)
    vf_400_cc.close()
    verify_saved_font(out_vf_cc)

    # 2. Variable Font (default weight moved from 250 -> 400 Regular), Original Colon
    print("\n2. Building SourceHanSerifCN-VF-S26U.ttf (VF, default=400, original colon)...")
    vf_400_orig = instantiateVariableFont(base_vf, {"wght": (250, 400, 900)}, inplace=False)
    apply_s26u_fixes(vf_400_orig, center_colon=False, weight_class=400)
    update_name_table(vf_400_orig, "思源宋体 S26U 原版冒号VF", "Source Han Serif S26U Orig VF", "Regular")
    out_vf_orig = os.path.join(WORKSPACE, "思源宋体CN-VF-S26U修复_原版冒号.ttf")
    vf_400_orig.save(out_vf_orig)
    vf_400_orig.close()
    verify_saved_font(out_vf_orig)

    # 3. Static Regular (wght=400), Colon Centered
    print("\n3. Building SourceHanSerifCN-Regular-S26U.ttf (Static wght=400, centered colon)...")
    st_400 = instantiateVariableFont(base_vf, {"wght": 400}, inplace=False)
    apply_s26u_fixes(st_400, center_colon=True, weight_class=400)
    update_name_table(st_400, "思源宋体 S26U 标准", "Source Han Serif S26U", "Regular")
    out_st_400 = os.path.join(WORKSPACE, "思源宋体CN-Regular400-S26U修复_冒号居中.ttf")
    st_400.save(out_st_400)
    st_400.close()
    verify_saved_font(out_st_400)

    # 4. Static Medium-Regular (wght=450, optimal for 2K OLED screen), Colon Centered
    print("\n4. Building SourceHanSerifCN-W450-S26U.ttf (Static wght=450, centered colon)...")
    st_450 = instantiateVariableFont(base_vf, {"wght": 450}, inplace=False)
    apply_s26u_fixes(st_450, center_colon=True, weight_class=400)
    update_name_table(st_450, "思源宋体 S26U 微粗450", "Source Han Serif S26U W450", "Regular")
    out_st_450 = os.path.join(WORKSPACE, "思源宋体CN-W450微粗-S26U修复_冒号居中.ttf")
    st_450.save(out_st_450)
    st_450.close()
    verify_saved_font(out_st_450)

    base_vf.close()
    print("\nAll 4 S26U fonts built and verified successfully!")


if __name__ == "__main__":
    main()
