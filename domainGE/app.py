import streamlit as st
import folium
from folium.plugins import Draw, MeasureControl
from streamlit_folium import st_folium
import math

st.set_page_config(page_title="WRF Domain Generator", layout="wide")

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if not st.session_state["password_correct"]:
        st.text_input("合言葉を入力してください", type="password", key="password_input")
        if st.session_state["password_input"] == "wrf2026":
            st.session_state["password_correct"] = True
            st.rerun()
        elif st.session_state["password_input"] != "":
            st.error("パスワードが違います")
        return False
    return True

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def calculate_bounds_from_grid(ref_lat, ref_lon, dx_m, dy_m, e_we, e_sn):
    lat_offset = (e_sn * (dy_m / 1000.0) / 2.0) / 111.32
    lon_offset = (e_we * (dx_m / 1000.0) / 2.0) / (111.32 * math.cos(math.radians(ref_lat)))
    return [
        [ref_lat - lat_offset, ref_lon - lon_offset],
        [ref_lat + lat_offset, ref_lon + lon_offset]
    ]

if check_password():
    st.title("WRF ドメインジェネレーター")
    
    col_settings, col_main = st.columns([1, 3])

    with col_settings:
        st.header("1. 中心座標の設定")
        ref_lat = st.number_input("中心緯度 (ref_lat)", min_value=-90.0, max_value=90.0, value=36.0, step=0.5)
        ref_lon = st.number_input("中心経度 (ref_lon)", min_value=-180.0, max_value=180.0, value=138.0, step=0.5)

        st.header("2. 投影法の設定")
        map_proj = st.selectbox("map_proj (投影法)", ["lambert", "mercator", "polar", "lat-lon"])
        truelat1 = st.number_input("truelat1", value=30.0, step=1.0)
        # ランベルト図法の場合のみ truelat2 を表示
        if map_proj == "lambert":
            truelat2 = st.number_input("truelat2", value=60.0, step=1.0)
        else:
            truelat2 = None

        st.header("3. ドメイン解像度の設定")
        unit = st.radio("入力する単位を選んでください", ["km", "m"], horizontal=True)
        u_label = f"({unit})"
        u_mult = 1000.0 if unit == "km" else 1.0

        domains_dx, domains_dy = [], []

        dx_d01 = st.number_input(f"d01: dx {u_label}", min_value=0.01, value=5.0 if unit=="km" else 5000.0, step=1.0)
        dy_d01 = st.number_input(f"d01: dy {u_label}", min_value=0.01, value=5.0 if unit=="km" else 5000.0, step=1.0)
        domains_dx.append(dx_d01 * u_mult)
        domains_dy.append(dy_d01 * u_mult)

        add_d02 = st.checkbox("子ドメイン(d02)を追加する")
        if add_d02:
            dx_d02 = st.number_input(f"d02: dx {u_label}", min_value=0.01, value=dx_d01/3.0, step=1.0)
            dy_d02 = st.number_input(f"d02: dy {u_label}", min_value=0.01, value=dy_d01/3.0, step=1.0)
            domains_dx.append(dx_d02 * u_mult)
            domains_dy.append(dy_d02 * u_mult)

            add_d03 = st.checkbox("孫ドメイン(d03)を追加する")
            if add_d03:
                dx_d03 = st.number_input(f"d03: dx {u_label}", min_value=0.01, value=dx_d02/3.0, step=1.0)
                dy_d03 = st.number_input(f"d03: dy {u_label}", min_value=0.01, value=dy_d02/3.0, step=1.0)
                domains_dx.append(dx_d03 * u_mult)
                domains_dy.append(dy_d03 * u_mult)

        st.header("4. 作成モードの選択")
        mode = st.radio("領域の決め方", ["A. 地図上でドラッグして描画", "B. 数値(グリッド数)を直接入力"])

    with col_main:
        m = folium.Map(location=[ref_lat, ref_lon], zoom_start=5, control_scale=True)
        folium.Marker(
            [ref_lat, ref_lon],
            popup=f"中心点<br>Lat: {ref_lat}<br>Lon: {ref_lon}",
            icon=folium.Icon(color="red", icon="info-sign")
        ).add_to(m)
        m.add_child(MeasureControl(primary_length_unit='kilometers'))

        namelist_output = ""

        # ==========================================
        # モードA: 地図上でドラッグして描画
        # ==========================================
        if mode == "A. 地図上でドラッグして描画":
            st.info("地図左上の「四角形ツール」を使って、d01, d02...の順に領域を囲んでください。")
            draw = Draw(draw_options={'polyline': False, 'polygon': False, 'circle': False, 'marker': False, 'circlemarker': False, 'rectangle': True})
            m.add_child(draw)
            
            output = st_folium(m, height=600, use_container_width=True, key="map_draw")

            if output["all_drawings"]:
                e_we_list, e_sn_list, i_start_list, j_start_list = [], [], [], []
                d01_min_lon, d01_min_lat = 0, 0

                for i, drawing in enumerate(output["all_drawings"]):
                    domain_id = i + 1
                    coords = drawing["geometry"]["coordinates"][0]
                    lons = [c[0] for c in coords]
                    lats = [c[1] for c in coords]
                    min_lon, max_lon = min(lons), max(lons)
                    min_lat, max_lat = min(lats), max(lats)
                    
                    center_lat_d = (min_lat + max_lat) / 2.0
                    center_lon_d = (min_lon + max_lon) / 2.0
                    
                    dist_x = calculate_distance(center_lat_d, min_lon, center_lat_d, max_lon)
                    dist_y = calculate_distance(min_lat, center_lon_d, max_lat, center_lon_d)
                    
                    if i < len(domains_dx):
                        curr_dx_m, curr_dy_m = domains_dx[i], domains_dy[i]
                    else:
                        curr_dx_m, curr_dy_m = domains_dx[-1] / 3.0, domains_dy[-1] / 3.0
                        domains_dx.append(curr_dx_m)
                        domains_dy.append(curr_dy_m)
                    
                    e_we = int(dist_x / (curr_dx_m / 1000.0)) + 1
                    e_sn = int(dist_y / (curr_dy_m / 1000.0)) + 1

                    if domain_id == 1:
                        d01_min_lon, d01_min_lat = min_lon, min_lat
                        i_start, j_start = 1, 1
                    else:
                        dist_x_start = calculate_distance(min_lat, d01_min_lon, min_lat, min_lon)
                        dist_y_start = calculate_distance(d01_min_lat, min_lon, min_lat, min_lon)
                        i_start = int(dist_x_start / (domains_dx[0] / 1000.0)) + 1
                        j_start = int(dist_y_start / (domains_dy[0] / 1000.0)) + 1
                    
                    e_we_list.append(e_we)
                    e_sn_list.append(e_sn)
                    i_start_list.append(i_start)
                    j_start_list.append(j_start)

                e_we_str = ", ".join(map(str, e_we_list)) + ","
                e_sn_str = ", ".join(map(str, e_sn_list)) + ","
                i_start_str = ", ".join(map(str, i_start_list)) + ","
                j_start_str = ", ".join(map(str, j_start_list)) + ","
                parent_id_str = "1, " + ", ".join([str(i) for i in range(1, len(e_we_list))]) + "," if len(e_we_list) > 1 else "1,"
                parent_ratio_str = "1, " + ", ".join([str(int(domains_dx[k-1]/domains_dx[k])) for k in range(1, len(e_we_list))]) + "," if len(e_we_list) > 1 else "1,"

        # ==========================================
        # モードB: 数値(グリッド数)を直接入力
        # ==========================================
        else:
            with col_settings:
                st.markdown("---")
                st.subheader("グリッド数の指定")
                e_we_in = st.number_input("d01: e_we (東西)", min_value=10, value=150, step=10)
                e_sn_in = st.number_input("d01: e_sn (南北)", min_value=10, value=150, step=10)
                
                if add_d02:
                    e_we_d02 = st.number_input("d02: e_we (東西)", min_value=10, value=100, step=10)
                    e_sn_d02 = st.number_input("d02: e_sn (南北)", min_value=10, value=100, step=10)
                if add_d02 and add_d03:
                    e_we_d03 = st.number_input("d03: e_we (東西)", min_value=10, value=100, step=10)
                    e_sn_d03 = st.number_input("d03: e_sn (南北)", min_value=10, value=100, step=10)

            bounds_d01 = calculate_bounds_from_grid(ref_lat, ref_lon, domains_dx[0], domains_dy[0], e_we_in, e_sn_in)
            folium.Rectangle(bounds_d01, color="blue", weight=2, fill=True, fill_opacity=0.1, tooltip="Domain 1").add_to(m)
            
            e_we_list, e_sn_list = [e_we_in], [e_sn_in]
            i_start_list, j_start_list = [1], [1]

            if add_d02:
                bounds_d02 = calculate_bounds_from_grid(ref_lat, ref_lon, domains_dx[1], domains_dy[1], e_we_d02, e_sn_d02)
                folium.Rectangle(bounds_d02, color="green", weight=2, fill=True, fill_opacity=0.2, tooltip="Domain 2").add_to(m)
                ratio_1 = domains_dx[0] / domains_dx[1]
                i_start_list.append(int(e_we_in / 2.0 - e_we_d02 / (2.0 * ratio_1)) + 1)
                j_start_list.append(int(e_sn_in / 2.0 - e_sn_d02 / (2.0 * ratio_1)) + 1)
                e_we_list.append(e_we_d02)
                e_sn_list.append(e_sn_d02)

                if add_d03:
                    bounds_d03 = calculate_bounds_from_grid(ref_lat, ref_lon, domains_dx[2], domains_dy[2], e_we_d03, e_sn_d03)
                    folium.Rectangle(bounds_d03, color="red", weight=2, fill=True, fill_opacity=0.3, tooltip="Domain 3").add_to(m)
                    ratio_2 = domains_dx[1] / domains_dx[2]
                    i_start_list.append(int(e_we_d02 / 2.0 - e_we_d03 / (2.0 * ratio_2)) + 1)
                    j_start_list.append(int(e_sn_d02 / 2.0 - e_sn_d03 / (2.0 * ratio_2)) + 1)
                    e_we_list.append(e_we_d03)
                    e_sn_list.append(e_sn_d03)

            e_we_str = ", ".join(map(str, e_we_list)) + ","
            e_sn_str = ", ".join(map(str, e_sn_list)) + ","
            i_start_str = ", ".join(map(str, i_start_list)) + ","
            j_start_str = ", ".join(map(str, j_start_list)) + ","
            parent_ids = [1] + [i for i in range(1, len(e_we_list))]
            parent_id_str = ", ".join(map(str, parent_ids)) + ","
            ratios = [1] + [int(domains_dx[k-1]/domains_dx[k]) for k in range(1, len(e_we_list))]
            parent_ratio_str = ", ".join(map(str, ratios)) + ","

            st_folium(m, height=600, use_container_width=True, key="map_manual")

        # namelist文字列の組み立て（両モード共通）
        if 'e_we_str' in locals():
            truelat2_line = f"truelat2          = {truelat2}," if truelat2 is not None else ""
            namelist_output = f"""
&geogrid
parent_id         = {parent_id_str}
parent_grid_ratio = {parent_ratio_str}
i_parent_start    = {i_start_str}
j_parent_start    = {j_start_str}
e_we              = {e_we_str}
e_sn              = {e_sn_str}
geog_data_res     = 'default',
dx                = {domains_dx[0]},
dy                = {domains_dy[0]},
map_proj          = '{map_proj}',
ref_lat           = {ref_lat:.4f},
ref_lon           = {ref_lon:.4f},
truelat1          = {truelat1},
{truelat2_line}
stand_lon         = {ref_lon:.4f},
/
"""
            # 空行を詰める処理
            namelist_output = "\n".join([line for line in namelist_output.split("\n") if line.strip() != ""])

            st.markdown("### 出力結果")
            
            # ダウンロードボタンを設置（ボタンを押すとファイルとして保存される）
            st.download_button(
                label="📥 namelist.wps をダウンロード",
                data=namelist_output,
                file_name="namelist.wps",
                mime="text/plain"
            )
            
            # プレビュー表示
            st.code(namelist_output, language='bash')