import fastapi
from starlette.requests import Request
from starlette.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi import Form, File, UploadFile, Query
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from plotly.utils import PlotlyJSONEncoder
from plotly.express.colors import sample_colorscale
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import glob
import re

from models.aquacrop_model import aquacrop_run_ussana, aquacrop_run_benatzu, run_ensemble_and_generate_plot

import openmeteo_requests
from openmeteo_sdk.Variable import Variable
import requests_cache
from retry_requests import retry

import folium
import geopandas as gpd
import rasterio
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from rasterstats import zonal_stats
from rasterio.mask import mask
from shapely.geometry import mapping
from pathlib import Path

from rasterio.transform import from_bounds
from sentinelhub import (
    SHConfig, BBox, CRS, DataCollection, SentinelHubCatalog,
    SentinelHubRequest, MimeType, bbox_to_dimensions, filter_times
)


templates = Jinja2Templates('templates')
router = fastapi.APIRouter()

@router.get('/', include_in_schema=False)
async def index(request: Request):
    return templates.TemplateResponse('index.html', {'request': request})

@router.get('/simulation', include_in_schema=False)
async def index(request: Request):
    return templates.TemplateResponse('simulation.html', {'request': request})

@router.get('/documentation', include_in_schema=False)
async def index(request: Request):
    return templates.TemplateResponse('documentation.html', {'request': request})

@router.get('/favicon.ico', include_in_schema=False)
def favicon():
    return fastapi.responses.RedirectResponse(url='https://arsinoe-project.eu/securstorage/2022/02/favicon-32.png')


