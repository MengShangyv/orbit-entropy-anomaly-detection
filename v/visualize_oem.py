from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio


EARTH_RADIUS_KM = 6378.137
WGS84_A_KM = 6378.137
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)


def parse_oem(path: Path):
    metadata = {}
    rows = []

    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue

        if re.match(r"^\d{4}-\d{2}-\d{2}T", line):
            parts = line.split()
            if len(parts) >= 7:
                rows.append(
                    [
                        pd.to_datetime(parts[0], utc=True),
                        *map(float, parts[1:7]),
                    ]
                )
        elif "=" in line:
            k, v = line.split("=", 1)
            metadata[k.strip()] = v.strip()

    if not rows:
        raise ValueError("没有在文件中找到 OEM 历元数据。")

    df = pd.DataFrame(
        rows, columns=["time", "x", "y", "z", "vx", "vy", "vz"]
    )
    return metadata, df


def datetime_to_jd(ts: pd.Timestamp) -> float:
    # Unix epoch JD = 2440587.5
    return ts.timestamp() / 86400.0 + 2440587.5


def gmst_rad(ts: pd.Timestamp) -> float:
    # 适合可视化的 GMST 近似公式。
    jd = datetime_to_jd(ts)
    t = (jd - 2451545.0) / 36525.0
    gmst_deg = (
        280.46061837
        + 360.98564736629 * (jd - 2451545.0)
        + 0.000387933 * t * t
        - (t * t * t) / 38710000.0
    ) % 360.0
    return math.radians(gmst_deg)


def eci_to_ecef(x, y, z, ts: pd.Timestamp):
    th = gmst_rad(ts)
    c, s = math.cos(th), math.sin(th)
    # ECI(J2000近似) -> ECEF
    xe = c * x + s * y
    ye = -s * x + c * y
    return xe, ye, z


def ecef_to_geodetic(x, y, z):
    lon = math.atan2(y, x)
    p = math.hypot(x, y)

    lat = math.atan2(z, p * (1.0 - WGS84_E2))
    for _ in range(6):
        sin_lat = math.sin(lat)
        n = WGS84_A_KM / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
        h = p / max(math.cos(lat), 1e-12) - n
        lat = math.atan2(z, p * (1.0 - WGS84_E2 * n / (n + h)))

    sin_lat = math.sin(lat)
    n = WGS84_A_KM / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
    h = p / max(math.cos(lat), 1e-12) - n

    return math.degrees(lat), math.degrees(lon), h