@router.get("/gfs_forecast/{latitude}/{longitude}", include_in_schema=False)
async def gfs_forecast(latitude: float, longitude: float):
    # Setup the Open-Meteo API client with cache and retry on error
    cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
    retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
    openmeteo = openmeteo_requests.Client(session = retry_session)

    # Make sure all required weather variables are listed here
    # The order of variables in hourly or daily is important to assign them correctly below
    url = "https://ensemble-api.open-meteo.com/v1/ensemble"
    params = {
        "latitude": latitude, #39.415
        "longitude": longitude, #9.1
        "hourly": ["temperature_2m", "precipitation", "et0_fao_evapotranspiration", "wind_speed_10m", "surface_temperature"],
        "forecast_days": 36,
        "temporal_resolution": "native",
        "models": "gfs_seamless"
    }
    responses = openmeteo.weather_api(url, params=params)

    # Process first location. Add a for-loop for multiple locations or weather models
    response = responses[0]
    print(f"Coordinates {response.Latitude()}°N {response.Longitude()}°E")
    print(f"Elevation {response.Elevation()} m asl")
    print(f"Timezone {response.Timezone()} {response.TimezoneAbbreviation()}")
    print(f"Timezone difference to GMT+0 {response.UtcOffsetSeconds()} s")

    # Process hourly data
    hourly = response.Hourly()
    hourly_variables = list(map(lambda i: hourly.Variables(i), range(0, hourly.VariablesLength())))

    hourly_temperature_2m = filter(lambda x: x.Variable() == Variable.temperature and x.Altitude() == 2, hourly_variables)

    hourly_precipitation = filter(lambda x: x.Variable() == Variable.precipitation, hourly_variables)

    hourly_et0_fao_evapotranspiration = filter(lambda x: x.Variable() == Variable.et0_fao_evapotranspiration, hourly_variables)

    hourly_wind_speed_10m = filter(lambda x: x.Variable() == Variable.wind_speed and x.Altitude() == 10, hourly_variables)

    hourly_data = {"date": pd.date_range(
        start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
        end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True) - pd.Timedelta(seconds=hourly.Interval()),
        freq=pd.Timedelta(seconds=hourly.Interval())
    )}

    # Process all members

    for variable in hourly_temperature_2m:
        member = variable.EnsembleMember()
        hourly_data[f"temperature_2m_M{member:02d}"] = variable.ValuesAsNumpy()

    for variable in hourly_precipitation:
        member = variable.EnsembleMember()
        hourly_data[f"precipitation_M{member:02d}"] = variable.ValuesAsNumpy()

    for variable in hourly_et0_fao_evapotranspiration:
        member = variable.EnsembleMember()
        hourly_data[f"et0_fao_evapotranspiration_M{member:02d}"] = variable.ValuesAsNumpy()

    for variable in hourly_wind_speed_10m:
        member = variable.EnsembleMember()
        hourly_data[f"wind_speed_10m_M{member:02d}"] = variable.ValuesAsNumpy()

    hourly_dataframe = pd.DataFrame(data = hourly_data)

    hourly_dataframe.index = hourly_dataframe.date
    hourly_dataframe = hourly_dataframe.drop(['date'], axis=1)

    # Daily dataframe
    daily_dataframe = hourly_dataframe[[f'temperature_2m_M{m:02d}' for m in range(31)]].resample('D').mean().add_prefix('mean_')
    daily_dataframe = pd.concat([daily_dataframe, hourly_dataframe[[f'temperature_2m_M{m:02d}' for m in range(31)]].resample('D').min().add_prefix('min_')], axis=1)
    daily_dataframe = pd.concat([daily_dataframe, hourly_dataframe[[f'temperature_2m_M{m:02d}' for m in range(31)]].resample('D').max().add_prefix('max_')], axis=1)
    daily_dataframe = pd.concat([daily_dataframe, hourly_dataframe[[f'precipitation_M{m:02d}' for m in range(31)]].resample('D').sum().add_prefix('sum_')], axis=1)
    daily_dataframe = pd.concat([daily_dataframe, hourly_dataframe[[f'et0_fao_evapotranspiration_M{m:02d}' for m in range(31)]].resample('D').sum().add_prefix('sum_')], axis=1)
    daily_dataframe = pd.concat([daily_dataframe, hourly_dataframe[[f'wind_speed_10m_M{m:02d}' for m in range(31)]].resample('D').max().add_prefix('max_')], axis=1)
    
    # Create a subplot figure with shared x-axis
    fig = make_subplots(
        rows=4, cols=1,  # Two rows, one column
        shared_xaxes=True,  # Share x-axis across rows
        vertical_spacing=0.05,  # Adjust vertical spacing between plots
        subplot_titles=("Total precipitation [mm/24h]", "Total ET0 FAO evotranspiration [mm/24h]", "10m Wind speed max [m/s]", "2m Temperature min/max [°C]")  # Titles for each subplot
    )

    df = daily_dataframe[[f'sum_precipitation_M{m:02d}' for m in range(1,31)]]
    for time in df.index:
        fig.add_trace(go.Box(
            y=df.loc[time],  # Values for the boxplot (columns at this time point)
            name=str(time.date()),  # Use date as x-axis label
            showlegend=False, 
            marker_color='grey'
            ), row=1, col=1
        )

    df = daily_dataframe[[f'sum_et0_fao_evapotranspiration_M{m:02d}' for m in range(1,31)]]
    for time in df.index:
        fig.add_trace(go.Box(
            y=df.loc[time],  # Values for the boxplot (columns at this time point)
            name=str(time.date()),  # Use date as x-axis label
            showlegend=False, 
            marker_color='green'
            ), row=2, col=1
        )

    df = daily_dataframe[[f'max_wind_speed_10m_M{m:02d}' for m in range(1,31)]]
    for time in df.index:
        fig.add_trace(go.Box(
            y=df.loc[time],  # Values for the boxplot (columns at this time point)
            name=str(time.date()),  # Use date as x-axis label
            showlegend=False, 
            marker_color='orange'
            ), row=3, col=1
        )

    df = daily_dataframe[[f'max_temperature_2m_M{m:02d}' for m in range(1,31)]]
    for time in df.index:
        fig.add_trace(go.Box(
            y=df.loc[time],  # Values for the boxplot (columns at this time point)
            name=str(time.date()),  # Use date as x-axis label
            showlegend=False, 
            marker_color='red'
            ), row=4, col=1
        )

    df = daily_dataframe[[f'min_temperature_2m_M{m:02d}' for m in range(1,31)]]
    for time in df.index:
        fig.add_trace(go.Box(
            y=df.loc[time],  # Values for the boxplot (columns at this time point)
            name=str(time.date()),  # Use date as x-axis label
            showlegend=False, 
            marker_color='blue'
            ), row=4, col=1
        )

    fig.add_trace(go.Scatter(
        y=daily_dataframe['sum_precipitation_M00'],
        x=df.index,
        name='control',
        showlegend=False, 
        marker_color='grey'
        ), row=1, col=1
    )

    fig.add_trace(go.Scatter(
        y=daily_dataframe['sum_et0_fao_evapotranspiration_M00'],
        x=df.index,
        name='control',
        showlegend=False, 
        marker_color='green'
        ), row=2, col=1
    )

    fig.add_trace(go.Scatter(
        y=daily_dataframe['max_wind_speed_10m_M00'],
        x=df.index,
        name='control',
        showlegend=False, 
        marker_color='orange'
        ), row=3, col=1
    )

    fig.add_trace(go.Scatter(
        y=daily_dataframe['max_temperature_2m_M00'],
        x=df.index,
        name='control',
        showlegend=False, 
        marker_color='red'
        ), row=4, col=1
    )

    fig.add_trace(go.Scatter(
        y=daily_dataframe['min_temperature_2m_M00'],
        x=df.index,
        name='control',
        showlegend=False, 
        marker_color='blue'
        ), row=4, col=1
    )

    # Update layout for better visuals
    fig.update_layout(
        title="GFS forecast",
        height=800
    )

    plot_json = json.dumps(fig, cls=PlotlyJSONEncoder)

    return json.loads(plot_json)

@router.get("/ndvi_map", include_in_schema=False, response_class=HTMLResponse)
def prepare_map():
    shapefile_path = "static/shapefiles/parcelle2022_2023.shp"
    ndvi_dir = "static/geotiff_ndvi"

    if not os.path.exists(shapefile_path):
        raise FileNotFoundError(f"Shapefile non trovato: {shapefile_path}")

    # Trova il file NDVI più recente
    ndvi_files = sorted([
        os.path.join(ndvi_dir, f)
        for f in os.listdir(ndvi_dir)
        if f.endswith(".tif")
    ])
    if not ndvi_files:
        raise FileNotFoundError(f"Nessun file NDVI trovato in {ndvi_dir}")
    geotiff_path = ndvi_files[-1]  # ultimo = più recente per ordinamento alfabetico

    # Carica shapefile e raster
    polygons = gpd.read_file(shapefile_path).to_crs("EPSG:4326")
    with rasterio.open(geotiff_path) as src:
        array = src.read(1)
        affine = src.transform
        no_data = src.nodata
        bounds = src.bounds
        metadata = src.tags()

    stats = zonal_stats(
        polygons,
        array,
        affine=affine,
        nodata=no_data,
        stats=["min", "max", "mean", "std"],
    )

    polygons["min_ndvi"] = [s["min"] for s in stats]
    polygons["max_ndvi"] = [s["max"] for s in stats]
    polygons["mean_ndvi"] = [s["mean"] for s in stats]
    polygons["std_ndvi"] = [s["std"] for s in stats]

    # Raster -> RGB
    valid_data = array[array != no_data]
    raster_min, raster_max = valid_data.min(), valid_data.max()
    raster_normalized = np.clip((array - raster_min) / (raster_max - raster_min), 0, 1)
    raster_image = plt.cm.viridis(raster_normalized)
    raster_image = (raster_image[:, :, :3] * 255).astype("uint8")
    raster_bounds = [[bounds.bottom, bounds.left], [bounds.top, bounds.right]]

    centroids = polygons.geometry.centroid
    center = [centroids.y.mean(), centroids.x.mean()]
    ndvi_map = folium.Map(location=center, zoom_start=14)

    folium.raster_layers.ImageOverlay(
        image=raster_image,
        bounds=raster_bounds,
        opacity=0.7,
        interactive=True,
    ).add_to(ndvi_map)

    # Colora i poligoni
    cmap = plt.get_cmap("viridis")
    def get_style(feature):
        ndvi_value = feature["properties"].get("mean_ndvi", raster_min)
        normalized_ndvi = np.clip((ndvi_value - raster_min) / (raster_max - raster_min), 0, 1)
        color = mcolors.to_hex(cmap(normalized_ndvi))
        return {
            "color": "black",
            "weight": 0.7,
            "fillColor": color,
            "fillOpacity": 0.6,
        }

    folium.GeoJson(
        polygons.to_json(),
        style_function=get_style,
        tooltip=folium.GeoJsonTooltip(
            fields=["LOCALITà", "TESI", "mean_ndvi", "min_ndvi", "max_ndvi", "std_ndvi"],
            aliases=["Località:", "Tesi:", "NDVI medio:", "NDVI min:", "NDVI max:", "Dev std NDVI:"],
            localize=True,
            labels=True,
            sticky=True
        )
    ).add_to(ndvi_map)

    map_html = ndvi_map._repr_html_()

    # Colorbar HTML
    n_ticks = 8
    tick_vals = np.linspace(raster_min, raster_max, n_ticks)
    colors = ['#440154', '#482878', '#3e4989', '#31688e', '#26828e',
            '#1f9e89', '#35b779', '#6ece58', '#b5de2b', '#fde725']
    gradient_css = ", ".join(colors)

    colorbar_vertical = f"""
    <div style="
        position: absolute;
        top: 80px;
        right: 20px;
        width: 100px;
        height: 600px;
        background-color: white;
        padding: 10px 8px 10px 10px;
        border: 1px solid #ccc;
        display: flex;
        flex-direction: row;
        align-items: center;
        z-index: 9999;
    ">
        <div style="
            width: 30px;
            height: 100%;
            background: linear-gradient(to top, {gradient_css});
            border: 1px solid #ccc;
        "></div>
        <div style="
            margin-left: 10px;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            font-size: 0.8rem;
        ">
    """
    for val in reversed(tick_vals):
        colorbar_vertical += f"<div style='text-align: left;'>{val:.2f}</div>"
    colorbar_vertical += "</div></div>"

    # Metadata box HTML
    keys = ["AREA_NAME", "SENSOR_TYPE", "DESCRIPTION", "ACQUISITION_DATETIME", "PROCESSING_VERSION"]
    metadata_html = """
    <div class="box" style="margin-top: 1.5rem;">
      <h4 class="title is-5">NDVI Metadata</h4>
      <div class="content">
        <dl>
    """
    for key in keys:
        if key in metadata:
            metadata_html += f"<dt>{key.replace('_', ' ').title()}</dt><dd>{metadata[key]}</dd>"
    metadata_html += """
        </dl>
      </div>
    </div>
    """

    return map_html + colorbar_vertical + metadata_html