def build_dashboard(metadata, df, output_path: Path):
    pos = df[["x", "y", "z"]].to_numpy(float)
    vel = df[["vx", "vy", "vz"]].to_numpy(float)

    df["radius_km"] = np.linalg.norm(pos, axis=1)
    df["altitude_km"] = df["radius_km"] - EARTH_RADIUS_KM
    df["speed_km_s"] = np.linalg.norm(vel, axis=1)

    lats, lons, geod_h = [], [], []
    for row in df.itertuples(index=False):
        xe, ye, ze = eci_to_ecef(row.x, row.y, row.z, row.time)
        lat, lon, h = ecef_to_geodetic(xe, ye, ze)
        lats.append(lat)
        lons.append(lon)
        geod_h.append(h)

    df["lat_deg"] = lats
    df["lon_deg"] = lons
    df["geodetic_h_km"] = geod_h

    # ---------- 3D 轨道 ----------
    u = np.linspace(0, 2 * np.pi, 72)
    v = np.linspace(0, np.pi, 36)
    ex = EARTH_RADIUS_KM * np.outer(np.cos(u), np.sin(v))
    ey = EARTH_RADIUS_KM * np.outer(np.sin(u), np.sin(v))
    ez = EARTH_RADIUS_KM * np.outer(np.ones_like(u), np.cos(v))

    fig3d = go.Figure()
    fig3d.add_trace(
        go.Surface(
            x=ex, y=ey, z=ez,
            opacity=0.55,
            showscale=False,
            hoverinfo="skip",
            name="Earth",
        )
    )
    fig3d.add_trace(
        go.Scatter3d(
            x=df["x"], y=df["y"], z=df["z"],
            mode="lines",
            name="Satellite orbit",
            line=dict(width=3),
            customdata=np.c_[df["time"].astype(str), df["altitude_km"]],
            hovertemplate=(
                "UTC=%{customdata[0]}<br>"
                "x=%{x:.1f} km<br>y=%{y:.1f} km<br>z=%{z:.1f} km<br>"
                "高度≈%{customdata[1]:.1f} km<extra></extra>"
            ),
        )
    )
    fig3d.add_trace(
        go.Scatter3d(
            x=[df.iloc[0]["x"], df.iloc[-1]["x"]],
            y=[df.iloc[0]["y"], df.iloc[-1]["y"]],
            z=[df.iloc[0]["z"], df.iloc[-1]["z"]],
            mode="markers+text",
            text=["START", "END"],
            textposition="top center",
            marker=dict(size=5),
            name="起止点",
        )
    )
    lim = float(np.max(np.abs(pos))) * 1.08
    fig3d.update_layout(
        title="J2000 地心惯性系 3D 轨道",
        scene=dict(
            xaxis_title="X / km",
            yaxis_title="Y / km",
            zaxis_title="Z / km",
            aspectmode="data",
            xaxis=dict(range=[-lim, lim]),
            yaxis=dict(range=[-lim, lim]),
            zaxis=dict(range=[-lim, lim]),
        ),
        margin=dict(l=0, r=0, t=48, b=0),
        height=720,
    )

    # ---------- 地面轨迹 ----------
    # 经度跨越 ±180° 时用 None 断开折线，避免跨地图画一条长线。
    track_lon, track_lat, track_time = [], [], []
    prev = None
    for lon, lat, ts in zip(df["lon_deg"], df["lat_deg"], df["time"]):
        if prev is not None and abs(lon - prev) > 180:
            track_lon.append(None)
            track_lat.append(None)
            track_time.append(None)
        track_lon.append(lon)
        track_lat.append(lat)
        track_time.append(str(ts))
        prev = lon

    fig_map = go.Figure(
        go.Scattergeo(
            lon=track_lon,
            lat=track_lat,
            mode="lines",
            name="Ground track",
            customdata=track_time,
            hovertemplate="经度=%{lon:.2f}°<br>纬度=%{lat:.2f}°<extra></extra>",
        )
    )
    fig_map.update_geos(
        projection_type="equirectangular",
        showland=True,
        showcountries=True,
        showcoastlines=True,
        showocean=True,
    )
    fig_map.update_layout(
        title="近似地面轨迹（J2000 → ECEF，GMST 近似）",
        margin=dict(l=0, r=0, t=48, b=0),
        height=470,
    )

    # ---------- 高度 / 速度 ----------
    fig_state = go.Figure()
    fig_state.add_trace(
        go.Scatter(
            x=df["time"], y=df["altitude_km"],
            mode="lines",
            name="高度 / km",
            yaxis="y",
        )
    )
    fig_state.add_trace(
        go.Scatter(
            x=df["time"], y=df["speed_km_s"],
            mode="lines",
            name="速度 / km/s",
            yaxis="y2",
        )
    )
    fig_state.update_layout(
        title="轨道高度与速度随时间变化",
        xaxis=dict(title="UTC"),
        yaxis=dict(title="高度 / km"),
        yaxis2=dict(title="速度 / km/s", overlaying="y", side="right"),
        hovermode="x unified",
        margin=dict(l=60, r=60, t=48, b=55),
        height=440,
    )

    obj = metadata.get("OBJECT_ID", metadata.get("OBJECT_NAME", "Satellite"))
    frame = metadata.get("REF_FRAME", "Unknown")
    start = df["time"].iloc[0]
    stop = df["time"].iloc[-1]

    summary = f"""
    <div class="summary">
      <div><b>对象</b><br>{obj}</div>
      <div><b>参考系</b><br>{frame}</div>
      <div><b>历元数</b><br>{len(df)}</div>
      <div><b>时间范围</b><br>{start} ～ {stop}</div>
      <div><b>高度范围</b><br>{df['altitude_km'].min():.1f} ～ {df['altitude_km'].max():.1f} km</div>
      <div><b>速度范围</b><br>{df['speed_km_s'].min():.3f} ～ {df['speed_km_s'].max():.3f} km/s</div>
    </div>
    """

    parts = [
        pio.to_html(fig3d, include_plotlyjs=True, full_html=False),
        pio.to_html(fig_map, include_plotlyjs=False, full_html=False),
        pio.to_html(fig_state, include_plotlyjs=False, full_html=False),
    ]

    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>OEM Satellite Visualization</title>
<style>
body{{font-family:Segoe UI,Arial,"Microsoft YaHei",sans-serif;margin:0;background:#f6f7f9;color:#1f2937}}
.wrap{{max-width:1280px;margin:0 auto;padding:24px}}
h1{{font-size:24px;margin:0 0 14px}}
.note{{font-size:14px;color:#667085;margin-bottom:18px;line-height:1.6}}
.summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin:0 0 20px}}
.summary>div{{background:white;border:1px solid #e5e7eb;border-radius:10px;padding:12px;line-height:1.5}}
.card{{background:white;border:1px solid #e5e7eb;border-radius:12px;margin:14px 0;padding:8px;overflow:hidden}}
</style>
</head>
<body>
<div class="wrap">
<h1>卫星 OEM 星历可视化</h1>
<div class="note">
3D 轨道直接使用 OEM 中的 J2000 坐标。地面轨迹使用 GMST 将惯性系近似转换到地固系，
适合教学/展示；若用于高精度测轨，请改用 IERS EOP、岁差章动和极移模型（如 Astropy/Orekit）。
</div>
{summary}
<div class="card">{parts[0]}</div>
<div class="card">{parts[1]}</div>
<div class="card">{parts[2]}</div>
</div>
</body>
</html>"""
    output_path.write_text(page, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="可视化 CCSDS OEM 星历文件")
    parser.add_argument("input", type=Path, help="OEM .dat/.oem 文件")
    parser.add_argument("-o", "--output", type=Path, default=Path("satellite_oem_visualization.html"))
    args = parser.parse_args()

    metadata, df = parse_oem(args.input)
    build_dashboard(metadata, df, args.output)
    print(f"已生成: {args.output.resolve()}")


if __name__ == "__main__":
    main()