def download_and_save_new_ndvi_scl(
    client_id,
    client_secret,
    bbox_coords,
    time_interval,
    ndvi_dir,
    scl_dir,
    resolution=10,
    max_cloud_cover=100
):
    os.makedirs(ndvi_dir, exist_ok=True)
    os.makedirs(scl_dir, exist_ok=True)

    config = SHConfig()
    config.sh_client_id = client_id
    config.sh_client_secret = client_secret
    config.sh_token_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    config.sh_base_url = "https://sh.dataspace.copernicus.eu"

    bbox = BBox(bbox=bbox_coords, crs=CRS.WGS84)
    size = bbox_to_dimensions(bbox, resolution=resolution)

    catalog = SentinelHubCatalog(config=config)
    search_iterator = catalog.search(
        DataCollection.SENTINEL2_L2A,
        bbox=bbox,
        time=time_interval,
        filter=f"eo:cloud_cover <= {max_cloud_cover}",
        fields={"include": ["id", "properties.datetime", "properties.eo:cloud_cover"], "exclude": []},
    )

    all_timestamps = search_iterator.get_timestamps()
    time_difference = timedelta(hours=1)
    unique_acquisitions = filter_times(all_timestamps, time_difference)

    evalscript_ndvi = """
    //VERSION=3
    function setup() {
        return {
            input: ["B04", "B08", "dataMask"],
            output: [
                { id: "index", bands: 1, sampleType: "FLOAT32" },
                { id: "dataMask", bands: 1 }
            ]
        };
    }
    function evaluatePixel(samples) {
        let ndvi = index(samples.B08, samples.B04);
        let masked = samples.dataMask === 1 ? ndvi : NaN;
        return {
            index: [masked],
            dataMask: [samples.dataMask]
        };
    }"""

    evalscript_scl = """
    //VERSION=3
    function setup() {
        return {
            input: ["SCL"],
            output: { bands: 1, sampleType: "UINT8" }
        };
    }
    function evaluatePixel(samples) {
        return [samples.SCL];
    }"""

    for timestamp in unique_acquisitions:
        ts_str = timestamp.strftime("%Y%m%dT%H%M%S")
        out_path_ndvi = os.path.join(ndvi_dir, f"ndvi_{ts_str}.tif")
        out_path_scl = os.path.join(scl_dir, f"scl_{ts_str}.tif")

        # Salta se entrambi i file esistono
        if os.path.exists(out_path_ndvi) and os.path.exists(out_path_scl):
            continue

        # === NDVI ===
        request_ndvi = SentinelHubRequest(
            evalscript=evalscript_ndvi,
            input_data=[
                SentinelHubRequest.input_data(
                    data_collection=DataCollection.SENTINEL2_L2A.define_from("s2l2a", service_url=config.sh_base_url),
                    time_interval=(timestamp - time_difference, timestamp + time_difference)
                )
            ],
            responses=[SentinelHubRequest.output_response("index", MimeType.TIFF)],
            bbox=bbox,
            size=size,
            config=config,
        )
        array_ndvi = request_ndvi.get_data()[0]
        transform = from_bounds(*bbox_coords, width=size[0], height=size[1])
        metadata_ndvi = {
            "driver": "GTiff",
            "dtype": rasterio.float32,
            "count": 1,
            "width": array_ndvi.shape[1],
            "height": array_ndvi.shape[0],
            "crs": "EPSG:4326",
            "transform": transform,
            "nodata": np.nan
        }
        with rasterio.open(out_path_ndvi, "w", **metadata_ndvi) as dst:
            dst.write(array_ndvi.astype(np.float32), 1)
            dst.update_tags(
                ACQUISITION_DATETIME=timestamp.isoformat(),
                SENSOR_TYPE="Sentinel-2 L2A",
                AREA_NAME=f"{bbox_coords}",
                DESCRIPTION="NDVI derived from Sentinel-2 (B08/B04)",
                PROCESSING_VERSION="1.0",
                RESOLUTION=str(resolution),
                CLOUD_COVER=str(max_cloud_cover)
            )

        # === SCL ===
        request_scl = SentinelHubRequest(
            evalscript=evalscript_scl,
            input_data=[
                SentinelHubRequest.input_data(
                    data_collection=DataCollection.SENTINEL2_L2A.define_from("s2l2a", service_url=config.sh_base_url),
                    time_interval=(timestamp - time_difference, timestamp + time_difference)
                )
            ],
            responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
            bbox=bbox,
            size=size,
            config=config,
        )
        array_scl = request_scl.get_data()[0]
        metadata_scl = {
            "driver": "GTiff",
            "dtype": rasterio.uint8,
            "count": 1,
            "width": array_scl.shape[1],
            "height": array_scl.shape[0],
            "crs": "EPSG:4326",
            "transform": transform,
            "nodata": None
        }
        with rasterio.open(out_path_scl, "w", **metadata_scl) as dst:
            dst.write(array_scl.astype(np.uint8), 1)
            dst.update_tags(
                ACQUISITION_DATETIME=timestamp.isoformat(),
                DESCRIPTION="Scene Classification Layer (SCL) from Sentinel-2",
                PROCESSING_VERSION="1.0"
            )

        print(f"✔ Saved NDVI: {out_path_ndvi}")
        print(f"✔ Saved SCL:  {out_path_scl}")


def extract_ndvi_series_grouped_by_treatment_valid_classes(
    shapefile_path,
    ndvi_dir,
    scl_dir,
    location_column="LOCALITà",
    treatment_column="TESI",
    valid_classes={4, 5}
):
    if not os.path.exists(shapefile_path):
        raise FileNotFoundError(f"Shapefile non trovato: {shapefile_path}")
    
    polygons = gpd.read_file(shapefile_path).to_crs("EPSG:4326")
    if location_column not in polygons.columns or treatment_column not in polygons.columns:
        raise ValueError("Colonne richieste non trovate nello shapefile")

    polygons["GROUP"] = (
        polygons[location_column].astype(str).str.upper().str.strip() + "_" +
        polygons[treatment_column].astype(str).str.strip()
    )

    ndvi_files = sorted([f for f in os.listdir(ndvi_dir) if f.endswith(".tif")])
    scl_files = sorted([f for f in os.listdir(scl_dir) if f.endswith(".tif")])

    if len(ndvi_files) != len(scl_files):
        raise ValueError("Numero di file NDVI e SCL non corrisponde")

    records = []
    for ndvi_file, scl_file in zip(ndvi_files, scl_files):
        ndvi_path = os.path.join(ndvi_dir, ndvi_file)
        scl_path = os.path.join(scl_dir, scl_file)

        with rasterio.open(ndvi_path) as ndvi_src, rasterio.open(scl_path) as scl_src:
            metadata = ndvi_src.tags()
            raw_date = metadata.get("ACQUISITION_DATETIME", None)
            label = None
            if raw_date:
                try:
                    label = datetime.fromisoformat(raw_date)
                except Exception:
                    pass
            if label is None:
                try:
                    label = pd.to_datetime(Path(ndvi_file).stem, errors="coerce")
                except Exception:
                    continue
            if label is None or pd.isna(label):
                continue

            group_values = {}
            for idx, row in polygons.iterrows():
                group = row["GROUP"]
                geom = [mapping(row.geometry)]
                try:
                    ndvi_masked, _ = mask(ndvi_src, geom, crop=True)
                    scl_masked, _ = mask(scl_src, geom, crop=True)
                except Exception:
                    continue

                ndvi_vals = ndvi_masked[0]
                scl_vals = scl_masked[0]

                valid_mask = (~np.isnan(ndvi_vals)) & (np.isin(scl_vals, list(valid_classes)))
                if np.any(valid_mask):
                    mean_val = float(np.nanmean(ndvi_vals[valid_mask]))
                else:
                    mean_val = np.nan

                if group not in group_values:
                    group_values[group] = []
                group_values[group].append(mean_val)

            aggregated = {
                g: np.nanmean(vals) if len(vals) > 0 and not all(np.isnan(vals)) else np.nan
                for g, vals in group_values.items()
            }
            records.append((label, aggregated))

    df = pd.DataFrame.from_records(
        [r[1] for r in records],
        index=[r[0] for r in records]
    )
    df.index.name = "timestamp"
    df = df.sort_index()
    return df

@router.get("/precipitation_plot/{latitude}/{longitude}", include_in_schema=False)
async def precipitation(latitude: float, longitude: float):

    # === Precipitation from Open-Meteo ===
    cache_session = requests_cache.CachedSession('.cache', expire_after=-1)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    openmeteo = openmeteo_requests.Client(session=retry_session)

    today = datetime.today().strftime("%Y-%m-%d")

    start_date = "2022-10-01"
    end_date = today
    time_interval = (start_date, end_date)

    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": today,
        "daily": "precipitation_sum",
        "models": "best_match"
    }
    responses = openmeteo.weather_api(url, params=params)
    response = responses[0]
    daily = response.Daily()
    daily_precipitation_sum = daily.Variables(0).ValuesAsNumpy()
    daily_data = {
        "date": pd.date_range(
            start=pd.to_datetime(daily.Time(), unit="s", utc=True),
            end=pd.to_datetime(daily.TimeEnd(), unit="s", utc=True),
            freq=pd.Timedelta(seconds=daily.Interval()),
            inclusive="left"
        ),
        "precipitation_sum": daily_precipitation_sum
    }
    daily_dataframe = pd.DataFrame(data=daily_data).set_index('date')

    # === Download dinamico NDVI/SCL ===
    bbox_coords = bbox_coords=(9.0747, 39.4022, 9.1186, 39.4361)
    ndvi_dir = "static/geotiff_ndvi"
    scl_dir = "static/geotiff_scl"
    
    download_and_save_new_ndvi_scl(
        #client_id=os.getenv("SH_CLIENT_ID"),
        #client_secret=os.getenv("SH_CLIENT_SECRET"),
        client_id="sh-031078ea-3866-4001-8550-5e8e942d7c78",
        client_secret="sT1q2RdKNfMwAGtlA2mebNLW23CxcocX",
        bbox_coords=bbox_coords,
        time_interval=time_interval,
        ndvi_dir=ndvi_dir,
        scl_dir=scl_dir, 
        resolution=10,
        max_cloud_cover=40  # puoi alzarlo o abbassarlo
    )

    # === NDVI data extraction ===
    shapefile_path = "static/shapefiles/parcelle2022_2023.shp"
    df_ndvi = extract_ndvi_series_grouped_by_treatment_valid_classes(
        shapefile_path=shapefile_path,
        ndvi_dir=ndvi_dir,
        scl_dir=scl_dir
    )

    group_names = [
        ("BENATZU_TEST", "Benatzu Test", 'Blugrn'),
        ("BENATZU_50", "Benatzu 50%", 'Blugrn'),
        ("BENATZU_100", "Benatzu 100%", 'Blugrn'),
        ("USSANA_TEST", "Ussana Test", 'Redor'),
        ("USSANA_50", "Ussana 50%", 'Redor'),
        ("USSANA_100", "Ussana 100%", 'Redor')
    ]

    # === DIAGNOSTICA ===
    #print(">>> NDVI DataFrame shape:", df_ndvi.shape)
    #print(">>> NDVI columns:", df_ndvi.columns.tolist())
    #print(">>> NDVI head:")
    #print(df_ndvi.head())

    #expected_groups = [g[0] for g in group_names]
    #missing = [g for g in expected_groups if g not in df_ndvi.columns]
    #print(">>> Missing groups:", missing)
    #print(">>> NDVI non-NaN counts:")
    #print(df_ndvi.notna().sum())

    # === Plot ===
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(
            x=daily_dataframe.index,
            y=daily_dataframe["precipitation_sum"],
            name="Precipitation",
            mode="lines+markers",
            line_color="darkblue"
        ),
        secondary_y=False
    )

    for i, (group_col, label, colorscale) in enumerate(group_names):
        if group_col not in df_ndvi.columns:
            continue
        s = df_ndvi[group_col].dropna()
        if s.empty:
            continue
        color = sample_colorscale(colorscale, [i / 6])[0]
        fig.add_trace(
            go.Scatter(
                x=s.index,
                y=s,
                name=label,
                mode='lines+markers',
                line_color=color
            ),
            secondary_y=True
    )

    fig.update_layout(
        title="Precipitation and NDVI",
        height=800
    )
    fig.update_xaxes(title_text="Date")
    fig.update_yaxes(title_text="Precipitation [mm H₂O]", secondary_y=False)
    fig.update_yaxes(title_text="NDVI [-]", secondary_y=True)

    return json.loads(json.dumps(fig, cls=PlotlyJSONEncoder))


@router.post("/simulation", response_class=HTMLResponse)
async def process_file(
    request: Request,
    file: UploadFile = File(...),  # File upload
    site: str = Form(...)     # Parameter selected by radio buttons
):
    # Save the uploaded file to a temporary location
    file_path = os.path.join('uploads', file.filename)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    # Perform simulation
    if site == "Ussana":
        #print(file_path)
        model = aquacrop_run_ussana(file_path)
    elif site == "Benatzu":
        model = aquacrop_run_benatzu(file_path)
    
    df = model._outputs.final_stats

    # Save the DataFrame as JSON
    json_filename = f"{file.filename}_results.json"
    json_filepath = os.path.join("uploads", json_filename)
    df.to_json(json_filepath, orient="records", date_format="iso")  # Save as JSON

    # Create a Plotly figure
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df['Harvest Date (YYYY/MM/DD)'], 
                             y=df['Yield potential (tonne/ha)'], 
                             mode="lines+markers", name="Yield potential", showlegend=False))
    fig.add_trace(go.Scatter(x=df['Harvest Date (YYYY/MM/DD)'], 
                             y=df['Fresh yield (tonne/ha)'], 
                             mode="lines+markers", name="Fresh yield", showlegend=False))
    fig.update_layout(title=f"{site} production", 
                      xaxis_title="Year", yaxis_title="Yield (tonne/ha)",
                      xaxis_showgrid=True, yaxis_showgrid=True, 
                      height=500)
    
    # Convert figure to JSON for frontend
    fig_json = json.dumps(fig, cls=PlotlyJSONEncoder)

    # Return response with download URL
    download_url = f"/download/{json_filename}"
    return JSONResponse(content={
        "plot": json.loads(fig_json),
        "download_url": download_url
    })


@router.get("/download/{filename}")
async def download_file(filename: str):
    file_path = os.path.join("uploads", filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="application/json", filename=filename)
    return JSONResponse(content={"error": "File not found"}, status_code=404)

@router.post("/upload/")
async def upload_file(file: UploadFile = File(...)):
    file_path = os.path.join('uploads', file.filename)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())
    return {"filename": file.filename, "filepath": file_path}


@router.get("/water_profile")
def water_profile(location: str = Query("Ussana"), force: bool = Query(False)):
    image_path_1, image_path_2 = run_ensemble_and_generate_plot(location, force=force)
    return {
        "image_url_1": f"/{image_path_1}", 
        "image_url_2": f"/{image_path_2}"
    }